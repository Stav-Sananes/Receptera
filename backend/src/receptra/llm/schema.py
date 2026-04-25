"""Pydantic v2 schema for the Hebrew suggestion engine (LLM-03 + LLM-04).

The schema is the public contract for:
- Plan 03-04 engine — yields ``SuggestionEvent`` instances
- Plan 03-06 CLI harness — pretty-prints CompleteEvent
- Phase 4 RAG — accepts ``list[ChunkRef]`` as input to ``generate_suggestions``
- Phase 5 hot path — TypeAdapter-validates events on the WebSocket muxer
- Phase 6 frontend — codegen-derived TypeScript types (Phase 6's concern)

Every model is ``frozen=True, extra='forbid'`` to mirror Plan 02-04's
``SttEvent`` contract: total switches in consumer code, no silent drift,
no accidental field addition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# --- Suggestion contract (LLM-04) ---


class Suggestion(BaseModel):
    """A single grounded reply suggestion the agent may read aloud."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(
        ...,
        min_length=1,
        max_length=280,
        description="Hebrew suggestion text, ≤ 280 chars",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Self-reported model confidence 0.0-1.0",
    )
    citation_ids: list[str] = Field(
        default_factory=list,
        description="Stable chunk IDs from RAG retrieval; empty list = no grounding",
    )


class SuggestionResponse(BaseModel):
    """Final assembled output the engine validates against (LLM-04)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suggestions: list[Suggestion] = Field(..., min_length=1, max_length=3)


# --- Streaming event union (LLM-02) ---


class TokenEvent(BaseModel):
    """Streamed token delta. Phase 5 forwards to Phase 6 UI for typewriter rendering."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    type: Literal["token"] = "token"
    delta: str


class CompleteEvent(BaseModel):
    """Final parsed structured output, plus TTFT/total wall-clock."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    type: Literal["complete"] = "complete"
    suggestions: list[Suggestion]
    ttft_ms: int  # -1 sentinel if no token ever arrived (error path)
    total_ms: int
    model: str  # which model actually served (dictalm3 / qwen2.5:7b)


class LlmErrorEvent(BaseModel):
    """Typed error envelope; Phase 5 maps onto WS error frames.

    The ``code`` Literal allowlist is intentionally narrow (4 values).
    Adding a 5th requires plan amendment so consumer switches stay total.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    type: Literal["error"] = "error"
    code: Literal["ollama_unreachable", "parse_error", "timeout", "no_context"]
    detail: str


SuggestionEvent = Annotated[
    TokenEvent | CompleteEvent | LlmErrorEvent,
    Field(discriminator="type"),
]
"""Discriminated union of all streaming events. Use ``TypeAdapter(SuggestionEvent)`` for parse."""

# Pre-construct the TypeAdapter so consumers don't have to:
SuggestionEventAdapter: TypeAdapter[TokenEvent | CompleteEvent | LlmErrorEvent] = TypeAdapter(
    SuggestionEvent
)


# --- Context chunk (Phase 4 forward-decl) ---


@dataclass(frozen=True)
class ChunkRef:
    """A retrieved context chunk passed into ``generate_suggestions``.

    Phase 3 owns the contract; Phase 4 RAG re-exports under
    ``receptra.rag.types`` once the retriever is built.

    The ``source`` dict is opaque to the LLM — it carries filename/offset
    metadata for the Phase 6 UI citation chips and is not rendered into the
    prompt (only ``id`` + ``text`` are; see ``receptra.llm.prompts``).
    """

    id: str
    text: str
    source: dict[str, str] | None = None


__all__ = [
    "ChunkRef",
    "CompleteEvent",
    "LlmErrorEvent",
    "Suggestion",
    "SuggestionEvent",
    "SuggestionEventAdapter",
    "SuggestionResponse",
    "TokenEvent",
]
