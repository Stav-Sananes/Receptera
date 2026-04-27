"""Hebrew document ingest pipeline (RAG-03 ingest half).

Pipeline: filename + bytes → ext+size+UTF-8 gates → chunk_hebrew → embed_batch
          → delete-existing-where-filename → collection.add → IngestResult.

Pitfall #8 mitigation: re-ingest of same filename DELETES prior chunks
BEFORE adding new ones. chunks_replaced count surfaced to caller.

D-09 lock: ALLOWED_EXTS = {".md", ".txt"} only; MAX_BYTES = 1 MiB.
D-03 lock: all sync chromadb calls wrapped via asyncio.to_thread.
D-02 lock: embedder is injected — never construct AsyncClient here.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from receptra.rag.chunker import chunk_hebrew
from receptra.rag.errors import IngestRejected
from receptra.rag.schema import IngestResult

if TYPE_CHECKING:
    from chromadb.api.models.Collection import Collection

    from receptra.rag.embeddings import BgeM3Embedder

ALLOWED_EXTS: frozenset[str] = frozenset({".md", ".txt"})
MAX_BYTES: int = 1_048_576  # 1 MiB (D-09 lock)


def _validate_extension(filename: str) -> None:
    lower = filename.lower()
    if not any(lower.endswith(ext) for ext in ALLOWED_EXTS):
        raise IngestRejected(
            code="unsupported_extension",
            detail=f"Only {sorted(ALLOWED_EXTS)} accepted in v1; got {filename!r}",
        )


def _validate_size(content: bytes) -> None:
    if len(content) > MAX_BYTES:
        raise IngestRejected(
            code="file_too_large",
            detail=f"{len(content)} bytes > {MAX_BYTES} byte limit",
        )


def _decode_utf8_strict(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise IngestRejected(
            code="encoding_error",
            detail="File must be UTF-8 (strict). Save as UTF-8 and re-upload.",
        ) from e


async def ingest_document(
    *,
    filename: str,
    content: bytes,
    embedder: BgeM3Embedder,
    collection: Collection,
) -> IngestResult:
    """Ingest one Hebrew .md/.txt document into the RAG collection.

    Args:
        filename: original filename (extension used for allowlist check;
            stored as metadata only — never used as a filesystem path).
        content: raw file bytes (UTF-8 strict; max 1 MiB).
        embedder: BgeM3Embedder instance (injected by lifespan / test).
        collection: ChromaDB Collection (injected by lifespan / test).

    Returns:
        IngestResult with chunks_added, chunks_replaced, bytes_ingested.

    Raises:
        IngestRejected: if extension, size, encoding, or content validation fails.
    """
    _validate_extension(filename)
    _validate_size(content)
    text = _decode_utf8_strict(content)

    doc_sha = hashlib.sha256(content).hexdigest()
    chunks = chunk_hebrew(text)
    if not chunks:
        raise IngestRejected(
            code="empty_after_chunking",
            detail="No content after Hebrew normalization + chunking",
        )

    # Delete-before-add: re-ingest of same filename replaces prior chunks cleanly.
    # RESEARCH §Pitfall 8: re-ingest WITHOUT delete doubles chunk count silently.
    # asyncio.to_thread per D-03 (sync chromadb HttpClient must not block event loop).
    existing = await asyncio.to_thread(collection.get, where={"filename": filename})
    chunks_replaced = len(existing["ids"])
    if chunks_replaced:
        await asyncio.to_thread(collection.delete, ids=existing["ids"])

    embeddings = await embedder.embed_batch([c.text for c in chunks])
    ingested_at = datetime.now(UTC).isoformat()

    await asyncio.to_thread(
        collection.add,
        ids=[f"{doc_sha[:8]}:{c.chunk_index}" for c in chunks],
        documents=[c.text for c in chunks],
        embeddings=embeddings,  # type: ignore[arg-type]
        metadatas=[
            {
                "filename": filename,
                "chunk_index": c.chunk_index,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "doc_sha": doc_sha,
                "ingested_at_iso": ingested_at,
                "tenant_id": None,  # RESEARCH §Open Decision 4 v2 forward-compat
            }
            for c in chunks
        ],
    )

    return IngestResult(
        filename=filename,
        chunks_added=len(chunks),
        chunks_replaced=chunks_replaced,
        bytes_ingested=len(content),
    )


__all__ = ["ALLOWED_EXTS", "MAX_BYTES", "ingest_document"]
