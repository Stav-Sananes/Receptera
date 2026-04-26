#!/usr/bin/env python3
"""Receptra Phase 3 — LLM Suggestion CLI Harness (LLM-06).

Independent of the STT pipeline by construction: imports only
``receptra.llm.*`` + ``receptra.config``. The structural regression test
``backend/tests/llm/test_harness_isolation.py`` enforces this.

Usage:
    # Single-shot
    python scripts/eval_llm.py \\
        --transcript "תוך כמה זמן אני יכול להחזיר מוצר?" \\
        --context-file fixtures/llm/policy_returns.json

    # Empty context (short-circuit refusal — no Ollama call)
    python scripts/eval_llm.py \\
        --transcript "שלום" \\
        --context-file fixtures/llm/empty_context.json --no-stream

    # Eval set
    python scripts/eval_llm.py \\
        --eval-set fixtures/llm/eval_set.jsonl \\
        --out-jsonl results/llm_eval.jsonl

Exit codes:
    0  success
    1  ollama unreachable / timeout (single-shot only)
    2  parse_error rate > 5% (eval-set only)
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import statistics
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

# IMPORTANT: Do NOT import receptra.stt or faster_whisper or silero_vad here.
# The harness STT-isolation regression test enforces this contract.
from receptra.config import settings
from receptra.llm.engine import LlmCallTrace, generate_suggestions
from receptra.llm.metrics import build_record_call
from receptra.llm.schema import ChunkRef, CompleteEvent, LlmErrorEvent, TokenEvent

PARSE_ERROR_RATE_THRESHOLD = 0.05  # exit 2 when > 5% in eval-set mode


# --- Argument parser -------------------------------------------------------


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eval_llm.py",
        description="Receptra Phase 3 LLM CLI harness (LLM-06).",
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--transcript", help="Single-shot transcript (Hebrew).")
    mode.add_argument(
        "--eval-set", help="Path to a JSONL eval set (one row per line)."
    )
    p.add_argument(
        "--context-file",
        help="Single-shot context JSON file ([{id,text,source?},...]).",
    )
    p.add_argument(
        "--out-jsonl",
        help="Eval-set mode: write per-row results to this JSONL file.",
    )
    p.add_argument("--model", help="Override settings.llm_model_tag.")
    p.add_argument(
        "--ollama-host",
        help="Override settings.ollama_host (e.g. http://localhost:11434).",
    )
    p.add_argument(
        "--system-prompt-lang",
        choices=["he", "en"],
        help="Override settings.llm_system_prompt_lang.",
    )
    p.add_argument(
        "--no-stream",
        action="store_true",
        help="Single-shot: suppress stderr TokenEvent feed.",
    )
    p.add_argument(
        "--no-audit",
        action="store_true",
        help="Skip build_record_call wiring (useful for CI smoke).",
    )
    return p


# --- Fixture loading -------------------------------------------------------


def _load_chunks(path: str | Path) -> list[ChunkRef]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"context file {path} must be a JSON array")
    chunks: list[ChunkRef] = []
    for item in raw:
        if not isinstance(item, dict) or "id" not in item or "text" not in item:
            raise ValueError(
                f"context file {path}: each row must be an object with 'id' + 'text'"
            )
        source_raw = item.get("source")
        source: dict[str, str] | None = None
        if source_raw is not None:
            if not isinstance(source_raw, dict):
                raise ValueError(
                    f"context file {path}: 'source' must be an object when present"
                )
            source = {str(k): str(v) for k, v in source_raw.items()}
        chunks.append(
            ChunkRef(
                id=str(item["id"]),
                text=str(item["text"]),
                source=source,
            )
        )
    return chunks


def _load_eval_set(path: str | Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"eval-set {path}: each line must be a JSON object")
            out.append(row)
    return out


# --- Single-shot mode ------------------------------------------------------


async def run_single_shot(
    transcript: str,
    chunks: list[ChunkRef],
    *,
    model: str | None,
    record_call: Callable[[LlmCallTrace], None] | None,
    stream_to_stderr: bool,
    out: TextIO,
    err: TextIO,
) -> int:
    """Returns exit code (0 success, 1 ollama unreachable/timeout)."""
    if settings.llm_system_prompt_lang not in {"he", "en"}:
        # build_messages will raise; surface a friendly error early.
        print(
            f"ERROR: invalid system_prompt_lang={settings.llm_system_prompt_lang}",
            file=err,
        )
        return 1

    complete: CompleteEvent | None = None
    fatal_code: str | None = None

    async for ev in generate_suggestions(
        transcript, chunks, model=model, record_call=record_call
    ):
        if isinstance(ev, TokenEvent):
            if stream_to_stderr:
                err.write(ev.delta)
                err.flush()
        elif isinstance(ev, CompleteEvent):
            complete = ev
        elif isinstance(ev, LlmErrorEvent):
            print(
                json.dumps(
                    {"type": "error", "code": ev.code, "detail": ev.detail},
                    ensure_ascii=False,
                ),
                file=err,
            )
            if ev.code in {"ollama_unreachable", "timeout"}:
                fatal_code = ev.code

    if stream_to_stderr:
        err.write("\n")  # newline after token feed

    if complete is None:
        # Reached only via ollama_unreachable / timeout (no terminal CompleteEvent).
        return 1 if fatal_code else 0

    # Pretty-print CompleteEvent JSON to stdout.
    out_payload = {
        "type": "complete",
        "suggestions": [
            {
                "text": s.text,
                "confidence": s.confidence,
                "citation_ids": list(s.citation_ids),
            }
            for s in complete.suggestions
        ],
        "ttft_ms": complete.ttft_ms,
        "total_ms": complete.total_ms,
        "model": complete.model,
    }
    print(json.dumps(out_payload, ensure_ascii=False, indent=2), file=out)

    grounded = any(s.citation_ids for s in complete.suggestions)
    print(
        f"TTFT: {complete.ttft_ms} ms  TOTAL: {complete.total_ms} ms  "
        f"MODEL: {complete.model}  GROUNDED: {str(grounded).lower()}",
        file=err,
    )
    return 1 if fatal_code else 0


# --- Eval-set mode ---------------------------------------------------------


async def _run_one_eval(
    row: dict[str, Any],
    *,
    model: str | None,
    record_call: Callable[[LlmCallTrace], None] | None,
) -> dict[str, Any]:
    """Run one eval row and return per-row result dict."""
    chunks: list[ChunkRef] = []
    for c in row.get("context", []):
        if not isinstance(c, dict) or "id" not in c or "text" not in c:
            raise ValueError(
                f"eval row {row.get('id')!r}: context entries must have 'id' + 'text'"
            )
        source_raw = c.get("source")
        source: dict[str, str] | None = None
        if isinstance(source_raw, dict):
            source = {str(k): str(v) for k, v in source_raw.items()}
        chunks.append(
            ChunkRef(id=str(c["id"]), text=str(c["text"]), source=source)
        )
    transcript = str(row["transcript"])
    expected = row.get("expected", {})

    complete: CompleteEvent | None = None
    error_code: str | None = None
    saw_parse_retry = False

    async for ev in generate_suggestions(
        transcript, chunks, model=model, record_call=record_call
    ):
        if isinstance(ev, CompleteEvent):
            complete = ev
        elif isinstance(ev, LlmErrorEvent):
            error_code = ev.code
            if ev.code == "parse_error":
                saw_parse_retry = True

    is_refusal = bool(
        complete
        and complete.suggestions
        and complete.suggestions[0].text == "אין לי מספיק מידע"
    )
    is_grounded = bool(
        complete and any(s.citation_ids for s in complete.suggestions)
    )

    expected_refusal = bool(expected.get("refusal", False))
    expected_grounded = bool(expected.get("grounded", False))

    if expected_refusal:
        passed = is_refusal
    elif expected_grounded:
        passed = is_grounded and not is_refusal
    else:
        passed = complete is not None  # at least we got a terminal event

    status = "ok"
    if error_code in {"ollama_unreachable", "timeout"}:
        status = error_code or "ok"
    elif saw_parse_retry and complete and is_refusal and not expected_refusal:
        status = "parse_error"
    elif saw_parse_retry and complete and not is_refusal:
        # Retry recovered to a valid reply
        status = "parse_retry_ok"

    return {
        "id": row.get("id"),
        "ttft_ms": complete.ttft_ms if complete else -1,
        "total_ms": complete.total_ms if complete else -1,
        "status": status,
        "is_refusal": is_refusal,
        "is_grounded": is_grounded,
        "passed": passed,
        "suggestions": [
            {
                "text": s.text,
                "confidence": s.confidence,
                "citation_ids": list(s.citation_ids),
            }
            for s in (complete.suggestions if complete else [])
        ],
        "error_code": error_code,
    }


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"count": 0}
    ttfts = [r["ttft_ms"] for r in rows if r["ttft_ms"] >= 0]
    refusals = sum(1 for r in rows if r["is_refusal"])
    grounded = sum(1 for r in rows if r["is_grounded"])
    parse_retries = sum(1 for r in rows if r["status"] == "parse_retry_ok")
    parse_errors = sum(1 for r in rows if r["status"] == "parse_error")
    passes = sum(1 for r in rows if r["passed"])

    def _p95(xs: list[int]) -> float:
        if not xs:
            return -1.0
        xs_sorted = sorted(xs)
        idx = max(0, round(0.95 * (len(xs_sorted) - 1)))
        return float(xs_sorted[idx])

    return {
        "count": n,
        "mean_ttft_ms": statistics.mean(ttfts) if ttfts else -1,
        "p95_ttft_ms": _p95(ttfts),
        "refusal_rate": refusals / n,
        "grounded_rate": grounded / n,
        "parse_retry_rate": parse_retries / n,
        "parse_error_rate": parse_errors / n,
        "pass_rate": passes / n,
    }


async def run_eval_set(
    eval_path: str,
    out_jsonl: str | None,
    *,
    model: str | None,
    record_call: Callable[[LlmCallTrace], None] | None,
    out: TextIO,
    err: TextIO,
) -> int:
    """Returns exit code (0 success, 1 ollama unreachable, 2 parse_error rate > threshold)."""
    rows = _load_eval_set(eval_path)
    results: list[dict[str, Any]] = []
    # Use ExitStack so the optional output file is managed by a context
    # manager regardless of whether --out-jsonl was supplied (SIM115 lock).
    with contextlib.ExitStack() as stack:
        out_handle: TextIO | None = (
            stack.enter_context(open(out_jsonl, "w", encoding="utf-8"))
            if out_jsonl
            else None
        )
        for row in rows:
            result = await _run_one_eval(row, model=model, record_call=record_call)
            results.append(result)
            if out_handle is not None:
                out_handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                out_handle.flush()
            print(
                json.dumps(
                    {
                        "id": result["id"],
                        "passed": result["passed"],
                        "status": result["status"],
                    },
                    ensure_ascii=False,
                ),
                file=err,
            )

    agg = _aggregate(results)
    print(json.dumps(agg, ensure_ascii=False, indent=2), file=out)

    if any(r["status"] in {"ollama_unreachable", "timeout"} for r in results):
        return 1
    if agg.get("parse_error_rate", 0.0) > PARSE_ERROR_RATE_THRESHOLD:
        return 2
    return 0


# --- Main ------------------------------------------------------------------


async def _amain(args: argparse.Namespace) -> int:
    # Apply CLI overrides on settings. Settings is a Pydantic BaseSettings
    # singleton; we patch via __dict__ to skip pydantic re-validation
    # (we trust the URL/lang since the developer is invoking the harness).
    if args.ollama_host:
        settings.__dict__["ollama_host"] = args.ollama_host
    if args.system_prompt_lang:
        settings.__dict__["llm_system_prompt_lang"] = args.system_prompt_lang

    record_call: Callable[[LlmCallTrace], None] | None = None
    if not args.no_audit:
        record_call = build_record_call(settings.audit_db_path)

    if args.transcript is not None:
        if not args.context_file:
            print(
                "ERROR: --context-file is required with --transcript",
                file=sys.stderr,
            )
            return 1
        chunks = _load_chunks(args.context_file)
        return await run_single_shot(
            args.transcript,
            chunks,
            model=args.model,
            record_call=record_call,
            stream_to_stderr=not args.no_stream,
            out=sys.stdout,
            err=sys.stderr,
        )
    else:  # --eval-set
        return await run_eval_set(
            args.eval_set,
            args.out_jsonl,
            model=args.model,
            record_call=record_call,
            out=sys.stdout,
            err=sys.stderr,
        )


def main() -> int:
    args = _make_parser().parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
