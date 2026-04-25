"""Tests for the FastAPI lifespan that loads Whisper + Silero VAD singletons.

Pitfall #1 defense: ``@app.on_event + lifespan=`` silently drops the startup
hook. test_no_on_event_decorators_remain guards against a regression where a
future contributor re-adds ``@app.on_event`` to main.py.

Pitfall #7 defense: first ``WhisperModel.transcribe`` call is 2-3x slower than
steady state; a warmup transcribe on 1s silence inside the lifespan ensures
the latency budget is met on the first user interaction.

All heavy loaders (``WhisperModel``, ``load_silero_vad``) are monkeypatched
to trivial stubs so tests stay offline + fast.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
MAIN_PY_PATH = BACKEND_ROOT / "src" / "receptra" / "main.py"


def test_no_on_event_decorators_remain() -> None:
    """main.py MUST NOT use ``@app.on_event`` (Pitfall #1 — silent no-op w/ lifespan=)."""
    source = MAIN_PY_PATH.read_text(encoding="utf-8")
    assert "@app.on_event" not in source, (
        "main.py contains @app.on_event; this is silently dropped when "
        "FastAPI(lifespan=...) is used (Pitfall #1). Move startup logic "
        "into receptra.lifespan.lifespan()."
    )


def test_app_has_lifespan() -> None:
    """FastAPI app MUST be constructed with ``lifespan=lifespan`` (not None)."""
    from receptra.main import app

    # ``router.lifespan_context`` is the internal handle FastAPI sets when
    # ``lifespan=`` is passed (bool-ish even if the underlying callable
    # defers to the default).
    assert app.router.lifespan_context is not None


@pytest.fixture
def stubbed_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Any, dict[str, Any]]]:
    """Monkeypatch heavy loaders, force a fresh import of receptra.main, yield app + call-log."""
    calls: dict[str, Any] = {"transcribe": 0, "languages": [], "kwargs_seen": []}

    class _Info:
        duration = 1.0
        language = "he"
        language_probability = 1.0

    class _WhisperStub:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def transcribe(self, audio: Any, **kwargs: Any) -> tuple[Any, _Info]:
            calls["transcribe"] += 1
            calls["languages"].append(kwargs.get("language"))
            calls["kwargs_seen"].append(dict(kwargs))
            return iter([]), _Info()

    def _load_silero_stub(*_args: Any, **_kwargs: Any) -> object:
        return object()  # opaque sentinel

    # Drop any cached import so monkeypatch bites on the next import.
    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)

    # Import lifespan module first so we can patch its symbols before the
    # context manager runs inside TestClient.
    lifespan_mod = importlib.import_module("receptra.lifespan")
    monkeypatch.setattr(lifespan_mod, "WhisperModel", _WhisperStub)
    monkeypatch.setattr(lifespan_mod, "load_silero_vad", _load_silero_stub)

    from receptra.main import app

    yield app, calls

    # Clean up so subsequent tests get a fresh (un-stubbed) import.
    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)


def test_whisper_loaded_on_state(stubbed_app: tuple[Any, dict[str, Any]]) -> None:
    """After startup, ``app.state.whisper``, ``.vad_model``, ``.warmup_complete`` are set."""
    app, _calls = stubbed_app

    with TestClient(app) as client:
        # Any request forces the lifespan startup to run.
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert app.state.whisper is not None
        assert app.state.vad_model is not None
        assert app.state.warmup_complete is True


def test_warmup_transcribe_called(stubbed_app: tuple[Any, dict[str, Any]]) -> None:
    """Warmup transcribe runs exactly once during startup w/ language='he' (Pitfall #7)."""
    app, calls = stubbed_app

    with TestClient(app) as client:
        client.get("/healthz")

    assert calls["transcribe"] == 1, (
        f"Expected exactly 1 warmup transcribe during lifespan startup; "
        f"got {calls['transcribe']}."
    )
    assert calls["languages"] == ["he"], (
        f"Warmup transcribe MUST use language='he' (ivrit-ai Hebrew-only "
        f"model); got {calls['languages']}."
    )
