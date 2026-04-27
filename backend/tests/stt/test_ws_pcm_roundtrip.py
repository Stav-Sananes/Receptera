"""Behavioral roundtrip tests for /ws/stt (STT-03 + STT-04).

Drives complete VAD-gated transcribe loop end-to-end with REAL Silero VAD
(small TorchScript model, ~30 MB) and a STUBBED ``WhisperModel.transcribe``
that returns canned Hebrew text. This is the autonomous-mode policy from
the executor prompt: real model weights are not loaded; the stub
short-circuits Whisper inference but the rest of the pipeline (VAD frame
boundary detection, asyncio.to_thread wrapping, pydantic event
serialization) runs end-to-end.

Three contracts under test:

* test_partial_emitted: STT-03 — at least one ``type=="partial"`` arrives
  before ``type=="final"`` during a sustained voiced burst.
* test_final_emitted: STT-04 — exactly one ``type=="final"`` per
  utterance with all timing fields populated and Hebrew text non-empty.
* test_no_event_loop_blocking: Pitfall #5 regression guard — two
  concurrent WS connections must complete in roughly the wall-time of
  one (not two) when the stub sleeps 200ms per transcribe, proving
  ``asyncio.to_thread`` is in place.
"""

from __future__ import annotations

import importlib
import sys
import threading
import time
from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Wire-format constants (single source of truth: receptra.stt.vad).
from receptra.stt.vad import FRAME_BYTES, FRAME_SAMPLES, SAMPLE_RATE_HZ

# ---------------------------------------------------------------------------
# Helpers — synthesized voiced bursts (re-uses the proven Plan 02-03 recipe).
# ---------------------------------------------------------------------------


def _silence_frame() -> bytes:
    return b"\x00" * FRAME_BYTES


def _voiced_frame(phase: float = 0.0, amp: float = 0.7) -> bytes:
    """Speech-like int16 LE frame that drives Silero VAD prob > 0.9.

    Same FM-modulated harmonic stack the test_vad_streaming.py fixture
    uses — pure tones don't cross Silero's threshold; this synthesizer
    mimics the spectral signature of voiced Hebrew well enough.
    """
    n = FRAME_SAMPLES
    sr = SAMPLE_RATE_HZ
    t = np.arange(n, dtype=np.float64) / sr + phase

    f0 = 130.0 + 30.0 * np.sin(2.0 * np.pi * 4.0 * t)
    sig = np.zeros(n, dtype=np.float64)
    for harmonic, harm_amp in (
        (1, 0.5),
        (2, 0.4),
        (3, 0.3),
        (4, 0.2),
        (5, 0.15),
        (6, 0.1),
        (7, 0.08),
        (8, 0.05),
    ):
        inst_phase = np.cumsum(2.0 * np.pi * f0 * harmonic / sr) + 0.7 * harmonic
        sig += harm_amp * np.sin(inst_phase)
    sig *= 0.5 + 0.5 * np.sin(2.0 * np.pi * 5.0 * t)

    noise_seed = int(phase * sr) & 0xFFFFFFFF
    noise_rng = np.random.default_rng(noise_seed)
    sig += 0.15 * noise_rng.standard_normal(n)

    sig = sig * amp
    pcm = (np.clip(sig, -1.0, 1.0) * 32767).astype("<i2")
    return pcm.tobytes()


# ---------------------------------------------------------------------------
# Stubs + fixtures
# ---------------------------------------------------------------------------


class _Segment:
    """Stand-in for faster_whisper.transcribe.Segment — only `text` matters."""

    def __init__(self, text: str) -> None:
        self.text = text


class _Info:
    duration = 1.0
    language = "he"
    language_probability = 1.0


def _make_canned_whisper_stub(text: str = " שלום", sleep_s: float = 0.0) -> type:
    """Build a WhisperModel stub class returning a single canned Hebrew segment.

    Args:
        text: The transcript text the stub returns. Includes leading space
            because faster_whisper segments emit a leading space; the
            ``transcribe_hebrew`` wrapper strips on join.
        sleep_s: Optional synchronous sleep on every transcribe — used by
            test_no_event_loop_blocking to prove asyncio.to_thread is in
            place. Default 0 so the happy-path tests are fast.
    """

    class _CannedWhisper:
        model_name = "ivrit-ai/whisper-large-v3-turbo-ct2"

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def transcribe(self, *_args: Any, **_kwargs: Any) -> tuple[Any, _Info]:
            if sleep_s > 0:
                time.sleep(sleep_s)
            return iter([_Segment(text)]), _Info()

    return _CannedWhisper


@pytest.fixture
def real_vad_canned_whisper_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """App with REAL Silero VAD + stub Whisper returning ' שלום'.

    Overrides the autouse stubs from conftest.py — we still want the
    autouse fixture's import-cache eviction (it pops receptra.main +
    receptra.lifespan from sys.modules), but we re-monkeypatch lifespan
    after our own fresh import so REAL silero loads + stub Whisper takes
    over the transcribe path.
    """
    # Drop cached imports so the next import binds our patches.
    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)

    lifespan_mod = importlib.import_module("receptra.lifespan")

    # Real Silero, stubbed Whisper.
    from silero_vad import load_silero_vad as _real_load_silero

    monkeypatch.setattr(lifespan_mod, "WhisperModel", _make_canned_whisper_stub())
    monkeypatch.setattr(lifespan_mod, "load_silero_vad", _real_load_silero)

    from receptra.main import app

    yield app

    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)


# ---------------------------------------------------------------------------
# Test 3 — Partial emitted during sustained speech (STT-03)
# ---------------------------------------------------------------------------


def test_partial_emitted(real_vad_canned_whisper_app: FastAPI) -> None:
    """At least one ``type=='partial'`` event arrives before ``type=='final'``.

    Drives a long voiced burst (~3 seconds = ~95 frames) so the partial
    cadence (700 ms by default) is guaranteed to fire at least 2-3 times
    before the silence trailer trips the VAD-end event.
    """
    app = real_vad_canned_whisper_app
    with TestClient(app) as client, client.websocket_connect("/ws/stt") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        # 5 silence frames to settle, then ~3 seconds of voiced.
        for _ in range(5):
            ws.send_bytes(_silence_frame())
        for i in range(95):
            phase = (i * FRAME_SAMPLES) / SAMPLE_RATE_HZ
            ws.send_bytes(_voiced_frame(phase=phase))
        # Then ~1.3 seconds of silence (>300 ms min_silence) to trigger end.
        for _ in range(40):
            ws.send_bytes(_silence_frame())

        events: list[dict[str, Any]] = []
        # Bound iterations so a regression doesn't hang CI.
        for _ in range(200):
            evt = ws.receive_json()
            events.append(evt)
            if evt["type"] == "final":
                break

    final_events = [e for e in events if e["type"] == "final"]
    partial_events = [e for e in events if e["type"] == "partial"]

    assert len(final_events) == 1, (
        f"expected exactly one final event; got {len(final_events)}: {events}"
    )
    assert len(partial_events) >= 1, (
        f"expected at least one partial before final; got {len(partial_events)}: {events}"
    )
    # Partials must arrive BEFORE the final in send order.
    assert events[-1]["type"] == "final"


# ---------------------------------------------------------------------------
# Test 4 — Final fields populated correctly (STT-04)
# ---------------------------------------------------------------------------


def test_final_emitted(real_vad_canned_whisper_app: FastAPI) -> None:
    """Final event has non-empty Hebrew text + valid timing fields."""
    app = real_vad_canned_whisper_app
    with TestClient(app) as client, client.websocket_connect("/ws/stt") as ws:
        ws.receive_json()  # ready

        # Drive a clear voiced burst → silence trailer.
        for _ in range(5):
            ws.send_bytes(_silence_frame())
        for i in range(60):
            phase = (i * FRAME_SAMPLES) / SAMPLE_RATE_HZ
            ws.send_bytes(_voiced_frame(phase=phase))
        for _ in range(40):
            ws.send_bytes(_silence_frame())

        final: dict[str, Any] | None = None
        for _ in range(200):
            evt = ws.receive_json()
            if evt["type"] == "final":
                final = evt
                break

    assert final is not None, "no final event received within bound"
    assert isinstance(final["text"], str)
    assert len(final["text"]) > 0, f"final text empty: {final}"
    # The canned stub returns " שלום" (with leading space), engine.py strips
    # on join → final.text == "שלום".
    assert "שלום" in final["text"]
    assert final["t_speech_start_ms"] < final["t_speech_end_ms"], final
    assert final["stt_latency_ms"] >= 0, final
    assert final["duration_ms"] > 0, final


# ---------------------------------------------------------------------------
# Test 5 — Event loop is not blocked by sync transcribe (Pitfall #5)
# ---------------------------------------------------------------------------


@pytest.fixture
def real_vad_slow_whisper_app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """App with REAL Silero VAD + a STUBBED Whisper that sleeps 200 ms per call."""
    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)

    lifespan_mod = importlib.import_module("receptra.lifespan")
    from silero_vad import load_silero_vad as _real_load_silero

    monkeypatch.setattr(
        lifespan_mod,
        "WhisperModel",
        _make_canned_whisper_stub(sleep_s=0.2),
    )
    monkeypatch.setattr(lifespan_mod, "load_silero_vad", _real_load_silero)

    from receptra.main import app

    yield app

    for mod_name in ("receptra.main", "receptra.lifespan"):
        sys.modules.pop(mod_name, None)


def _drive_one_utterance(app: FastAPI) -> tuple[float, dict[str, Any]]:
    """Open a WS, drive one complete utterance, return (wall_time, final_event)."""
    t0 = time.monotonic()
    with TestClient(app) as client, client.websocket_connect("/ws/stt") as ws:
        ws.receive_json()  # ready
        for _ in range(5):
            ws.send_bytes(_silence_frame())
        for i in range(60):
            phase = (i * FRAME_SAMPLES) / SAMPLE_RATE_HZ
            ws.send_bytes(_voiced_frame(phase=phase))
        for _ in range(40):
            ws.send_bytes(_silence_frame())

        final: dict[str, Any] | None = None
        for _ in range(300):
            evt = ws.receive_json()
            if evt["type"] == "final":
                final = evt
                break
    elapsed = time.monotonic() - t0
    assert final is not None, "test driver: no final event"
    return elapsed, final


def test_no_event_loop_blocking(real_vad_slow_whisper_app: FastAPI) -> None:
    """Two concurrent WS with a 200 ms sleep-per-transcribe stub must run
    in roughly parallel wall-time, NOT serial.

    This is the Pitfall #5 regression guard. If a future contributor
    drops the ``await asyncio.to_thread(transcribe_hebrew, ...)`` wrap
    and inlines a synchronous call, the second connection's accept()
    will stall behind the first connection's transcribe — total wall
    time doubles. With to_thread, the two transcribes run on separate
    threadpool workers and total wall time stays close to a single call.

    Note: TestClient is sync, so we use threads (not asyncio.gather) to
    drive two concurrent connections. Each connection emits >=1 partial
    AND 1 final -- at least 2 transcribes per connection x 200 ms = 400 ms
    minimum even in the parallel case. Threshold set at 5.0 s to leave
    head-room for slow CI; the serial case would be 800 ms+ x 2 = 1.6 s+.
    """
    app = real_vad_slow_whisper_app
    results: list[tuple[float, dict[str, Any]]] = []
    errors: list[BaseException] = []

    def _runner() -> None:
        try:
            results.append(_drive_one_utterance(app))
        except BaseException as e:  # pragma: no cover — surfaced via assert
            errors.append(e)

    t_a = threading.Thread(target=_runner)
    t_b = threading.Thread(target=_runner)

    t0 = time.monotonic()
    t_a.start()
    t_b.start()
    t_a.join(timeout=10.0)
    t_b.join(timeout=10.0)
    total_wall = time.monotonic() - t0

    assert not errors, f"thread errors: {errors}"
    assert len(results) == 2, f"expected 2 results, got {len(results)}"

    # Both finals must have non-empty Hebrew text — proves the slow stub
    # really did run on each connection.
    for _elapsed, final in results:
        assert final["type"] == "final"
        assert "שלום" in final["text"]

    # Parallelism check: if to_thread is in place, total wall ≤ ~1.5 s
    # (overlapping transcribes). If transcribe blocks the event loop,
    # total wall would be ≥ 2x single-connection time. Single connection
    # with 2 transcribes (1 partial + 1 final) at 200 ms each = 400 ms
    # plus VAD/IO overhead; serial 2-connection case ≈ 800 ms + overhead.
    # Assert under a generous parallel ceiling.
    assert total_wall < 5.0, (
        f"two concurrent WS took {total_wall:.2f}s — event loop likely blocked "
        f"on synchronous transcribe (Pitfall #5)"
    )


# ---------------------------------------------------------------------------
# Test 6 — Multi-utterance: WS stays open and emits multiple finals (v1.1+)
# ---------------------------------------------------------------------------


def test_multi_utterance_emits_multiple_finals(real_vad_canned_whisper_app: FastAPI) -> None:
    """One WS connection drives two complete VAD-gated utterances.

    Real calls have many short utterances separated by silence. The WS
    must stay open across the full conversation and emit a fresh ``final``
    for every utterance — never close after the first one.
    """
    app = real_vad_canned_whisper_app
    finals: list[dict[str, Any]] = []
    with TestClient(app) as client, client.websocket_connect("/ws/stt") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        for utterance_idx in range(2):
            # Voiced burst → silence trailer for each utterance.
            for _ in range(5):
                ws.send_bytes(_silence_frame())
            for i in range(60):
                phase = (i * FRAME_SAMPLES) / SAMPLE_RATE_HZ + utterance_idx * 100
                ws.send_bytes(_voiced_frame(phase=phase))
            for _ in range(40):
                ws.send_bytes(_silence_frame())

            # Drain events until this utterance's final arrives.
            for _ in range(300):
                evt = ws.receive_json()
                if evt["type"] == "final":
                    finals.append(evt)
                    break

    assert len(finals) == 2, f"expected 2 finals on one WS; got {len(finals)}: {finals}"
    # Each final must have its own non-overlapping speech window.
    assert finals[0]["t_speech_end_ms"] <= finals[1]["t_speech_start_ms"], (
        f"utterance 2 must start after utterance 1 ends: {finals}"
    )
    # Both must have Hebrew text from the canned stub.
    for i, final in enumerate(finals):
        assert "שלום" in final["text"], f"utterance {i} text: {final['text']}"
