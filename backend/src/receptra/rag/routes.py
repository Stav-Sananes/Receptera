"""FastAPI router for /api/kb/* (RAG-03 + RAG-04 + RAG-06).

6 endpoints exposing the RAG surface to the frontend (Phase 6 FE-06) and
evaluation tools (Plan 04-06 scripts/eval_rag.py). All routes pull
app.state.embedder + app.state.chroma_collection populated by lifespan.

HTTP status mapping (RESEARCH §REST API):
  unsupported_extension → 415, file_too_large → 413, encoding_error → 400,
  empty_after_chunking → 422, ollama_unreachable / chroma_unreachable → 503.

PII boundary: ``event="rag.ingest"`` and ``event="rag.query"`` log lines carry
structural metadata only — never chunk text body. Mirrors Phase 2/3 patterns.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from loguru import logger

from receptra.rag.errors import IngestRejected, RagInitError
from receptra.rag.ingest import MAX_BYTES, ingest_document
from receptra.rag.retriever import retrieve
from receptra.rag.schema import (
    IngestResult,
    IngestTextRequest,
    KbDocument,
    KbErrorResponse,
    KbQueryRequest,
)

router = APIRouter()

# --- Status mapping -----------------------------------------------------------

_INGEST_STATUS: dict[str, int] = {
    "unsupported_extension": 415,
    "file_too_large": 413,
    "encoding_error": 400,
    "empty_after_chunking": 422,
}
_RAG_INIT_STATUS: dict[str, int] = {
    "ollama_unreachable": 503,
    "chroma_unreachable": 503,
    "model_missing": 503,
}
_WIRE_CODE_REMAP: dict[str, str] = {
    "model_missing": "ollama_unreachable",  # collapse for wire contract
}


def _ingest_rejected_to_http(e: IngestRejected) -> HTTPException:
    return HTTPException(
        status_code=_INGEST_STATUS.get(e.code, 422),
        detail=KbErrorResponse(code=e.code, detail=e.detail).model_dump(),
    )


def _rag_init_to_http(e: RagInitError) -> HTTPException:
    wire_code = _WIRE_CODE_REMAP.get(e.code, e.code)
    return HTTPException(
        status_code=_RAG_INIT_STATUS.get(e.code, 503),
        detail=KbErrorResponse(
            code=wire_code,
            detail=e.detail,
        ).model_dump(),
    )


# --- Endpoints ----------------------------------------------------------------


@router.post("/upload", response_model=IngestResult)
async def upload_kb_doc(
    request: Request,
    file: UploadFile = File(...),  # noqa: B008
) -> IngestResult:
    """Multipart file upload (FE-06 entry). Streams body; enforces MAX_BYTES."""
    # Content-Length pre-check (RESEARCH §Cluster 4 — FastAPI cannot enforce
    # via Pydantic for UploadFile). 2x slack for multipart envelope overhead.
    cl = request.headers.get("content-length")
    if cl is not None and int(cl) > MAX_BYTES * 2:
        raise _ingest_rejected_to_http(
            IngestRejected(
                code="file_too_large",
                detail=f"Content-Length {cl} bytes exceeds limit",
            )
        )

    # Chunked read with running total — catches the missing-Content-Length case.
    buf = bytearray()
    async for chunk in _iter_upload(file):
        buf.extend(chunk)
        if len(buf) > MAX_BYTES:
            raise _ingest_rejected_to_http(
                IngestRejected(
                    code="file_too_large",
                    detail=f"Body exceeded {MAX_BYTES} bytes during read",
                )
            )

    filename = file.filename or "uploaded.txt"
    return await _ingest_with_app_state(request, filename=filename, content=bytes(buf))


@router.post("/ingest-text", response_model=IngestResult)
async def ingest_text(request: Request, body: IngestTextRequest) -> IngestResult:
    """JSON ingest (eval_rag.py + CI tests entry). Pydantic validates size."""
    return await _ingest_with_app_state(
        request,
        filename=body.filename,
        content=body.content.encode("utf-8"),
    )


@router.get("/documents", response_model=list[KbDocument])
async def list_documents(request: Request) -> list[KbDocument]:
    """Group chunk metadata by filename → KbDocument list."""
    collection = request.app.state.chroma_collection
    try:
        result = await asyncio.to_thread(collection.get, include=["metadatas"])
    except Exception as e:
        raise _rag_init_to_http(
            RagInitError(code="chroma_unreachable", detail=str(e))
        ) from e

    by_filename: dict[str, dict[str, Any]] = {}
    for meta in result.get("metadatas") or []:
        fn = meta.get("filename")
        if not fn:
            continue
        entry = by_filename.setdefault(fn, {"chunk_count": 0, "ingested_at_iso": ""})
        entry["chunk_count"] += 1
        # Last-seen ingested_at wins (re-ingest overwrites); deterministic per Plan 04-04
        entry["ingested_at_iso"] = meta.get("ingested_at_iso", "") or entry["ingested_at_iso"]

    return [
        KbDocument(
            filename=fn,
            chunk_count=v["chunk_count"],
            ingested_at_iso=v["ingested_at_iso"],
        )
        for fn, v in sorted(by_filename.items())
    ]


@router.delete("/documents/{filename}")
async def delete_document(request: Request, filename: str) -> dict[str, int]:
    """Remove all chunks for a given filename. Returns {deleted: int}."""
    collection = request.app.state.chroma_collection
    ids: list[str] = []
    try:
        existing = await asyncio.to_thread(
            collection.get, where={"filename": filename}
        )
        ids = existing.get("ids") or []
        if ids:
            await asyncio.to_thread(collection.delete, ids=ids)
    except Exception as e:
        raise _rag_init_to_http(
            RagInitError(code="chroma_unreachable", detail=str(e))
        ) from e
    logger.bind(event="rag.delete").info({"filename": filename, "deleted": len(ids)})
    return {"deleted": len(ids)}


@router.post("/query")
async def query_kb(
    request: Request,
    body: KbQueryRequest,
) -> list[dict[str, Any]]:
    """Hebrew query → list[ChunkRef-as-dict]. ChunkRef is a dataclass; serialize explicitly."""
    embedder = request.app.state.embedder
    collection = request.app.state.chroma_collection
    try:
        results = await retrieve(
            query=body.query,
            top_k=body.top_k,
            embedder=embedder,
            collection=collection,
        )
    except httpx.HTTPError as e:
        raise _rag_init_to_http(
            RagInitError(code="ollama_unreachable", detail=str(e))
        ) from e
    except Exception as e:
        raise _rag_init_to_http(
            RagInitError(code="chroma_unreachable", detail=str(e))
        ) from e

    # PII boundary: log query_hash + result count, NEVER raw query text.
    query_hash = hashlib.sha256(body.query.encode("utf-8")).hexdigest()[:16]
    logger.bind(event="rag.query").info({
        "query_hash": query_hash,
        "top_k": body.top_k,
        "n_results": len(results),
    })

    return [{"id": r.id, "text": r.text, "source": r.source} for r in results]


@router.get("/health")
async def kb_health(request: Request) -> dict[str, Any]:
    """Per-subsystem readiness — Phase 5 hot path + Phase 6 FE health poll."""
    collection = request.app.state.chroma_collection
    try:
        count = await asyncio.to_thread(collection.count)
        chroma_status = "ok"
    except Exception:
        count = -1
        chroma_status = "down"
    # Embedder presence on app.state is the Ollama health proxy; runtime
    # round-trip intentionally skipped here (would add ~50ms to FE health poll).
    ollama_status = "ok" if request.app.state.embedder is not None else "down"
    return {"chroma": chroma_status, "ollama": ollama_status, "collection_count": count}


# --- Helpers ------------------------------------------------------------------


async def _iter_upload(file: UploadFile, chunk_size: int = 65_536) -> Any:
    """Async iter over UploadFile bytes — compatible with TestClient + Starlette."""
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        yield chunk


async def _ingest_with_app_state(
    request: Request,
    *,
    filename: str,
    content: bytes,
) -> IngestResult:
    embedder = request.app.state.embedder
    collection = request.app.state.chroma_collection
    try:
        result = await ingest_document(
            filename=filename,
            content=content,
            embedder=embedder,
            collection=collection,
        )
    except IngestRejected as e:
        raise _ingest_rejected_to_http(e) from e
    except httpx.HTTPError as e:
        raise _rag_init_to_http(
            RagInitError(code="ollama_unreachable", detail=str(e))
        ) from e
    except Exception as e:
        raise _rag_init_to_http(
            RagInitError(code="chroma_unreachable", detail=str(e))
        ) from e

    # PII boundary: structural metadata only — never chunk text body.
    logger.bind(event="rag.ingest").info({
        "filename": result.filename,
        "chunks_added": result.chunks_added,
        "chunks_replaced": result.chunks_replaced,
        "bytes_ingested": result.bytes_ingested,
    })
    return result


__all__ = ["router"]
