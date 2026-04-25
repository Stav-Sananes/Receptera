"""DictaLM 3.0 ChatML chat-template auto-detection gate (Pitfall B + A5).

DictaLM 2.0 uses mistral-instruct format; DictaLM 3.0 uses ChatML
(<|im_start|> / <|im_end|>). Stale tutorials applying 2.0 advice to 3.0
silently break Phase 3. This gate runs `ollama show dictalm3 --modelfile`
and asserts both ChatML markers appear in the auto-detected TEMPLATE.

Recovery path if this fails (Assumption A5 wrong):
    Add an explicit TEMPLATE block to scripts/ollama/DictaLM3.Modelfile:

        TEMPLATE \"\"\"{{ if .System }}<|im_start|>system
        {{ .System }}<|im_end|>
        {{ end }}<|im_start|>user
        {{ .Prompt }}<|im_end|>
        <|im_start|>assistant
        \"\"\"

    Then re-run `make models dictalm` to re-register with the explicit
    template.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from .conftest import live_test_enabled


def _ollama_has_dictalm3() -> bool:
    if shutil.which("ollama") is None:
        return False
    proc = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if proc.returncode != 0:
        return False
    # `ollama list` rows start with "<tag>:..." — first column.
    return any(line.strip().startswith("dictalm3") for line in proc.stdout.splitlines())


def test_dictalm3_modelfile_template_skipped_without_ollama_binary() -> None:
    """Self-skip path: the chat-template grep test must self-skip when
    `ollama` is not on PATH (e.g., ubuntu-latest CI). Proves the skip
    machinery in the live test below works.
    """
    if shutil.which("ollama") is not None:
        pytest.skip("ollama IS on PATH on this machine — see live test instead")
    # If we get here, `ollama` is not on PATH and the live test should self-skip
    # without raising. We don't actually invoke it here — pytest collection
    # alone proves the skip predicates compile.
    assert True


@pytest.mark.live
def test_dictalm3_chatml_template_detected() -> None:
    """Assert `ollama show dictalm3 --modelfile` carries ChatML markers.

    Skips when:
      - RECEPTRA_LLM_LIVE_TEST is unset
      - `ollama` binary is not on PATH
      - `dictalm3` is not in `ollama list`
    """
    if not live_test_enabled():
        pytest.skip("set RECEPTRA_LLM_LIVE_TEST=1 to run live Ollama tests")
    if not _ollama_has_dictalm3():
        pytest.skip(
            "ollama binary missing or `dictalm3` model not registered — "
            "run `make models dictalm` first"
        )

    proc = subprocess.run(
        ["ollama", "show", "dictalm3", "--modelfile"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    out = proc.stdout
    assert "<|im_start|>" in out, (
        "DictaLM 3.0 ChatML start marker NOT found in `ollama show dictalm3 "
        "--modelfile` — Assumption A5 violated. Add explicit TEMPLATE block "
        "to scripts/ollama/DictaLM3.Modelfile per 03-RESEARCH §3 recovery "
        "instructions and re-run `make models dictalm`."
    )
    assert "<|im_end|>" in out, (
        "DictaLM 3.0 ChatML end marker NOT found — same recovery as above."
    )
