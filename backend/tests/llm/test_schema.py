"""Schema invariants + discriminated-union round-trip (Plan 03-02).

Covers LLM-04 (structured ``suggestions[]`` parse contract) and the
streaming event union (LLM-02). Mirrors Plan 02-04's ``test_events.py``
discipline — every behavior bullet from the plan has a regression guard.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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

# Suggestion ----------------------------------------------------------------


def test_suggestion_accepts_valid_hebrew() -> None:
    s = Suggestion(text="שלום", confidence=0.9, citation_ids=["kb-1"])
    assert s.text == "שלום"
    assert s.confidence == 0.9
    assert s.citation_ids == ["kb-1"]


def test_suggestion_default_citation_ids_is_empty_list() -> None:
    s = Suggestion(text="x", confidence=0.5)
    assert s.citation_ids == []


def test_suggestion_rejects_empty_text() -> None:
    with pytest.raises(ValidationError):
        Suggestion(text="", confidence=0.5, citation_ids=[])


def test_suggestion_rejects_too_long_text() -> None:
    with pytest.raises(ValidationError):
        Suggestion(text="x" * 281, confidence=0.5, citation_ids=[])


def test_suggestion_accepts_text_at_max_length() -> None:
    s = Suggestion(text="x" * 280, confidence=0.5, citation_ids=[])
    assert len(s.text) == 280


@pytest.mark.parametrize("bad_conf", [-0.01, 1.01, 1.5])
def test_suggestion_rejects_confidence_out_of_range(bad_conf: float) -> None:
    with pytest.raises(ValidationError):
        Suggestion(text="x", confidence=bad_conf, citation_ids=[])


@pytest.mark.parametrize("good_conf", [0.0, 0.5, 1.0])
def test_suggestion_accepts_confidence_at_bounds(good_conf: float) -> None:
    s = Suggestion(text="x", confidence=good_conf, citation_ids=[])
    assert s.confidence == good_conf


def test_suggestion_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Suggestion.model_validate(
            {"text": "x", "confidence": 0.5, "citation_ids": [], "extra": True}
        )


def test_suggestion_is_frozen() -> None:
    s = Suggestion(text="x", confidence=0.5, citation_ids=[])
    with pytest.raises(ValidationError):
        s.text = "y"  # type: ignore[misc]


# SuggestionResponse --------------------------------------------------------


def test_suggestion_response_accepts_one_to_three() -> None:
    SuggestionResponse(suggestions=[Suggestion(text="a", confidence=0.5, citation_ids=[])])
    SuggestionResponse(
        suggestions=[Suggestion(text=str(i), confidence=0.5, citation_ids=[]) for i in range(3)]
    )


def test_suggestion_response_rejects_zero() -> None:
    with pytest.raises(ValidationError):
        SuggestionResponse(suggestions=[])


def test_suggestion_response_rejects_four_plus() -> None:
    with pytest.raises(ValidationError):
        SuggestionResponse(
            suggestions=[Suggestion(text=str(i), confidence=0.5, citation_ids=[]) for i in range(4)]
        )


def test_suggestion_response_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SuggestionResponse.model_validate(
            {
                "suggestions": [{"text": "x", "confidence": 0.5, "citation_ids": []}],
                "extra": "x",
            }
        )


def test_validate_json_round_trips_hebrew_byte_exact() -> None:
    payload = '{"suggestions":[{"text":"שלום עולם","confidence":0.9,"citation_ids":["kb-1"]}]}'
    parsed = SuggestionResponse.model_validate_json(payload)
    assert parsed.suggestions[0].text == "שלום עולם"
    # round-trip check
    out = parsed.model_dump_json()
    assert "שלום עולם" in out


def test_validate_json_rejects_extra_field_in_suggestion() -> None:
    payload = '{"suggestions":[{"text":"x","confidence":0.5,"citation_ids":[],"extra":1}]}'
    with pytest.raises(ValidationError):
        SuggestionResponse.model_validate_json(payload)


# Event union ---------------------------------------------------------------


def test_token_event_constructs_with_default_type() -> None:
    ev = TokenEvent(delta="שלום")
    assert ev.type == "token"
    assert ev.delta == "שלום"


def test_token_event_via_discriminated_union() -> None:
    ev = SuggestionEventAdapter.validate_python({"type": "token", "delta": "שלום"})
    assert isinstance(ev, TokenEvent)
    assert ev.delta == "שלום"


def test_complete_event_via_discriminated_union() -> None:
    ev = SuggestionEventAdapter.validate_python(
        {
            "type": "complete",
            "suggestions": [{"text": "x", "confidence": 0.5, "citation_ids": []}],
            "ttft_ms": 312,
            "total_ms": 1845,
            "model": "dictalm3",
        }
    )
    assert isinstance(ev, CompleteEvent)
    assert ev.ttft_ms == 312
    assert ev.total_ms == 1845
    assert ev.model == "dictalm3"
    assert len(ev.suggestions) == 1


def test_error_event_code_literal_allowlist() -> None:
    # Each Literal value constructs cleanly via model_validate (runtime check;
    # static narrowing across a tuple-literal iteration is not what mypy proves).
    for code in ("ollama_unreachable", "parse_error", "timeout", "no_context"):
        ev = LlmErrorEvent.model_validate({"code": code, "detail": "x"})
        assert ev.code == code
    with pytest.raises(ValidationError):
        LlmErrorEvent.model_validate({"code": "random", "detail": "x"})


def test_error_event_via_discriminated_union() -> None:
    ev = SuggestionEventAdapter.validate_python(
        {"type": "error", "code": "parse_error", "detail": "bad json"}
    )
    assert isinstance(ev, LlmErrorEvent)
    assert ev.code == "parse_error"


def test_event_adapter_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        SuggestionEventAdapter.validate_python({"type": "unknown", "x": 1})


def test_token_event_is_frozen() -> None:
    ev = TokenEvent(delta="x")
    with pytest.raises(ValidationError):
        ev.delta = "y"  # type: ignore[misc]


def test_token_event_rejects_extra() -> None:
    with pytest.raises(ValidationError):
        TokenEvent.model_validate({"type": "token", "delta": "x", "extra": 1})


# ChunkRef ------------------------------------------------------------------


def test_chunkref_frozen_with_optional_source() -> None:
    c = ChunkRef(id="kb-1", text="שלום")
    assert c.id == "kb-1"
    assert c.text == "שלום"
    assert c.source is None


def test_chunkref_accepts_source_dict() -> None:
    c = ChunkRef(id="kb-2", text="x", source={"filename": "kb.md", "offset": "120"})
    assert c.source == {"filename": "kb.md", "offset": "120"}


def test_chunkref_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    c = ChunkRef(id="kb-1", text="שלום")
    with pytest.raises(FrozenInstanceError):
        c.id = "kb-2"  # type: ignore[misc]


# Package boundary ----------------------------------------------------------


def test_package_reexports_public_surface() -> None:
    from receptra.llm import (
        ChunkRef as _ChunkRef,
    )
    from receptra.llm import (
        CompleteEvent as _CompleteEvent,
    )
    from receptra.llm import (
        LlmErrorEvent as _LlmErrorEvent,
    )
    from receptra.llm import (
        Suggestion as _Suggestion,
    )
    from receptra.llm import (
        SuggestionEvent as _SuggestionEvent,  # noqa: F401
    )
    from receptra.llm import (
        SuggestionResponse as _SuggestionResponse,
    )
    from receptra.llm import (
        TokenEvent as _TokenEvent,
    )

    assert _Suggestion is Suggestion
    assert _SuggestionResponse is SuggestionResponse
    assert _ChunkRef is ChunkRef
    assert _TokenEvent is TokenEvent
    assert _CompleteEvent is CompleteEvent
    assert _LlmErrorEvent is LlmErrorEvent


# Static type-check anchor: SuggestionEvent is a usable annotation target.
_ANNOTATION_PROBE: SuggestionEvent
