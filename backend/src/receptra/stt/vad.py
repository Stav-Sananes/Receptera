"""Per-connection Silero VAD wrapper for streaming STT (STT-02).

Pitfall #2 mitigation: each WebSocket connection constructs its own
``StreamingVad`` instance wrapping the SHARED Silero model singleton loaded
at app startup (Plan 02-02 lifespan, ``app.state.vad_model``). The
``VADIterator`` carries per-session state — sharing it across connections
corrupts segmentation boundaries (one user's "end-of-speech" leaks into
another user's stream).

Wire contract (RESEARCH §6 + §4.3):

* Frame = 512 int16 LE samples = 1024 bytes = 32 ms at 16 kHz.
* Silero v5+ mandates the 512-sample window EXACTLY — arbitrary sizes are
  no longer supported.
* Audio MUST be float32 in ``[-1.0, 1.0]`` and mono.
* The model is stateful — call ``reset()`` between independent sessions.

Constants exported for Plan 02-04 (WebSocket handler) so it can validate
incoming frames against the same wire-format contract:

* ``FRAME_BYTES`` — 1024
* ``FRAME_SAMPLES`` — 512
* ``SAMPLE_RATE_HZ`` — 16000
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

import numpy as np
from silero_vad import VADIterator

FRAME_BYTES = 1024
FRAME_SAMPLES = 512  # Silero v5+ mandatory window at 16 kHz.
SAMPLE_RATE_HZ = 16000
INT16_MAX = 32768.0


class InvalidFrameError(ValueError):
    """Raised when a PCM frame does not match the wire contract.

    Plan 02-04's WebSocket handler converts this to a
    ``{"type": "error", "code": "protocol_error"}`` envelope and closes the
    connection (T-02-03-01 mitigation, ASVS V5 input validation).
    """


class VadEvent(TypedDict):
    """Speech-boundary event emitted by ``StreamingVad.feed``.

    ``t_ms`` is the timestamp of the boundary in milliseconds since the
    iterator was constructed (or last reset). ``kind`` is ``"start"`` for
    speech-start and ``"end"`` for speech-end.
    """

    kind: Literal["start", "end"]
    t_ms: int


class StreamingVad:
    """Per-connection Silero VAD iterator wrapping a shared model.

    Usage (in Plan 02-04 WebSocket handler)::

        vad = StreamingVad(
            model=app.state.vad_model,
            threshold=settings.vad_threshold,
            min_silence_ms=settings.vad_min_silence_ms,
            speech_pad_ms=settings.vad_speech_pad_ms,
        )
        event = vad.feed(binary_ws_frame)   # 1024 bytes
        if event and event["kind"] == "start":
            ...
        vad.reset()  # on WebSocket close or new utterance cycle
    """

    def __init__(
        self,
        model: Any,
        threshold: float,
        min_silence_ms: int,
        speech_pad_ms: int,
    ) -> None:
        self._iter = VADIterator(
            model,
            threshold=threshold,
            sampling_rate=SAMPLE_RATE_HZ,
            min_silence_duration_ms=min_silence_ms,
            speech_pad_ms=speech_pad_ms,
        )
        # Defensive reset — even though VADIterator constructs fresh state,
        # explicit reset documents the per-connection isolation contract.
        self._iter.reset_states()

    def feed(self, frame_bytes: bytes) -> VadEvent | None:
        """Consume one 1024-byte int16 LE frame; return event or ``None``.

        Args:
            frame_bytes: Exactly ``FRAME_BYTES`` (1024) bytes of int16
                little-endian PCM = 512 samples = 32 ms at 16 kHz.

        Returns:
            ``None`` when this frame did not cross a speech boundary, a
            ``VadEvent`` (``{"kind": "start", "t_ms": int}`` or
            ``{"kind": "end", "t_ms": int}``) when it did.

        Raises:
            InvalidFrameError: if ``len(frame_bytes) != FRAME_BYTES``.
                Raised BEFORE any numpy allocation so the model is never
                fed malformed input.
        """
        if len(frame_bytes) != FRAME_BYTES:
            raise InvalidFrameError(
                f"expected exactly {FRAME_BYTES} bytes (512 int16 samples), "
                f"got {len(frame_bytes)}"
            )
        # Little-endian int16 is mandatory (Pitfall #4). ``dtype=np.int16``
        # would honor native byte order — explicit ``"<i2"`` pins LE so the
        # contract holds on any host architecture.
        pcm_int16 = np.frombuffer(frame_bytes, dtype="<i2")
        pcm_f32 = pcm_int16.astype(np.float32) / INT16_MAX
        raw = self._iter(pcm_f32, return_seconds=True)
        if raw is None:
            return None
        if "start" in raw:
            return {"kind": "start", "t_ms": int(raw["start"] * 1000)}
        if "end" in raw:
            return {"kind": "end", "t_ms": int(raw["end"] * 1000)}
        return None

    def reset(self) -> None:
        """Clear per-session VAD state.

        Call between utterances or on WebSocket reconnect to drop any
        in-flight active-speech timers. Plan 02-04 invokes this on
        connection close to ensure no state survives into the next session
        if the underlying ``VADIterator`` somehow gets reused.
        """
        self._iter.reset_states()
