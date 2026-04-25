"""SQLite audit log stub (Phase 2; Phase 5 owns final INT-05 schema).

Stdlib ``sqlite3`` only — no SQLAlchemy / aiosqlite (RESEARCH
§Recommended Dependencies "Intentionally NOT added"). ``sqlite3``
connections are NOT safe to share across threads; each call opens +
closes within a ``with`` block.

Schema verbatim from RESEARCH §11. Phase 5's INT-05 plan extends via
``ALTER TABLE ADD COLUMN`` — ``CREATE TABLE IF NOT EXISTS`` is forward
compatible.

T-02-06-03 mitigation:
    The INSERT happens ONLY after a complete ``UtteranceMetrics`` is
    constructed in the pipeline (i.e., after final transcript is sent).
    Half-written rows are impossible because ``with sqlite3.connect``
    commits atomically per block. The chaos test
    (``test_chaos_disconnect.py``) is a regression guard.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from receptra.stt.metrics import UtteranceMetrics

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stt_utterances (
    utterance_id TEXT PRIMARY KEY,
    ts_utc TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    stt_latency_ms INTEGER NOT NULL,
    transcribe_ms INTEGER NOT NULL,
    partials_emitted INTEGER NOT NULL,
    text TEXT NOT NULL,
    wer_sample_id TEXT
);
"""


def init_audit_db(path: str | Path) -> None:
    """Idempotent. Create parent dir + table if missing.

    Parent-dir creation is the T-02-06-06 mitigation (docker-compose
    volume bind on a host without ./data pre-existing).
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(p)) as conn:
        conn.execute(_SCHEMA)
        conn.commit()


def insert_stt_utterance(path: str | Path, m: UtteranceMetrics) -> None:
    """Insert one row.

    Caller must have invoked ``init_audit_db`` before first use; this
    function deliberately does NOT lazy-init so that
    ``test_insert_without_init_raises`` is green and Phase 5 cannot
    accidentally race on schema migrations.
    """
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """
            INSERT INTO stt_utterances
                (utterance_id, ts_utc, duration_ms, stt_latency_ms,
                 transcribe_ms, partials_emitted, text, wer_sample_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                m.utterance_id,
                m.ts_utc,
                m.duration_ms,
                m.stt_latency_ms,
                m.transcribe_ms,
                m.partials_emitted,
                m.text,
                m.wer_sample_id,
            ),
        )
        conn.commit()


__all__ = ["init_audit_db", "insert_stt_utterance"]
