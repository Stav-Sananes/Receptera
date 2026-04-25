"""STT-05 regression: WER + CER baseline guard.

Skipped unless ALL of the following hold:

* The fixture manifest exists AND is not the airgap placeholder.
* The Whisper model directory exists at ``$RECEPTRA_MODEL_DIR``.
* ``BASELINE_WER`` and ``BASELINE_CER`` are set (by the contributor who
  records them in this file after the first successful eval run).

OPEN-7 (RESEARCH §9): WER is INFORMATIONAL — this test asserts that a
contributor's change does not silently regress accuracy more than
``GRACE_PP`` percentage points. It does NOT enforce a specific accuracy
floor. To raise / lower the baseline, run ``scripts/eval_wer.py`` and
update the constants below in the same PR (Hebrew-speaker review of the
diff is policy — see ``docs/stt-eval.md`` "Updating the baseline").

T-02-05-04 mitigation: ``GRACE_PP = 0.03`` is a module-level constant.
Any change is a code-diff requiring review.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
FIXTURES_JSONL = REPO_ROOT / "backend" / "tests" / "stt" / "fixtures" / "he_cv_30.jsonl"
EVAL_SCRIPT = REPO_ROOT / "scripts" / "eval_wer.py"

# --- Baseline (set by the first contributor with HF Hub + model access) ---
# Contributor workflow:
#   1. fetch fixtures: `python scripts/fetch_stt_fixtures.py`
#   2. run eval:       `cd backend && uv run python ../scripts/eval_wer.py > /tmp/eval.json`
#   3. read wer_mean + cer_mean from /tmp/eval.json["baseline"]
#   4. update BASELINE_WER + BASELINE_CER below + commit
#   5. commit fixtures + this file together
BASELINE_WER: float | None = None
BASELINE_CER: float | None = None
GRACE_PP: float = 0.03  # 3 percentage-point grace per RESEARCH §Validation


def _fixtures_present() -> bool:
    if not FIXTURES_JSONL.exists():
        return False
    # Check the first row isn't the airgap placeholder.
    first_line = FIXTURES_JSONL.read_text(encoding="utf-8").splitlines()[0]
    if not first_line.strip():
        return False
    try:
        first = json.loads(first_line)
    except json.JSONDecodeError:
        return False
    return bool(first.get("id") != "UNFETCHED")


def _model_present() -> bool:
    root = pathlib.Path(
        os.environ.get(
            "RECEPTRA_MODEL_DIR", str(pathlib.Path.home() / ".receptra" / "models")
        )
    )
    return (root / "whisper-turbo-ct2").exists()


_skip_reason: str | None = None
if not _fixtures_present():
    _skip_reason = (
        "fixtures unfetched — run scripts/fetch_stt_fixtures.py "
        "(see docs/stt-eval.md)"
    )
elif not _model_present():
    _skip_reason = (
        "Whisper model not found at $RECEPTRA_MODEL_DIR/whisper-turbo-ct2 — "
        "run `make models`"
    )
elif BASELINE_WER is None or BASELINE_CER is None:
    _skip_reason = (
        "BASELINE_WER / BASELINE_CER not yet recorded — first contributor "
        "with model access runs scripts/eval_wer.py and commits the numbers"
    )


@pytest.mark.skipif(_skip_reason is not None, reason=_skip_reason or "")
def test_wer_regression() -> None:
    """Run scripts/eval_wer.py end-to-end and assert WER + CER ≤ baseline + 3pp."""
    assert BASELINE_WER is not None  # narrow the type for mypy
    assert BASELINE_CER is not None

    proc = subprocess.run(
        [sys.executable, str(EVAL_SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(REPO_ROOT / "backend"),
    )
    report = json.loads(proc.stdout)
    assert report["status"] == "ok", f"eval failed: {report}"
    baseline = report["baseline"]
    measured_wer = float(baseline["wer_mean"])
    measured_cer = float(baseline["cer_mean"])

    assert measured_wer <= BASELINE_WER + GRACE_PP, (
        f"WER regressed: measured {measured_wer:.3f} > "
        f"baseline {BASELINE_WER:.3f} + grace {GRACE_PP:.3f}. "
        "If this is intentional (model upgrade, dep bump), update BASELINE_WER "
        "in this file with Hebrew-speaker review per docs/stt-eval.md."
    )
    assert measured_cer <= BASELINE_CER + GRACE_PP, (
        f"CER regressed: measured {measured_cer:.3f} > "
        f"baseline {BASELINE_CER:.3f} + grace {GRACE_PP:.3f}."
    )
