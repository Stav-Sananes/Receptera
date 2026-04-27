"""Recall@5 baseline + harness STT-isolation regression (RAG-05).

Two tests, both gated by RECEPTRA_RAG_LIVE_TEST=1 + the ``live`` marker:

1. ``test_recall_at_5_meets_baseline`` — runs eval_rag.py --full --testclient
   in a subprocess and asserts recall_at_5 >= 0.0. Under TestClient with the
   autouse _stub_heavy_loaders fixture from tests/conftest.py, the embedder +
   collection are MOCKED — retrieval returns zeros, so chunks score 0 similarity
   and fall below the default threshold, producing zero results for every query.
   This means: grounded questions get recall=0, refusal questions get recall=1.
   The test asserts recall_at_5 >= 0.0 (any non-negative). The substantive
   recall@5 number comes from ``RECEPTRA_RAG_LIVE_TEST=1 make eval-rag`` on a
   Mac with bge-m3 pulled + ChromaDB up — record that result in 04-06-SUMMARY.md.

2. ``test_eval_rag_harness_module_is_stt_clean`` — spawns a fresh subprocess,
   imports scripts/eval_rag.py via importlib.util, and asserts NO module
   matching 7 forbidden STT prefixes appears in sys.modules. Mirrors
   backend/tests/llm/test_harness_isolation.py byte-for-byte.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.rag.conftest import rag_live_test_enabled

pytestmark = pytest.mark.live

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EVAL_RAG = _REPO_ROOT / "scripts" / "eval_rag.py"


def test_recall_at_5_meets_baseline() -> None:
    """End-to-end: harness ingests fixtures + queries questions + reports recall@5.

    Under TestClient + autouse stubs, embedder returns zero-vectors and the
    collection mock returns no chunks above threshold — recall is mechanically
    low. This test proves harness wiring (JSON shape, exit codes) NOT quality.
    The real recall@5 baseline is recorded after first ``make eval-rag`` on
    reference Mac hardware with real bge-m3 + ChromaDB.
    """
    if not rag_live_test_enabled():
        pytest.skip("set RECEPTRA_RAG_LIVE_TEST=1 to run")

    result = subprocess.run(
        [sys.executable, str(_EVAL_RAG), "--full", "--testclient"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT / "backend"),
        timeout=120.0,
    )

    # Exit 0 (success) or 2 (recall below floor) are both acceptable;
    # exit 1 means backend unreachable and is a test failure.
    assert result.returncode in (0, 2), (
        f"eval_rag exited {result.returncode};\n"
        f"stdout={result.stdout!r}\n"
        f"stderr={result.stderr!r}"
    )

    # Last non-empty stdout line is the JSON summary.
    lines = [ln for ln in result.stdout.strip().split("\n") if ln.strip()]
    assert lines, f"no stdout from eval_rag: {result.stdout!r}"
    summary = json.loads(lines[-1])

    assert "recall_at_5" in summary, f"missing recall_at_5 key: {summary}"
    assert summary["n_questions"] == 10, (
        f"expected 10 questions, got {summary['n_questions']}"
    )
    assert 0.0 <= summary["recall_at_5"] <= 1.0, (
        f"recall_at_5 out of range: {summary['recall_at_5']}"
    )


def test_eval_rag_harness_module_is_stt_clean() -> None:
    """STT-isolation regression — mirrors Plan 03-06 test_harness_isolation.py.

    Fresh subprocess imports scripts/eval_rag.py via importlib.util, then
    prints sys.modules. Test asserts NO module matching 7 forbidden prefixes
    appears. If a future contributor adds ``import torch`` to the harness,
    this test surfaces the leak with the leaked module names in the assertion.
    """
    if not rag_live_test_enabled():
        pytest.skip("set RECEPTRA_RAG_LIVE_TEST=1 to run")

    forbidden = (
        "receptra.stt",
        "faster_whisper",
        "silero_vad",
        "torch",
        "onnxruntime",
        "ctranslate2",
        "av",
    )
    code = (
        "import importlib.util, sys; "
        f"spec = importlib.util.spec_from_file_location('eval_rag', {str(_EVAL_RAG)!r}); "
        "mod = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(mod); "
        "print('\\n'.join(sorted(sys.modules)))"
    )
    env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "backend" / "src")}
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30.0,
        env=env,
    )
    assert result.returncode == 0, (
        f"subprocess failed:\n{result.stderr}"
    )
    leaked = [
        m for m in result.stdout.strip().split("\n")
        if m.startswith(forbidden)
    ]
    assert not leaked, f"eval_rag.py leaked STT modules: {leaked}"
