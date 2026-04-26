"""Smoke: live Ollama BGE-M3 returns 1024-dim Hebrew embeddings.

Self-skips on every CI executor (RECEPTRA_RAG_LIVE_TEST unset). First Mac
contributor with `make models-bge` complete runs:

    RECEPTRA_RAG_LIVE_TEST=1 uv run pytest backend/tests/rag/test_ollama_embed_smoke.py -x

Triple-gate skip mirrors Plan 03-01 ChatML test pattern:

1. ``RECEPTRA_RAG_LIVE_TEST=1`` (RAG live-test gate — separate from LLM gate)
2. ``ollama`` binary on PATH (ensures host Ollama is installed)
3. ``client.show("bge-m3")`` round-trip (ensures the model is actually pulled)

All three must succeed for the live assert to run. CI executors fail at gate 1.
"""

from __future__ import annotations

import shutil

import pytest

from receptra.config import settings
from tests.rag.conftest import rag_live_test_enabled

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_bge_m3_returns_1024dim_for_hebrew() -> None:
    if not rag_live_test_enabled():
        pytest.skip("set RECEPTRA_RAG_LIVE_TEST=1 to run live RAG (Ollama bge-m3) tests")
    if shutil.which("ollama") is None:
        pytest.skip("ollama binary not on PATH")
    from ollama import AsyncClient

    client = AsyncClient(host=settings.ollama_host)
    # Verify model is pulled before round-trip (clear failure mode).
    try:
        await client.show("bge-m3")
    except Exception as e:
        pytest.skip(f"bge-m3 not pulled (run `make models-bge`): {e}")

    resp = await client.embed(model="bge-m3", input="שלום עולם")
    assert len(resp.embeddings) == 1
    # RESEARCH §Cluster 2: BGE-M3 publishes 1024-dim dense vectors.
    assert len(resp.embeddings[0]) == 1024
