"""Pydantic roundtrip + discriminated-union dispatch tests for /ws/stt events.

These tests pin the public wire contract Plan 02-04 publishes for Plan 02-05
(WER batch) and Plan 02-06 (latency instrumentation). Every event the server
emits MUST round-trip through pydantic exactly — no ad-hoc ``json.dumps``.

Coverage map:

* Test 1 — ``SttReady`` model_dump_json + parse-back.
* Test 2 — ``PartialTranscript`` Hebrew text round-trips byte-exact (UTF-8).
* Test 3 — ``FinalTranscript`` preserves all timing fields.
* Test 4 — ``SttError`` accepts only research-locked codes.
* Test 5 — ``TypeAdapter(SttEvent)`` discriminated-union dispatch picks the
  right concrete class given a ``{"type": "..."}`` envelope.
* Test 6 — frozen models reject ``.type`` mutation post-construction
  (defense against in-process field corruption).
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from pydantic import TypeAdapter, ValidationError

from receptra.stt.events import (
    FinalTranscript,
    PartialTranscript,
    SttError,
    SttEvent,
    SttReady,
)

# Module-level adapter — TypeAdapter is expensive to construct repeatedly.
_ADAPTER: TypeAdapter[
    SttReady | PartialTranscript | FinalTranscript | SttError
] = TypeAdapter(SttEvent)

# ---------------------------------------------------------------------------
# Test 1 — SttReady roundtrip
# ---------------------------------------------------------------------------


def test_ready_roundtrip() -> None:
    """``SttReady`` JSON-dumps with ``"type":"ready"`` and parses back via SttEvent."""
    ready = SttReady(model="ivrit-ai/whisper-large-v3-turbo-ct2")
    raw = ready.model_dump_json()

    payload = json.loads(raw)
    assert payload["type"] == "ready"
    assert payload["model"] == "ivrit-ai/whisper-large-v3-turbo-ct2"
    assert payload["sample_rate"] == 16000
    assert payload["frame_bytes"] == 1024

    parsed = _ADAPTER.validate_python(payload)
    assert isinstance(parsed, SttReady)
    assert parsed == ready


# ---------------------------------------------------------------------------
# Test 2 — Hebrew text round-trips byte-exact through Partial
# ---------------------------------------------------------------------------


def test_partial_roundtrip() -> None:
    """Hebrew UTF-8 in PartialTranscript must round-trip byte-exact."""
    hebrew = "שלום"
    partial = PartialTranscript(
        text=hebrew,
        t_speech_start_ms=1234,
        t_emit_ms=1700,
    )
    payload = json.loads(partial.model_dump_json())
    assert payload["type"] == "partial"
    assert payload["text"] == hebrew

    parsed = _ADAPTER.validate_python(payload)
    assert isinstance(parsed, PartialTranscript)
    assert parsed.text == hebrew  # byte-exact preservation
    assert parsed.t_speech_start_ms == 1234
    assert parsed.t_emit_ms == 1700


# ---------------------------------------------------------------------------
# Test 3 — FinalTranscript preserves all timing + metric fields
# ---------------------------------------------------------------------------


def test_final_roundtrip() -> None:
    """``FinalTranscript`` round-trips text + all 4 timing fields."""
    final = FinalTranscript(
        text="שלום עולם",
        t_speech_start_ms=1000,
        t_speech_end_ms=2200,
        stt_latency_ms=350,
        duration_ms=1200,
    )
    payload = json.loads(final.model_dump_json())

    assert payload["type"] == "final"
    parsed = _ADAPTER.validate_python(payload)
    assert isinstance(parsed, FinalTranscript)
    assert parsed.stt_latency_ms == 350
    assert parsed.duration_ms == 1200
    assert parsed.t_speech_start_ms == 1000
    assert parsed.t_speech_end_ms == 2200
    assert parsed.text == "שלום עולם"


# ---------------------------------------------------------------------------
# Test 4 — SttError code allowlist
# ---------------------------------------------------------------------------


def test_error_roundtrip() -> None:
    """``SttError`` accepts the 3 research-locked codes and rejects others."""
    err = SttError(code="protocol_error", message="bad frame size")
    parsed = _ADAPTER.validate_python(json.loads(err.model_dump_json()))
    assert isinstance(parsed, SttError)
    assert parsed.code == "protocol_error"
    assert parsed.message == "bad frame size"

    # Other allowed codes
    SttError(code="model_error", message="x")
    SttError(code="vad_error", message="y")

    # Bogus code rejected at construction time. Cast to Any so mypy does not
    # short-circuit the runtime ValidationError path with its own complaint.
    bogus: Any = "bogus"
    with pytest.raises(ValidationError):
        SttError(code=bogus, message="z")


# ---------------------------------------------------------------------------
# Test 5 — Discriminated union dispatches on `type`
# ---------------------------------------------------------------------------


def test_discriminator_dispatches() -> None:
    """A raw ``final`` dict MUST hydrate as ``FinalTranscript``, not Partial/dict."""
    raw = {
        "type": "final",
        "text": "",
        "t_speech_start_ms": 0,
        "t_speech_end_ms": 100,
        "stt_latency_ms": 50,
        "duration_ms": 100,
    }
    parsed = _ADAPTER.validate_python(raw)
    assert isinstance(parsed, FinalTranscript)
    assert not isinstance(parsed, PartialTranscript)


# ---------------------------------------------------------------------------
# Test 6 — Frozen models reject `.type` mutation
# ---------------------------------------------------------------------------


def test_frozen_type_discriminator() -> None:
    """``frozen=True`` MUST forbid mutating ``.type`` after construction."""
    ready = SttReady(model="m")
    # Cast through Any so mypy doesn't short-circuit the runtime error path
    # (Literal["ready"] forbids assignment of any other string at type-check
    # time; the runtime check we want to assert is pydantic's frozen guard).
    ready_any = cast(Any, ready)
    with pytest.raises(ValidationError):
        ready_any.type = "partial"
