"""Typed RAG exception tests for Phase 4 Wave-0.

The ``code`` allowlist on each error matches the RESEARCH §REST API
``KbErrorResponse.code`` schema (Plan 04-05 wires HTTP status mapping).
Adding a new code requires plan amendment so consumer switches stay total.
"""

from __future__ import annotations

from receptra.rag.errors import IngestRejected, RagInitError


def test_rag_init_error_codes() -> None:
    for code in ("ollama_unreachable", "model_missing", "chroma_unreachable"):
        err = RagInitError(code=code, detail="x")  # type: ignore[arg-type]
        assert err.code == code
        assert err.detail == "x"
        # __str__ collapses to "code: detail" so loguru/print yield a useful line.
        assert str(err) == f"{code}: x"


def test_ingest_rejected_codes() -> None:
    for code in (
        "unsupported_extension",
        "file_too_large",
        "encoding_error",
        "empty_after_chunking",
    ):
        err = IngestRejected(code=code, detail="x")  # type: ignore[arg-type]
        assert err.code == code
        assert err.detail == "x"
        assert str(err) == f"{code}: x"


def test_errors_subclass_exception() -> None:
    """Route handlers catch via except clauses; both must be Exception subclasses."""
    assert issubclass(RagInitError, Exception)
    assert issubclass(IngestRejected, Exception)


def test_errors_are_frozen() -> None:
    """frozen=True dataclass: code/detail must not be mutable post-construction."""
    import dataclasses

    import pytest as _pytest

    err1 = RagInitError(code="ollama_unreachable", detail="x")
    with _pytest.raises(dataclasses.FrozenInstanceError):
        err1.code = "model_missing"  # type: ignore[misc]

    err2 = IngestRejected(code="encoding_error", detail="y")
    with _pytest.raises(dataclasses.FrozenInstanceError):
        err2.detail = "z"  # type: ignore[misc]
