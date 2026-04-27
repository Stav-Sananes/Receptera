"""Post-call summary evaluation harness.

For each labelled call transcript, runs the production summary endpoint
(via the in-process router) and scores:

* Topic recall — does the topic mention any of the expected keywords?
* Action-item recall — do the action items mention any of the expected
  action keywords?

Recall is a soft metric (substring match, no exact-string requirement)
because Hebrew summaries can phrase the same action many valid ways.

Usage::

    python -m receptra.eval.summary_eval
    python -m receptra.eval.summary_eval --json
    python -m receptra.eval.summary_eval --threshold 0.6
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from importlib.resources import files
from pathlib import Path
from typing import TypedDict

from receptra.summary.prompts import build_summary_messages
from receptra.summary.schema import CallSummary


class _Sample(TypedDict):
    id: str
    transcript_lines: list[str]
    expected_topic_keywords: list[str]
    expected_action_keywords: list[str]


class _Score(TypedDict):
    id: str
    topic: str
    action_items: list[str]
    topic_recall: float
    action_recall: float
    latency_ms: int


def _load_dataset(path: Path | None) -> list[_Sample]:
    if path is None:
        data = json.loads(
            files("receptra.eval.datasets").joinpath("summary_he.json").read_text(encoding="utf-8")
        )
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    return list(data["samples"])


async def _generate_summary(transcript_lines: list[str]) -> CallSummary:
    """Call DictaLM via the same code path as the /api/summary endpoint."""
    # Import lazily so module import doesn't require Ollama setup.
    from receptra.llm.client import get_async_client, select_model

    transcript = "\n".join(transcript_lines)
    messages = build_summary_messages(transcript)
    client = get_async_client()
    chosen_model = await select_model(client)
    t0 = time.monotonic()
    response = await client.chat(
        model=chosen_model,
        messages=messages,
        stream=False,
        options={"temperature": 0.2, "num_predict": 400},
    )
    total_ms = int((time.monotonic() - t0) * 1000)
    raw = (response.message.content or "").strip()
    parsed = json.loads(raw)
    return CallSummary(
        topic=parsed["topic"],
        key_points=parsed.get("key_points", []),
        action_items=parsed.get("action_items", []),
        raw_text=raw,
        model=chosen_model,
        total_ms=total_ms,
    )


def _keyword_recall(text: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    hits = sum(1 for kw in keywords if kw in text)
    return hits / len(keywords)


async def _run_one(sample: _Sample) -> _Score:
    t0 = time.monotonic()
    try:
        summary = await _generate_summary(sample["transcript_lines"])
    except Exception as exc:
        return {
            "id": sample["id"],
            "topic": f"ERROR: {exc}",
            "action_items": [],
            "topic_recall": 0.0,
            "action_recall": 0.0,
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }
    actions_concat = " | ".join(summary.action_items)
    return {
        "id": sample["id"],
        "topic": summary.topic,
        "action_items": list(summary.action_items),
        "topic_recall": _keyword_recall(summary.topic, sample["expected_topic_keywords"]),
        "action_recall": _keyword_recall(actions_concat, sample["expected_action_keywords"]),
        "latency_ms": int((time.monotonic() - t0) * 1000),
    }


async def run_eval(dataset_path: Path | None = None) -> dict:
    samples = _load_dataset(dataset_path)
    scores: list[_Score] = []
    for sample in samples:
        scores.append(await _run_one(sample))

    n = len(scores)
    avg_topic = sum(s["topic_recall"] for s in scores) / n if n else 0.0
    avg_action = sum(s["action_recall"] for s in scores) / n if n else 0.0
    avg_latency = sum(s["latency_ms"] for s in scores) / n if n else 0.0
    p95 = (
        sorted(s["latency_ms"] for s in scores)[int(n * 0.95)] if n else 0
    )
    return {
        "n_total": n,
        "avg_topic_recall": avg_topic,
        "avg_action_recall": avg_action,
        "avg_latency_ms": avg_latency,
        "p95_latency_ms": p95,
        "samples": scores,
    }


def _render_text(report: dict) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("Post-Call Summary Eval — Receptra v1.1 F3")
    lines.append("=" * 60)
    lines.append(f"Samples:       {report['n_total']}")
    lines.append(f"Topic recall:  {report['avg_topic_recall']:.1%}")
    lines.append(f"Action recall: {report['avg_action_recall']:.1%}")
    lines.append(
        f"Latency:       avg={report['avg_latency_ms']:.0f}ms  p95={report['p95_latency_ms']}ms"
    )
    lines.append("")
    lines.append("Per-sample:")
    for s in report["samples"]:
        lines.append(
            f"  [{s['id']}] topic={s['topic_recall']:.1%}  action={s['action_recall']:.1%}"
            f"  ({s['latency_ms']}ms)"
        )
        lines.append(f"      topic: {s['topic']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Receptra post-call summary eval.")
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = asyncio.run(run_eval(args.dataset))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_text(report))

    avg = (report["avg_topic_recall"] + report["avg_action_recall"]) / 2.0
    if avg < args.threshold:
        print(f"FAIL: avg recall {avg:.1%} < threshold {args.threshold:.1%}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["main", "run_eval"]
