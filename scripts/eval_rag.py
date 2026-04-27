#!/usr/bin/env python3
"""Receptra RAG evaluation harness — recall@5 measurement (RAG-05).

Mirrors scripts/eval_llm.py (Plan 03-06) argparse pattern. Three flow modes:

    --seed-only:  Ingest fixtures/rag/seed_kb/*.md via /api/kb/ingest-text
    --query-only: Run fixtures/rag/eval_questions.jsonl through /api/kb/query
    --full:       Both, in order

Backend can be live ASGI (--backend-url, default http://localhost:8080) or
in-process FastAPI TestClient (--testclient flag — CI-friendly path).

When invoked from INSIDE pytest (via test_recall_live.py), the autouse
_stub_heavy_loaders fixture from tests/conftest.py patches BgeM3Embedder +
open_collection before the app starts — retrieval returns mocked vectors and
the recall number is mechanically determined by the stub, not real BGE-M3.
This proves harness wiring only.

When invoked OUTSIDE pytest (``uv run python scripts/eval_rag.py --testclient``
or ``make eval-rag``), the real lifespan fires. If bge-m3 is not pulled or
ChromaDB is not running, the lifespan starts with embedder=None / collection=None
(fail-soft). _health_check then detects the subsystem failures and exits with
code 1. The real recall@5 number requires: ``make models-bge`` + ``docker compose
up chromadb`` + ``RECEPTRA_RAG_LIVE_TEST=1 make eval-rag``.

Recall@5 formula:
    For each question with gold_filename != null:
        hit = (any chunk in top-5 has source.filename == gold_filename
               AND gold_chunk_match in chunk.text)
    For each question with gold_filename == null:
        hit = (zero chunks returned — refusal correctness)
    recall_at_5 = sum(hits) / n_questions

Exit codes:
    0  success
    1  backend unreachable or subsystems down (health check fails)
    2  recall@5 below --floor (default 0.5); Phase 7 prompt-tuner attention bar

STT-isolation contract: this harness imports receptra.rag.* + receptra.llm.schema
only. NEVER receptra.stt + faster_whisper + silero_vad + torch + onnxruntime
+ ctranslate2 + av. tests/rag/test_recall_live.py enforces via subprocess
sys.modules introspection.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

_DEFAULT_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent / "fixtures" / "rag"
)
_DEFAULT_SEED_DIR = _DEFAULT_FIXTURES_DIR / "seed_kb"
_DEFAULT_QUESTIONS = _DEFAULT_FIXTURES_DIR / "eval_questions.jsonl"


# ---------------------------------------------------------------------------
# HTTP client factory
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _make_client(
    backend_url: str,
    testclient: bool,
) -> Iterator[httpx.Client]:
    """Yield an httpx-compatible client; manage lifecycle."""
    if testclient:
        # NOTE: imports receptra.main which triggers settings + lifespan stack.
        # Outside pytest, lifespan tries real Ollama + Chroma (fail-soft).
        # Inside pytest, autouse _stub_heavy_loaders patches them beforehand.
        from fastapi.testclient import TestClient

        from receptra.main import app

        with TestClient(app) as tc:
            yield tc
    else:
        with httpx.Client(base_url=backend_url, timeout=60.0) as hc:
            yield hc


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def _health_check(client: httpx.Client) -> bool:
    """Return True iff both chroma and ollama subsystems report 'ok'."""
    try:
        resp = client.get("/api/kb/health", timeout=10.0)
        if resp.status_code != 200:
            return False
        body = resp.json()
        return bool(
            body.get("chroma") == "ok"
            and body.get("ollama") == "ok"
        )
    except httpx.HTTPError:
        return False


# ---------------------------------------------------------------------------
# Seed (ingest) pass
# ---------------------------------------------------------------------------


def _load_questions(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _ingest_via_http(
    client: httpx.Client,
    seed_dir: Path,
) -> dict[str, int]:
    """Ingest all .md fixtures; return aggregate counts."""
    seeded = 0
    chunks_added = 0
    chunks_replaced = 0
    for md in sorted(seed_dir.glob("*.md")):
        content = md.read_text(encoding="utf-8")
        resp = client.post(
            "/api/kb/ingest-text",
            json={"filename": md.name, "content": content},
            timeout=60.0,
        )
        resp.raise_for_status()
        body = resp.json()
        seeded += 1
        chunks_added += body["chunks_added"]
        chunks_replaced += body["chunks_replaced"]
    return {
        "seeded": seeded,
        "chunks_added": chunks_added,
        "chunks_replaced": chunks_replaced,
    }


# ---------------------------------------------------------------------------
# Query + score pass
# ---------------------------------------------------------------------------


def _query_and_score(
    client: httpx.Client,
    questions: list[dict[str, Any]],
    top_k: int = 5,
) -> dict[str, Any]:
    """Run each question through /api/kb/query; compute recall@5."""
    details: list[dict[str, Any]] = []
    hits = 0
    refusal_correct = 0

    for q in questions:
        resp = client.post(
            "/api/kb/query",
            json={"query": q["question"], "top_k": top_k},
            timeout=30.0,
        )
        resp.raise_for_status()
        results: list[dict[str, Any]] = resp.json()

        row: dict[str, Any] = {
            "question": q["question"],
            "gold_filename": q["gold_filename"],
            "gold_chunk_match": q.get("gold_chunk_match"),
            "retrieved_filenames": [
                (r.get("source") or {}).get("filename", "") for r in results
            ],
            "n_results": len(results),
        }

        if q["gold_filename"] is None:
            # Refusal correctness: hit iff retriever returns zero chunks.
            hit = len(results) == 0
            if hit:
                refusal_correct += 1
        else:
            match_str = q.get("gold_chunk_match") or ""
            hit = any(
                (r.get("source") or {}).get("filename") == q["gold_filename"]
                and match_str in r.get("text", "")
                for r in results
            )

        row["hit"] = hit
        if hit:
            hits += 1
        details.append(row)

    n_with_gold = sum(1 for q in questions if q["gold_filename"] is not None)
    n_no_gold = len(questions) - n_with_gold
    return {
        "recall_at_5": round(hits / max(len(questions), 1), 4),
        "n_questions": len(questions),
        "n_with_gold": n_with_gold,
        "n_no_gold": n_no_gold,
        "refusal_correct": refusal_correct,
        "hits": hits,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eval_rag",
        description="Receptra RAG evaluation harness (recall@5).",
    )
    p.add_argument("--seed-only", action="store_true",
                   help="Ingest fixtures only; print seed counts.")
    p.add_argument("--query-only", action="store_true",
                   help="Run questions against existing collection; print recall.")
    p.add_argument("--full", action="store_true",
                   help="Seed then query.")
    p.add_argument("--out-jsonl", type=Path, default=None,
                   help="Per-question result JSONL output path.")
    p.add_argument("--backend-url", default="http://localhost:8080",
                   help="Live backend URL (ignored when --testclient).")
    p.add_argument("--testclient", action="store_true",
                   help="Use in-process FastAPI TestClient (CI-friendly).")
    p.add_argument("--seed-dir", type=Path, default=_DEFAULT_SEED_DIR,
                   help="Directory containing .md seed fixtures.")
    p.add_argument("--questions", type=Path, default=_DEFAULT_QUESTIONS,
                   help="Path to JSONL eval question set.")
    p.add_argument("--top-k", type=int, default=5,
                   help="Number of chunks to retrieve per question.")
    p.add_argument("--floor", type=float, default=0.5,
                   help="Exit 2 if recall@5 below this value.")
    return p


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = _make_parser()
    args = parser.parse_args()

    if not (args.seed_only or args.query_only or args.full):
        parser.error("must specify one of --seed-only / --query-only / --full")

    with _make_client(args.backend_url, args.testclient) as client:
        if not _health_check(client):
            print(
                json.dumps({"error": "backend unreachable or subsystems down"},
                           ensure_ascii=False),
                file=sys.stderr,
            )
            return 1

        if args.seed_only or args.full:
            seed_result = _ingest_via_http(client, args.seed_dir)
            if not args.full:
                print(json.dumps(seed_result, ensure_ascii=False))
                return 0

        if args.query_only or args.full:
            questions = _load_questions(args.questions)
            agg = _query_and_score(client, questions, top_k=args.top_k)

            if args.out_jsonl:
                with args.out_jsonl.open("w", encoding="utf-8") as fh:
                    for row in agg["details"]:
                        fh.write(json.dumps(row, ensure_ascii=False) + "\n")

            summary = {k: v for k, v in agg.items() if k != "details"}
            print(json.dumps(summary, ensure_ascii=False))

            if agg["recall_at_5"] < args.floor:
                return 2
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
