"""Hebrew suggestion engine — AsyncGenerator[SuggestionEvent, None] (LLM-02 + LLM-03 + LLM-04).

Five paths, all observable from a single function:

1. Hard short-circuit — empty context or empty transcript → canonical
   refusal CompleteEvent, ZERO Ollama calls (RESEARCH §5.5 layer 1).
2. Happy path — stream tokens, parse on done, emit CompleteEvent + TTFT.
3. Parse-retry path — JSON parse fails → ONE bounded retry via
   ``retry_with_strict_json`` → either parsed CompleteEvent OR canonical
   refusal CompleteEvent + LlmErrorEvent(code='parse_error').
4. Ollama-unreachable — typed error from ``select_model`` or
   ``httpx.ConnectError`` mid-stream → LlmErrorEvent only.
5. Timeout — ``httpx.ReadTimeout`` → LlmErrorEvent(code='timeout').

Plan 03-05 wraps with metrics + SQLite audit via the ``record_call``
callback hook; this module deliberately does NOT call loguru / sqlite3
directly so engine tests can run without a writable audit DB.
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
from pydantic import ValidationError

from receptra.config import settings
from receptra.llm.client import (
    OllamaModelMissingError,
    OllamaUnreachableError,
    get_async_client,
    retry_with_strict_json,
    select_model,
)
from receptra.llm.prompts import build_messages
from receptra.llm.schema import (
    ChunkRef,
    CompleteEvent,
    LlmErrorEvent,
    Suggestion,
    SuggestionEvent,
    SuggestionResponse,
    TokenEvent,
)

# --- Trace dataclass (consumed by Plan 03-05 metrics + audit) -------------


@dataclass(frozen=True)
class LlmCallTrace:
    """Per-call structural trace handed to ``record_call``.

    Plan 03-05 converts this into ``LlmCallMetrics`` (loguru + SQLite).
    Status values: 'ok' | 'parse_retry_ok' | 'parse_error' |
    'ollama_unreachable' | 'timeout' | 'no_context' | 'model_missing'.
    """

    request_id: str
    transcript: str
    n_chunks: int
    model: str
    t_request_sent: float
    t_first_token: float | None
    t_done: float
    eval_count: int | None
    prompt_eval_count: int | None
    status: str
    suggestions_count: int
    grounded: bool


# --- Constants -------------------------------------------------------------


_CANONICAL_REFUSAL = Suggestion(
    text="אין לי מספיק מידע",
    confidence=0.0,
    citation_ids=[],
)


# --- Public API ------------------------------------------------------------


async def generate_suggestions(
    transcript: str,
    context_chunks: list[ChunkRef],
    *,
    request_id: str | None = None,
    model: str | None = None,
    record_call: Callable[[LlmCallTrace], None] | None = None,
) -> AsyncGenerator[SuggestionEvent, None]:
    """Stream suggestion events for one ``(transcript, context)`` pair.

    Yields ``TokenEvent`` for each non-empty content delta, then exactly one
    ``CompleteEvent`` (after JSON parse + bounded retry), OR exactly one
    ``LlmErrorEvent`` if Ollama is unreachable / times out (no terminal
    CompleteEvent in those error modes — Phase 5 INT-04 graceful-degradation
    branch handles them).

    The ``record_call`` callback is invoked EXACTLY ONCE per invocation,
    in the finally block; default no-op. Plan 03-05 wires it to
    ``log_llm_call`` + ``insert_llm_call``.
    """
    rid = request_id or uuid4().hex
    chosen_model = model or settings.llm_model_tag
    t_request_sent = time.perf_counter()
    t_first_token: float | None = None
    eval_count: int | None = None
    prompt_eval_count: int | None = None
    accumulated: list[str] = []
    status = "ok"
    suggestions_count = 0
    grounded = False
    cb = record_call or (lambda _trace: None)

    try:
        # --- Short-circuit (RESEARCH §5.5 layer 1) ---
        if not context_chunks or not transcript.strip():
            status = "no_context"
            yield CompleteEvent(
                suggestions=[_CANONICAL_REFUSAL],
                ttft_ms=0,
                total_ms=int((time.perf_counter() - t_request_sent) * 1000),
                model=chosen_model,
            )
            suggestions_count = 1
            grounded = False
            return

        # --- Build messages (DoS bounds enforced by build_user_message) ---
        try:
            messages = build_messages(
                transcript,
                context_chunks,
                lang=settings.llm_system_prompt_lang,
            )
        except ValueError as exc:
            status = "no_context"
            yield LlmErrorEvent(code="no_context", detail=str(exc))
            return

        # --- Acquire client + choose model ---
        client = get_async_client()
        try:
            chosen_model = await select_model(client) if model is None else model
        except OllamaUnreachableError as exc:
            status = "ollama_unreachable"
            yield LlmErrorEvent(code="ollama_unreachable", detail=str(exc))
            return
        except OllamaModelMissingError as exc:
            status = "model_missing"
            # Wire-level we collapse model_missing onto ollama_unreachable so
            # the consumer-facing Literal allowlist stays at 4 values; audit
            # status retains the granular 'model_missing' for Phase 7 analysis.
            yield LlmErrorEvent(
                code="ollama_unreachable", detail=f"model_missing: {exc}"
            )
            return

        # --- Stream the chat call ---
        try:
            stream = await client.chat(
                model=chosen_model,
                messages=messages,
                stream=True,
                options={
                    "temperature": settings.llm_temperature,
                    "num_predict": settings.llm_num_predict,
                    "num_ctx": settings.llm_num_ctx,
                    "top_p": settings.llm_top_p,
                    "stop": ["<|im_end|>"],
                },
                # NOTE: format=<schema> intentionally OMITTED while streaming
                # (RESEARCH §3.5 — upstream issues #14440/#15260).
            )
            async for chunk in stream:
                delta, done, ec, pec = _extract_chunk_fields(chunk)
                if delta:
                    if t_first_token is None:
                        t_first_token = time.perf_counter()
                    accumulated.append(delta)
                    yield TokenEvent(delta=delta)
                if done:
                    eval_count = ec
                    prompt_eval_count = pec
        except httpx.ReadTimeout as exc:
            status = "timeout"
            yield LlmErrorEvent(code="timeout", detail=str(exc))
            return
        except httpx.ConnectError as exc:
            status = "ollama_unreachable"
            yield LlmErrorEvent(code="ollama_unreachable", detail=str(exc))
            return

        # --- Parse on done; bounded retry on failure ---
        raw = "".join(accumulated)
        cleaned = _strip_markdown_fences(raw)
        parsed: SuggestionResponse | None = None
        try:
            parsed = SuggestionResponse.model_validate_json(cleaned)
        except (ValidationError, ValueError, json.JSONDecodeError):
            # Bounded ONE retry (RESEARCH §6.2 step 7)
            retry_raw = await retry_with_strict_json(client, chosen_model, messages)
            if retry_raw is not None:
                try:
                    parsed = SuggestionResponse.model_validate_json(
                        _strip_markdown_fences(retry_raw)
                    )
                    status = "parse_retry_ok"
                except (ValidationError, ValueError, json.JSONDecodeError):
                    parsed = None
            if parsed is None:
                status = "parse_error"
                t_done_now = time.perf_counter()
                ttft = (
                    int((t_first_token - t_request_sent) * 1000)
                    if t_first_token is not None
                    else -1
                )
                yield LlmErrorEvent(
                    code="parse_error", detail="JSON parse failed after retry"
                )
                yield CompleteEvent(
                    suggestions=[_CANONICAL_REFUSAL],
                    ttft_ms=ttft,
                    total_ms=int((t_done_now - t_request_sent) * 1000),
                    model=chosen_model,
                )
                suggestions_count = 1
                grounded = False
                return

        # --- Happy path / parse_retry_ok path ---
        t_done = time.perf_counter()
        ttft_ms = (
            int((t_first_token - t_request_sent) * 1000)
            if t_first_token is not None
            else -1
        )
        yield CompleteEvent(
            suggestions=list(parsed.suggestions),
            ttft_ms=ttft_ms,
            total_ms=int((t_done - t_request_sent) * 1000),
            model=chosen_model,
        )
        suggestions_count = len(parsed.suggestions)
        grounded = any(s.citation_ids for s in parsed.suggestions)

    finally:
        t_done_final = time.perf_counter()
        with contextlib.suppress(Exception):
            # Defense in depth: a callback bug must NEVER crash the engine.
            # Plan 03-05's record_call also swallows internally.
            cb(
                LlmCallTrace(
                    request_id=rid,
                    transcript=transcript,
                    n_chunks=len(context_chunks),
                    model=chosen_model,
                    t_request_sent=t_request_sent,
                    t_first_token=t_first_token,
                    t_done=t_done_final,
                    eval_count=eval_count,
                    prompt_eval_count=prompt_eval_count,
                    status=status,
                    suggestions_count=suggestions_count,
                    grounded=grounded,
                )
            )


# --- Helpers ---------------------------------------------------------------


def _extract_chunk_fields(
    chunk: Any,
) -> tuple[str, bool, int | None, int | None]:
    """Normalize an Ollama stream chunk to (delta, done, eval_count, prompt_eval_count).

    ollama-python returns dict-shaped chunks per RESEARCH §1.3; some versions
    expose object-shaped responses. Duck-type both.
    """
    msg = getattr(chunk, "message", None)
    if msg is not None:
        delta_raw = getattr(msg, "content", None)
        if delta_raw is None and isinstance(msg, dict):
            delta_raw = msg.get("content", "")
        delta = delta_raw or ""
    elif isinstance(chunk, dict):
        delta = chunk.get("message", {}).get("content", "") or ""
    else:
        delta = ""

    if isinstance(chunk, dict):
        done = bool(chunk.get("done", False))
        ec = chunk.get("eval_count")
        pec = chunk.get("prompt_eval_count")
    else:
        done = bool(getattr(chunk, "done", False))
        ec = getattr(chunk, "eval_count", None)
        pec = getattr(chunk, "prompt_eval_count", None)

    return str(delta), done, ec, pec


_FENCE_PREFIXES: tuple[str, ...] = ("```json", "```")


def _strip_markdown_fences(text: str) -> str:
    """Strip leading ```json / ``` and trailing ``` if present.

    Idempotent. Non-fenced text returns unchanged. Mid-body backticks
    are preserved.
    """
    s = text.strip()
    for prefix in _FENCE_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix) :]
            # Drop one optional newline after the prefix
            if s.startswith("\n"):
                s = s[1:]
            break
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


__all__ = [
    "_CANONICAL_REFUSAL",
    "LlmCallTrace",
    "_strip_markdown_fences",
    "generate_suggestions",
]
