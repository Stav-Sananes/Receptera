"""Pipeline WebSocket event types (Phase 5 INT-01).

Sent on the same /ws/stt connection after each FinalTranscript, carrying
the suggestion stream from RAG + LLM. The ``type`` field uses the
``suggestion_*`` prefix to avoid collisions with STT event discriminators
(``ready``, ``partial``, ``final``, ``error``).

All models: frozen=True, extra="forbid" (mirrors receptra.stt.events contract).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from receptra.llm.schema import Suggestion


class SuggestionToken(BaseModel):
    """One LLM token delta — streamed for typewriter rendering in the frontend."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["suggestion_token"] = "suggestion_token"
    delta: str


class SuggestionComplete(BaseModel):
    """LLM generation done — structured suggestions + full latency breakdown.

    INT-03 fields:
        rag_latency_ms: embed + ChromaDB query time in ms (0 if RAG skipped).
        e2e_latency_ms: monotonic ms from t_speech_end_ms to this event sent.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["suggestion_complete"] = "suggestion_complete"
    suggestions: list[Suggestion]
    ttft_ms: int = Field(..., description="LLM time-to-first-token; -1 if no token received")
    total_ms: int = Field(..., description="Total LLM generation time in ms")
    model: str = Field(..., description="Ollama model tag that served this request")
    rag_latency_ms: int = Field(..., description="RAG embed+query latency; 0 if skipped")
    e2e_latency_ms: int = Field(..., description="t_speech_end → suggestion_complete in ms")
    rag_max_similarity: float = Field(
        default=0.0,
        description="Max chunk cosine similarity; 0.0 if no chunks retrieved",
    )
    rag_low_confidence: bool = Field(
        default=False,
        description="True when max_similarity < rag_suggestion_threshold",
    )


class SuggestionError(BaseModel):
    """Pipeline error — RAG failure, LLM error, or graceful-degradation notice.

    The ``code`` field is a free string (not a Literal) because errors can
    originate from RAG (``rag_unavailable``) or LLM (``ollama_unreachable``,
    ``timeout``, ``parse_error``, ``no_context``) or the pipeline itself
    (``pipeline_error``). The frontend renders all variants as a warning badge.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["suggestion_error"] = "suggestion_error"
    code: str
    detail: str


PipelineEvent = Annotated[
    SuggestionToken | SuggestionComplete | SuggestionError,
    Field(discriminator="type"),
]
"""Discriminated union of all pipeline-layer WebSocket events.

Usage::

    from pydantic import TypeAdapter
    from receptra.pipeline.events import PipelineEvent
    parsed = TypeAdapter(PipelineEvent).validate_python(raw_dict)
"""

__all__ = [
    "PipelineEvent",
    "SuggestionComplete",
    "SuggestionError",
    "SuggestionToken",
]
