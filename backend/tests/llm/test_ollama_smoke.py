"""Smoke tests for the Phase 3 Ollama dep pin (LLM-01 Wave 0).

The ``live`` test asserts a host Ollama is reachable from the developer's
machine; CI on ubuntu-latest does NOT have Ollama installed so the test
self-skips when ``RECEPTRA_LLM_LIVE_TEST`` is unset.

The ``no side effects`` test runs in every environment and proves Task 1's
``ollama>=0.6.1,<1`` pin actually installed.
"""

from __future__ import annotations

import httpx
import pytest

from receptra.config import settings

from .conftest import live_test_enabled


def test_ollama_async_client_no_module_side_effects() -> None:
    """Importing ``ollama`` does not require Ollama to be running.

    Proves Task 1's dep pin worked. Runs everywhere.
    """
    import ollama

    assert hasattr(ollama, "AsyncClient")
    assert hasattr(ollama, "Client")


@pytest.mark.live
@pytest.mark.asyncio
async def test_ollama_async_client_lists_models() -> None:
    """Live Ollama smoke — only when RECEPTRA_LLM_LIVE_TEST=1.

    Asserts AsyncClient(host=settings.ollama_host).list() returns a dict
    containing a 'models' (or equivalent) key. Does NOT require dictalm3
    to be present — that is the chat-template grep test's job.
    """
    if not live_test_enabled():
        pytest.skip("set RECEPTRA_LLM_LIVE_TEST=1 to run live Ollama tests")

    from ollama import AsyncClient

    client = AsyncClient(
        host=settings.ollama_host,
        timeout=httpx.Timeout(settings.llm_request_timeout_s),
    )
    response = await client.list()
    # ollama-python 0.6.x returns a ListResponse with a `.models` attribute.
    # Older 0.5.x returns a dict {"models": [...]}. Accept both.
    models = response.models if hasattr(response, "models") else response["models"]
    assert models is not None
