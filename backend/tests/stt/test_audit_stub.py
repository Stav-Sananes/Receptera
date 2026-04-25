"""Tests for receptra.stt.audit — SQLite stt_utterances stub schema.

Stdlib sqlite3 only (no SQLAlchemy / aiosqlite). RESEARCH §11 schema verbatim;
Phase 5 (INT-05) extends via ``ALTER TABLE ADD COLUMN``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _make_metrics(text: str = "שלום עולם"):
    from receptra.stt.metrics import UtteranceMetrics, new_utterance_id, utc_now_iso

    return UtteranceMetrics(
        utterance_id=new_utterance_id(),
        ts_utc=utc_now_iso(),
        t_speech_start_ms=500,
        t_speech_end_ms=1500,
        t_final_ready_ms=1900,
        duration_ms=1000,
        transcribe_ms=350,
        partials_emitted=1,
        text=text,
        text_len_chars=len(text),
        wer_sample_id=None,
    )


def test_init_creates_table(tmp_path: Path) -> None:
    """T1 — init_audit_db creates ``stt_utterances`` (RESEARCH §11)."""
    from receptra.stt.audit import init_audit_db

    db = tmp_path / "audit.sqlite"
    init_audit_db(db)
    assert db.exists()

    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()

    assert ("stt_utterances",) in rows


def test_insert_roundtrip(tmp_path: Path) -> None:
    """T2 — insert + select-by-id preserves every field byte-exact."""
    from receptra.stt.audit import init_audit_db, insert_stt_utterance

    db = tmp_path / "audit.sqlite"
    init_audit_db(db)

    m = _make_metrics()
    insert_stt_utterance(db, m)

    with sqlite3.connect(str(db)) as conn:
        row = conn.execute(
            """
            SELECT utterance_id, ts_utc, duration_ms, stt_latency_ms,
                   transcribe_ms, partials_emitted, text, wer_sample_id
            FROM stt_utterances WHERE utterance_id = ?
            """,
            (m.utterance_id,),
        ).fetchone()

    assert row is not None
    (uid, ts_utc, dur, lat, tr, pe, text, wer_sid) = row
    assert uid == m.utterance_id
    assert ts_utc == m.ts_utc
    assert dur == m.duration_ms
    assert lat == m.stt_latency_ms
    assert tr == m.transcribe_ms
    assert pe == m.partials_emitted
    assert text == m.text
    assert wer_sid == m.wer_sample_id


def test_init_is_idempotent(tmp_path: Path) -> None:
    """T3 — calling init twice is a no-op + no exception."""
    from receptra.stt.audit import init_audit_db

    db = tmp_path / "audit.sqlite"
    init_audit_db(db)
    init_audit_db(db)  # must not raise

    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stt_utterances'"
        ).fetchall()
    assert len(rows) == 1


def test_insert_preserves_hebrew_text(tmp_path: Path) -> None:
    """T4 — Hebrew NFC + niqqud round-trips via SQLite without normalisation."""
    from receptra.stt.audit import init_audit_db, insert_stt_utterance

    db = tmp_path / "audit.sqlite"
    init_audit_db(db)

    hebrew = "שָׁלוֹם עולם"  # NFC composed + niqqud retained
    m = _make_metrics(text=hebrew)
    insert_stt_utterance(db, m)

    with sqlite3.connect(str(db)) as conn:
        (got_text,) = conn.execute(
            "SELECT text FROM stt_utterances WHERE utterance_id = ?",
            (m.utterance_id,),
        ).fetchone()

    assert got_text == hebrew  # byte-exact, no normalisation


def test_init_creates_parent_dir(tmp_path: Path) -> None:
    """T5 (T-02-06-06 mitigation) — init creates parent dirs lazily."""
    from receptra.stt.audit import init_audit_db

    db = tmp_path / "nested" / "subdir" / "audit.sqlite"
    assert not db.parent.exists()
    init_audit_db(db)
    assert db.exists()


def test_insert_without_init_raises(tmp_path: Path) -> None:
    """T6 — sanity: insert before init raises (sqlite3.OperationalError)."""
    from receptra.stt.audit import insert_stt_utterance

    db = tmp_path / "audit.sqlite"
    m = _make_metrics()
    with pytest.raises(sqlite3.OperationalError):
        insert_stt_utterance(db, m)
