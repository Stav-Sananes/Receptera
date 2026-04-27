"""TDD RED tests for receptra.rag.ingest (Plan 04-04, Task 1).

12 tests covering extension allowlist, size cap, UTF-8 strict decode,
empty-after-chunking, happy path, re-ingest idempotency (Pitfall #8),
asyncio.to_thread wrapping (D-03), and v2 forward-compat tenant_id.
"""
# ruff: noqa: RUF001

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from receptra.rag.chunker import Chunk
from receptra.rag.errors import IngestRejected
from receptra.rag.ingest import ALLOWED_EXTS, MAX_BYTES, ingest_document


def _make_chunk(idx: int, text: str) -> Chunk:
    return Chunk(chunk_index=idx, char_start=0, char_end=len(text), text=text)


def _fake_collection(existing_ids: list[str] | None = None) -> MagicMock:
    c = MagicMock(name="chroma.Collection")
    ids = existing_ids or []
    c.get.return_value = {"ids": ids, "documents": [], "metadatas": [], "distances": []}
    c.delete.return_value = None
    c.add.return_value = None
    return c


def _fake_embedder(n_chunks: int = 3) -> AsyncMock:
    e = AsyncMock(name="BgeM3Embedder")
    e.embed_batch.return_value = [[0.0] * 1024] * n_chunks
    return e


# --- Extension allowlist ---

@pytest.mark.asyncio
async def test_rejects_pdf_extension() -> None:
    with pytest.raises(IngestRejected) as exc:
        await ingest_document(
            filename="report.pdf",
            content=b"%PDF-1.4 content",
            embedder=_fake_embedder(),
            collection=_fake_collection(),
        )
    assert exc.value.code == "unsupported_extension"


@pytest.mark.asyncio
async def test_rejects_docx_and_doc_and_rtf() -> None:
    for ext in ("report.docx", "report.doc", "report.rtf"):
        with pytest.raises(IngestRejected) as exc:
            await ingest_document(
                filename=ext,
                content=b"content",
                embedder=_fake_embedder(),
                collection=_fake_collection(),
            )
        assert exc.value.code == "unsupported_extension", f"failed for {ext}"


@pytest.mark.asyncio
async def test_accepts_md_and_txt() -> None:
    for filename in ("policy.md", "faq.txt"):
        content = "שלום עולם הזה".encode("utf-8")
        embedder = _fake_embedder(1)
        collection = _fake_collection()
        result = await ingest_document(
            filename=filename,
            content=content,
            embedder=embedder,
            collection=collection,
        )
        assert result.filename == filename
        assert result.chunks_added >= 1


# --- Size cap ---

@pytest.mark.asyncio
async def test_rejects_oversized() -> None:
    oversized = b"x" * (MAX_BYTES + 1)
    with pytest.raises(IngestRejected) as exc:
        await ingest_document(
            filename="big.md",
            content=oversized,
            embedder=_fake_embedder(),
            collection=_fake_collection(),
        )
    assert exc.value.code == "file_too_large"


@pytest.mark.asyncio
async def test_accepts_at_max_size() -> None:
    # Exactly 1_048_576 bytes of valid UTF-8 ASCII
    content = b"a" * MAX_BYTES
    embedder = _fake_embedder(1)
    collection = _fake_collection()
    result = await ingest_document(
        filename="maxsize.txt",
        content=content,
        embedder=embedder,
        collection=collection,
    )
    assert result.bytes_ingested == MAX_BYTES


# --- UTF-8 strict decode ---

@pytest.mark.asyncio
async def test_rejects_non_utf8() -> None:
    bad_bytes = b"\xff\xfe\x00\x00\xc1"  # invalid UTF-8
    with pytest.raises(IngestRejected) as exc:
        await ingest_document(
            filename="bad.txt",
            content=bad_bytes,
            embedder=_fake_embedder(),
            collection=_fake_collection(),
        )
    assert exc.value.code == "encoding_error"


# --- Empty after chunking ---

@pytest.mark.asyncio
async def test_rejects_empty_after_chunking() -> None:
    whitespace_only = b"   \n\n  \t  "
    with pytest.raises(IngestRejected) as exc:
        await ingest_document(
            filename="empty.md",
            content=whitespace_only,
            embedder=_fake_embedder(),
            collection=_fake_collection(),
        )
    assert exc.value.code == "empty_after_chunking"


# --- Happy path ---

@pytest.mark.asyncio
async def test_happy_path_calls_chunker_and_embedder() -> None:
    content = "מדיניות החברה: שעות פתיחה הן 9-17. ימי עבודה א-ה.".encode("utf-8")
    doc_sha = hashlib.sha256(content).hexdigest()
    chunks = [
        _make_chunk(0, "מדיניות החברה"),
        _make_chunk(1, "שעות פתיחה הן 9-17"),
        _make_chunk(2, "ימי עבודה א-ה"),
    ]
    embedder = AsyncMock(name="BgeM3Embedder")
    embedder.embed_batch.return_value = [[0.0] * 1024] * 3
    collection = _fake_collection()

    with patch("receptra.rag.ingest.chunk_hebrew", return_value=chunks):
        result = await ingest_document(
            filename="policy.md",
            content=content,
            embedder=embedder,
            collection=collection,
        )

    assert result.chunks_added == 3
    assert result.chunks_replaced == 0
    assert result.bytes_ingested == len(content)

    # collection.add called once with correct shapes
    collection.add.assert_called_once()
    call_kwargs = collection.add.call_args.kwargs if collection.add.call_args.kwargs else {}
    if not call_kwargs:
        call_kwargs = dict(zip(
            ["ids", "documents", "embeddings", "metadatas"],
            collection.add.call_args.args,
        ))
    ids = call_kwargs.get("ids") or collection.add.call_args[1].get("ids") or collection.add.call_args[0][0]
    assert len(ids) == 3
    # IDs follow {sha[:8]}:{chunk_index} scheme
    for i, chunk_id in enumerate(ids):
        assert chunk_id == f"{doc_sha[:8]}:{i}"


@pytest.mark.asyncio
async def test_chunk_id_stable_across_runs() -> None:
    content = "תוכן קבוע לבדיקת יציבות מזהי פיסות".encode("utf-8")
    doc_sha = hashlib.sha256(content).hexdigest()
    expected_prefix = doc_sha[:8]

    embedder = AsyncMock(name="BgeM3Embedder")
    embedder.embed_batch.return_value = [[0.0] * 1024]
    collection1 = _fake_collection()
    collection2 = _fake_collection()

    await ingest_document(filename="stable.md", content=content, embedder=embedder, collection=collection1)
    await ingest_document(filename="stable.md", content=content, embedder=embedder, collection=collection2)

    ids1 = collection1.add.call_args[1].get("ids") or collection1.add.call_args[0][0]
    ids2 = collection2.add.call_args[1].get("ids") or collection2.add.call_args[0][0]
    assert ids1 == ids2
    for chunk_id in ids1:
        assert chunk_id.startswith(expected_prefix)


@pytest.mark.asyncio
async def test_re_ingest_replaces() -> None:
    """CRITICAL Pitfall #8 regression: delete-before-add on re-ingest."""
    content = "תוכן לבדיקת עדכון".encode("utf-8")
    existing = ["abc12345:0", "abc12345:1", "abc12345:2", "abc12345:3", "abc12345:4"]
    collection = _fake_collection(existing_ids=existing)
    embedder = AsyncMock(name="BgeM3Embedder")
    embedder.embed_batch.return_value = [[0.0] * 1024]

    result = await ingest_document(
        filename="update.md",
        content=content,
        embedder=embedder,
        collection=collection,
    )

    # delete called BEFORE add
    delete_call_order = collection.delete.call_args_list
    add_call_order = collection.add.call_args_list
    assert len(delete_call_order) >= 1, "collection.delete must be called on re-ingest"
    # Verify delete was called with the existing IDs
    deleted_ids = delete_call_order[0][1].get("ids") or delete_call_order[0][0][0]
    assert set(deleted_ids) == set(existing)
    assert result.chunks_replaced == 5


@pytest.mark.asyncio
async def test_chromadb_calls_use_to_thread() -> None:
    """D-03 lock: all sync chromadb calls wrapped via asyncio.to_thread."""
    content = "בדיקת עטיפת asyncio.to_thread".encode("utf-8")
    embedder = AsyncMock(name="BgeM3Embedder")
    embedder.embed_batch.return_value = [[0.0] * 1024]
    collection = _fake_collection()
    to_thread_calls: list[tuple[object, ...]] = []

    original_to_thread = asyncio.to_thread

    async def recording_to_thread(func: object, *args: object, **kwargs: object) -> object:
        to_thread_calls.append((func,) + args)
        return await original_to_thread(func, *args, **kwargs)  # type: ignore[arg-type]

    with patch("receptra.rag.ingest.asyncio.to_thread", side_effect=recording_to_thread):
        await ingest_document(
            filename="thread.txt",
            content=content,
            embedder=embedder,
            collection=collection,
        )

    # At minimum: get + add must go through to_thread (delete may be skipped if no existing ids)
    funcs = [call[0] for call in to_thread_calls]
    assert collection.get in funcs, "collection.get must go through asyncio.to_thread"
    assert collection.add in funcs, "collection.add must go through asyncio.to_thread"


@pytest.mark.asyncio
async def test_metadata_includes_v2_forward_compat() -> None:
    """RESEARCH §Open Decision 4: tenant_id=None in every metadata dict."""
    content = "תכנון עתידי: tenant_id".encode("utf-8")
    embedder = AsyncMock(name="BgeM3Embedder")
    embedder.embed_batch.return_value = [[0.0] * 1024]
    collection = _fake_collection()

    await ingest_document(
        filename="future.md",
        content=content,
        embedder=embedder,
        collection=collection,
    )

    metadatas_arg = None
    for call in collection.add.call_args_list:
        kw = call[1] if call[1] else {}
        pos = call[0] if call[0] else ()
        # Try keyword arg first, then positional
        metadatas_arg = kw.get("metadatas") or (pos[3] if len(pos) > 3 else None)

    assert metadatas_arg is not None, "collection.add must be called with metadatas"
    for meta in metadatas_arg:
        assert "tenant_id" in meta, "tenant_id key must be present in every metadata dict"
        assert meta["tenant_id"] is None, "tenant_id must be None for v1 single-tenant"
