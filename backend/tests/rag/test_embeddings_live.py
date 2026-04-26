"""Live BGE-M3 round-trip — gated by RECEPTRA_RAG_LIVE_TEST=1.

Self-skips on every CI executor + every developer machine without bge-m3
pulled. First Mac contributor with `make models-bge` complete runs:

    RECEPTRA_RAG_LIVE_TEST=1 uv run pytest backend/tests/rag/test_embeddings_live.py -x

and confirms the 1024-dim Hebrew round-trip via the production wrapper.

Triple-gate skip pattern (Plan 03-01 ChatML test precedent):
1. ``RECEPTRA_RAG_LIVE_TEST=1`` (RAG live-test gate)
2. ``ollama`` binary on PATH (host Ollama installed)
3. ``BgeM3Embedder.create_and_verify()`` round-trip (model is actually pulled)
"""
from __future__ import annotations

import shutil

import pytest

from tests.rag.conftest import rag_live_test_enabled

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_bge_m3_embed_one_round_trip() -> None:
    if not rag_live_test_enabled():
        pytest.skip("set RECEPTRA_RAG_LIVE_TEST=1 to run")
    if shutil.which("ollama") is None:
        pytest.skip("ollama binary not on PATH")
    from receptra.rag.embeddings import BgeM3Embedder
    from receptra.rag.errors import RagInitError

    try:
        embedder = await BgeM3Embedder.create_and_verify()
    except RagInitError as e:
        pytest.skip(f"bge-m3 not pulled (run `make models-bge`): {e}")

    v = await embedder.embed_one("שלום עולם")
    assert len(v) == 1024
    assert all(isinstance(x, float) for x in v)


@pytest.mark.asyncio
async def test_bge_m3_embed_batch_round_trip() -> None:
    if not rag_live_test_enabled():
        pytest.skip("set RECEPTRA_RAG_LIVE_TEST=1 to run")
    if shutil.which("ollama") is None:
        pytest.skip("ollama binary not on PATH")
    from receptra.rag.embeddings import BgeM3Embedder
    from receptra.rag.errors import RagInitError

    try:
        embedder = await BgeM3Embedder.create_and_verify()
    except RagInitError as e:
        pytest.skip(f"bge-m3 not pulled: {e}")

    texts = ["שלום עולם", "מה שעות הפתיחה?", "מדיניות החזרות"]
    vectors = await embedder.embed_batch(texts, batch_size=2)
    assert len(vectors) == 3
    assert all(len(v) == 1024 for v in vectors)
