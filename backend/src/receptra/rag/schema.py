"""Pydantic v2 request/response schemas for /api/kb/* (RAG-04 + RAG-06).

All models are frozen=True, extra="forbid" — total switch in consumer code,
no silent field drift. Mirrors receptra.llm.schema (Plan 03-02 lock).

Plan 04-05 routes layer imports these and FastAPI auto-validates.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IngestTextRequest(BaseModel):
    """JSON ingest body (eval_rag.py + CI tests entry point)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., max_length=1_048_576)


class IngestResult(BaseModel):
    """Ingest success envelope returned to the HTTP caller."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str
    chunks_added: int
    chunks_replaced: int
    bytes_ingested: int


class KbDocument(BaseModel):
    """List-response item for GET /api/kb/documents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str
    chunk_count: int
    ingested_at_iso: str


class KbQueryRequest(BaseModel):
    """Query body for POST /api/kb/query."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(..., min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=20)


class KbErrorResponse(BaseModel):
    """Typed error envelope. code Literal allowlist matches errors.py Literal types.

    HTTP status mapping (Plan 04-05):
      unsupported_extension → 415, file_too_large → 413, encoding_error → 400,
      empty_after_chunking → 422, ollama_unreachable → 503, chroma_unreachable → 503.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: Literal[
        "unsupported_extension",
        "file_too_large",
        "encoding_error",
        "ollama_unreachable",
        "chroma_unreachable",
        "empty_after_chunking",
    ]
    detail: str


__all__ = [
    "IngestResult",
    "IngestTextRequest",
    "KbDocument",
    "KbErrorResponse",
    "KbQueryRequest",
]
