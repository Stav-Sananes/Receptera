"""Prompt-builder structure + Hebrew byte-exact preservation + DoS bounds (Plan 03-02).

Covers LLM-03 (grounded refusal — system prompt + few-shot example #2 hardcode the
canonical "אין לי מספיק מידע" shape) and the pre-LLM DoS guards from
T-03-02-02 in the plan threat register.
"""

from __future__ import annotations

import json

import pytest

from receptra.llm.prompts import (
    FEW_SHOTS_HE,
    SYSTEM_PROMPT_EN,
    SYSTEM_PROMPT_HE,
    build_messages,
    build_user_message,
)
from receptra.llm.schema import ChunkRef, SuggestionResponse

# System prompt -------------------------------------------------------------


def test_system_prompt_he_contains_canonical_refusal() -> None:
    assert "אין לי מספיק מידע" in SYSTEM_PROMPT_HE


def test_system_prompt_he_contains_json_shape_literal() -> None:
    assert '{"suggestions":[{"text":"..."' in SYSTEM_PROMPT_HE


def test_system_prompt_he_contains_context_tag_rule() -> None:
    # Rule #1 — grounded-only-from-<context> is the LLM-03 contract
    assert "<context>" in SYSTEM_PROMPT_HE
    assert "</context>" in SYSTEM_PROMPT_HE


def test_system_prompt_he_280_char_limit_referenced() -> None:
    assert "280" in SYSTEM_PROMPT_HE


def test_system_prompt_en_contains_refusal_in_hebrew_quotes() -> None:
    # English prompt MUST instruct the model to refuse in Hebrew, not English
    assert "אין לי מספיק מידע" in SYSTEM_PROMPT_EN


def test_system_prompt_en_contains_json_shape_literal() -> None:
    assert '{"suggestions":[{"text":"..."' in SYSTEM_PROMPT_EN


# Few-shot ------------------------------------------------------------------


def test_few_shots_alternating_roles() -> None:
    assert len(FEW_SHOTS_HE) == 4
    assert [m["role"] for m in FEW_SHOTS_HE] == ["user", "assistant", "user", "assistant"]


def test_few_shot_user_turns_contain_context_and_transcript_tags() -> None:
    for i in (0, 2):
        content = FEW_SHOTS_HE[i]["content"]
        assert "<context>" in content
        assert "</context>" in content
        assert "<transcript>" in content
        assert "</transcript>" in content


def test_few_shot_assistants_are_valid_suggestion_response() -> None:
    for i in (1, 3):  # asst entries at index 1 and 3
        payload = FEW_SHOTS_HE[i]["content"]
        # Must be parseable JSON
        json.loads(payload)
        # Must be a valid SuggestionResponse (proves the few-shot is itself a valid demo)
        SuggestionResponse.model_validate_json(payload)


def test_few_shot_2_is_canonical_refusal() -> None:
    parsed = SuggestionResponse.model_validate_json(FEW_SHOTS_HE[3]["content"])
    assert parsed.suggestions[0].text == "אין לי מספיק מידע"
    assert parsed.suggestions[0].confidence == 0.0
    assert parsed.suggestions[0].citation_ids == []


def test_few_shot_1_has_grounded_citation() -> None:
    parsed = SuggestionResponse.model_validate_json(FEW_SHOTS_HE[1]["content"])
    assert parsed.suggestions[0].citation_ids == ["kb-policy-returns"]
    assert parsed.suggestions[0].confidence > 0.5


# build_user_message --------------------------------------------------------


def test_build_user_message_empty_chunks_uses_hebrew_marker() -> None:
    out = build_user_message("שלום", [])
    assert "<context>\n(אין קטעי הקשר זמינים)\n</context>" in out
    assert "<transcript>\nשלום\n</transcript>" in out


def test_build_user_message_renders_inline_id_markers() -> None:
    chunks = [
        ChunkRef(id="kb-1", text="טקסט א"),
        ChunkRef(id="kb-2", text="טקסט ב"),
    ]
    out = build_user_message("שלום", chunks)
    assert "[id: kb-1]\nטקסט א" in out
    assert "[id: kb-2]\nטקסט ב" in out
    # blank-line separator between chunks
    assert "טקסט א\n\n[id: kb-2]" in out
    # Wrapped in <context> / <transcript> tags
    assert "<context>\n[id: kb-1]" in out
    assert out.endswith("</transcript>")


def test_build_user_message_does_not_render_source_metadata() -> None:
    """`source` is opaque to the LLM (Phase 6 UI uses it for citation chips)."""
    chunks = [
        ChunkRef(id="kb-1", text="טקסט", source={"filename": "secret.md", "offset": "120"}),
    ]
    out = build_user_message("שלום", chunks)
    assert "secret.md" not in out
    assert "filename" not in out
    assert "offset" not in out


def test_build_user_message_rejects_oversize_transcript() -> None:
    with pytest.raises(ValueError, match="transcript exceeds 2000"):
        build_user_message("x" * 2001, [])


def test_build_user_message_rejects_too_many_chunks() -> None:
    chunks = [ChunkRef(id=f"k{i}", text="x") for i in range(11)]
    with pytest.raises(ValueError, match="more than 10 context chunks"):
        build_user_message("שלום", chunks)


def test_build_user_message_rejects_oversize_context_body() -> None:
    chunks = [ChunkRef(id="big", text="x" * 12001)]
    with pytest.raises(ValueError, match="context body exceeds 12000"):
        build_user_message("שלום", chunks)


def test_build_user_message_accepts_at_bounds() -> None:
    # 2000-char transcript + 10 chunks summing to 12000 chars all PASS
    chunks = [ChunkRef(id=f"k{i}", text="x" * 1200) for i in range(10)]
    out = build_user_message("y" * 2000, chunks)
    assert "[id: k0]" in out
    assert len(out) > 12000


def test_build_user_message_accepts_just_below_transcript_bound() -> None:
    out = build_user_message("x" * 2000, [])
    assert "x" * 2000 in out


def test_build_user_message_accepts_exactly_10_chunks() -> None:
    chunks = [ChunkRef(id=f"k{i}", text="x") for i in range(10)]
    out = build_user_message("שלום", chunks)
    assert "[id: k9]" in out


# build_messages ------------------------------------------------------------


def test_build_messages_he_returns_six_messages() -> None:
    msgs = build_messages("שלום", [], lang="he")
    assert len(msgs) == 6
    assert msgs[0] == {"role": "system", "content": SYSTEM_PROMPT_HE}
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == build_user_message("שלום", [])


def test_build_messages_default_lang_is_he() -> None:
    msgs = build_messages("שלום", [])
    assert msgs[0]["content"] == SYSTEM_PROMPT_HE


def test_build_messages_he_role_sequence() -> None:
    msgs = build_messages("שלום", [], lang="he")
    assert [m["role"] for m in msgs] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]


def test_build_messages_few_shots_are_unmodified() -> None:
    msgs = build_messages("שלום", [], lang="he")
    assert msgs[1] == FEW_SHOTS_HE[0]
    assert msgs[2] == FEW_SHOTS_HE[1]
    assert msgs[3] == FEW_SHOTS_HE[2]
    assert msgs[4] == FEW_SHOTS_HE[3]


def test_build_messages_en_swaps_only_system() -> None:
    msgs_he = build_messages("שלום", [], lang="he")
    msgs_en = build_messages("שלום", [], lang="en")
    assert msgs_en[0]["content"] == SYSTEM_PROMPT_EN
    # Few-shots remain Hebrew demonstrations
    assert msgs_he[1] == msgs_en[1]
    assert msgs_he[2] == msgs_en[2]
    # Final user-message identical (lang only affects system prompt)
    assert msgs_he[-1] == msgs_en[-1]


def test_build_messages_rejects_unknown_lang() -> None:
    with pytest.raises(ValueError, match="unsupported lang"):
        build_messages("שלום", [], lang="fr")


def test_build_messages_propagates_dos_bound_violations() -> None:
    with pytest.raises(ValueError, match="transcript exceeds 2000"):
        build_messages("x" * 2001, [], lang="he")


def test_build_messages_with_chunks_renders_full_user_message() -> None:
    chunks = [ChunkRef(id="kb-1", text="טקסט")]
    msgs = build_messages("מה השעה?", chunks, lang="he")
    assert "[id: kb-1]" in msgs[-1]["content"]
    assert "<transcript>\nמה השעה?\n</transcript>" in msgs[-1]["content"]
