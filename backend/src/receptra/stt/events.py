"""Pydantic event schema for /ws/stt (RESEARCH §8).

Single source of truth for the wire contract Plan 02-04 publishes. Every
event leaving the WebSocket handler MUST be constructed via one of these
models and serialised through ``model_dump()`` / ``model_dump_json()`` —
no ad-hoc ``json.dumps`` of plain dicts (regression-tested by the
discriminator test).

Discriminated union on the ``type`` field. Plan 02-05 (WER batch) and
Plan 02-06 (latency instrumentation) parse incoming events via
``TypeAdapter(SttEvent).validate_python(...)`` to dispatch on type.

All timestamps are monotonic milliseconds (``int(time.monotonic() * 1000)``
inside the WebSocket handler). Hebrew text is UTF-8 preserved; pydantic
v2 does not alter string content (frozen models forbid post-hoc mutation
as a belt-and-braces guard).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class SttReady(BaseModel):
    """Sent immediately after WebSocket accept — declares wire contract."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ready"] = "ready"
    model: str
    sample_rate: int = 16000
    frame_bytes: int = 1024


class PartialTranscript(BaseModel):
    """Emitted ≥1x per active utterance per ``stt_partial_interval_ms``."""

    model_config = ConfigDict(frozen=True)

    type: Literal["partial"] = "partial"
    text: str
    t_speech_start_ms: int = Field(..., description="Monotonic ms when VAD start fired")
    t_emit_ms: int = Field(..., description="Monotonic ms when this event was built")


class FinalTranscript(BaseModel):
    """Emitted exactly once per utterance on VAD end."""

    model_config = ConfigDict(frozen=True)

    type: Literal["final"] = "final"
    text: str
    t_speech_start_ms: int
    t_speech_end_ms: int
    stt_latency_ms: int = Field(..., description="t_final_ready - t_speech_end (STT-06)")
    duration_ms: int = Field(..., description="Utterance audio duration in ms")


class SttError(BaseModel):
    """Protocol / model / VAD error envelope.

    The 3-code allowlist is research-locked (RESEARCH §8). Adding a new
    code requires a plan amendment so downstream consumers' switch
    statements stay total.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["error"] = "error"
    code: Literal["model_error", "vad_error", "protocol_error"]
    message: str


SttEvent = Annotated[
    SttReady | PartialTranscript | FinalTranscript | SttError,
    Field(discriminator="type"),
]
"""Discriminated-union alias for parsing inbound events.

Usage::

    from pydantic import TypeAdapter
    parsed = TypeAdapter(SttEvent).validate_python(raw_dict)
    if isinstance(parsed, FinalTranscript): ...
"""
