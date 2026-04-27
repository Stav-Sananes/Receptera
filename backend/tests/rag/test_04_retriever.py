"""TDD RED tests for receptra.rag.retriever (Plan 04-04, Task 1).

10 tests covering ChunkRef class identity, query passthrough, top_k passthrough,
min_similarity filtering, settings default threshold, empty result path,
source metadata shape, asyncio.to_thread wrap, and include= contract.
"""
# ruff: noqa: RUF001

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from receptra.llm.schema import ChunkRef as LlmChunkRef
from receptra.rag.retriever import retrieve


def _make_query_result(
    ids: list[str],
    docs: list[str],
    metas: list[dict],  # type: ignore[type-arg]
    distances: list[float],
) -> dict:  # type: ignore[type-arg]
    return {
        "ids": [ids],
        "documents": [docs],
        "metadatas": [metas],
        "distances": [distances],
    }


def _meta(filename: str = "policy.md", idx: int = 0, cs: int = 0, ce: int = 10) -> dict:  # type: ignore[type-arg]
    return {
        "filename": filename,
        "chunk_index": idx,
        "char_start": cs,
        "char_end": ce,
        "doc_sha": "abcd1234",
        "ingested_at_iso": "2026-04-27T12:00:00+00:00",
        "tenant_id": None,
    }


def _fake_embedder() -> AsyncMock:
    e = AsyncMock(name="BgeM3Embedder")
    e.embed_one.return_value = [0.0] * 1024
    return e


def _fake_collection(result: dict | None = None) -> MagicMock:  # type: ignore[type-arg]
    c = MagicMock(name="chroma.Collection")
    c.query.return_value = result or _make_query_result([], [], [], [])
    return c


@pytest.mark.asyncio
async def test_returns_chunkrefs() -> None:
    result = _make_query_result(
        ["id1"], ["שלום"], [_meta()], [0.1]  # similarity = 0.9
    )
    embedder = _fake_embedder()
    collection = _fake_collection(result)

    refs = await retrieve(query="שלום", top_k=1, embedder=embedder, collection=collection, min_similarity=0.0)
    assert len(refs) == 1
    assert isinstance(refs[0], LlmChunkRef)


@pytest.mark.asyncio
async def test_chunkref_class_identity() -> None:
    """Plan 04-01 contract: retriever returns receptra.llm.schema.ChunkRef instances."""
    result = _make_query_result(
        ["id1", "id2"],
        ["chunk1", "chunk2"],
        [_meta(), _meta(idx=1)],
        [0.05, 0.2],  # similarities 0.95, 0.8
    )
    embedder = _fake_embedder()
    collection = _fake_collection(result)

    refs = await retrieve(query="x", top_k=2, embedder=embedder, collection=collection, min_similarity=0.0)
    assert all(isinstance(r, LlmChunkRef) for r in refs)
    # Import via alias must be the SAME class
    from receptra.rag.types import ChunkRef as RagChunkRef
    assert LlmChunkRef is RagChunkRef


@pytest.mark.asyncio
async def test_query_passed_to_embedder() -> None:
    embedder = _fake_embedder()
    collection = _fake_collection()

    await retrieve(query="מה שעות הפתיחה", top_k=5, embedder=embedder, collection=collection)
    embedder.embed_one.assert_awaited_once_with("מה שעות הפתיחה")


@pytest.mark.asyncio
async def test_top_k_passed_to_collection() -> None:
    embedder = _fake_embedder()
    collection = _fake_collection()

    await retrieve(query="x", top_k=7, embedder=embedder, collection=collection, min_similarity=0.0)
    call_kwargs = collection.query.call_args[1] if collection.query.call_args[1] else {}
    n_results = call_kwargs.get("n_results") or collection.query.call_args[0][1]
    assert n_results == 7


@pytest.mark.asyncio
async def test_filters_below_min_similarity() -> None:
    # distances [0.1, 0.5, 0.8] → similarities [0.9, 0.5, 0.2]
    result = _make_query_result(
        ["id1", "id2", "id3"],
        ["chunk1", "chunk2", "chunk3"],
        [_meta(idx=0), _meta(idx=1), _meta(idx=2)],
        [0.1, 0.5, 0.8],
    )
    embedder = _fake_embedder()
    collection = _fake_collection(result)

    refs = await retrieve(query="x", top_k=3, embedder=embedder, collection=collection, min_similarity=0.4)
    assert len(refs) == 2  # 0.9 and 0.5 pass; 0.2 filtered out


@pytest.mark.asyncio
async def test_uses_settings_default_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """No min_similarity kwarg → uses settings.rag_min_similarity."""
    from receptra import config as config_mod

    monkeypatch.setattr(config_mod.settings, "rag_min_similarity", 0.5)
    # similarity = 1 - 0.6 = 0.4 < 0.5 → filtered
    result = _make_query_result(
        ["id1"], ["chunk1"], [_meta()], [0.6]
    )
    embedder = _fake_embedder()
    collection = _fake_collection(result)

    refs = await retrieve(query="x", top_k=1, embedder=embedder, collection=collection)
    assert len(refs) == 0  # 0.4 < settings.rag_min_similarity (0.5)

    # Now set threshold to 0.3 → passes
    monkeypatch.setattr(config_mod.settings, "rag_min_similarity", 0.3)
    refs = await retrieve(query="x", top_k=1, embedder=embedder, collection=collection)
    assert len(refs) == 1  # 0.4 >= 0.3


@pytest.mark.asyncio
async def test_empty_result_when_all_below_threshold() -> None:
    result = _make_query_result(
        ["id1", "id2"],
        ["chunk1", "chunk2"],
        [_meta(), _meta(idx=1)],
        [0.9, 0.95],  # similarities 0.1, 0.05
    )
    embedder = _fake_embedder()
    collection = _fake_collection(result)

    refs = await retrieve(query="x", top_k=2, embedder=embedder, collection=collection, min_similarity=0.4)
    assert refs == []


@pytest.mark.asyncio
async def test_source_metadata_populated() -> None:
    import re
    result = _make_query_result(
        ["abc:0"],
        ["chunk text"],
        [_meta(filename="faq.md", idx=2, cs=100, ce=200)],
        [0.1],  # similarity = 0.9
    )
    embedder = _fake_embedder()
    collection = _fake_collection(result)

    refs = await retrieve(query="x", top_k=1, embedder=embedder, collection=collection, min_similarity=0.0)
    assert len(refs) == 1
    src = refs[0].source
    assert src is not None
    assert src["filename"] == "faq.md"
    assert src["chunk_index"] == "2"
    assert src["char_start"] == "100"
    assert src["char_end"] == "200"
    # similarity must be a 3-decimal float string
    assert re.match(r"^\d+\.\d{3}$", src["similarity"]), f"bad similarity format: {src['similarity']!r}"


@pytest.mark.asyncio
async def test_collection_query_uses_to_thread() -> None:
    """D-03 lock: collection.query wrapped via asyncio.to_thread."""
    embedder = _fake_embedder()
    collection = _fake_collection()
    to_thread_calls: list[object] = []

    original_to_thread = asyncio.to_thread

    async def recording_to_thread(func: object, *args: object, **kwargs: object) -> object:
        to_thread_calls.append(func)
        return await original_to_thread(func, *args, **kwargs)  # type: ignore[arg-type]

    with patch("receptra.rag.retriever.asyncio.to_thread", side_effect=recording_to_thread):
        await retrieve(query="x", top_k=3, embedder=embedder, collection=collection, min_similarity=0.0)

    assert collection.query in to_thread_calls, "collection.query must go through asyncio.to_thread"


@pytest.mark.asyncio
async def test_include_distances_metadatas_documents() -> None:
    """collection.query called with include=["documents", "metadatas", "distances"]."""
    embedder = _fake_embedder()
    collection = _fake_collection()

    await retrieve(query="x", top_k=3, embedder=embedder, collection=collection, min_similarity=0.0)

    call_kwargs = collection.query.call_args[1] if collection.query.call_args[1] else {}
    include = call_kwargs.get("include")
    if include is None:
        include = collection.query.call_args[0][2] if len(collection.query.call_args[0]) > 2 else None
    assert include is not None
    assert set(include) == {"documents", "metadatas", "distances"}
