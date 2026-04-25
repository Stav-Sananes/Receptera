"""Phase 3 — Hebrew Suggestion LLM package.

Public surface:
    Suggestion, SuggestionResponse — pydantic v2 models for parse target (LLM-04)
    TokenEvent, CompleteEvent, LlmErrorEvent, SuggestionEvent — streaming event union
    ChunkRef — context-chunk dataclass (Phase 4 RAG re-exports)

Plans 03-03 (client), 03-04 (engine), 03-05 (metrics + audit), 03-06 (CLI harness)
add modules to this package.
"""

from __future__ import annotations

from receptra.llm.schema import (
    ChunkRef,
    CompleteEvent,
    LlmErrorEvent,
    Suggestion,
    SuggestionEvent,
    SuggestionEventAdapter,
    SuggestionResponse,
    TokenEvent,
)

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
