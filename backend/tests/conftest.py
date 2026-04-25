"""Shared pytest fixtures for Receptra backend tests.

The ``client`` fixture wraps ``TestClient(app) as c:``, which runs the full
lifespan startup — including the Whisper + Silero VAD singleton loaders
added in Plan 02-02. To keep tests offline + fast, ``_stub_heavy_loaders``
is autouse and monkeypatches those loaders with trivial stubs BEFORE the
app module is imported in any fixture.

Tests that need to assert on loader behavior (e.g., tests/stt/test_lifespan.py)
opt into their own scoped fixture which overrides the stubs with
introspectable variants.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _InfoStub:
    """Minimal stand-in for faster_whisper.transcribe.TranscriptionInfo."""

    duration = 1.0
    language = "he"
    language_probability = 1.0


class _WhisperStub:
    """Silent stand-in for faster_whisper.WhisperModel (no weights loaded)."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def transcribe(self, *_args: Any, **_kwargs: Any) -> tuple[Any, _InfoStub]:
        # Accept ``audio`` as either positional or keyword (engine.py passes it
        # as ``audio=...`` keyword; mocks can be invoked either way).
        return iter([]), _InfoStub()


def _load_silero_stub(*_args: Any, **_kwargs: Any) -> object:
    return object()  # opaque sentinel


@pytest.fixture(autouse=True)
def _stub_heavy_loaders(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Replace WhisperModel + load_silero_vad before any app import.

    Ensures TestClient's lifespan startup does not try to load real weights
    from ``$MODEL_DIR/whisper-turbo-ct2`` during offline CI. Individual STT
    tests that need a richer mock (e.g., call counting) override these in
    their own monkeypatch scope.
    """
    # Drop any cached import so fresh module-import picks up the stubs.
    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)

    import receptra.lifespan as lifespan_mod

    monkeypatch.setattr(lifespan_mod, "WhisperModel", _WhisperStub)
    monkeypatch.setattr(lifespan_mod, "load_silero_vad", _load_silero_stub)

    yield

    # Reset again so the next test's autouse fixture gets a clean slate.
    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)


@pytest.fixture
def app() -> FastAPI:
    """Return the FastAPI app instance for tests.

    Imported lazily so that test discovery does not require a populated .env.
    """
    from receptra.main import app as receptra_app

    return receptra_app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Return a FastAPI TestClient wrapping the app."""
    with TestClient(app) as test_client:
        yield test_client
