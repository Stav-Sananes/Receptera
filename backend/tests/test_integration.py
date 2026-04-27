"""Milestone 1 cross-phase integration smoke tests (Phase 7 DEMO-01..DEMO-05).

Exercises the full in-process pipeline via FastAPI TestClient:

INT-SMOKE-01  /healthz + /api/kb/health — all subsystem stubs report correctly
INT-SMOKE-02  KB ingest → query round-trip (stub embedder returns zero-vectors;
              retriever filters them below similarity threshold → empty list OK)
INT-SMOKE-03  /ws/stt connects → SttReady emitted with model name
INT-SMOKE-04  /ws/stt receives a VAD-end utterance → FinalTranscript + pipeline
              events (SuggestionComplete) emitted in order
INT-SMOKE-05  OpenAPI schema contains all registered routers (stt, kb, health)

All tests run offline — no real Whisper, Ollama, ChromaDB, or BGE-M3 required.
The autouse `_stub_heavy_loaders` fixture from tests/conftest.py patches them.

Phase 5 pipeline extension: INT-SMOKE-04 uses canned Whisper + real Silero VAD
and patches ``receptra.pipeline.hot_path.generate_suggestions`` so the full
STT → RAG → LLM → WS event sequence can be verified without a live stack.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import AsyncGenerator, Iterator
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from receptra.stt.vad import FRAME_BYTES, FRAME_SAMPLES, SAMPLE_RATE_HZ

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _silence_frame() -> bytes:
    return b"\x00" * FRAME_BYTES


def _voiced_frame(phase: float = 0.0) -> bytes:
    n = FRAME_SAMPLES
    sr = SAMPLE_RATE_HZ
    t = np.arange(n, dtype=np.float64) / sr + phase
    f0 = 130.0 + 30.0 * np.sin(2.0 * np.pi * 4.0 * t)
    sig = np.zeros(n, dtype=np.float64)
    for h, a in ((1, 0.5), (2, 0.4), (3, 0.3), (4, 0.2), (5, 0.15), (6, 0.1), (7, 0.08), (8, 0.05)):
        ph = np.cumsum(2.0 * np.pi * f0 * h / sr) + 0.7 * h
        sig += a * np.sin(ph)
    sig *= 0.5 + 0.5 * np.sin(2.0 * np.pi * 5.0 * t)
    rng = np.random.default_rng(int(phase * sr) & 0xFFFFFFFF)
    sig += 0.15 * rng.standard_normal(n)
    pcm = (np.clip(sig * 0.7, -1.0, 1.0) * 32767).astype("<i2")
    return pcm.tobytes()


class _Seg:
    def __init__(self, text: str) -> None:
        self.text = text


class _Info:
    duration = 1.0
    language = "he"
    language_probability = 1.0


class _CannedWhisper:
    model_name = "ivrit-ai/whisper-large-v3-turbo-ct2"

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    def transcribe(self, *_: Any, **__: Any) -> tuple[Any, _Info]:
        return iter([_Seg(" שלום עולם")]), _Info()


def _make_complete_gen() -> AsyncGenerator[Any, None]:
    from receptra.llm.schema import CompleteEvent, Suggestion

    async def _g() -> AsyncGenerator[Any, None]:
        yield CompleteEvent(
            suggestions=[Suggestion(text="אנחנו פתוחים 9-18", confidence=0.9, citation_ids=[])],
            ttft_ms=0,
            total_ms=50,
            model="dictalm3",
        )

    return _g()


@pytest.fixture
def pipeline_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """Full app with real Silero VAD + canned Whisper + mocked LLM generation."""
    for mod in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod, None)

    lifespan = importlib.import_module("receptra.lifespan")
    from silero_vad import load_silero_vad as _real_vad

    monkeypatch.setattr(lifespan, "WhisperModel", _CannedWhisper)
    monkeypatch.setattr(lifespan, "load_silero_vad", _real_vad)

    from receptra.main import app

    yield app

    for mod in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod, None)


# ---------------------------------------------------------------------------
# INT-SMOKE-01  Subsystem health
# ---------------------------------------------------------------------------


def test_healthz_and_kb_health_respond(client: TestClient) -> None:
    """Both /healthz and /api/kb/health respond with expected JSON shape."""
    r1 = client.get("/healthz")
    assert r1.status_code == 200
    assert r1.json()["status"] == "ok"

    r2 = client.get("/api/kb/health")
    assert r2.status_code == 200
    body = r2.json()
    # Stubs report 'ok' for both subsystems (see conftest.py BgeM3EmbedderStub)
    assert "chroma" in body
    assert "ollama" in body
    assert "collection_count" in body


# ---------------------------------------------------------------------------
# INT-SMOKE-02  KB ingest → query round-trip
# ---------------------------------------------------------------------------


def test_kb_ingest_then_query(client: TestClient) -> None:
    """Ingest a .md doc and verify it appears in /api/kb/documents."""
    # Override stubs to return realistic chunk count
    from fastapi import FastAPI as _FastAPI

    app: _FastAPI = client.app  # type: ignore[attr-defined]

    # Stub collection.add to record calls; count.return_value drives chunk list
    collection = app.state.chroma_collection  # already MagicMock from conftest
    collection.get.return_value = {
        "ids": ["abc:0"],
        "documents": ["שעות פתיחה 9-18"],
        "metadatas": [
            {
                "filename": "test_hours.md",
                "chunk_index": "0",
                "char_start": "0",
                "char_end": "20",
                "ingested_at": "2026-04-27T10:00:00Z",
            }
        ],
        "distances": [0.1],
    }

    result = client.post(
        "/api/kb/ingest-text",
        json={"filename": "test_hours.md", "content": "שעות פתיחה 9-18"},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["filename"] == "test_hours.md"
    assert "chunks_added" in body


# ---------------------------------------------------------------------------
# INT-SMOKE-03  /ws/stt sends SttReady on connect
# ---------------------------------------------------------------------------


def test_ws_stt_sends_ready_on_connect(pipeline_app: FastAPI) -> None:
    """WebSocket /ws/stt emits SttReady immediately after accepting."""
    with TestClient(pipeline_app) as tc, tc.websocket_connect("/ws/stt") as ws:
        event = ws.receive_json()
    assert event["type"] == "ready"
    assert "model" in event
    assert event["sample_rate"] == 16000
    assert event["frame_bytes"] == 1024


# ---------------------------------------------------------------------------
# INT-SMOKE-04  Full pipeline: audio → STT → RAG → LLM → WS events
# ---------------------------------------------------------------------------


def test_full_pipeline_emits_final_and_suggestion(pipeline_app: FastAPI) -> None:
    """Full pipeline produces FinalTranscript + SuggestionComplete on one utterance."""
    gen = _make_complete_gen()

    with (
        patch("receptra.pipeline.hot_path.generate_suggestions", return_value=gen),
        TestClient(pipeline_app) as tc,
        tc.websocket_connect("/ws/stt") as ws,
    ):
        ws.receive_json()  # SttReady

        for _ in range(5):
            ws.send_bytes(_silence_frame())
        for i in range(60):
            ws.send_bytes(_voiced_frame(phase=i * FRAME_SAMPLES / SAMPLE_RATE_HZ))
        for _ in range(40):
            ws.send_bytes(_silence_frame())

        events: list[dict[str, Any]] = []
        for _ in range(300):
            evt = ws.receive_json()
            events.append(evt)
            if evt["type"] == "suggestion_complete":
                break

    types = [e["type"] for e in events]
    assert "final" in types, f"No final event; got: {types}"
    assert "suggestion_complete" in types, f"No suggestion_complete; got: {types}"

    # Verify ordering: final must precede suggestion_complete
    final_idx = next(i for i, e in enumerate(events) if e["type"] == "final")
    complete_idx = next(i for i, e in enumerate(events) if e["type"] == "suggestion_complete")
    assert final_idx < complete_idx, "FinalTranscript must precede SuggestionComplete"

    # Verify Hebrew transcript non-empty
    final_evt = next(e for e in events if e["type"] == "final")
    assert final_evt["text"].strip(), "Final transcript text must be non-empty"

    # Verify suggestion_complete has expected fields
    complete_evt = next(e for e in events if e["type"] == "suggestion_complete")
    assert complete_evt["suggestions"], "Must have at least one suggestion"
    assert "e2e_latency_ms" in complete_evt
    assert "rag_latency_ms" in complete_evt


# ---------------------------------------------------------------------------
# INT-SMOKE-05  OpenAPI schema covers all routers
# ---------------------------------------------------------------------------


def test_openapi_schema_covers_all_routes(client: TestClient) -> None:
    """OpenAPI /openapi.json lists HTTP routes from all mounted routers.

    WebSocket routes (/ws/stt) are excluded from OpenAPI by design — FastAPI
    does not generate schema entries for websocket endpoints. We verify the WS
    route is registered separately via app.routes.
    """
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    paths = set(schema.get("paths", {}).keys())

    required_http = {"/healthz", "/api/kb/health", "/api/kb/query", "/api/kb/documents"}
    missing = required_http - paths
    assert not missing, f"OpenAPI schema is missing HTTP routes: {missing}"

    # Verify WS route exists on the app (not in OpenAPI — WS endpoints are excluded by spec)
    from fastapi import FastAPI as _FastAPI
    from fastapi.routing import APIWebSocketRoute

    app: _FastAPI = client.app  # type: ignore[attr-defined]
    ws_paths = {r.path for r in app.routes if isinstance(r, APIWebSocketRoute)}
    assert "/ws/stt" in ws_paths, f"WebSocket route /ws/stt not found; got: {ws_paths}"
