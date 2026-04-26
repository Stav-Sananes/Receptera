"""Behavioral tests for receptra.llm.engine (Plan 03-04).

All tests use mocked AsyncClient — zero live Ollama dependency. The live
round-trip lives in test_engine_live.py, gated behind RECEPTRA_LLM_LIVE_TEST=1.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from receptra.llm.engine import (
    _CANONICAL_REFUSAL,
    LlmCallTrace,
    _strip_markdown_fences,
    generate_suggestions,
)
from receptra.llm.schema import (
    ChunkRef,
    CompleteEvent,
    LlmErrorEvent,
    SuggestionEvent,
    TokenEvent,
)


# --- Helpers ---------------------------------------------------------------


def _chunk(content: str = "", done: bool = False, **extra: Any) -> dict[str, Any]:
    return {"message": {"content": content}, "done": done, **extra}


async def _async_iter(items: list[Any]) -> AsyncIterator[Any]:
    for it in items:
        yield it


def _mock_async_client(stream_chunks: list[dict[str, Any]]) -> Any:
    """Return a MagicMock client whose .chat returns the canned async iterator."""
    client = MagicMock()
    client.chat = AsyncMock(return_value=_async_iter(stream_chunks))
    client.list = AsyncMock(
        return_value=MagicMock(models=[MagicMock(model="dictalm3:latest")])
    )
    return client


async def _drain(gen: Any) -> list[SuggestionEvent]:
    out: list[SuggestionEvent] = []
    async for ev in gen:
        out.append(ev)
    return out


def _patch_client_factory_and_select(
    monkeypatch: pytest.MonkeyPatch, client: Any, chosen: str = "dictalm3"
) -> None:
    monkeypatch.setattr("receptra.llm.engine.get_async_client", lambda: client)
    monkeypatch.setattr(
        "receptra.llm.engine.select_model", AsyncMock(return_value=chosen)
    )


# --- _strip_markdown_fences ------------------------------------------------


@pytest.mark.parametrize(
    "inp,expected",
    [
        ('```json\n{"a":1}\n```', '{"a":1}'),
        ('```\n{"a":1}\n```', '{"a":1}'),
        ('```{"a":1}```', '{"a":1}'),
        ('{"a":1}', '{"a":1}'),
        ('  {"a":1}  ', '{"a":1}'),
        ('{"a":"`backtick`"}', '{"a":"`backtick`"}'),
    ],
)
def test_strip_markdown_fences(inp: str, expected: str) -> None:
    assert _strip_markdown_fences(inp) == expected


# --- Short-circuit paths ---------------------------------------------------


@pytest.mark.asyncio
async def test_short_circuit_on_empty_context(monkeypatch: pytest.MonkeyPatch) -> None:
    traces: list[LlmCallTrace] = []
    chat_mock = AsyncMock()
    monkeypatch.setattr(
        "receptra.llm.engine.get_async_client",
        lambda: MagicMock(chat=chat_mock),
    )

    events = await _drain(
        generate_suggestions("שלום", [], record_call=traces.append)
    )

    assert len(events) == 1
    assert isinstance(events[0], CompleteEvent)
    assert events[0].suggestions == [_CANONICAL_REFUSAL]
    assert events[0].ttft_ms == 0
    chat_mock.assert_not_called()
    assert len(traces) == 1
    assert traces[0].status == "no_context"


@pytest.mark.asyncio
async def test_short_circuit_on_whitespace_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_mock = AsyncMock()
    monkeypatch.setattr(
        "receptra.llm.engine.get_async_client",
        lambda: MagicMock(chat=chat_mock),
    )

    events = await _drain(
        generate_suggestions("   \n\t  ", [ChunkRef(id="kb-1", text="x")])
    )

    assert len(events) == 1
    assert isinstance(events[0], CompleteEvent)
    assert events[0].suggestions == [_CANONICAL_REFUSAL]
    chat_mock.assert_not_called()


# --- Happy path ------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_streams_tokens_and_parses_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [
        _chunk('{"sug'),
        _chunk(
            'gestions":[{"text":"שלום","confidence":0.9,"citation_ids":["kb-1"]}]}'
        ),
        _chunk("", done=True, eval_count=12, prompt_eval_count=40),
    ]
    client = _mock_async_client(chunks)
    _patch_client_factory_and_select(monkeypatch, client)

    traces: list[LlmCallTrace] = []
    events = await _drain(
        generate_suggestions(
            "שלום עולם",
            [ChunkRef(id="kb-1", text="חומר רקע")],
            record_call=traces.append,
        )
    )

    token_evs = [e for e in events if isinstance(e, TokenEvent)]
    complete_evs = [e for e in events if isinstance(e, CompleteEvent)]
    assert len(token_evs) == 2
    assert len(complete_evs) == 1
    assert complete_evs[0].suggestions[0].text == "שלום"
    assert complete_evs[0].model == "dictalm3"
    assert complete_evs[0].ttft_ms >= 0
    assert traces[0].status == "ok"
    assert traces[0].suggestions_count == 1
    assert traces[0].grounded is True
    assert traces[0].eval_count == 12
    assert traces[0].prompt_eval_count == 40


@pytest.mark.asyncio
async def test_engine_does_not_pass_format_schema_while_streaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pitfall A regression — RESEARCH §3.5 streaming + format=schema unreliable."""
    chunks = [
        _chunk(
            '{"suggestions":[{"text":"x","confidence":0.5,"citation_ids":[]}]}',
            done=True,
        )
    ]
    client = _mock_async_client(chunks)
    _patch_client_factory_and_select(monkeypatch, client)

    await _drain(generate_suggestions("שלום", [ChunkRef(id="k", text="t")]))

    sent_kwargs = client.chat.call_args.kwargs
    assert sent_kwargs.get("stream") is True
    assert "format" not in sent_kwargs or sent_kwargs.get("format") is None


# --- Markdown fence handling ----------------------------------------------


@pytest.mark.asyncio
async def test_markdown_fenced_json_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = [
        _chunk(
            '```json\n{"suggestions":[{"text":"א","confidence":0.5,"citation_ids":[]}]}\n```',
            done=True,
        ),
    ]
    client = _mock_async_client(chunks)
    _patch_client_factory_and_select(monkeypatch, client)

    events = await _drain(
        generate_suggestions("שלום", [ChunkRef(id="k", text="t")])
    )
    completes = [e for e in events if isinstance(e, CompleteEvent)]
    assert completes[0].suggestions[0].text == "א"


# --- Parse retry paths -----------------------------------------------------


@pytest.mark.asyncio
async def test_parse_retry_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    bad_chunks = [_chunk('{"sug...truncated', done=True)]
    client = _mock_async_client(bad_chunks)
    _patch_client_factory_and_select(monkeypatch, client)

    monkeypatch.setattr(
        "receptra.llm.engine.retry_with_strict_json",
        AsyncMock(
            return_value='{"suggestions":[{"text":"ok","confidence":0.5,"citation_ids":[]}]}'
        ),
    )

    traces: list[LlmCallTrace] = []
    events = await _drain(
        generate_suggestions(
            "שלום", [ChunkRef(id="k", text="t")], record_call=traces.append
        )
    )

    completes = [e for e in events if isinstance(e, CompleteEvent)]
    errors = [e for e in events if isinstance(e, LlmErrorEvent)]
    assert len(completes) == 1
    assert len(errors) == 0
    assert completes[0].suggestions[0].text == "ok"
    assert traces[0].status == "parse_retry_ok"


@pytest.mark.asyncio
async def test_parse_retry_exhausted_yields_error_then_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad_chunks = [_chunk('{"sug...truncated', done=True)]
    client = _mock_async_client(bad_chunks)
    _patch_client_factory_and_select(monkeypatch, client)
    monkeypatch.setattr(
        "receptra.llm.engine.retry_with_strict_json",
        AsyncMock(return_value=None),
    )

    traces: list[LlmCallTrace] = []
    events = await _drain(
        generate_suggestions(
            "שלום", [ChunkRef(id="k", text="t")], record_call=traces.append
        )
    )

    errors = [(i, e) for i, e in enumerate(events) if isinstance(e, LlmErrorEvent)]
    completes = [(i, e) for i, e in enumerate(events) if isinstance(e, CompleteEvent)]
    assert len(errors) == 1
    assert len(completes) == 1
    assert (
        errors[0][0] < completes[0][0]
    ), "LlmErrorEvent must precede CompleteEvent on parse_error"
    assert errors[0][1].code == "parse_error"
    assert completes[0][1].suggestions == [_CANONICAL_REFUSAL]
    assert traces[0].status == "parse_error"


@pytest.mark.asyncio
async def test_parse_retry_returns_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    bad_chunks = [_chunk("not even json", done=True)]
    client = _mock_async_client(bad_chunks)
    _patch_client_factory_and_select(monkeypatch, client)
    monkeypatch.setattr(
        "receptra.llm.engine.retry_with_strict_json",
        AsyncMock(return_value="still not json"),
    )

    traces: list[LlmCallTrace] = []
    events = await _drain(
        generate_suggestions(
            "שלום", [ChunkRef(id="k", text="t")], record_call=traces.append
        )
    )
    assert any(
        isinstance(e, LlmErrorEvent) and e.code == "parse_error" for e in events
    )
    assert any(
        isinstance(e, CompleteEvent) and e.suggestions == [_CANONICAL_REFUSAL]
        for e in events
    )
    assert traces[0].status == "parse_error"


# --- Error paths -----------------------------------------------------------


@pytest.mark.asyncio
async def test_select_model_unreachable_yields_error_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from receptra.llm.client import OllamaUnreachableError

    monkeypatch.setattr("receptra.llm.engine.get_async_client", lambda: MagicMock())
    monkeypatch.setattr(
        "receptra.llm.engine.select_model",
        AsyncMock(side_effect=OllamaUnreachableError("connection refused")),
    )

    traces: list[LlmCallTrace] = []
    events = await _drain(
        generate_suggestions(
            "שלום", [ChunkRef(id="k", text="t")], record_call=traces.append
        )
    )

    assert len(events) == 1
    assert isinstance(events[0], LlmErrorEvent)
    assert events[0].code == "ollama_unreachable"
    assert traces[0].status == "ollama_unreachable"


@pytest.mark.asyncio
async def test_select_model_missing_yields_unreachable_with_model_missing_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from receptra.llm.client import OllamaModelMissingError

    monkeypatch.setattr("receptra.llm.engine.get_async_client", lambda: MagicMock())
    monkeypatch.setattr(
        "receptra.llm.engine.select_model",
        AsyncMock(
            side_effect=OllamaModelMissingError(
                "Neither dictalm3 nor qwen2.5:7b"
            )
        ),
    )

    traces: list[LlmCallTrace] = []
    events = await _drain(
        generate_suggestions(
            "שלום", [ChunkRef(id="k", text="t")], record_call=traces.append
        )
    )

    assert len(events) == 1
    assert isinstance(events[0], LlmErrorEvent)
    assert events[0].code == "ollama_unreachable"
    assert "model_missing:" in events[0].detail
    assert traces[0].status == "model_missing"


@pytest.mark.asyncio
async def test_read_timeout_mid_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    async def raising_iter() -> AsyncIterator[Any]:
        yield _chunk("partial")
        raise httpx.ReadTimeout("slow ollama")

    client = MagicMock()
    client.chat = AsyncMock(return_value=raising_iter())
    _patch_client_factory_and_select(monkeypatch, client)

    traces: list[LlmCallTrace] = []
    events = await _drain(
        generate_suggestions(
            "שלום", [ChunkRef(id="k", text="t")], record_call=traces.append
        )
    )

    # First a TokenEvent('partial') then LlmErrorEvent(code='timeout')
    assert any(isinstance(e, TokenEvent) and e.delta == "partial" for e in events)
    errs = [e for e in events if isinstance(e, LlmErrorEvent)]
    assert len(errs) == 1
    assert errs[0].code == "timeout"
    assert traces[0].status == "timeout"


@pytest.mark.asyncio
async def test_connect_error_mid_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    async def raising_iter() -> AsyncIterator[Any]:
        raise httpx.ConnectError("refused")
        yield  # unreachable

    client = MagicMock()
    client.chat = AsyncMock(return_value=raising_iter())
    _patch_client_factory_and_select(monkeypatch, client)

    traces: list[LlmCallTrace] = []
    events = await _drain(
        generate_suggestions(
            "שלום", [ChunkRef(id="k", text="t")], record_call=traces.append
        )
    )
    assert any(
        isinstance(e, LlmErrorEvent) and e.code == "ollama_unreachable"
        for e in events
    )
    assert traces[0].status == "ollama_unreachable"


@pytest.mark.asyncio
async def test_dos_oversize_transcript_yields_no_context_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("receptra.llm.engine.get_async_client", lambda: MagicMock())
    traces: list[LlmCallTrace] = []
    events = await _drain(
        generate_suggestions(
            "x" * 2001,
            [ChunkRef(id="k", text="t")],
            record_call=traces.append,
        )
    )
    assert len(events) == 1
    assert isinstance(events[0], LlmErrorEvent)
    assert events[0].code == "no_context"
    assert "transcript exceeds 2000" in events[0].detail
    assert traces[0].status == "no_context"


# --- TTFT measurement ------------------------------------------------------


@pytest.mark.asyncio
async def test_ttft_measured_within_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow_first_token() -> AsyncIterator[Any]:
        await asyncio.sleep(0.05)
        yield _chunk("שלום")
        yield _chunk("", done=True)

    client = MagicMock()
    client.chat = AsyncMock(return_value=slow_first_token())
    _patch_client_factory_and_select(monkeypatch, client)

    monkeypatch.setattr(
        "receptra.llm.engine.retry_with_strict_json",
        AsyncMock(
            return_value='{"suggestions":[{"text":"x","confidence":0.5,"citation_ids":[]}]}'
        ),
    )

    events = await _drain(
        generate_suggestions("שלום", [ChunkRef(id="k", text="t")])
    )
    completes = [e for e in events if isinstance(e, CompleteEvent)]
    assert (
        30 <= completes[0].ttft_ms <= 250
    ), f"ttft outside expected range: {completes[0].ttft_ms}"


# --- Concurrency regression (Pitfall C) ------------------------------------


@pytest.mark.asyncio
async def test_no_event_loop_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two concurrent generate_suggestions must NOT serialize.

    Each call's mock chat-iterator awaits asyncio.sleep(0.05) between 3 chunks
    (~150 ms per call). Concurrent should complete in ~150 ms; serialized
    would be ~300 ms. We assert <250 ms to leave scheduler slack.
    """

    def make_iter() -> Any:
        async def it() -> AsyncIterator[Any]:
            await asyncio.sleep(0.05)
            yield _chunk('{"suggestions":[{"text":"a"')
            await asyncio.sleep(0.05)
            yield _chunk(',"confidence":0.5,"citation_ids":[]}]}')
            await asyncio.sleep(0.05)
            yield _chunk("", done=True)

        return it()

    def make_client() -> Any:
        c = MagicMock()
        c.chat = AsyncMock(side_effect=lambda **_: make_iter())
        c.list = AsyncMock(
            return_value=MagicMock(models=[MagicMock(model="dictalm3:latest")])
        )
        return c

    monkeypatch.setattr("receptra.llm.engine.get_async_client", make_client)
    monkeypatch.setattr(
        "receptra.llm.engine.select_model", AsyncMock(return_value="dictalm3")
    )

    async def one_call() -> list[SuggestionEvent]:
        return await _drain(
            generate_suggestions("שלום", [ChunkRef(id="k", text="t")])
        )

    t0 = time.perf_counter()
    results = await asyncio.gather(one_call(), one_call())
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert all(any(isinstance(e, CompleteEvent) for e in r) for r in results)
    assert elapsed_ms < 250, f"concurrent calls serialized: {elapsed_ms} ms"


# --- Callback invariants ---------------------------------------------------


@pytest.mark.asyncio
async def test_record_call_invoked_exactly_once_per_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [
        _chunk(
            '{"suggestions":[{"text":"x","confidence":0.5,"citation_ids":[]}]}',
            done=True,
        )
    ]
    client = _mock_async_client(chunks)
    _patch_client_factory_and_select(monkeypatch, client)

    counter = {"n": 0}

    def cb(_t: LlmCallTrace) -> None:
        counter["n"] += 1

    await _drain(
        generate_suggestions(
            "שלום", [ChunkRef(id="k", text="t")], record_call=cb
        )
    )
    assert counter["n"] == 1


@pytest.mark.asyncio
async def test_record_call_default_no_op_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = [
        _chunk(
            '{"suggestions":[{"text":"x","confidence":0.5,"citation_ids":[]}]}',
            done=True,
        )
    ]
    client = _mock_async_client(chunks)
    _patch_client_factory_and_select(monkeypatch, client)

    events = await _drain(
        generate_suggestions("שלום", [ChunkRef(id="k", text="t")])
    )
    assert any(isinstance(e, CompleteEvent) for e in events)


@pytest.mark.asyncio
async def test_record_call_failure_does_not_crash_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense in depth: a buggy callback must NEVER propagate."""
    chunks = [
        _chunk(
            '{"suggestions":[{"text":"x","confidence":0.5,"citation_ids":[]}]}',
            done=True,
        )
    ]
    client = _mock_async_client(chunks)
    _patch_client_factory_and_select(monkeypatch, client)

    def bad_cb(_t: LlmCallTrace) -> None:
        raise RuntimeError("oops")

    events = await _drain(
        generate_suggestions(
            "שלום", [ChunkRef(id="k", text="t")], record_call=bad_cb
        )
    )
    assert any(isinstance(e, CompleteEvent) for e in events)
