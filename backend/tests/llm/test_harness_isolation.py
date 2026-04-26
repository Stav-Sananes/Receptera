"""LLM-06 structural regression: scripts/eval_llm.py harness MUST NOT pull
in receptra.stt or any STT-only deps (faster_whisper, silero_vad, torch,
onnxruntime, ctranslate2, av).

Runs the harness module in a SUBPROCESS so any module-state pollution from
other tests in this session cannot mask a real regression.

If this fails, the most likely culprits are:
- Someone added ``from receptra.stt.* import ...`` to receptra.llm.*
- Someone added ``import faster_whisper`` to a shared module
- A circular import in receptra/__init__.py started executing STT init
"""
from __future__ import annotations

import json as _json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HARNESS_PATH = Path(__file__).resolve().parents[3] / "scripts" / "eval_llm.py"
_REPO_ROOT = Path(__file__).resolve().parents[3]


# Modules whose presence in sys.modules indicates an isolation regression.
_FORBIDDEN_PREFIXES = (
    "receptra.stt",
    "faster_whisper",
    "silero_vad",
    "torch",  # heavy; pulled by silero
    "onnxruntime",  # pulled by silero
    "ctranslate2",  # pulled by faster_whisper
    "av",  # pulled by faster_whisper
)


def test_harness_module_is_stt_clean() -> None:
    """Importing the harness module must not load any STT-domain modules."""
    if not _HARNESS_PATH.exists():
        pytest.skip(f"harness not at {_HARNESS_PATH}")

    code = (
        "import sys, json\n"
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('eval_llm', {str(_HARNESS_PATH)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "assert spec.loader is not None\n"
        "spec.loader.exec_module(mod)\n"
        f"forbidden = {_FORBIDDEN_PREFIXES!r}\n"
        "leaked = sorted(k for k in sys.modules "
        "if any(k == p or k.startswith(p + '.') for p in forbidden))\n"
        "print(json.dumps({'leaked': leaked}))\n"
    )

    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        cwd=str(_REPO_ROOT),
        env={
            **os.environ,
            # Belt + braces: ensure the subprocess does not load .env auto-magic
            # that might side-trigger imports.
            "RECEPTRA_LLM_LIVE_TEST": "",
        },
    )

    assert proc.returncode == 0, (
        f"harness import subprocess failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )

    last_line = proc.stdout.strip().splitlines()[-1]
    payload = _json.loads(last_line)
    assert payload["leaked"] == [], (
        f"LLM-06 isolation contract violated: scripts/eval_llm.py transitively "
        f"imported {payload['leaked']}. Find the import in receptra.llm.* or "
        f"the harness itself and remove it. (Don't ignore — LLM-06 requires "
        f"the CLI harness to be independent of the STT pipeline.)"
    )


def test_engine_module_is_stt_clean() -> None:
    """Belt + braces: also verify importing receptra.llm.engine alone is STT-clean.

    The harness test above is the user-facing contract; this is the lower-level
    canary so a regression in receptra.llm.engine surfaces here even if the
    harness imports something else.
    """
    code = (
        "import sys, json\n"
        "import receptra.llm.engine  # noqa: F401\n"
        f"forbidden = {_FORBIDDEN_PREFIXES!r}\n"
        "leaked = sorted(k for k in sys.modules "
        "if any(k == p or k.startswith(p + '.') for p in forbidden))\n"
        "print(json.dumps({'leaked': leaked}))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        cwd=str(_REPO_ROOT / "backend"),
        env={**os.environ, "PYTHONPATH": str(_REPO_ROOT / "backend" / "src")},
    )
    assert proc.returncode == 0, f"engine subprocess failed:\n{proc.stderr}"
    last_line = proc.stdout.strip().splitlines()[-1]
    payload = _json.loads(last_line)
    assert payload["leaked"] == [], (
        f"LLM-06 contract violated at engine level: receptra.llm.engine pulled "
        f"{payload['leaked']}. Plan 03-04 boundary regressed."
    )
