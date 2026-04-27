"""Unified pipeline_runs SQLite audit table (Phase 5 INT-05).

Extends the existing ``stt_utterances`` table strategy: stdlib ``sqlite3``
only, per-call open+commit+close, no shared connections across threads.

Schema: one row per completed utterance pipeline run.
Nullable columns (rag_latency_ms, llm_ttft_ms, llm_total_ms, e2e_latency_ms)
accommodate the INT-04 degradation path where RAG or LLM is unavailable.

T-05-INT-05 mitigation (mirrors T-02-06-03):
    INSERT runs only after the full pipeline completes for one utterance.
    Half-written rows are impossible because ``with sqlite3.connect`` commits
    atomically per block.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineRunRecord:
    """Per-utterance pipeline telemetry row."""

    utterance_id: str        # FK to stt_utterances.utterance_id
    ts_utc: str              # ISO-8601 UTC timestamp of the pipeline run
    stt_latency_ms: int      # STT latency from t_speech_end to t_final_ready
    rag_latency_ms: int | None   # RAG embed+query; None if skipped
    llm_ttft_ms: int | None      # LLM time-to-first-token; None if error before token
    llm_total_ms: int | None     # Total LLM wall time; None if LLM error
    n_chunks: int            # Chunks retrieved (0 on degradation / empty KB)
    n_suggestions: int       # Suggestions in CompleteEvent (1 for canonical refusal)
    status: str              # 'ok' | 'rag_degraded' | 'llm_error' | 'no_context' | 'pipeline_error'
    e2e_latency_ms: int | None   # t_speech_end → suggestion_complete; None on error


_SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    utterance_id   TEXT PRIMARY KEY,
    ts_utc         TEXT NOT NULL,
    stt_latency_ms INTEGER NOT NULL,
    rag_latency_ms INTEGER,
    llm_ttft_ms    INTEGER,
    llm_total_ms   INTEGER,
    n_chunks       INTEGER NOT NULL DEFAULT 0,
    n_suggestions  INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL,
    e2e_latency_ms INTEGER
);
"""


def init_pipeline_db(path: str | Path) -> None:
    """Idempotent — create parent dir + pipeline_runs table if missing.

    Safe to call alongside ``receptra.stt.audit.init_audit_db`` on the
    same SQLite file; both use ``CREATE TABLE IF NOT EXISTS``.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(p)) as conn:
        conn.execute(_SCHEMA)
        conn.commit()


def insert_pipeline_run(path: str | Path, record: PipelineRunRecord) -> None:
    """Insert one pipeline run row.

    Caller must have called ``init_pipeline_db`` before first use — this
    function does NOT lazy-init so that ``test_insert_without_init_raises``
    stays green and Phase 7 cannot accidentally race on schema migrations.
    """
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """
            INSERT INTO pipeline_runs
                (utterance_id, ts_utc, stt_latency_ms, rag_latency_ms,
                 llm_ttft_ms, llm_total_ms, n_chunks, n_suggestions,
                 status, e2e_latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.utterance_id,
                record.ts_utc,
                record.stt_latency_ms,
                record.rag_latency_ms,
                record.llm_ttft_ms,
                record.llm_total_ms,
                record.n_chunks,
                record.n_suggestions,
                record.status,
                record.e2e_latency_ms,
            ),
        )
        conn.commit()


__all__ = ["PipelineRunRecord", "init_pipeline_db", "insert_pipeline_run"]
