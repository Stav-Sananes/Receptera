"""Unit tests for ``receptra.stt.vad.StreamingVad`` (STT-02).

These tests use the REAL Silero VAD model — it is small (~30 MB JIT) and the
TorchScript path loads in well under a second on Apple Silicon. Mocking the
model would not exercise the per-connection state-isolation contract that
Pitfall #2 mandates we regression-guard.

Wire contract under test (RESEARCH §6 + §4.3):

* Frame size: exactly 1024 bytes = 512 int16 LE samples = 32 ms @ 16 kHz.
* Audio path: int16 LE → float32 in [-1.0, 1.0].
* State: each ``StreamingVad`` instance owns its own ``VADIterator``; the
  underlying Silero model is shared (singleton in ``app.state.vad_model``).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from receptra.stt.vad import (
    FRAME_BYTES,
    FRAME_SAMPLES,
    SAMPLE_RATE_HZ,
    InvalidFrameError,
    StreamingVad,
    VadEvent,
)

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def silero_model() -> Any:
    """Load the real Silero VAD model once for the module.

    ``onnx=False`` matches Plan 02-02's lifespan — TorchScript path on Apple
    Silicon avoids onnxruntime arm64 oddities (Pitfall #8).
    """
    from silero_vad import load_silero_vad

    return load_silero_vad(onnx=False)


def _silence_frame() -> bytes:
    """1024 bytes of digital silence (int16 LE all-zeros)."""
    return b"\x00" * FRAME_BYTES


def _voiced_frame(
    n_samples: int = FRAME_SAMPLES,
    sr: int = SAMPLE_RATE_HZ,
    amp: float = 0.7,
    phase: float = 0.0,
) -> bytes:
    """Generate a speech-like int16 LE frame that crosses Silero's threshold.

    Silero VAD is trained on real speech, not pure sine tones. A static
    harmonic stack barely registers (raw prob ~0.1-0.2). What Silero
    actually responds to is the *combination* of pitch wobble (FM),
    syllable-rate amplitude modulation (AM ~5 Hz), a deep harmonic stack
    (8 harmonics), and broadband noise. That mimics the spectral signature
    of voiced speech well enough to drive the model above 0.9 reliably,
    without bundling a recorded WAV asset into the test suite.
    """
    t = np.arange(n_samples, dtype=np.float64) / sr + phase

    # Pitch wobble (~130 Hz mean, ±30 Hz at ~4 Hz vibrato).
    f0 = 130.0 + 30.0 * np.sin(2.0 * np.pi * 4.0 * t)

    # FM-synthesized harmonic stack — instantaneous-phase integration so
    # the harmonics track the wobbling f0 smoothly.
    sig = np.zeros(n_samples, dtype=np.float64)
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

    # Syllable-rate AM envelope (5 Hz).
    sig *= 0.5 + 0.5 * np.sin(2.0 * np.pi * 5.0 * t)

    # Breath / fricative-like broadband noise.
    # Seeded by the integer-rounded phase so identical phases produce identical
    # noise — this keeps the synthesizer stateless and makes test ordering
    # irrelevant (each test's voiced burst sees the same waveform).
    noise_seed = int(phase * sr) & 0xFFFFFFFF
    noise_rng = np.random.default_rng(noise_seed)
    sig += 0.15 * noise_rng.standard_normal(n_samples)

    sig = sig * amp
    pcm = (np.clip(sig, -1.0, 1.0) * 32767).astype("<i2")
    return pcm.tobytes()


def _make_vad(model: Any) -> StreamingVad:
    """Construct a StreamingVad with research-locked defaults."""
    return StreamingVad(
        model=model,
        threshold=0.5,
        min_silence_ms=300,
        speech_pad_ms=200,
    )


# ---------------------------------------------------------------------------
# Test 1 — Frame-size guard (T-02-03-01 mitigation)
# ---------------------------------------------------------------------------


def test_invalid_frame_size_raises(silero_model: Any) -> None:
    """``feed`` rejects any byte length other than exactly 1024."""
    vad = _make_vad(silero_model)

    with pytest.raises(InvalidFrameError, match="1024"):
        vad.feed(b"\x00" * 1000)

    with pytest.raises(InvalidFrameError, match="1024"):
        vad.feed(b"\x00" * 1028)

    with pytest.raises(InvalidFrameError, match="1024"):
        vad.feed(b"")


# ---------------------------------------------------------------------------
# Test 2 — Silence yields no events
# ---------------------------------------------------------------------------


def test_silence_produces_no_event(silero_model: Any) -> None:
    """Pure digital silence MUST never emit a speech-start event."""
    vad = _make_vad(silero_model)

    events: list[VadEvent | None] = [vad.feed(_silence_frame()) for _ in range(10)]

    assert all(e is None for e in events), f"silence emitted events: {events}"


# ---------------------------------------------------------------------------
# Test 3 — Voiced burst yields a speech-start event
# ---------------------------------------------------------------------------


def test_tone_burst_produces_start_event(silero_model: Any) -> None:
    """A voiced (speech-like) burst surfaces at least one ``kind == 'start'`` event."""
    vad = _make_vad(silero_model)

    # 5 silence frames to settle, then up to 30 voiced frames with continuous
    # phase so the harmonic stack stays smooth across frame boundaries
    # (Silero is sensitive to phase discontinuities).
    for _ in range(5):
        vad.feed(_silence_frame())

    saw_start = False
    for i in range(30):
        phase = (i * FRAME_SAMPLES) / SAMPLE_RATE_HZ
        ev = vad.feed(_voiced_frame(phase=phase))
        if ev is not None and ev["kind"] == "start":
            saw_start = True
            assert ev["t_ms"] >= 0
            break

    assert saw_start, "expected at least one 'start' event during voiced burst"


# ---------------------------------------------------------------------------
# Test 4 — Silence after voiced burst yields a speech-end event
# ---------------------------------------------------------------------------


def test_silence_after_tone_produces_end_event(silero_model: Any) -> None:
    """Voiced → silence sequence eventually emits a ``kind == 'end'`` event."""
    vad = _make_vad(silero_model)

    # Drive into active speech.
    for i in range(30):
        phase = (i * FRAME_SAMPLES) / SAMPLE_RATE_HZ
        vad.feed(_voiced_frame(phase=phase))

    # Then >300 ms of silence (min_silence_ms) — feed enough frames that the
    # speech-end timer is guaranteed to fire. 32 ms/frame * 40 = 1.28 s.
    saw_end = False
    for _ in range(40):
        ev = vad.feed(_silence_frame())
        if ev is not None and ev["kind"] == "end":
            saw_end = True
            assert ev["t_ms"] > 0
            break

    assert saw_end, "expected at least one 'end' event after silence trailer"


# ---------------------------------------------------------------------------
# Test 5 — Per-connection state isolation (T-02-03-02 mitigation, Pitfall #2)
# ---------------------------------------------------------------------------


def test_two_instances_have_independent_state(silero_model: Any) -> None:
    """Instance A's speech state MUST NOT leak into instance B.

    Construct TWO ``StreamingVad`` wrappers around the SAME shared Silero
    model. Drive A through a voiced burst (A enters active-speech mode).
    Then feed silence to B. B was never in active speech → must NOT emit
    'end'.
    """
    vad_a = _make_vad(silero_model)
    vad_b = _make_vad(silero_model)

    # Push A into active speech.
    for i in range(20):
        phase = (i * FRAME_SAMPLES) / SAMPLE_RATE_HZ
        vad_a.feed(_voiced_frame(phase=phase))

    # B has only ever seen silence (which we are about to feed it). If state
    # leaked from A → B via a shared VADIterator, the next 40 silence frames
    # would trigger B to fire a spurious 'end'.
    b_events = [vad_b.feed(_silence_frame()) for _ in range(40)]

    assert all(e is None for e in b_events), (
        f"instance B leaked state from instance A: events={b_events}"
    )


# ---------------------------------------------------------------------------
# Test 6 — reset() clears per-session state
# ---------------------------------------------------------------------------


def test_reset_clears_state(silero_model: Any) -> None:
    """Calling ``reset()`` returns the wrapper to a clean (no-active-speech) state."""
    vad = _make_vad(silero_model)

    # Drive into active speech.
    for i in range(20):
        phase = (i * FRAME_SAMPLES) / SAMPLE_RATE_HZ
        vad.feed(_voiced_frame(phase=phase))

    vad.reset()

    # Post-reset, silence MUST NOT trigger an 'end' event — the iterator no
    # longer believes we are inside active speech.
    post_reset_events = [vad.feed(_silence_frame()) for _ in range(40)]

    assert all(e is None for e in post_reset_events), (
        f"reset() did not clear active-speech state: events={post_reset_events}"
    )


# ---------------------------------------------------------------------------
# Test 7 — Byte-order contract is documented (not enforced inside the wrapper)
# ---------------------------------------------------------------------------


def test_int16_le_byte_order_enforced(silero_model: Any) -> None:
    """Big-endian int16 frames decode as garbled float32 but MUST NOT raise.

    Byte-order validation lives at the wire layer (Plan 02-04's WebSocket
    protocol check), not inside StreamingVad. This test makes the contract
    explicit: feeding a 1024-byte BE frame is silently mis-decoded — the
    wrapper never raises and never crashes.
    """
    vad = _make_vad(silero_model)

    # Deliberately build a frame with the WRONG byte order.
    samples = (np.linspace(-0.5, 0.5, FRAME_SAMPLES) * 32767).astype(">i2")
    be_frame = samples.tobytes()
    assert len(be_frame) == FRAME_BYTES

    # Should return either None or a VadEvent — anything is fine, just don't
    # crash. The behavior is permitted to vary across silero-vad versions.
    result = vad.feed(be_frame)
    assert result is None or result["kind"] in {"start", "end"}
