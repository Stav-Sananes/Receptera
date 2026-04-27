"""Tests for the intent eval harness — mocks DictaLM so no Ollama needed."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch


def test_dataset_loads_with_30_samples_across_6_labels() -> None:
    from receptra.eval.intent_eval import _load_dataset

    samples = _load_dataset(None)
    assert len(samples) >= 24, f"need >= 24 labelled samples, got {len(samples)}"
    labels = {s["label"] for s in samples}
    assert labels == {"booking", "complaint", "billing", "information", "cancellation", "other"}


def test_perfect_run_reports_100_percent_accuracy() -> None:
    """When detect_intent always returns the expected label, accuracy = 100%."""
    from receptra.eval.intent_eval import _load_dataset, run_eval

    samples = _load_dataset(None)
    by_text = {s["text"]: s["label"] for s in samples}

    async def perfect_intent(text: str) -> str:
        return by_text[text]

    with patch("receptra.eval.intent_eval.detect_intent", new=perfect_intent):
        report = asyncio.run(run_eval(None))

    assert report["accuracy"] == 1.0
    assert report["n_correct"] == report["n_total"]
    assert all(m["f1"] == 1.0 for m in report["per_label"].values())


def test_all_other_run_reports_partial_accuracy() -> None:
    """If detect_intent always returns 'other', accuracy == proportion of 'other' samples."""
    from receptra.eval.intent_eval import _load_dataset, run_eval

    samples = _load_dataset(None)
    n_other = sum(1 for s in samples if s["label"] == "other")
    n_total = len(samples)

    with patch("receptra.eval.intent_eval.detect_intent", new=AsyncMock(return_value="other")):
        report = asyncio.run(run_eval(None))

    assert report["n_correct"] == n_other
    assert abs(report["accuracy"] - n_other / n_total) < 0.001


def test_main_returns_1_on_threshold_fail() -> None:
    from receptra.eval.intent_eval import main

    with patch("receptra.eval.intent_eval.detect_intent", new=AsyncMock(return_value="other")):
        # threshold 0.99 — single-label model can't hit it
        rc = main(["--threshold", "0.99"])
    assert rc == 1


def test_main_returns_0_on_perfect_run() -> None:
    from receptra.eval.intent_eval import _load_dataset, main

    samples = _load_dataset(None)
    by_text = {s["text"]: s["label"] for s in samples}

    async def perfect_intent(text: str) -> str:
        return by_text[text]

    with patch("receptra.eval.intent_eval.detect_intent", new=perfect_intent):
        rc = main(["--threshold", "0.95"])
    assert rc == 0


def test_confusion_matrix_records_misclassifications() -> None:
    from receptra.eval.intent_eval import run_eval

    # Always wrong: booking → complaint
    with patch("receptra.eval.intent_eval.detect_intent", new=AsyncMock(return_value="complaint")):
        report = asyncio.run(run_eval(None))

    cm = report["confusion_matrix"]
    # Every sample with expected=booking gets predicted=complaint
    assert cm.get("booking", {}).get("complaint", 0) > 0
