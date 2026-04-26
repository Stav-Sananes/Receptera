"""Ollama AsyncClient factory + model selection + bounded JSON-retry helper (LLM-01).

Three concerns, deliberately small surface:

1. ``get_async_client`` — factory; bound to ``settings.ollama_host`` +
   ``settings.llm_request_timeout_s`` by default. CLI harness (Plan 03-06)
   passes overrides for ``--ollama-host`` and per-test scenarios.

2. ``select_model`` — startup probe. Prefers ``settings.llm_model_tag``
   ('dictalm3'); falls back to ``settings.llm_model_fallback``
   ('qwen2.5:7b'); raises ``OllamaModelMissingError`` if both absent.
   Emits one structured loguru log line so Phase 7 prompt-eval can
   correlate results against which model actually served.

3. ``retry_with_strict_json`` — the one-shot bounded retry the engine
   (Plan 03-04) invokes when the streamed JSON fails to parse.
   ``stream=False`` + ``format='json'`` (loose Ollama JSON mode) + a Hebrew
   strict-JSON suffix on the system prompt. Returns the raw completion
   string; engine re-parses. Returns ``None`` on any failure so the engine
   can deterministically map onto the canonical Hebrew refusal.

Custom exceptions ``OllamaModelMissingError`` and ``OllamaUnreachableError``
are plain Exception subclasses; the engine maps them onto ``LlmErrorEvent``.

This module is STT-clean: importing it MUST NOT pull ``receptra.stt.*``.
A regression test in ``tests/llm/test_client.py`` guards the boundary.
"""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger
from ollama import AsyncClient

from receptra.config import settings

# --- Custom exceptions -----------------------------------------------------


class OllamaModelMissingError(Exception):
    """Neither primary nor fallback Ollama model is registered locally."""


class OllamaUnreachableError(Exception):
    """The Ollama HTTP server is unreachable (connection refused, timeout, etc.)."""


# --- Strict-JSON retry suffix (Hebrew) -------------------------------------
# RESEARCH §6.2 step 7 + OPEN-LLM-3: the bounded retry appends this suffix to
# the SYSTEM message only. The Hebrew literal stays in source so it is part
# of the audited LLM-input surface — modifying it requires plan amendment.
_STRICT_JSON_SUFFIX_HE: str = "\n\nהחזר אך ורק JSON תקין, ללא Markdown, ללא הסברים."


# --- Public surface --------------------------------------------------------


def get_async_client(
    host: str | None = None,
    timeout_s: float | None = None,
) -> AsyncClient:
    """Construct an ``ollama.AsyncClient`` bound to settings (or args).

    Args:
        host: Override ``settings.ollama_host``. Plan 03-06 CLI harness uses
            this to pass through the ``--ollama-host`` flag.
        timeout_s: Override ``settings.llm_request_timeout_s``. Per-test
            scenarios may shorten this to surface timeout paths.

    Returns:
        A configured ``ollama.AsyncClient``. The underlying ``httpx.AsyncClient``
        is bound to a ``Timeout(timeout_s)`` so every call returns within the
        bound — preventing a wedged Ollama process from hanging the WS loop
        (T-03-03-01 mitigation).
    """
    h = host if host is not None else settings.ollama_host
    t = timeout_s if timeout_s is not None else settings.llm_request_timeout_s
    return AsyncClient(host=h, timeout=httpx.Timeout(t))


def _extract_models(list_response: Any) -> list[str]:
    """Normalize ``client.list()`` output across ollama-python versions.

    Returns a list of model tag strings (e.g., ``['dictalm3:latest', 'qwen2.5:7b']``).
    Accepts both:

    - New ollama-python 0.6.x: ``ListResponse`` with ``.models`` attribute
      containing ``Model`` objects (each with ``.model`` attr).
    - Older versions: plain dict ``{'models': [{'model': '...'} | {'name': '...'}]}``.

    Unknown shapes return ``[]`` rather than raising — caller treats empty
    result as "neither tag present" which routes through the typed missing-
    model error path.
    """
    # New API: ListResponse-like with .models attribute
    if hasattr(list_response, "models"):
        out: list[str] = []
        for m in list_response.models:
            tag = getattr(m, "model", None)
            if tag is None and isinstance(m, dict):
                tag = m.get("model") or m.get("name")
            if tag:
                out.append(str(tag))
        return out

    # Old API: dict with 'models' key
    if isinstance(list_response, dict) and "models" in list_response:
        out2: list[str] = []
        for m in list_response["models"]:
            if isinstance(m, dict):
                tag = m.get("model") or m.get("name")
            else:
                tag = getattr(m, "model", None) or getattr(m, "name", None)
            if tag:
                out2.append(str(tag))
        return out2

    return []


def _tag_present(target: str, available: list[str]) -> bool:
    """Match ``target`` (e.g. ``'dictalm3'``) against ``available`` (e.g. ``['dictalm3:latest']``).

    Match policy:

    - Exact match wins (``'qwen2.5:7b'`` matches ``'qwen2.5:7b'``).
    - Bare repo name matches any tagged variant — split on ``:`` (``'dictalm3'``
      matches ``'dictalm3:latest'`` AND ``'dictalm3'``).
    - Repo prefix also matches across tag variants (``'qwen2.5:7b'`` against
      ``'qwen2.5:14b'`` — same repo, different tag, accept).
    """
    if target in available:
        return True
    target_repo = target.split(":")[0]
    return any(tag == target or tag.split(":")[0] == target_repo for tag in available)


async def select_model(client: AsyncClient) -> str:
    """Return the model tag to use; raises if neither primary nor fallback registered.

    Args:
        client: a configured ``AsyncClient``.

    Returns:
        ``settings.llm_model_tag`` when present in ``ollama list``,
        otherwise ``settings.llm_model_fallback``.

    Raises:
        OllamaUnreachableError: ``client.list()`` fails with
            ``httpx.ConnectError`` or ``httpx.ReadTimeout``.
        OllamaModelMissingError: neither primary nor fallback is registered.

    Side effects:
        Emits exactly one structured loguru log line:

        - INFO ``event="llm.model_selection"`` on primary selection.
        - WARN ``event="llm.model_selection"`` on fallback selection.

        The payload contains model tags only — never transcript text
        (T-03-03-04 mitigation).
    """
    try:
        resp = await client.list()
    except (httpx.ConnectError, httpx.ReadTimeout) as exc:
        raise OllamaUnreachableError(f"Ollama HTTP server unreachable: {exc}") from exc

    available = _extract_models(resp)
    primary = settings.llm_model_tag
    fallback = settings.llm_model_fallback

    if _tag_present(primary, available):
        logger.bind(event="llm.model_selection").info(
            {
                "chosen": primary,
                "primary_missing": False,
                "fallback_used": False,
                "available": available,
            }
        )
        return primary

    if _tag_present(fallback, available):
        logger.bind(event="llm.model_selection").warning(
            {
                "chosen": fallback,
                "primary_missing": True,
                "fallback_used": True,
                "available": available,
            }
        )
        return fallback

    raise OllamaModelMissingError(
        f"Neither {primary!r} nor {fallback!r} present in Ollama — "
        f"run `make models dictalm` or `make models qwen-fallback`. "
        f"Available: {available}"
    )


async def retry_with_strict_json(
    client: AsyncClient,
    model: str,
    base_messages: list[dict[str, str]],
) -> str | None:
    """One-shot bounded retry on JSON parse failure (RESEARCH §6.2 step 7).

    LOCKED retry contract:

    - ONE attempt only — no exponential backoff, no multi-attempt loop.
    - ``stream=False`` (we already streamed once and the parse failed; the
      retry trades latency for correctness).
    - ``format='json'`` (loose Ollama JSON mode — works without schema;
      RESEARCH §3.5 + §9 note ``format=<schema>`` + streaming unreliable).
    - Strict-JSON Hebrew suffix appended to the SYSTEM message of
      ``base_messages`` only — keeps few-shot turns intact.
    - Returns the assembled completion string (NOT a parsed
      ``SuggestionResponse`` — Plan 03-04 owns the parse + validation).
    - Returns ``None`` on any failure (httpx error, empty response,
      malformed shape). Plan 03-04 maps ``None`` → final canonical refusal.

    Args:
        client: a configured AsyncClient.
        model: the model tag selected by ``select_model``.
        base_messages: the original ChatML message list (system + few-shots
            + user). The first message MUST be the system prompt.

    Returns:
        The raw completion string on success; ``None`` on any failure.

    Side effects:
        Logs one WARN ``event="llm.retry_failed"`` line on each failure path.
    """
    if not base_messages or base_messages[0].get("role") != "system":
        # Defensive — Plan 03-02 always emits system as messages[0]. A caller
        # violating the contract gets a clean None; engine maps to canonical refusal.
        return None

    # Append the strict-JSON suffix to the system message; keep few-shots intact.
    # Defensive copy so the caller's list is not mutated.
    strict_messages: list[dict[str, str]] = [dict(m) for m in base_messages]
    strict_messages[0]["content"] = strict_messages[0]["content"] + _STRICT_JSON_SUFFIX_HE

    try:
        resp = await client.chat(
            model=model,
            messages=strict_messages,
            stream=False,
            format="json",
            options={
                "temperature": settings.llm_temperature,
                "num_predict": settings.llm_num_predict,
                "num_ctx": settings.llm_num_ctx,
                "top_p": settings.llm_top_p,
            },
        )
    except (httpx.ConnectError, httpx.ReadTimeout) as exc:
        logger.bind(event="llm.retry_failed").warning(
            {"error": str(exc), "model": model, "kind": exc.__class__.__name__}
        )
        return None
    except Exception as exc:  # broad except is intentional (T-03-03-03)
        # T-03-03-03: a malformed Ollama response or unexpected library error must
        # NEVER propagate up the retry boundary. Engine relies on this returning
        # None to deterministically fall back to the canonical Hebrew refusal.
        logger.bind(event="llm.retry_failed").warning(
            {"error": str(exc), "model": model, "kind": exc.__class__.__name__}
        )
        return None

    # Extract content via attribute then dict access (forward-compat).
    content: str | None = None
    msg = getattr(resp, "message", None)
    if msg is not None:
        content = getattr(msg, "content", None)
    if content is None and isinstance(resp, dict):
        content = resp.get("message", {}).get("content")

    if not content:
        logger.bind(event="llm.retry_failed").warning(
            {"error": "empty completion", "model": model}
        )
        return None
    return str(content)


__all__ = [
    "OllamaModelMissingError",
    "OllamaUnreachableError",
    "get_async_client",
    "retry_with_strict_json",
    "select_model",
]
