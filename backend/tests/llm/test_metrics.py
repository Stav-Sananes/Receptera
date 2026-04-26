"""Tests for receptra.llm.metrics (Plan 03-05).

Verifies:
- ttft_ms / total_ms derived properties (incl. -1 sentinel and clamps)
- transcript_hash byte-stability for Hebrew
- log_llm_call PII redaction default + opt-in
- build_record_call composition + independent failure isolation
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import Any

import pytest
from loguru import logger

from receptra.llm.engine import LlmCallTrace
from receptra.llm.metrics import (
    LlmCallMetrics,
    build_record_call,
    from_trace,
    log_llm_call,
)

# --- Derived properties ----------------------------------------------------


def _make_metrics(**overrides: Any) -> LlmCallMetrics:
    base: dict[str, Any] = {
        "request_id": "rid-1",
        "ts_utc": "2026-04-25T10:00:00+00:00",
        "transcript": "שלום",
        "transcript_hash": "abcd1234abcd1234",
        "text_len_chars": 4,
        "n_chunks": 1,
        "model": "dictalm3",
        "t_request_sent": 100.0,
        "t_first_token": 100.05,
        "t_done": 100.5,
        "eval_count": 12,
        "prompt_eval_count": 40,
        "status": "ok",
        "suggestions_count": 1,
        "grounded": True,
    }
    base.update(overrides)
    return LlmCallMetrics(**base)


def test_ttft_ms_happy() -> None:
    # Use values whose float arithmetic is exact (powers of 2 fractions) so
    # int truncation does not race against IEEE-754 rounding.
    m = _make_metrics(t_request_sent=10.0, t_first_token=10.0625, t_done=10.5)
    assert m.ttft_ms == 62
    assert m.total_ms == 500


def test_ttft_ms_sentinel_when_no_token() -> None:
    m = _make_metrics(t_first_token=None)
    assert m.ttft_ms == -1


def test_ttft_ms_clamped_to_zero_on_negative_drift() -> None:
    m = _make_metrics(t_request_sent=10.0, t_first_token=9.999)
    assert m.ttft_ms == 0


def test_total_ms_clamped_to_zero_on_negative_drift() -> None:
    m = _make_metrics(t_request_sent=10.0, t_done=9.999)
    assert m.total_ms == 0


# --- transcript_hash ------------------------------------------------------


def test_transcript_hash_hebrew_byte_stable() -> None:
    """Pinned regression: ensure the hash function is sha256[:16] over UTF-8.

    If this changes, downstream audit queries break — the hash IS the
    primary key for cross-call correlation in Phase 7.
    """
    expected = hashlib.sha256("שלום".encode()).hexdigest()[:16]
    trace = LlmCallTrace(
        request_id="rid",
        transcript="שלום",
        n_chunks=0,
        model="dictalm3",
        t_request_sent=0.0,
        t_first_token=None,
        t_done=0.001,
        eval_count=None,
        prompt_eval_count=None,
        status="no_context",
        suggestions_count=1,
        grounded=False,
    )
    m = from_trace(trace)
    assert m.transcript_hash == expected
    assert len(m.transcript_hash) == 16


def test_text_len_chars_counts_unicode_codepoints() -> None:
    trace = LlmCallTrace(
        request_id="r",
        transcript="שלום עולם",
        n_chunks=0,
        model="dictalm3",
        t_request_sent=0.0,
        t_first_token=None,
        t_done=0.0,
        eval_count=None,
        prompt_eval_count=None,
        status="no_context",
        suggestions_count=1,
        grounded=False,
    )
    m = from_trace(trace)
    assert m.text_len_chars == 9  # 4 + space + 4 codepoints


def test_from_trace_preserves_transcript_for_opt_in() -> None:
    trace = LlmCallTrace(
        request_id="rid-x",
        transcript="שלום עולם",
        n_chunks=2,
        model="dictalm3",
        t_request_sent=1.0,
        t_first_token=1.1,
        t_done=2.0,
        eval_count=42,
        prompt_eval_count=50,
        status="ok",
        suggestions_count=2,
        grounded=True,
    )
    m = from_trace(trace)
    assert m.transcript == "שלום עולם"
    assert m.request_id == "rid-x"
    assert m.n_chunks == 2
    assert m.model == "dictalm3"
    assert m.eval_count == 42
    assert m.prompt_eval_count == 50
    assert m.status == "ok"
    assert m.suggestions_count == 2
    assert m.grounded is True


def test_from_trace_request_id_override() -> None:
    trace = LlmCallTrace(
        request_id="rid-original",
        transcript="x",
        n_chunks=0,
        model="dictalm3",
        t_request_sent=0.0,
        t_first_token=None,
        t_done=0.001,
        eval_count=None,
        prompt_eval_count=None,
        status="no_context",
        suggestions_count=1,
        grounded=False,
    )
    m = from_trace(trace, request_id_override="rid-override")
    assert m.request_id == "rid-override"


# --- log_llm_call PII redaction ------------------------------------------


@pytest.fixture
def loguru_sink() -> Iterator[list[Any]]:
    """Capture loguru records; restore default sink after test."""
    captured: list[Any] = []

    def sink(message: Any) -> None:
        captured.append(message.record)

    sink_id = logger.add(sink, format="{message}", level="DEBUG", serialize=False)
    yield captured
    logger.remove(sink_id)


def test_log_llm_call_redacts_transcript_by_default(
    loguru_sink: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "receptra.llm.metrics.settings.llm_log_text_redaction_disabled", False
    )
    m = _make_metrics(transcript="שלום עולם")
    log_llm_call(m)

    # The payload is logged via logger.bind(event=...).info({...}). The secret
    # 'שלום עולם' MUST NOT appear in any record's repr.
    rendered = "\n".join(str(r) for r in loguru_sink)
    assert "שלום עולם" not in rendered
    assert m.transcript_hash in rendered


def test_log_llm_call_includes_transcript_when_redaction_disabled(
    loguru_sink: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "receptra.llm.metrics.settings.llm_log_text_redaction_disabled", True
    )
    m = _make_metrics(transcript="שלום עולם")
    log_llm_call(m)

    rendered = "\n".join(str(r) for r in loguru_sink)
    assert "שלום עולם" in rendered


def test_log_llm_call_emits_event_llm_call(loguru_sink: list[Any]) -> None:
    m = _make_metrics()
    log_llm_call(m)
    extras = [r.get("extra") for r in loguru_sink]
    assert any(e is not None and e.get("event") == "llm.call" for e in extras)


def test_log_llm_call_includes_ttft_and_total(
    loguru_sink: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "receptra.llm.metrics.settings.llm_log_text_redaction_disabled", False
    )
    # Power-of-2 fractions give exact float arithmetic.
    m = _make_metrics(t_request_sent=10.0, t_first_token=10.0625, t_done=10.5)
    log_llm_call(m)
    rendered = "\n".join(str(r) for r in loguru_sink)
    # ttft_ms == 62, total_ms == 500
    assert "62" in rendered
    assert "500" in rendered


# --- build_record_call composition + isolation ----------------------------


def test_build_record_call_invokes_log_and_insert(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    audit_path = tmp_path / "audit.sqlite"
    log_calls: list[Any] = []
    insert_calls: list[Any] = []

    monkeypatch.setattr(
        "receptra.llm.metrics.log_llm_call", lambda m: log_calls.append(m)
    )
    monkeypatch.setattr(
        "receptra.llm.metrics.insert_llm_call",
        lambda p, m: insert_calls.append((p, m)),
    )

    record = build_record_call(audit_path)
    trace = LlmCallTrace(
        request_id="r",
        transcript="שלום",
        n_chunks=1,
        model="dictalm3",
        t_request_sent=0.0,
        t_first_token=0.05,
        t_done=0.5,
        eval_count=12,
        prompt_eval_count=40,
        status="ok",
        suggestions_count=1,
        grounded=True,
    )
    record(trace)
    assert len(log_calls) == 1
    assert len(insert_calls) == 1


def test_build_record_call_swallows_log_failure_but_still_inserts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    audit_path = tmp_path / "audit.sqlite"
    insert_calls: list[Any] = []

    def raising_log(_m: Any) -> None:
        raise RuntimeError("loguru sink failed")

    monkeypatch.setattr("receptra.llm.metrics.log_llm_call", raising_log)
    monkeypatch.setattr(
        "receptra.llm.metrics.insert_llm_call",
        lambda p, m: insert_calls.append((p, m)),
    )

    record = build_record_call(audit_path)
    trace = LlmCallTrace(
        request_id="r",
        transcript="x",
        n_chunks=0,
        model="dictalm3",
        t_request_sent=0.0,
        t_first_token=None,
        t_done=0.001,
        eval_count=None,
        prompt_eval_count=None,
        status="no_context",
        suggestions_count=1,
        grounded=False,
    )
    record(trace)  # MUST NOT raise
    assert len(insert_calls) == 1


def test_build_record_call_swallows_insert_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    audit_path = tmp_path / "audit.sqlite"
    log_calls: list[Any] = []

    def raising_insert(_p: Any, _m: Any) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(
        "receptra.llm.metrics.log_llm_call", lambda m: log_calls.append(m)
    )
    monkeypatch.setattr("receptra.llm.metrics.insert_llm_call", raising_insert)

    record = build_record_call(audit_path)
    trace = LlmCallTrace(
        request_id="r",
        transcript="x",
        n_chunks=0,
        model="dictalm3",
        t_request_sent=0.0,
        t_first_token=None,
        t_done=0.001,
        eval_count=None,
        prompt_eval_count=None,
        status="no_context",
        suggestions_count=1,
        grounded=False,
    )
    record(trace)  # MUST NOT raise
    assert len(log_calls) == 1


def test_build_record_call_returns_callable(tmp_path: Any) -> None:
    audit_path = tmp_path / "audit.sqlite"
    record = build_record_call(audit_path)
    assert callable(record)


def test_build_record_call_eager_init_creates_audit_file(tmp_path: Any) -> None:
    """build_record_call calls init_llm_audit_table eagerly at hook construction."""
    audit_path = tmp_path / "data" / "audit.sqlite"
    assert not audit_path.exists()
    build_record_call(audit_path)
    # init_llm_audit_table creates parent dir + file via sqlite3.connect.
    assert audit_path.exists()
