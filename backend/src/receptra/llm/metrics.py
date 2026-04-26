"""Per-call LLM metrics + loguru JSON sink (LLM-05).

Mirrors ``receptra.stt.metrics`` (Plan 02-06) deliberately so audit queries
across the STT and LLM domains share idiom. Differences:
- ``ttft_ms`` (LLM) where STT had ``stt_latency_ms``
- ``transcript_hash`` (LLM) where STT had ``text`` (LLM hashes by default;
  STT stores body in SQLite because the audit DB is filesystem-permissioned
  but logs both redact body — symmetric PII model)

PII policy (T-03-05-01):
    The ``transcript`` field is PII. By default it is OMITTED from the
    loguru JSON line and ALWAYS hashed (not stored) in the SQLite row.
    Opt-in inclusion via ``settings.llm_log_text_redaction_disabled``.
    Documented in .env.example (Plan 03-01) and docs/llm.md (Plan 03-06).

Hash collision space (T-03-05-07 acceptance):
    ``transcript_hash`` is sha256[:16] (8 bytes prefix). 2^64 collision
    space is sufficient for cross-call correlation in Phase 7 audit
    queries — the hash is NOT used as a cryptographic identity. Compact
    + indexable (fits in TEXT(16)).
"""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from receptra.config import settings
from receptra.llm.audit import init_llm_audit_table, insert_llm_call
from receptra.llm.engine import LlmCallTrace


@dataclass(frozen=True)
class LlmCallMetrics:
    """Per-call metric record. Frozen — caller constructs once, reads N times.

    ``ttft_ms`` and ``total_ms`` are derived properties over monotonic
    timestamps; we never store the derived value as a field, mirroring
    ``UtteranceMetrics.stt_latency_ms`` from Plan 02-06.
    """

    request_id: str
    ts_utc: str

    transcript: str  # PII — redacted by default in log_llm_call
    transcript_hash: str  # sha256[:16] — always safe to log/store
    text_len_chars: int

    n_chunks: int
    model: str

    t_request_sent: float  # perf_counter monotonic
    t_first_token: float | None
    t_done: float

    eval_count: int | None
    prompt_eval_count: int | None

    status: str
    suggestions_count: int
    grounded: bool

    @property
    def ttft_ms(self) -> int:
        """Wall-clock TTFT (LLM-05). -1 sentinel when no token arrived.

        Clamped to ``>= 0`` to guard against rare monotonic-clock + thread
        scheduling deltas going negative — same defense as Plan 02-06
        ``UtteranceMetrics.stt_latency_ms``.
        """
        if self.t_first_token is None:
            return -1
        return max(0, int((self.t_first_token - self.t_request_sent) * 1000))

    @property
    def total_ms(self) -> int:
        """Wall-clock total request time. Clamped to ``>= 0``."""
        return max(0, int((self.t_done - self.t_request_sent) * 1000))


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp for human-readable ordering in audit log."""
    return datetime.now(tz=UTC).isoformat()


def _hash_transcript(transcript: str) -> str:
    """sha256[:16] — RESEARCH §6.4 PII boundary: 8 bytes prefix."""
    return hashlib.sha256(transcript.encode("utf-8")).hexdigest()[:16]


def from_trace(
    trace: LlmCallTrace, request_id_override: str | None = None
) -> LlmCallMetrics:
    """Convert engine LlmCallTrace → persistence LlmCallMetrics.

    Computes transcript_hash + text_len_chars; preserves all timestamps
    monotonically (so derived ttft_ms / total_ms cannot drift from the
    log line vs SQLite row).
    """
    return LlmCallMetrics(
        request_id=request_id_override or trace.request_id,
        ts_utc=_utc_now_iso(),
        transcript=trace.transcript,
        transcript_hash=_hash_transcript(trace.transcript),
        text_len_chars=len(trace.transcript),
        n_chunks=trace.n_chunks,
        model=trace.model,
        t_request_sent=trace.t_request_sent,
        t_first_token=trace.t_first_token,
        t_done=trace.t_done,
        eval_count=trace.eval_count,
        prompt_eval_count=trace.prompt_eval_count,
        status=trace.status,
        suggestions_count=trace.suggestions_count,
        grounded=trace.grounded,
    )


def log_llm_call(m: LlmCallMetrics) -> None:
    """Emit one structured JSON log line (event='llm.call').

    Default: ``transcript`` is OMITTED (PII redaction). Opt-in inclusion
    via ``settings.llm_log_text_redaction_disabled``.
    """
    payload: dict[str, object] = {
        "request_id": m.request_id,
        "ts_utc": m.ts_utc,
        "transcript_hash": m.transcript_hash,
        "text_len_chars": m.text_len_chars,
        "n_chunks": m.n_chunks,
        "model": m.model,
        "ttft_ms": m.ttft_ms,
        "total_ms": m.total_ms,
        "eval_count": m.eval_count,
        "prompt_eval_count": m.prompt_eval_count,
        "suggestions_count": m.suggestions_count,
        "grounded": m.grounded,
        "status": m.status,
    }
    if settings.llm_log_text_redaction_disabled:
        payload["transcript"] = m.transcript
    logger.bind(event="llm.call").info(payload)


def build_record_call(audit_path: str | Path) -> Callable[[LlmCallTrace], None]:
    """Factory for the ``record_call`` hook consumed by ``generate_suggestions``.

    Eager-initializes the audit table at hook-construction time (T-02-06-06
    pattern from STT-06 — absorbs missing ./data dir on fresh checkouts).

    The returned callable wraps ``log_llm_call`` and ``insert_llm_call`` in
    INDEPENDENT try/except blocks: a failure in one MUST NOT short-circuit
    the other, and NEITHER may propagate to the engine generator (mirrors
    Plan 02-06 robustness).
    """
    init_llm_audit_table(audit_path)

    def _record(trace: LlmCallTrace) -> None:
        m = from_trace(trace)
        # Two independent suppress blocks: log failure must not skip insert,
        # insert failure must not skip log. Defense in depth — Plan 02-06
        # parity. Any callback bug MUST NEVER crash the engine generator.
        with contextlib.suppress(Exception):
            log_llm_call(m)
        with contextlib.suppress(Exception):
            insert_llm_call(audit_path, m)

    return _record


__all__ = [
    "LlmCallMetrics",
    "build_record_call",
    "from_trace",
    "log_llm_call",
]
