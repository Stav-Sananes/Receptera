"""Typed RAG exceptions.

The ``code`` field on each error is a frozen Literal whose allowlist matches
the RESEARCH §REST API ``KbErrorResponse.code`` (Plan 04-05 wires HTTP status
mapping). Adding a new code requires plan amendment so consumer switches stay total.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RagInitErrorCode = Literal["ollama_unreachable", "model_missing", "chroma_unreachable"]
IngestRejectedCode = Literal[
    "unsupported_extension",
    "file_too_large",
    "encoding_error",
    "empty_after_chunking",
]


@dataclass(frozen=True)
class RagInitError(Exception):
    """Raised when RAG dependencies (Ollama or Chroma) are unavailable at startup.

    Plan 04-05 maps each ``code`` to an HTTP status in the FastAPI lifespan +
    ``KbErrorResponse`` body. ``code`` is a frozen Literal so consumer switches
    stay total — adding a value requires a plan amendment.
    """

    code: RagInitErrorCode
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True)
class IngestRejected(Exception):
    """Raised when the ingest pipeline declines an input file.

    Plan 04-04 raises this from the ingest pipeline; Plan 04-05 maps each
    ``code`` to an HTTP 4xx + ``KbErrorResponse`` body for the REST surface.
    """

    code: IngestRejectedCode
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


__all__ = [
    "IngestRejected",
    "IngestRejectedCode",
    "RagInitError",
    "RagInitErrorCode",
]
