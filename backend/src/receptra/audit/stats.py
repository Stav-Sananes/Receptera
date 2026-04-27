"""Read-only aggregate stats over the audit DB.

Powers ``GET /api/audit/stats`` — surfaces total counts, latency
aggregates (avg/p95), and a 24h window so an operator can see whether
the system is meeting the <2s e2e target without grepping JSON logs.

PII: this module reads ONLY counts + numeric latency columns. Raw text
columns stay in SQLite and never leave the host.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class StatsWindow:
    """One row per time window (e.g. all-time or last 24h)."""

    label: str
    n_utterances: int
    n_pipeline_runs: int
    avg_stt_latency_ms: float | None
    p95_stt_latency_ms: int | None
    avg_e2e_latency_ms: float | None
    p95_e2e_latency_ms: int | None
    pct_rag_degraded: float
    pct_low_confidence: float | None


_QUERY_AGG = """
SELECT
    COUNT(DISTINCT u.utterance_id)                                AS n_utterances,
    COUNT(p.utterance_id)                                         AS n_pipeline_runs,
    AVG(u.stt_latency_ms)                                         AS avg_stt,
    AVG(p.e2e_latency_ms)                                         AS avg_e2e,
    SUM(CASE WHEN p.status = 'rag_degraded' THEN 1 ELSE 0 END)    AS n_rag_degraded
FROM stt_utterances u
LEFT JOIN pipeline_runs p ON p.utterance_id = u.utterance_id
WHERE (? IS NULL OR u.ts_utc >= ?)
"""

_QUERY_LATENCIES = """
SELECT
    u.stt_latency_ms AS stt_ms,
    p.e2e_latency_ms AS e2e_ms
FROM stt_utterances u
LEFT JOIN pipeline_runs p ON p.utterance_id = u.utterance_id
WHERE (? IS NULL OR u.ts_utc >= ?)
"""


def _percentile(values: list[int], pct: float) -> int | None:
    """Discrete-rank p95 (no interpolation). Returns None for empty input."""
    if not values:
        return None
    sorted_values = sorted(values)
    idx = max(0, min(len(sorted_values) - 1, int(len(sorted_values) * pct)))
    return sorted_values[idx]


def _read_window(
    conn: sqlite3.Connection,
    label: str,
    since_iso: str | None,
) -> StatsWindow:
    cur = conn.execute(_QUERY_AGG, (since_iso, since_iso))
    row = cur.fetchone()
    n_utt, n_pipe, avg_stt, avg_e2e, n_rag_deg = row

    cur2 = conn.execute(_QUERY_LATENCIES, (since_iso, since_iso))
    rows = cur2.fetchall()
    stt_values = [r[0] for r in rows if r[0] is not None]
    e2e_values = [r[1] for r in rows if r[1] is not None]

    pct_rag_deg = (n_rag_deg / n_pipe) if n_pipe > 0 else 0.0

    return StatsWindow(
        label=label,
        n_utterances=n_utt or 0,
        n_pipeline_runs=n_pipe or 0,
        avg_stt_latency_ms=avg_stt,
        p95_stt_latency_ms=_percentile(stt_values, 0.95),
        avg_e2e_latency_ms=avg_e2e,
        p95_e2e_latency_ms=_percentile(e2e_values, 0.95),
        pct_rag_degraded=pct_rag_deg,
        # Confidence flag isn't stored on pipeline_runs (yet) — leave null
        # so the schema is forward-compatible if we extend the table later.
        pct_low_confidence=None,
    )


def read_stats(path: str | Path, since_iso_24h: str | None = None) -> dict:
    """Return all-time + 24h aggregate stats from the audit DB.

    Args:
        path: Path to the audit SQLite file.
        since_iso_24h: ISO-8601 timestamp (UTC) for the 24h window. If
            None, only the all-time window is returned.

    Returns:
        ``{"all_time": StatsWindow-as-dict, "last_24h": StatsWindow | null}``
    """
    p = Path(path)
    if not p.exists():
        # Empty audit DB — return zeroed stats rather than 500.
        empty = StatsWindow(
            label="all_time",
            n_utterances=0,
            n_pipeline_runs=0,
            avg_stt_latency_ms=None,
            p95_stt_latency_ms=None,
            avg_e2e_latency_ms=None,
            p95_e2e_latency_ms=None,
            pct_rag_degraded=0.0,
            pct_low_confidence=None,
        )
        return {"all_time": asdict(empty), "last_24h": None}

    with sqlite3.connect(str(p)) as conn:
        all_time = _read_window(conn, "all_time", None)
        last_24h = (
            _read_window(conn, "last_24h", since_iso_24h) if since_iso_24h else None
        )
    return {
        "all_time": asdict(all_time),
        "last_24h": asdict(last_24h) if last_24h else None,
    }


__all__ = ["StatsWindow", "read_stats"]
