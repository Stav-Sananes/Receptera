"""Tests for confidence-gated suggestions (Feature 1, v1.1).

Verifies:
- SuggestionComplete carries rag_max_similarity + rag_low_confidence fields
- low_confidence=True when max similarity < rag_suggestion_threshold
- low_confidence=False when max similarity >= threshold
- Frontend types mirror new fields (static — verified by TypeScript compiler)
"""
from __future__ import annotations

from receptra.pipeline.events import SuggestionComplete
from receptra.llm.schema import Suggestion


def _make_complete(**extra) -> SuggestionComplete:
    return SuggestionComplete(
        suggestions=[Suggestion(text="בסדר", confidence=0.9, citation_ids=[])],
        ttft_ms=100,
        total_ms=500,
        model="dictalm3",
        rag_latency_ms=50,
        e2e_latency_ms=1000,
        **extra,
    )


def test_suggestion_complete_has_rag_max_similarity_field() -> None:
    evt = _make_complete(rag_max_similarity=0.85, rag_low_confidence=False)
    assert evt.rag_max_similarity == 0.85


def test_suggestion_complete_has_rag_low_confidence_field() -> None:
    evt = _make_complete(rag_max_similarity=0.50, rag_low_confidence=True)
    assert evt.rag_low_confidence is True


def test_low_confidence_default_false() -> None:
    """Fields default to 0.0 / False for backward compat (e.g. degraded path)."""
    evt = _make_complete()
    assert evt.rag_max_similarity == 0.0
    assert evt.rag_low_confidence is False


def test_config_has_suggestion_threshold() -> None:
    from receptra.config import Settings
    s = Settings()
    assert hasattr(s, "rag_suggestion_threshold")
    assert 0.0 <= s.rag_suggestion_threshold <= 1.0


def test_suggestion_threshold_default_is_0_65() -> None:
    from receptra.config import Settings
    s = Settings()
    assert s.rag_suggestion_threshold == 0.65


def test_hot_path_computes_low_confidence_flag(tmp_path) -> None:
    """make_suggest_fn sets rag_low_confidence=True when max chunk similarity < threshold."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from receptra.pipeline.hot_path import make_suggest_fn
    from receptra.llm.schema import CompleteEvent, Suggestion, ChunkRef

    sent = []

    class FakeWs:
        async def send_json(self, data):
            sent.append(data)

    # Chunk with low similarity (0.45 < 0.65 threshold)
    low_sim_chunk = ChunkRef(
        id="chunk-1",
        text="שעות פתיחה 9-18",
        source={"filename": "hours.md", "chunk_index": "0", "similarity": "0.450"},
    )

    complete_event = CompleteEvent(
        suggestions=[Suggestion(text="test", confidence=0.9, citation_ids=[])],
        ttft_ms=0,
        total_ms=50,
        model="dictalm3",
    )

    async def fake_gen(transcript, chunks):
        yield complete_event

    with (
        patch("receptra.pipeline.hot_path.retrieve", return_value=[low_sim_chunk]),
        patch("receptra.pipeline.hot_path.generate_suggestions", side_effect=fake_gen),
    ):
        embedder = AsyncMock()
        collection = MagicMock()
        suggest = make_suggest_fn(FakeWs(), embedder, collection)
        asyncio.get_event_loop().run_until_complete(suggest("שאלה", 1000, "uid-1"))

    complete_events = [e for e in sent if e.get("type") == "suggestion_complete"]
    assert complete_events, f"No suggestion_complete found in: {sent}"
    evt = complete_events[0]
    assert "rag_low_confidence" in evt
    assert evt["rag_low_confidence"] is True
    assert "rag_max_similarity" in evt
    assert evt["rag_max_similarity"] == pytest.approx(0.45, abs=0.01)


import pytest
