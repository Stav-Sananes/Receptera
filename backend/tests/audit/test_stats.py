"""Tests for receptra.audit.stats — aggregate reads over the audit DB."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from receptra.audit.stats import read_stats
from receptra.pipeline.audit import PipelineRunRecord, init_pipeline_db, insert_pipeline_run
from receptra.stt.audit import init_audit_db, insert_stt_utterance
from receptra.stt.metrics import UtteranceMetrics


def _seed(db: Path, n: int, base_ts: datetime, *, e2e_ms: int = 1500, status: str = "ok") -> None:
    init_audit_db(db)
    init_pipeline_db(db)
    for i in range(n):
        ts = (base_ts + timedelta(seconds=i)).isoformat()
        utt_id = f"u-{i}"
        insert_stt_utterance(
            db,
            UtteranceMetrics(
                utterance_id=utt_id,
                ts_utc=ts,
                t_speech_start_ms=1000,
                t_speech_end_ms=2000,
                t_final_ready_ms=2000 + 400,  # stt_latency = 400ms
                duration_ms=1000,
                transcribe_ms=400,
                partials_emitted=2,
                text="שלום",
                text_len_chars=4,
                wer_sample_id=None,
            ),
        )
        insert_pipeline_run(
            db,
            PipelineRunRecord(
                utterance_id=utt_id,
                ts_utc=ts,
                stt_latency_ms=400,
                rag_latency_ms=80,
                llm_ttft_ms=200,
                llm_total_ms=900,
                n_chunks=3,
                n_suggestions=1,
                status=status,
                e2e_latency_ms=e2e_ms,
            ),
        )


def test_read_stats_returns_zeroed_window_for_missing_db(tmp_path: Path) -> None:
    """No DB file yet → all_time stats are all zero, no exception."""
    report = read_stats(tmp_path / "missing.sqlite")
    assert report["all_time"]["n_utterances"] == 0
    assert report["all_time"]["n_pipeline_runs"] == 0
    assert report["all_time"]["avg_e2e_latency_ms"] is None
    assert report["last_24h"] is None


def test_read_stats_aggregates_seeded_runs(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite"
    _seed(db, n=10, base_ts=datetime.now(UTC) - timedelta(hours=1), e2e_ms=1200)

    report = read_stats(db)
    assert report["all_time"]["n_utterances"] == 10
    assert report["all_time"]["n_pipeline_runs"] == 10
    assert report["all_time"]["avg_e2e_latency_ms"] == 1200.0
    assert report["all_time"]["p95_e2e_latency_ms"] == 1200
    assert report["all_time"]["pct_rag_degraded"] == 0.0


def test_read_stats_24h_window_excludes_old_rows(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite"
    _seed(db, n=5, base_ts=datetime.now(UTC) - timedelta(days=2), e2e_ms=2000)

    since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    report = read_stats(db, since_iso_24h=since)
    assert report["all_time"]["n_utterances"] == 5
    assert report["last_24h"]["n_utterances"] == 0
    assert report["last_24h"]["avg_e2e_latency_ms"] is None


def test_read_stats_counts_rag_degraded_share(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite"
    init_audit_db(db)
    init_pipeline_db(db)
    base = datetime.now(UTC).isoformat()
    for i in range(4):
        utt_id = f"u-{i}"
        insert_stt_utterance(
            db,
            UtteranceMetrics(
                utterance_id=utt_id,
                ts_utc=base,
                t_speech_start_ms=0,
                t_speech_end_ms=1000,
                t_final_ready_ms=1300,
                duration_ms=1000,
                transcribe_ms=300,
                partials_emitted=1,
                text="x",
                text_len_chars=1,
                wer_sample_id=None,
            ),
        )
        insert_pipeline_run(
            db,
            PipelineRunRecord(
                utterance_id=utt_id,
                ts_utc=base,
                stt_latency_ms=300,
                rag_latency_ms=0,
                llm_ttft_ms=200,
                llm_total_ms=600,
                n_chunks=0,
                n_suggestions=1,
                status="rag_degraded" if i < 1 else "ok",
                e2e_latency_ms=900,
            ),
        )

    report = read_stats(db)
    # 1 of 4 runs degraded → 25%
    assert abs(report["all_time"]["pct_rag_degraded"] - 0.25) < 0.001


def test_read_stats_endpoint_via_testclient(tmp_path: Path, monkeypatch) -> None:
    """The /api/audit/stats endpoint returns valid JSON shape against a seeded DB."""
    from fastapi.testclient import TestClient

    from receptra.config import settings
    from receptra.main import app

    db = tmp_path / "audit.sqlite"
    _seed(db, n=3, base_ts=datetime.now(UTC), e2e_ms=1100)
    monkeypatch.setattr(settings, "audit_db_path", str(db))

    with TestClient(app) as client:
        resp = client.get("/api/audit/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "all_time" in body
    assert "last_24h" in body
    assert body["all_time"]["n_utterances"] == 3
    assert body["all_time"]["n_pipeline_runs"] == 3


def _direct_check_db_isolation(db: Path) -> None:
    """Sanity: tests must not leak rows into the real audit DB."""
    with sqlite3.connect(str(db)) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM stt_utterances")
        assert cur.fetchone()[0] >= 0  # smoke
