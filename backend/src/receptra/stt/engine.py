"""Hebrew-locked Whisper transcribe wrapper.

Single source of truth for transcribe parameters — every call site (live
streaming in Plan 02-04, batch WER eval in Plan 02-05) MUST go through this
wrapper so Hebrew params can never drift.

RESEARCH §7 contract (locked kwargs):
    language="he", task="transcribe", beam_size=1, best_of=1, temperature=0.0,
    condition_on_previous_text=False, vad_filter=False, without_timestamps=True,
    initial_prompt=None.

Threat T-02-02-01 mitigation: the unit tests in tests/stt/test_engine.py
assert every locked kwarg is present; future contributors who add a new call
site MUST reuse this wrapper or pay the CI failure tax.
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray


class _TranscribeCapable(Protocol):
    """Structural type matching ``faster_whisper.WhisperModel.transcribe``.

    We intentionally avoid importing ``WhisperModel`` here to keep this module
    trivially testable with ``unittest.mock`` and to avoid pulling the heavy
    CT2 backend into test-collection time.
    """

    def transcribe(
        self, audio: NDArray[np.float32], **kwargs: Any
    ) -> tuple[Any, Any]:  # pragma: no cover - protocol
        ...


def transcribe_hebrew(
    model: _TranscribeCapable,
    audio_f32: NDArray[np.float32],
) -> tuple[str, dict[str, Any]]:
    """Transcribe float32 PCM with every Hebrew param locked (RESEARCH §7).

    Args:
        model: A ``faster_whisper.WhisperModel`` instance (or any object
            implementing the ``_TranscribeCapable`` protocol).
        audio_f32: 1-D ``float32`` numpy array, 16 kHz mono, values in
            ``[-1.0, 1.0]``. The ``int16 LE → float32`` conversion MUST happen
            at the WebSocket boundary (Pitfall #4); this module refuses any
            other dtype as a defense-in-depth check.

    Returns:
        ``(text, info_dict)``. ``text`` is ``"".join(seg.text for seg in
        segments).strip()`` — faster-whisper emits a leading space on every
        segment, so stripping + joining is intentional. ``info_dict`` carries
        ``duration``, ``language``, and ``language_probability`` for latency
        and quality logging by callers (Plan 02-04, Plan 02-05).

    Raises:
        TypeError: if ``audio_f32.dtype`` is not ``np.float32``. Raised
            BEFORE ``model.transcribe`` is invoked, so the model is never
            fed wrong-dtype data.
    """
    if audio_f32.dtype != np.float32:
        raise TypeError(
            f"transcribe_hebrew requires float32 audio; got {audio_f32.dtype}. "
            "Wire contract is int16 LE → float32 conversion at the WebSocket "
            "boundary (Pitfall #4)."
        )
    segments, info = model.transcribe(
        audio=audio_f32,
        language="he",
        task="transcribe",
        beam_size=1,
        best_of=1,
        temperature=0.0,
        condition_on_previous_text=False,
        vad_filter=False,
        without_timestamps=True,
        initial_prompt=None,
    )
    text = "".join(seg.text for seg in segments).strip()
    info_dict: dict[str, Any] = {
        "duration": getattr(info, "duration", None),
        "language": getattr(info, "language", "he"),
        "language_probability": getattr(info, "language_probability", None),
    }
    return text, info_dict
