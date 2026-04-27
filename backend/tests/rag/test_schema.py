"""Pydantic v2 schema tests for receptra.rag.schema (RAG-04 + RAG-06 contract).

Pins the FastAPI request/response shapes Plan 04-05 routes layer consumes.
All models must be ``frozen=True, extra='forbid'`` mirroring receptra.llm.schema
byte-for-byte (Plan 03-02 contract — total switches in consumer code, no silent
field drift, no accidental field addition).

RESEARCH §REST API (lines 304-352) is the byte-for-byte reference; these tests
exist to make a single field rename or bound change a hard test failure rather
than a silent contract drift.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

# --------------------------------------------------------------------------
# IngestTextRequest
# --------------------------------------------------------------------------


def test_ingest_text_request_valid() -> None:
    """Happy-path construction + model_dump round-trip."""
    from receptra.rag.schema import IngestTextRequest

    req = IngestTextRequest(filename="a.md", content="שלום")
    assert req.filename == "a.md"
    assert req.content == "שלום"
    dumped = req.model_dump()
    assert dumped == {"filename": "a.md", "content": "שלום"}
    # Round-trip through the model survives byte-for-byte.
    assert IngestTextRequest(**dumped) == req


def test_ingest_text_request_filename_bounds() -> None:
    """Filename min_length=1 and max_length=255 enforced."""
    from receptra.rag.schema import IngestTextRequest

    # Empty filename rejected.
    with pytest.raises(ValidationError):
        IngestTextRequest(filename="", content="x")

    # 256-char filename rejected.
    with pytest.raises(ValidationError):
        IngestTextRequest(filename="a" * 256 + ".md", content="x")

    # 1-char filename accepted.
    IngestTextRequest(filename="a", content="x")

    # 255-char filename accepted.
    IngestTextRequest(filename="a" * 255, content="x")


def test_ingest_text_request_content_max() -> None:
    """Content max_length=1_048_576 (1 MiB chars) enforced."""
    from receptra.rag.schema import IngestTextRequest

    # 1_048_577 chars rejected.
    with pytest.raises(ValidationError):
        IngestTextRequest(filename="a.md", content="x" * 1_048_577)

    # 1_048_576 chars accepted (exact boundary).
    IngestTextRequest(filename="a.md", content="x" * 1_048_576)


# --------------------------------------------------------------------------
# IngestResult
# --------------------------------------------------------------------------


def test_ingest_result_shape() -> None:
    """IngestResult constructs with all 4 fields; frozen=True blocks mutation."""
    from receptra.rag.schema import IngestResult

    res = IngestResult(
        filename="a.md",
        chunks_added=3,
        chunks_replaced=0,
        bytes_ingested=120,
    )
    assert res.filename == "a.md"
    assert res.chunks_added == 3
    assert res.chunks_replaced == 0
    assert res.bytes_ingested == 120

    # Frozen: mutation must raise.
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        res.chunks_added = 999  # type: ignore[misc]


# --------------------------------------------------------------------------
# KbDocument
# --------------------------------------------------------------------------


def test_kb_document_shape() -> None:
    """KbDocument constructs with filename + chunk_count + ingested_at_iso."""
    from receptra.rag.schema import KbDocument

    doc = KbDocument(
        filename="policy.md",
        chunk_count=5,
        ingested_at_iso="2026-04-26T12:34:56+00:00",
    )
    assert doc.filename == "policy.md"
    assert doc.chunk_count == 5
    assert doc.ingested_at_iso == "2026-04-26T12:34:56+00:00"


# --------------------------------------------------------------------------
# KbQueryRequest
# --------------------------------------------------------------------------


def test_kb_query_request_defaults() -> None:
    """top_k defaults to 5; bounds [1, 20] enforced."""
    from receptra.rag.schema import KbQueryRequest

    # Default top_k = 5.
    req = KbQueryRequest(query="x")
    assert req.top_k == 5

    # top_k = 21 rejected (le=20).
    with pytest.raises(ValidationError):
        KbQueryRequest(query="x", top_k=21)

    # top_k = 0 rejected (ge=1).
    with pytest.raises(ValidationError):
        KbQueryRequest(query="x", top_k=0)

    # Boundaries 1 and 20 accepted.
    assert KbQueryRequest(query="x", top_k=1).top_k == 1
    assert KbQueryRequest(query="x", top_k=20).top_k == 20

    # query length bounds: empty rejected, 2001 chars rejected.
    with pytest.raises(ValidationError):
        KbQueryRequest(query="")
    with pytest.raises(ValidationError):
        KbQueryRequest(query="x" * 2001)


# --------------------------------------------------------------------------
# KbErrorResponse
# --------------------------------------------------------------------------


def test_kb_error_response_codes() -> None:
    """All 6 v1 codes accepted; unknown code rejected."""
    from receptra.rag.schema import KbErrorResponse

    accepted = [
        "unsupported_extension",
        "file_too_large",
        "encoding_error",
        "ollama_unreachable",
        "chroma_unreachable",
        "empty_after_chunking",
    ]
    for code in accepted:
        err = KbErrorResponse(code=code, detail="x")  # type: ignore[arg-type]
        assert err.code == code
        assert err.detail == "x"

    # Unknown code rejected.
    with pytest.raises(ValidationError):
        KbErrorResponse(code="not_a_real_code", detail="x")  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# extra='forbid' contract
# --------------------------------------------------------------------------


def test_extra_fields_forbidden() -> None:
    """Every model rejects extra fields (extra='forbid' verified per model)."""
    from receptra.rag.schema import (
        IngestResult,
        IngestTextRequest,
        KbDocument,
        KbErrorResponse,
        KbQueryRequest,
    )

    with pytest.raises(ValidationError):
        IngestTextRequest(filename="a.md", content="x", surprise="boom")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        IngestResult(
            filename="a.md",
            chunks_added=1,
            chunks_replaced=0,
            bytes_ingested=1,
            surprise="boom",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        KbDocument(
            filename="a.md",
            chunk_count=1,
            ingested_at_iso="x",
            surprise="boom",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        KbQueryRequest(query="x", top_k=5, surprise="boom")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        KbErrorResponse(
            code="encoding_error",
            detail="x",
            surprise="boom",  # type: ignore[call-arg]
        )


# --------------------------------------------------------------------------
# Frozen=True contract
# --------------------------------------------------------------------------


def test_all_models_frozen() -> None:
    """Every Pydantic model is frozen=True (mutation must raise)."""
    from receptra.rag.schema import (
        IngestResult,
        IngestTextRequest,
        KbDocument,
        KbErrorResponse,
        KbQueryRequest,
    )

    instances: list[object] = [
        IngestTextRequest(filename="a.md", content="x"),
        IngestResult(filename="a.md", chunks_added=0, chunks_replaced=0, bytes_ingested=0),
        KbDocument(filename="a.md", chunk_count=0, ingested_at_iso="2026-01-01T00:00:00Z"),
        KbQueryRequest(query="x"),
        KbErrorResponse(code="encoding_error", detail="x"),
    ]
    for inst in instances:
        with pytest.raises((ValidationError, TypeError, AttributeError)):
            inst.filename = "mutated"  # type: ignore[attr-defined]
