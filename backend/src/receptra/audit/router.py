"""HTTP routes for /api/audit/* — operator-facing observability endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from receptra.audit.stats import read_stats
from receptra.config import settings

router = APIRouter()


@router.get("/stats")
async def get_stats() -> dict:
    """Aggregate counts + latency percentiles over the audit DB.

    Returns ``{all_time, last_24h}`` — both windows surface n_utterances,
    n_pipeline_runs, avg/p95 STT + e2e latencies, and the share of runs
    that hit RAG-degraded fallback.
    """
    now = datetime.now(UTC)
    since_24h = (now - timedelta(hours=24)).isoformat()
    return read_stats(settings.audit_db_path, since_iso_24h=since_24h)


__all__ = ["router"]
