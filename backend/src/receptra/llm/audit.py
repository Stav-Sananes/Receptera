"""SQLite audit log for the LLM suggestion engine (LLM-05).

Mirrors ``receptra.stt.audit`` (Plan 02-06) deliberately: stdlib ``sqlite3``
only — no SQLAlchemy / aiosqlite (RESEARCH §Recommended Dependencies
"Intentionally NOT added"); per-call connection inside ``with sqlite3.connect``
for atomic commits + zero thread-safety concerns; idempotent
``CREATE TABLE IF NOT EXISTS`` so this co-exists cleanly with the
``stt_utterances`` table on the same file.

Schema is RESEARCH §6.4 verbatim. Phase 5 INT-05 may extend via
``ALTER TABLE ADD COLUMN`` (CREATE IF NOT EXISTS is forward-compatible).

T-02-06-06 inheritance:
    Parent-dir creation is lazy (mirrors ``receptra.stt.audit``) so a
    docker-compose volume bind onto a host without ``./data`` pre-existing
    still works on first call.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from receptra.llm.metrics import LlmCallMetrics


_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id      TEXT    NOT NULL,
    transcript_hash TEXT    NOT NULL,
    model           TEXT    NOT NULL,
    n_chunks        INTEGER NOT NULL,
    ttft_ms         INTEGER NOT NULL,
    total_ms        INTEGER NOT NULL,
    eval_count      INTEGER,
    prompt_eval_count INTEGER,
    suggestions_count INTEGER NOT NULL,
    grounded        INTEGER NOT NULL,
    status          TEXT    NOT NULL,
    ts              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

_INDEX_TS = "CREATE INDEX IF NOT EXISTS idx_llm_calls_ts ON llm_calls(ts);"
_INDEX_STATUS = (
    "CREATE INDEX IF NOT EXISTS idx_llm_calls_status ON llm_calls(status);"
)


def init_llm_audit_table(path: str | Path) -> None:
    """Idempotent. Create parent dir + ``llm_calls`` table + indexes if missing."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(p)) as conn:
        conn.execute(_SCHEMA)
        conn.execute(_INDEX_TS)
        conn.execute(_INDEX_STATUS)
        conn.commit()


def insert_llm_call(path: str | Path, m: LlmCallMetrics) -> None:
    """Insert one row.

    Caller must have invoked ``init_llm_audit_table`` first; this function
    deliberately does NOT lazy-init so a missing-table scenario surfaces as
    ``sqlite3.OperationalError`` (mirrors STT audit Plan 02-06 pattern).
    """
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """
            INSERT INTO llm_calls
                (request_id, transcript_hash, model, n_chunks,
                 ttft_ms, total_ms, eval_count, prompt_eval_count,
                 suggestions_count, grounded, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                m.request_id,
                m.transcript_hash,
                m.model,
                m.n_chunks,
                m.ttft_ms,
                m.total_ms,
                m.eval_count,
                m.prompt_eval_count,
                m.suggestions_count,
                1 if m.grounded else 0,
                m.status,
            ),
        )
        conn.commit()


__all__ = ["init_llm_audit_table", "insert_llm_call"]
