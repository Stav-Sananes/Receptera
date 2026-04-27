"""Tests for pipeline_runs SQLite audit table (Phase 5 INT-05)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from receptra.pipeline.audit import PipelineRunRecord, init_pipeline_db, insert_pipeline_run


def _make_record(utterance_id: str = "test-123") -> PipelineRunRecord:
    return PipelineRunRecord(
        utterance_id=utterance_id,
        ts_utc="2026-04-27T10:00:00Z",
        stt_latency_ms=120,
        rag_latency_ms=45,
        llm_ttft_ms=380,
        llm_total_ms=1200,
        n_chunks=3,
        n_suggestions=2,
        status="ok",
        e2e_latency_ms=1500,
    )


def test_init_pipeline_db_creates_table(tmp_path: Path) -> None:
    """init_pipeline_db creates pipeline_runs table."""
    db = tmp_path / "audit.sqlite"
    init_pipeline_db(db)
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_runs'"
        ).fetchall()
    assert rows, "pipeline_runs table not created"


def test_init_pipeline_db_is_idempotent(tmp_path: Path) -> None:
    """init_pipeline_db can be called multiple times without error."""
    db = tmp_path / "audit.sqlite"
    init_pipeline_db(db)
    init_pipeline_db(db)  # second call is a no-op


def test_insert_pipeline_run_roundtrip(tmp_path: Path) -> None:
    """insert_pipeline_run stores all fields; read back matches."""
    db = tmp_path / "audit.sqlite"
    init_pipeline_db(db)
    rec = _make_record("utt-roundtrip")
    insert_pipeline_run(db, rec)

    with sqlite3.connect(str(db)) as conn:
        row = conn.execute(
            "SELECT * FROM pipeline_runs WHERE utterance_id = ?",
            ("utt-roundtrip",),
        ).fetchone()

    assert row is not None
    assert row[0] == "utt-roundtrip"  # utterance_id
    assert row[2] == 120  # stt_latency_ms
    assert row[3] == 45   # rag_latency_ms


def test_insert_pipeline_run_null_rag(tmp_path: Path) -> None:
    """rag_latency_ms and llm_ttft_ms can be None (degradation path)."""
    db = tmp_path / "audit.sqlite"
    init_pipeline_db(db)
    rec = PipelineRunRecord(
        utterance_id="utt-degraded",
        ts_utc="2026-04-27T10:00:00Z",
        stt_latency_ms=100,
        rag_latency_ms=None,
        llm_ttft_ms=None,
        llm_total_ms=None,
        n_chunks=0,
        n_suggestions=1,
        status="rag_degraded",
        e2e_latency_ms=None,
    )
    insert_pipeline_run(db, rec)  # must not raise


def test_insert_without_init_raises(tmp_path: Path) -> None:
    """insert_pipeline_run raises if table does not exist (mirrors stt/audit contract)."""
    db = tmp_path / "no_init.sqlite"
    rec = _make_record()
    with pytest.raises(sqlite3.OperationalError):
        insert_pipeline_run(db, rec)
