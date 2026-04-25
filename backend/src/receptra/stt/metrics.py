"""Per-utterance STT metrics + loguru JSON sink (STT-06).

PII policy (T-02-06-01):
    The ``text`` field is PII (Hebrew transcripts of live conversations).
    By default it is OMITTED from the loguru JSON line; the SQLite audit
    table (filesystem-permissioned, single-user, local-only) is the
    canonical store for the body. Opt-in override via
    ``settings.stt_log_text_redaction_disabled``. Documented in
    ``docs/stt.md §Audit log + PII warning``.

Wall-clock policy:
    ``stt_latency_ms`` is a derived ``@property`` over monotonic-clock
    timestamps captured by the WebSocket pipeline. We never store the
    derived value as a field — that would risk silent drift between
    log line + SQLite row. Computing it on read keeps both surfaces
    pinned to one source of truth (the captured timestamps).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from loguru import logger

from receptra.config import settings


@dataclass(frozen=True)
class UtteranceMetrics:
    """Per-utterance metric record. Frozen — caller constructs once, reads N times."""

    utterance_id: str
    ts_utc: str
    t_speech_start_ms: int
    t_speech_end_ms: int
    t_final_ready_ms: int
    duration_ms: int
    transcribe_ms: int
    partials_emitted: int
    text: str  # PII — redacted by default in log_utterance
    text_len_chars: int
    wer_sample_id: str | None = None

    @property
    def stt_latency_ms(self) -> int:
        """STT-06 metric (speech-end → final-ready). Clamped to >= 0.

        The clamp guards against the rare case where a fast monotonic
        clock + thread scheduling produces ``t_final_ready_ms <
        t_speech_end_ms`` (negative deltas would otherwise leak into the
        audit DB and break percentile math downstream).
        """
        return max(0, self.t_final_ready_ms - self.t_speech_end_ms)


def new_utterance_id() -> str:
    """Generate a fresh utterance id (uuid4 hex, 32 chars, URL-safe)."""
    return uuid.uuid4().hex


def utc_now_iso() -> str:
    """Wall-clock UTC ISO-8601 timestamp for ``ts_utc`` audit column.

    Used ONLY for human-readable ordering in the audit table — latency
    math always uses the monotonic ``t_*_ms`` fields.
    """
    return datetime.now(tz=UTC).isoformat()


def log_utterance(m: UtteranceMetrics) -> None:
    """Emit one structured JSON log line (event='stt.utterance').

    Default: ``text`` is OMITTED (PII redaction). Opt-in via
    ``settings.stt_log_text_redaction_disabled``.
    """
    payload: dict[str, object] = {
        "utterance_id": m.utterance_id,
        "ts_utc": m.ts_utc,
        "t_speech_start_ms": m.t_speech_start_ms,
        "t_speech_end_ms": m.t_speech_end_ms,
        "t_final_ready_ms": m.t_final_ready_ms,
        "duration_ms": m.duration_ms,
        "stt_latency_ms": m.stt_latency_ms,
        "transcribe_ms": m.transcribe_ms,
        "partials_emitted": m.partials_emitted,
        "text_len_chars": m.text_len_chars,
        "wer_sample_id": m.wer_sample_id,
    }
    if settings.stt_log_text_redaction_disabled:
        payload["text"] = m.text
    logger.bind(event="stt.utterance").info(payload)


__all__ = [
    "UtteranceMetrics",
    "log_utterance",
    "new_utterance_id",
    "utc_now_iso",
]
