"""Shared pytest fixtures for Receptra backend tests.

The ``client`` fixture wraps ``TestClient(app) as c:``, which runs the full
lifespan startup — including the Whisper + Silero VAD singleton loaders
added in Plan 02-02. To keep tests offline + fast, ``_stub_heavy_loaders``
is autouse and monkeypatches those loaders with trivial stubs BEFORE the
app module is imported in any fixture.

Tests that need to assert on loader behavior (e.g., tests/stt/test_lifespan.py)
opt into their own scoped fixture which overrides the stubs with
introspectable variants.

Plan 04-01: registers the ``live`` marker at the TOP-LEVEL conftest so it is
visible to every subdirectory under ``--strict-markers`` regardless of which
test path is collected. (Plan 03-01 originally registered it in
``tests/llm/conftest.py``; that registration is removed to avoid duplicate
addinivalue_line entries.) Per-package live-test gates (LLM vs RAG) keep
their separate ``RECEPTRA_*_LIVE_TEST`` env vars.

Plan 04-05: ``_stub_heavy_loaders`` also stubs ``BgeM3Embedder`` and
``open_collection`` so that the RAG lifespan init added in that plan does
not attempt to reach Ollama or ChromaDB in offline CI. RAG route tests
override ``app.state`` directly after TestClient startup (see
tests/rag/conftest.py).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def pytest_configure(config: pytest.Config) -> None:
    """Register the ``live`` marker once for both LLM (Plan 03-01) and RAG (Plan 04-01)."""
    config.addinivalue_line(
        "markers",
        "live: opt-in test against a live host service (Ollama, ChromaDB). "
        "Set RECEPTRA_LLM_LIVE_TEST=1 (LLM) or RECEPTRA_RAG_LIVE_TEST=1 (RAG).",
    )


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


class _BgeM3EmbedderStub:
    """Offline stand-in for BgeM3Embedder — no Ollama connection."""

    @classmethod
    async def create_and_verify(cls) -> _BgeM3EmbedderStub:
        stub = cls()
        stub.embed_one = AsyncMock(return_value=[0.0] * 1024)  # type: ignore[attr-defined]
        stub.embed_batch = AsyncMock(return_value=[[0.0] * 1024])  # type: ignore[attr-defined]
        return stub


def _open_collection_stub() -> MagicMock:
    """Offline stand-in for open_collection — no ChromaDB connection."""
    c = MagicMock(name="chroma.Collection.global_stub")
    c.get.return_value = {"ids": [], "documents": [], "metadatas": [], "distances": []}
    c.count.return_value = 0
    c.query.return_value = {
        "ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]
    }
    return c


@pytest.fixture(autouse=True)
def _stub_heavy_loaders(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Replace WhisperModel + load_silero_vad + RAG singletons before any app import.

    Ensures TestClient's lifespan startup does not try to load real weights
    from ``$MODEL_DIR/whisper-turbo-ct2`` or reach Ollama/ChromaDB during
    offline CI. Individual tests that need richer mocks override these in
    their own monkeypatch scope.
    """
    # Drop any cached import so fresh module-import picks up the stubs.
    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)

    import receptra.lifespan as lifespan_mod

    monkeypatch.setattr(lifespan_mod, "WhisperModel", _WhisperStub)
    monkeypatch.setattr(lifespan_mod, "load_silero_vad", _load_silero_stub)
    monkeypatch.setattr(lifespan_mod, "BgeM3Embedder", _BgeM3EmbedderStub)
    monkeypatch.setattr(lifespan_mod, "open_collection", _open_collection_stub)

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
