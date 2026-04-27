"""Intent classification evaluation harness.

Runs ``detect_intent`` over a labelled Hebrew test set and reports
per-class precision/recall + overall accuracy.

Usage::

    # Requires Ollama running with DictaLM 3.0 loaded
    python -m receptra.eval.intent_eval

    # Custom dataset
    python -m receptra.eval.intent_eval --dataset path/to/eval.json

    # JSON output (for CI)
    python -m receptra.eval.intent_eval --json > report.json

Exit codes:
    0  — accuracy >= --threshold (default 0.70)
    1  — accuracy < --threshold (regression)
    2  — Ollama unreachable / setup error
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path
from typing import TypedDict

from receptra.pipeline.intent import detect_intent


class _Sample(TypedDict):
    id: str
    text: str
    label: str


class _Result(TypedDict):
    id: str
    text: str
    expected: str
    predicted: str
    correct: bool
    latency_ms: int


def _load_dataset(path: Path | None) -> list[_Sample]:
    if path is None:
        # bundled default
        data = json.loads(
            files("receptra.eval.datasets").joinpath("intent_he.json").read_text(encoding="utf-8")
        )
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    return list(data["samples"])


async def _run_one(sample: _Sample) -> _Result:
    t0 = time.monotonic()
    try:
        predicted = await detect_intent(sample["text"])
    except Exception as exc:
        return {
            "id": sample["id"],
            "text": sample["text"],
            "expected": sample["label"],
            "predicted": f"ERROR: {exc}",
            "correct": False,
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }
    return {
        "id": sample["id"],
        "text": sample["text"],
        "expected": sample["label"],
        "predicted": predicted,
        "correct": predicted == sample["label"],
        "latency_ms": int((time.monotonic() - t0) * 1000),
    }


def _confusion_matrix(results: Iterable[_Result]) -> dict[str, dict[str, int]]:
    cm: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in results:
        cm[r["expected"]][r["predicted"]] += 1
    return {k: dict(v) for k, v in cm.items()}


def _precision_recall(
    results: list[_Result],
    labels: Iterable[str],
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for label in labels:
        tp = sum(1 for r in results if r["expected"] == label and r["predicted"] == label)
        fp = sum(1 for r in results if r["expected"] != label and r["predicted"] == label)
        fn = sum(1 for r in results if r["expected"] == label and r["predicted"] != label)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        out[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    return out


async def run_eval(dataset_path: Path | None = None) -> dict:
    samples = _load_dataset(dataset_path)
    results: list[_Result] = []
    for sample in samples:
        results.append(await _run_one(sample))

    n_total = len(results)
    n_correct = sum(1 for r in results if r["correct"])
    accuracy = n_correct / n_total if n_total > 0 else 0.0
    p50_latency = sorted(r["latency_ms"] for r in results)[n_total // 2] if n_total > 0 else 0
    p95_latency = (
        sorted(r["latency_ms"] for r in results)[int(n_total * 0.95)] if n_total > 0 else 0
    )

    labels = sorted({r["expected"] for r in results})
    return {
        "n_total": n_total,
        "n_correct": n_correct,
        "accuracy": accuracy,
        "p50_latency_ms": p50_latency,
        "p95_latency_ms": p95_latency,
        "per_label": _precision_recall(results, labels),
        "confusion_matrix": _confusion_matrix(results),
        "errors": [r for r in results if not r["correct"]],
    }


def _render_text(report: dict) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("Intent Classification Eval — Receptra v1.1 F4")
    lines.append("=" * 60)
    lines.append(
        f"Accuracy: {report['accuracy']:.1%}  ({report['n_correct']}/{report['n_total']})"
    )
    lines.append(f"Latency:  p50={report['p50_latency_ms']}ms  p95={report['p95_latency_ms']}ms")
    lines.append("")
    lines.append("Per-label F1:")
    for label, m in sorted(report["per_label"].items()):
        lines.append(
            f"  {label:14s} P={m['precision']:.2f} R={m['recall']:.2f} "
            f"F1={m['f1']:.2f}  (n={m['support']})"
        )
    lines.append("")
    if report["errors"]:
        lines.append(f"Errors ({len(report['errors'])}):")
        for e in report["errors"][:10]:
            lines.append(f"  [{e['id']}] expected={e['expected']:<13} got={e['predicted']:<13}")
            lines.append(f"      \"{e['text']}\"")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Receptra intent classification eval.")
    parser.add_argument("--dataset", type=Path, default=None, help="Path to JSON dataset")
    parser.add_argument(
        "--threshold", type=float, default=0.70, help="Min accuracy to pass (default 0.70)"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report instead of text")
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

    if report["accuracy"] < args.threshold:
        print(
            f"FAIL: accuracy {report['accuracy']:.1%} < threshold {args.threshold:.1%}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["_load_dataset", "main", "run_eval"]
