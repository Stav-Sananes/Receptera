"""Tests for the pipeline hot-path suggest factory (Phase 5 INT-01..INT-04).

Tests that make_suggest_fn:
- Returns an async callable
- Streams SuggestionToken / SuggestionComplete on the happy path (mocked LLM)
- Gracefully degrades when embedder is None (INT-04)
- Gracefully degrades when retrieval raises (INT-04)
- Emits SuggestionError on LLM error
- Records rag_latency_ms + e2e_latency_ms in SuggestionComplete
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.pipeline.conftest import _FakeWs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(coro: Any) -> Any:
    return await coro


def _make_token_complete_gen(
    tokens: list[str],
    model: str = "dictalm3",
) -> AsyncGenerator[Any, None]:
    """Async generator that yields TokenEvents then a CompleteEvent."""
    from receptra.llm.schema import CompleteEvent, Suggestion, TokenEvent

    async def _gen() -> AsyncGenerator[Any, None]:
        for t in tokens:
            yield TokenEvent(delta=t)
        yield CompleteEvent(
            suggestions=[Suggestion(text="תשובה", confidence=0.8, citation_ids=[])],
            ttft_ms=50,
            total_ms=200,
            model=model,
        )

    return _gen()


def _make_error_gen(code: str = "ollama_unreachable") -> AsyncGenerator[Any, None]:
    """Async generator that yields a single LlmErrorEvent."""
    from receptra.llm.schema import LlmErrorEvent

    async def _gen() -> AsyncGenerator[Any, None]:
        yield LlmErrorEvent(code=code, detail="test error")

    return _gen()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_make_suggest_fn_returns_callable(
    fake_ws: _FakeWs,
    fake_embedder: AsyncMock,
    fake_collection: MagicMock,
) -> None:
    """make_suggest_fn returns an async callable."""
    from receptra.pipeline.hot_path import make_suggest_fn

    fn = make_suggest_fn(fake_ws, fake_embedder, fake_collection)  # type: ignore[arg-type]
    assert callable(fn)


@pytest.mark.asyncio
async def test_suggest_happy_path_streams_tokens(
    fake_ws: _FakeWs,
    fake_embedder: AsyncMock,
    fake_collection: MagicMock,
) -> None:
    """Happy path: token events + suggestion_complete event emitted."""
    from receptra.pipeline.hot_path import make_suggest_fn

    gen = _make_token_complete_gen(["שלום", " ", "עולם"])

    with patch(
        "receptra.pipeline.hot_path.generate_suggestions",
        return_value=gen,
    ), patch(
        "receptra.pipeline.hot_path.retrieve",
        new_callable=lambda: lambda **_kw: asyncio.coroutine(lambda: [])(),
    ):
        # patch retrieve to return empty list (refusal path via chunks=[])
        # actually let's use a simple AsyncMock
        pass

    gen2 = _make_token_complete_gen(["שלום", " עולם"])

    async def _fake_retrieve(**_kw: Any) -> list[Any]:
        return []

    with patch("receptra.pipeline.hot_path.generate_suggestions", return_value=gen2), \
         patch("receptra.pipeline.hot_path.retrieve", side_effect=_fake_retrieve):
        fn = make_suggest_fn(fake_ws, fake_embedder, fake_collection)  # type: ignore[arg-type]
        await fn("מה שעות הפתיחה?", 1000, "test-utterance-id")

    types = [e["type"] for e in fake_ws.sent]
    assert "suggestion_token" in types
    assert "suggestion_complete" in types
    # No error events
    assert "suggestion_error" not in types


@pytest.mark.asyncio
async def test_suggest_with_null_embedder_degrades(
    fake_ws: _FakeWs,
    fake_collection: MagicMock,
) -> None:
    """INT-04: embedder=None → skip RAG → refusal (no exception, completes)."""
    from receptra.pipeline.hot_path import make_suggest_fn

    gen = _make_token_complete_gen([])

    with patch("receptra.pipeline.hot_path.generate_suggestions", return_value=gen):
        fn = make_suggest_fn(fake_ws, None, fake_collection)  # type: ignore[arg-type]
        await fn("שאלה כלשהי", 0, "utt-id-null-embedder")

    # Should NOT raise; should emit suggestion_complete (canonical refusal)
    types = [e["type"] for e in fake_ws.sent]
    assert "suggestion_complete" in types


@pytest.mark.asyncio
async def test_suggest_with_null_collection_degrades(
    fake_ws: _FakeWs,
    fake_embedder: AsyncMock,
) -> None:
    """INT-04: collection=None → skip RAG → refusal (no exception, completes)."""
    from receptra.pipeline.hot_path import make_suggest_fn

    gen = _make_token_complete_gen([])

    with patch("receptra.pipeline.hot_path.generate_suggestions", return_value=gen):
        fn = make_suggest_fn(fake_ws, fake_embedder, None)  # type: ignore[arg-type]
        await fn("שאלה", 0, "utt-id-null-collection")

    types = [e["type"] for e in fake_ws.sent]
    assert "suggestion_complete" in types


@pytest.mark.asyncio
async def test_suggest_rag_error_degrades(
    fake_ws: _FakeWs,
    fake_embedder: AsyncMock,
    fake_collection: MagicMock,
) -> None:
    """INT-04: retrieval exception → SuggestionError emitted, generation continues."""
    from receptra.pipeline.hot_path import make_suggest_fn

    gen = _make_token_complete_gen([])

    async def _bad_retrieve(**_kw: Any) -> list[Any]:
        raise RuntimeError("ChromaDB down")

    with patch("receptra.pipeline.hot_path.generate_suggestions", return_value=gen), \
         patch("receptra.pipeline.hot_path.retrieve", side_effect=_bad_retrieve):
        fn = make_suggest_fn(fake_ws, fake_embedder, fake_collection)  # type: ignore[arg-type]
        await fn("שאלה", 0, "utt-id-rag-error")

    types = [e["type"] for e in fake_ws.sent]
    # A degradation SuggestionError should be emitted
    assert "suggestion_error" in types
    # And generation still completes
    assert "suggestion_complete" in types


@pytest.mark.asyncio
async def test_suggest_llm_error_emits_suggestion_error(
    fake_ws: _FakeWs,
    fake_embedder: AsyncMock,
    fake_collection: MagicMock,
) -> None:
    """LLM error → SuggestionError emitted; no crash."""
    from receptra.pipeline.hot_path import make_suggest_fn

    gen = _make_error_gen("ollama_unreachable")

    async def _fake_retrieve(**_kw: Any) -> list[Any]:
        return []

    with patch("receptra.pipeline.hot_path.generate_suggestions", return_value=gen), \
         patch("receptra.pipeline.hot_path.retrieve", side_effect=_fake_retrieve):
        fn = make_suggest_fn(fake_ws, fake_embedder, fake_collection)  # type: ignore[arg-type]
        await fn("שאלה", 0, "utt-id-llm-error")

    types = [e["type"] for e in fake_ws.sent]
    assert "suggestion_error" in types


@pytest.mark.asyncio
async def test_suggest_complete_has_latency_fields(
    fake_ws: _FakeWs,
    fake_embedder: AsyncMock,
    fake_collection: MagicMock,
) -> None:
    """SuggestionComplete carries rag_latency_ms and e2e_latency_ms (INT-03)."""
    from receptra.pipeline.hot_path import make_suggest_fn

    gen = _make_token_complete_gen([])

    async def _fake_retrieve(**_kw: Any) -> list[Any]:
        return []

    with patch("receptra.pipeline.hot_path.generate_suggestions", return_value=gen), \
         patch("receptra.pipeline.hot_path.retrieve", side_effect=_fake_retrieve):
        fn = make_suggest_fn(fake_ws, fake_embedder, fake_collection)  # type: ignore[arg-type]
        await fn("שאלה", 0, "utt-id-latency")

    complete_events = [e for e in fake_ws.sent if e["type"] == "suggestion_complete"]
    assert complete_events, "No suggestion_complete event emitted"
    ev = complete_events[0]
    assert "rag_latency_ms" in ev
    assert "e2e_latency_ms" in ev
    assert isinstance(ev["rag_latency_ms"], int)
    assert isinstance(ev["e2e_latency_ms"], int)
