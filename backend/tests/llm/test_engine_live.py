"""Live DictaLM 3.0 round-trip tests (LLM-03 grounding contract).

Gated behind RECEPTRA_LLM_LIVE_TEST=1 + @pytest.mark.live. CI on
ubuntu-latest skips these; a Mac developer with `ollama serve` running
and `dictalm3` registered runs:

    cd backend && RECEPTRA_LLM_LIVE_TEST=1 uv run pytest tests/llm/test_engine_live.py -x -v

The first test is structural — proves the streaming + parse + TTFT loop
is wired end-to-end against a real model. The second test is the
grounding contract: when context is IRRELEVANT to the question, the
model MUST emit the canonical Hebrew refusal. This is the v1 Phase 3
grounding bar (LLM-03 / RESEARCH §5.5).
"""

from __future__ import annotations

import asyncio

import pytest

from receptra.llm.engine import generate_suggestions
from receptra.llm.schema import ChunkRef, CompleteEvent, LlmErrorEvent, TokenEvent

from .conftest import live_test_enabled

_RETURNS_POLICY_CHUNK = ChunkRef(
    id="kb-policy-returns",
    text="מדיניות החזרים: ניתן להחזיר מוצר תוך 14 יום מיום הקנייה עם החשבונית המקורית.",
)


@pytest.mark.live
@pytest.mark.asyncio
async def test_grounded_reply_smoke_live() -> None:
    """Structural smoke: stream → parse → CompleteEvent, end-to-end against real DictaLM 3.0."""
    if not live_test_enabled():
        pytest.skip("set RECEPTRA_LLM_LIVE_TEST=1 to run live Ollama tests")

    transcript = "תוך כמה זמן אני יכול להחזיר מוצר?"
    chunks = [_RETURNS_POLICY_CHUNK]

    events: list[object] = []

    async def collect() -> None:
        async for ev in generate_suggestions(transcript, chunks):
            events.append(ev)

    # Cold-start absorbs ~5s; allow 60s ceiling.
    await asyncio.wait_for(collect(), timeout=60.0)

    # Filter and assert structurally.
    errors = [e for e in events if isinstance(e, LlmErrorEvent)]
    assert errors == [], f"unexpected LlmErrorEvent(s): {errors}"

    tokens = [e for e in events if isinstance(e, TokenEvent)]
    completes = [e for e in events if isinstance(e, CompleteEvent)]

    assert len(tokens) >= 1, "expected at least one TokenEvent (streaming worked)"
    assert (
        len(completes) == 1
    ), f"expected exactly one CompleteEvent, got {len(completes)}"

    complete = completes[0]
    assert complete.ttft_ms > 0, f"TTFT not measured: {complete.ttft_ms}"
    assert len(complete.suggestions) >= 1
    # Either grounded reply OR canonical refusal (both are valid model outputs;
    # grounding contract is enforced by the SECOND live test below).
    text = complete.suggestions[0].text
    assert text, "suggestion text empty"
    # Hebrew bytes must round-trip cleanly through the streaming + parse pipeline.
    assert (
        any(0x0590 <= ord(c) <= 0x05FF for c in text) or text == "אין לי מספיק מידע"
    ), f"suggestion text contains no Hebrew characters: {text!r}"


@pytest.mark.live
@pytest.mark.asyncio
async def test_grounding_refusal_on_irrelevant_context_live() -> None:
    """LLM-03 / RESEARCH §5.5 grounding contract — irrelevant context → canonical refusal.

    Transcript asks about store hours; the only chunk is about returns policy.
    The model MUST output exactly 'אין לי מספיק מידע' with empty citation_ids.
    If this assertion fails on a developer's machine, it indicates either
    (a) the prompt template regressed, or (b) DictaLM 3.0 behavior shifted —
    BOTH are Phase 3-quality blockers.
    """
    if not live_test_enabled():
        pytest.skip("set RECEPTRA_LLM_LIVE_TEST=1 to run live Ollama tests")

    transcript = "מה שעות הפעילות של החנות?"
    chunks = [_RETURNS_POLICY_CHUNK]

    events: list[object] = []

    async def collect() -> None:
        async for ev in generate_suggestions(transcript, chunks):
            events.append(ev)

    await asyncio.wait_for(collect(), timeout=60.0)

    completes = [e for e in events if isinstance(e, CompleteEvent)]
    assert len(completes) == 1
    refusal = completes[0].suggestions[0]
    assert refusal.text == "אין לי מספיק מידע", (
        f"grounding contract violated: model returned {refusal.text!r} when "
        f"context was irrelevant to the question. Phase 3 exit blocked. "
        f"Investigate: (a) prompt regression, (b) DictaLM version drift, (c) "
        f"few-shot example-2 byte-exact preservation in prompts.py."
    )
    assert (
        refusal.citation_ids == []
    ), f"grounding contract violated: refusal carried citation_ids={refusal.citation_ids}"
    assert refusal.confidence == 0.0
