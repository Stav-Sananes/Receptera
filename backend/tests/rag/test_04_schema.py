"""TDD RED tests for receptra.rag.schema (Plan 04-04, Task 1).

8 tests covering IngestTextRequest, IngestResult, KbDocument, KbQueryRequest,
KbErrorResponse — all frozen=True, extra='forbid' Pydantic v2 models.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from receptra.rag.schema import (
    IngestResult,
    IngestTextRequest,
    KbDocument,
    KbErrorResponse,
    KbQueryRequest,
)


def test_ingest_text_request_valid() -> None:
    req = IngestTextRequest(filename="readme.md", content="שלום עולם")
    assert req.filename == "readme.md"
    assert req.content == "שלום עולם"
    d = req.model_dump()
    assert d == {"filename": "readme.md", "content": "שלום עולם"}
    # Round-trip
    req2 = IngestTextRequest(**d)
    assert req2 == req


def test_ingest_text_request_filename_bounds() -> None:
    # Empty filename rejected
    with pytest.raises(ValidationError):
        IngestTextRequest(filename="", content="x")
    # 256-char filename rejected
    with pytest.raises(ValidationError):
        IngestTextRequest(filename="a" * 256, content="x")
    # 1-char name accepted
    IngestTextRequest(filename="a.md", content="x")
    # 255-char name accepted
    IngestTextRequest(filename="a" * 251 + ".txt", content="x")


def test_ingest_text_request_content_max() -> None:
    # Exactly 1_048_576 chars OK
    IngestTextRequest(filename="a.md", content="x" * 1_048_576)
    # 1_048_577 chars rejected
    with pytest.raises(ValidationError):
        IngestTextRequest(filename="a.md", content="x" * 1_048_577)


def test_ingest_result_shape() -> None:
    r = IngestResult(
        filename="a.md",
        chunks_added=3,
        chunks_replaced=0,
        bytes_ingested=120,
    )
    assert r.filename == "a.md"
    assert r.chunks_added == 3
    assert r.chunks_replaced == 0
    assert r.bytes_ingested == 120
    # Frozen — mutation raises
    with pytest.raises((ValidationError, TypeError)):
        r.filename = "b.md"  # type: ignore[misc]


def test_kb_document_shape() -> None:
    doc = KbDocument(
        filename="policy.md",
        chunk_count=5,
        ingested_at_iso="2026-04-27T12:00:00+00:00",
    )
    assert doc.chunk_count == 5
    assert "2026" in doc.ingested_at_iso


def test_kb_query_request_defaults() -> None:
    req = KbQueryRequest(query="מה שעות הפתיחה?")
    assert req.top_k == 5  # default
    # top_k=21 rejected
    with pytest.raises(ValidationError):
        KbQueryRequest(query="x", top_k=21)
    # top_k=0 rejected
    with pytest.raises(ValidationError):
        KbQueryRequest(query="x", top_k=0)
    # top_k=20 accepted
    KbQueryRequest(query="x", top_k=20)
    # empty query rejected
    with pytest.raises(ValidationError):
        KbQueryRequest(query="")


def test_kb_error_response_codes() -> None:
    valid_codes = [
        "unsupported_extension",
        "file_too_large",
        "encoding_error",
        "ollama_unreachable",
        "chroma_unreachable",
        "empty_after_chunking",
    ]
    for code in valid_codes:
        resp = KbErrorResponse(code=code, detail="test")  # type: ignore[arg-type]
        assert resp.code == code
    # Invalid code rejected
    with pytest.raises(ValidationError):
        KbErrorResponse(code="bad_code", detail="test")  # type: ignore[arg-type]


def test_extra_fields_forbidden() -> None:
    models_and_valid_kwargs = [
        (IngestTextRequest, {"filename": "a.md", "content": "x"}),
        (IngestResult, {"filename": "a.md", "chunks_added": 1, "chunks_replaced": 0, "bytes_ingested": 1}),
        (KbDocument, {"filename": "a.md", "chunk_count": 1, "ingested_at_iso": "2026-01-01T00:00:00Z"}),
        (KbQueryRequest, {"query": "x"}),
        (KbErrorResponse, {"code": "file_too_large", "detail": "d"}),
    ]
    for model_cls, valid_kwargs in models_and_valid_kwargs:
        with pytest.raises(ValidationError):
            model_cls(**valid_kwargs, extra_field_not_allowed="boom")  # type: ignore[call-arg]
