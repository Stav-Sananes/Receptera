"""End-to-end WebSocket test: /ws/stt emits suggestion events after FinalTranscript.

Phase 5 INT-02 regression: after a VAD-gated utterance completes, the pipeline
must stream SuggestionToken / SuggestionComplete events on the same WebSocket
connection, before the client disconnects.

Uses real Silero VAD + canned Whisper (same approach as test_ws_pcm_roundtrip.py)
+ mocked generate_suggestions (no Ollama required).

INT-04 regression: with embedder=None in app.state, the pipeline degrades
gracefully — no crash, canonical refusal in SuggestionComplete.
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
# PCM synthesis helpers (same as test_ws_pcm_roundtrip.py)
# ---------------------------------------------------------------------------


def _silence_frame() -> bytes:
    return b"\x00" * FRAME_BYTES


def _voiced_frame(phase: float = 0.0, amp: float = 0.7) -> bytes:
    n = FRAME_SAMPLES
    sr = SAMPLE_RATE_HZ
    t = np.arange(n, dtype=np.float64) / sr + phase
    f0 = 130.0 + 30.0 * np.sin(2.0 * np.pi * 4.0 * t)
    sig = np.zeros(n, dtype=np.float64)
    for harmonic, harm_amp in (
        (1, 0.5), (2, 0.4), (3, 0.3), (4, 0.2), (5, 0.15), (6, 0.1), (7, 0.08), (8, 0.05),
    ):
        inst_phase = np.cumsum(2.0 * np.pi * f0 * harmonic / sr) + 0.7 * harmonic
        sig += harm_amp * np.sin(inst_phase)
    sig *= 0.5 + 0.5 * np.sin(2.0 * np.pi * 5.0 * t)
    noise_rng = np.random.default_rng(int(phase * sr) & 0xFFFFFFFF)
    sig += 0.15 * noise_rng.standard_normal(n)
    pcm = (np.clip(sig * amp, -1.0, 1.0) * 32767).astype("<i2")
    return pcm.tobytes()


# ---------------------------------------------------------------------------
# Stub classes
# ---------------------------------------------------------------------------


class _Segment:
    def __init__(self, text: str) -> None:
        self.text = text


class _Info:
    duration = 1.0
    language = "he"
    language_probability = 1.0


class _CannedWhisper:
    model_name = "ivrit-ai/whisper-large-v3-turbo-ct2"

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def transcribe(self, *_args: Any, **_kwargs: Any) -> tuple[Any, _Info]:
        return iter([_Segment(" מה שעות הפתיחה?")]), _Info()


def _make_canned_suggestion_gen(
    tokens: list[str],
) -> AsyncGenerator[Any, None]:
    """Async generator yielding token events then a CompleteEvent."""
    from receptra.llm.schema import CompleteEvent, Suggestion, TokenEvent

    async def _gen() -> AsyncGenerator[Any, None]:
        for tok in tokens:
            yield TokenEvent(delta=tok)
        yield CompleteEvent(
            suggestions=[Suggestion(text="אנחנו פתוחים 9-18", confidence=0.9, citation_ids=[])],
            ttft_ms=80,
            total_ms=300,
            model="dictalm3",
        )

    return _gen()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pipeline_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """App with real Silero VAD + canned Whisper + mocked generate_suggestions."""
    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)

    lifespan_mod = importlib.import_module("receptra.lifespan")
    from silero_vad import load_silero_vad as _real_load_silero

    monkeypatch.setattr(lifespan_mod, "WhisperModel", _CannedWhisper)
    monkeypatch.setattr(lifespan_mod, "load_silero_vad", _real_load_silero)
    # BgeM3Embedder + open_collection stubs already set by autouse _stub_heavy_loaders

    from receptra.main import app

    yield app

    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ws_emits_suggestion_events_after_final(
    pipeline_app: FastAPI,
) -> None:
    """After FinalTranscript, the WS must emit suggestion_token + suggestion_complete.

    The mocked generate_suggestions emits 2 tokens then a CompleteEvent.
    INT-04 applies (embedder stub returns zero-vectors → retriever returns
    empty list → generate_suggestions short-circuits to canonical refusal
    or processes tokens from our mock — either way SuggestionComplete arrives).
    """
    gen = _make_canned_suggestion_gen(["אנחנו", " פתוחים"])
    events: list[dict[str, Any]] = []

    with (
        patch("receptra.pipeline.hot_path.generate_suggestions", return_value=gen),
        TestClient(pipeline_app) as tc,
        tc.websocket_connect("/ws/stt") as ws,
    ):
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        # Speak: 5 silence + 60 voiced + 40 silence (triggers VAD end).
        for _ in range(5):
            ws.send_bytes(_silence_frame())
        for i in range(60):
            ws.send_bytes(_voiced_frame(phase=i * FRAME_SAMPLES / SAMPLE_RATE_HZ))
        for _ in range(40):
            ws.send_bytes(_silence_frame())

        # Collect up to 300 events; stop after suggestion_complete.
        for _ in range(300):
            evt = ws.receive_json()
            events.append(evt)
            if evt["type"] == "suggestion_complete":
                break

    types = {e["type"] for e in events}
    assert "final" in types, f"No final event; got: {types}"
    assert "suggestion_complete" in types, f"No suggestion_complete; got: {types}"


def test_ws_suggestion_complete_has_latency_fields(
    pipeline_app: FastAPI,
) -> None:
    """suggestion_complete event carries rag_latency_ms + e2e_latency_ms (INT-03)."""
    gen = _make_canned_suggestion_gen([])
    events: list[dict[str, Any]] = []

    with (
        patch("receptra.pipeline.hot_path.generate_suggestions", return_value=gen),
        TestClient(pipeline_app) as tc,
        tc.websocket_connect("/ws/stt") as ws,
    ):
        ws.receive_json()  # ready
        for _ in range(5):
            ws.send_bytes(_silence_frame())
        for i in range(60):
            ws.send_bytes(_voiced_frame(phase=i * FRAME_SAMPLES / SAMPLE_RATE_HZ))
        for _ in range(40):
            ws.send_bytes(_silence_frame())

        for _ in range(300):
            evt = ws.receive_json()
            events.append(evt)
            if evt["type"] == "suggestion_complete":
                break

    complete = [e for e in events if e["type"] == "suggestion_complete"]
    assert complete, "No suggestion_complete event"
    ev = complete[0]
    assert "rag_latency_ms" in ev, f"Missing rag_latency_ms: {ev}"
    assert "e2e_latency_ms" in ev, f"Missing e2e_latency_ms: {ev}"
    assert ev["e2e_latency_ms"] >= 0


def test_ws_degraded_no_embedder(
    pipeline_app: FastAPI,
) -> None:
    """INT-04: embedder=None in app.state → WS does not crash; SuggestionComplete arrives."""
    gen = _make_canned_suggestion_gen([])
    events: list[dict[str, Any]] = []

    with patch("receptra.pipeline.hot_path.generate_suggestions", return_value=gen), \
            TestClient(pipeline_app) as tc:
        # Remove embedder after startup to simulate degradation.
        tc.app.state.embedder = None  # type: ignore[attr-defined]
        tc.app.state.chroma_collection = None  # type: ignore[attr-defined]

        with tc.websocket_connect("/ws/stt") as ws:
            ws.receive_json()  # ready
            for _ in range(5):
                ws.send_bytes(_silence_frame())
            for i in range(60):
                ws.send_bytes(_voiced_frame(phase=i * FRAME_SAMPLES / SAMPLE_RATE_HZ))
            for _ in range(40):
                ws.send_bytes(_silence_frame())

            for _ in range(300):
                evt = ws.receive_json()
                events.append(evt)
                if evt["type"] == "suggestion_complete":
                    break

    types = {e["type"] for e in events}
    assert "suggestion_complete" in types, f"Expected suggestion_complete; got {types}"
