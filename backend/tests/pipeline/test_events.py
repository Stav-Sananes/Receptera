"""Tests for pipeline WebSocket event types (Phase 5 INT-01).

Verifies:
- All three event types have correct ``type`` discriminator literals
- Pydantic validation enforces required fields (extra="forbid")
- TypeAdapter-based PipelineEvent union parses all three correctly
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from receptra.pipeline.events import (
    PipelineEvent,
    SuggestionComplete,
    SuggestionError,
    SuggestionToken,
)


def test_suggestion_token_discriminator() -> None:
    """SuggestionToken.type is 'suggestion_token'."""
    tok = SuggestionToken(delta="שלום")
    assert tok.type == "suggestion_token"
    assert tok.delta == "שלום"


def test_suggestion_complete_fields() -> None:
    """SuggestionComplete accepts all required fields."""
    from receptra.llm.schema import Suggestion

    s = Suggestion(text="אין לי מידע", confidence=0.0, citation_ids=[])
    ev = SuggestionComplete(
        suggestions=[s],
        ttft_ms=123,
        total_ms=456,
        model="dictalm3",
        rag_latency_ms=50,
        e2e_latency_ms=600,
    )
    assert ev.type == "suggestion_complete"
    assert len(ev.suggestions) == 1
    assert ev.rag_latency_ms == 50
    assert ev.e2e_latency_ms == 600


def test_suggestion_error_fields() -> None:
    """SuggestionError requires code + detail."""
    ev = SuggestionError(code="ollama_unreachable", detail="connection refused")
    assert ev.type == "suggestion_error"
    assert ev.code == "ollama_unreachable"


def test_suggestion_token_extra_forbidden() -> None:
    """extra='forbid' rejects unknown fields."""
    with pytest.raises(ValidationError):
        SuggestionToken(delta="x", unexpected_field="y")  # type: ignore[call-arg]


def test_pipeline_event_adapter_token() -> None:
    """TypeAdapter(PipelineEvent) parses a SuggestionToken dict."""
    ta: TypeAdapter[SuggestionToken | SuggestionComplete | SuggestionError] = TypeAdapter(
        PipelineEvent
    )
    parsed = ta.validate_python({"type": "suggestion_token", "delta": "hello"})
    assert isinstance(parsed, SuggestionToken)


def test_pipeline_event_adapter_error() -> None:
    """TypeAdapter(PipelineEvent) parses a SuggestionError dict."""
    ta: TypeAdapter[SuggestionToken | SuggestionComplete | SuggestionError] = TypeAdapter(
        PipelineEvent
    )
    parsed = ta.validate_python({"type": "suggestion_error", "code": "timeout", "detail": "x"})
    assert isinstance(parsed, SuggestionError)


def test_pipeline_event_adapter_rejects_unknown_type() -> None:
    """TypeAdapter(PipelineEvent) raises on unknown discriminator."""
    ta: TypeAdapter[SuggestionToken | SuggestionComplete | SuggestionError] = TypeAdapter(
        PipelineEvent
    )
    with pytest.raises(ValidationError):
        ta.validate_python({"type": "unknown_type", "delta": "x"})
