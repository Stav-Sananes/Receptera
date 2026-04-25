"""Tests for receptra.stt.metrics — UtteranceMetrics + log_utterance redaction.

PII policy regression guards (T-02-06-01): the loguru JSON line for
``event="stt.utterance"`` MUST NOT include the raw ``text`` field by default.
A `settings.stt_log_text_redaction_disabled` opt-in re-enables logging the body
for local debugging.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from loguru import logger

if TYPE_CHECKING:
    from receptra.stt.metrics import UtteranceMetrics


@pytest.fixture
def log_sink() -> Iterator[io.StringIO]:
    """Attach a serialize=True loguru sink and yield the buffer.

    The fixture removes ALL existing sinks (so the autouse stderr sink the
    Phase 2 lifespan installs is silenced) and restores the default sink on
    teardown. Each captured line is a single-line JSON payload.
    """
    logger.remove()
    buf = io.StringIO()
    handler_id = logger.add(buf, serialize=True, level="DEBUG")
    yield buf
    logger.remove(handler_id)


def _last_record(buf: io.StringIO) -> dict[str, object]:
    """Pull the last serialized loguru line out of the buffer as a dict."""
    lines = [line for line in buf.getvalue().splitlines() if line.strip()]
    assert lines, "no log lines captured"
    parsed: dict[str, object] = json.loads(lines[-1])
    return parsed


def _make_metrics(
    *,
    text: str = "שלום עולם",
    t_speech_end_ms: int = 1000,
    t_final_ready_ms: int = 1420,
) -> UtteranceMetrics:
    from receptra.stt.metrics import UtteranceMetrics, new_utterance_id, utc_now_iso

    return UtteranceMetrics(
        utterance_id=new_utterance_id(),
        ts_utc=utc_now_iso(),
        t_speech_start_ms=500,
        t_speech_end_ms=t_speech_end_ms,
        t_final_ready_ms=t_final_ready_ms,
        duration_ms=500,
        transcribe_ms=200,
        partials_emitted=2,
        text=text,
        text_len_chars=len(text),
    )


def test_log_utterance_redacts_text_by_default(
    log_sink: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T1 — default redaction: no raw text in log; metadata still present."""
    from receptra.config import settings
    from receptra.stt.metrics import log_utterance

    monkeypatch.setattr(settings, "stt_log_text_redaction_disabled", False)

    m = _make_metrics(text="שלום")
    log_utterance(m)

    rec = _last_record(log_sink)
    serialized = json.dumps(rec, ensure_ascii=False)
    # PII MUST NOT leak into the log line by default.
    assert "שלום" not in serialized
    # Metadata fields are present in the structured payload (loguru places the
    # dict we logged into rec["record"]["message"] OR rec["record"]["extra"]).
    record = rec["record"]
    assert isinstance(record, dict)
    extra = record["extra"]
    msg_str = str(record["message"])
    payload_str = json.dumps(extra, ensure_ascii=False) + msg_str
    assert m.utterance_id in payload_str
    assert "stt_latency_ms" in payload_str
    assert "duration_ms" in payload_str
    assert "text_len_chars" in payload_str
    # No "text" key with PII.
    assert '"text": "שלום"' not in payload_str
    assert "'text': 'שלום'" not in payload_str


def test_log_utterance_includes_text_when_redaction_disabled(
    log_sink: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T2 — opt-in: when disabled flag is True, text DOES land in the log."""
    from receptra.config import settings
    from receptra.stt.metrics import log_utterance

    monkeypatch.setattr(settings, "stt_log_text_redaction_disabled", True)

    m = _make_metrics(text="שלום")
    log_utterance(m)

    rec = _last_record(log_sink)
    serialized = json.dumps(rec, ensure_ascii=False)
    assert "שלום" in serialized


def test_stt_latency_ms_is_property() -> None:
    """T3 — stt_latency_ms = t_final_ready_ms - t_speech_end_ms."""
    m = _make_metrics(t_speech_end_ms=1000, t_final_ready_ms=1420)
    assert m.stt_latency_ms == 420


def test_stt_latency_ms_clamps_negative_to_zero() -> None:
    """T4 — clock-skew defense: negative deltas clamped to 0 (never negative)."""
    m = _make_metrics(t_speech_end_ms=2000, t_final_ready_ms=1900)
    assert m.stt_latency_ms == 0
