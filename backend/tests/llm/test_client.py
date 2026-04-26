"""Mocked-AsyncClient unit tests for receptra.llm.client (Plan 03-03).

Covers the three responsibilities of ``receptra.llm.client``:

1. ``get_async_client`` factory — defaults from settings, override args.
2. ``select_model`` probe — primary/fallback/missing branches; reachable
   error handling. Helpers ``_extract_models`` + ``_tag_present`` covered
   exhaustively (both API shapes accepted).
3. ``retry_with_strict_json`` helper — strict-suffix on system message,
   stream=False + format='json', None on connect/timeout/empty.

Plus a module-import regression: ``receptra.llm.client`` MUST NOT introduce
any new ``receptra.stt.*`` imports beyond what is already loaded by the
autouse conftest. Phase 5 hot-path keeps the LLM module STT-clean.
"""
from __future__ import annotations

import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from receptra.llm.client import (
    OllamaModelMissingError,
    OllamaUnreachableError,
    _extract_models,
    _tag_present,
    get_async_client,
    retry_with_strict_json,
    select_model,
)

# --- get_async_client ------------------------------------------------------


def test_get_async_client_uses_settings_defaults() -> None:
    """Smoke: factory constructs without error when called with no args."""
    c = get_async_client()
    assert c is not None


def test_get_async_client_accepts_override() -> None:
    """Override host + timeout — both should be accepted."""
    c = get_async_client(host="http://localhost:11434", timeout_s=5.0)
    assert c is not None


def test_get_async_client_accepts_only_host_override() -> None:
    """Partial override: host only, timeout falls back to settings."""
    c = get_async_client(host="http://example.invalid:11434")
    assert c is not None


def test_get_async_client_accepts_only_timeout_override() -> None:
    """Partial override: timeout only, host falls back to settings."""
    c = get_async_client(timeout_s=2.5)
    assert c is not None


# --- _extract_models / _tag_present (helpers) -----------------------------


def test_extract_models_handles_list_response_object() -> None:
    """ollama-python 0.6.x ListResponse with .models attr containing Model objects."""
    fake_model = MagicMock()
    fake_model.model = "dictalm3:latest"
    resp = MagicMock(spec=["models"])
    resp.models = [fake_model]
    assert _extract_models(resp) == ["dictalm3:latest"]


def test_extract_models_handles_dict_old_api() -> None:
    """Older ollama-python returned plain dicts {'models': [...]}."""
    resp = {"models": [{"model": "qwen2.5:7b"}, {"name": "bge-m3:latest"}]}
    assert _extract_models(resp) == ["qwen2.5:7b", "bge-m3:latest"]


def test_extract_models_empty_when_unknown_shape() -> None:
    """Unknown response shape (string, None, etc.) yields empty list, not crash."""
    assert _extract_models("not a known shape") == []
    assert _extract_models(None) == []


def test_extract_models_handles_listresponse_with_multiple_models() -> None:
    """List with multiple models returns them all in order."""
    fake_a = MagicMock()
    fake_a.model = "dictalm3:latest"
    fake_b = MagicMock()
    fake_b.model = "qwen2.5:7b"
    resp = MagicMock(spec=["models"])
    resp.models = [fake_a, fake_b]
    assert _extract_models(resp) == ["dictalm3:latest", "qwen2.5:7b"]


@pytest.mark.parametrize(
    "target,available,expected",
    [
        ("dictalm3", ["dictalm3:latest"], True),
        ("dictalm3", ["dictalm3"], True),
        ("qwen2.5:7b", ["qwen2.5:7b"], True),
        ("qwen2.5:7b", ["qwen2.5:14b"], True),  # repo prefix match
        ("dictalm3", ["llama3:8b"], False),
        ("dictalm3", [], False),
        ("dictalm3", ["dictalm3:latest", "qwen2.5:7b"], True),
    ],
)
def test_tag_present_matching(target: str, available: list[str], expected: bool) -> None:
    assert _tag_present(target, available) is expected


# --- select_model ----------------------------------------------------------


def _mock_client_with_models(tags: list[str]) -> Any:
    """AsyncMock client whose .list() returns a ListResponse-like object."""
    fake_resp = MagicMock(spec=["models"])
    fake_resp.models = [MagicMock(model=t) for t in tags]
    client = MagicMock()
    client.list = AsyncMock(return_value=fake_resp)
    return client


@pytest.mark.asyncio
async def test_select_model_prefers_primary_when_present() -> None:
    """Primary registered → returns settings.llm_model_tag."""
    client = _mock_client_with_models(["dictalm3:latest", "qwen2.5:7b"])
    chosen = await select_model(client)
    assert chosen == "dictalm3"


@pytest.mark.asyncio
async def test_select_model_falls_back_when_primary_missing() -> None:
    """Primary missing, fallback present → returns settings.llm_model_fallback."""
    client = _mock_client_with_models(["qwen2.5:7b"])
    chosen = await select_model(client)
    assert chosen == "qwen2.5:7b"


@pytest.mark.asyncio
async def test_select_model_raises_when_both_missing() -> None:
    """Neither tag present → typed OllamaModelMissingError with a recovery hint."""
    client = _mock_client_with_models(["llama3:8b"])
    with pytest.raises(OllamaModelMissingError, match="Neither"):
        await select_model(client)


@pytest.mark.asyncio
async def test_select_model_raises_when_both_missing_empty_list() -> None:
    """Empty model list → typed OllamaModelMissingError."""
    client = _mock_client_with_models([])
    with pytest.raises(OllamaModelMissingError):
        await select_model(client)


@pytest.mark.asyncio
async def test_select_model_unreachable_raises_typed_error() -> None:
    """httpx.ConnectError on .list() → OllamaUnreachableError, not raw httpx."""
    client = MagicMock()
    client.list = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    with pytest.raises(OllamaUnreachableError):
        await select_model(client)


@pytest.mark.asyncio
async def test_select_model_timeout_raises_unreachable() -> None:
    """httpx.ReadTimeout on .list() → OllamaUnreachableError."""
    client = MagicMock()
    client.list = AsyncMock(side_effect=httpx.ReadTimeout("read timed out"))
    with pytest.raises(OllamaUnreachableError):
        await select_model(client)


@pytest.mark.asyncio
async def test_select_model_handles_old_dict_api() -> None:
    """Backward-compat: old ollama-python returned {'models': [{'name': ...}]}."""
    client = MagicMock()
    client.list = AsyncMock(return_value={"models": [{"model": "dictalm3:latest"}]})
    chosen = await select_model(client)
    assert chosen == "dictalm3"


# --- retry_with_strict_json -----------------------------------------------


def _mock_chat_response(content: str) -> Any:
    """Build a ChatResponse-like mock with .message.content."""
    msg = MagicMock(spec=["content"])
    msg.content = content
    resp = MagicMock(spec=["message"])
    resp.message = msg
    return resp


@pytest.mark.asyncio
async def test_retry_appends_strict_suffix_to_system_message() -> None:
    """Strict suffix glued to system msg; turns untouched; stream=False, format=json."""
    captured: dict[str, Any] = {}

    async def fake_chat(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _mock_chat_response(
            '{"suggestions":[{"text":"x","confidence":0.5,"citation_ids":[]}]}'
        )

    client = MagicMock()
    client.chat = fake_chat

    base = [
        {"role": "system", "content": "ORIGINAL"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "final"},
    ]
    out = await retry_with_strict_json(client, "dictalm3", base)

    assert out == '{"suggestions":[{"text":"x","confidence":0.5,"citation_ids":[]}]}'
    sent = captured["messages"]
    assert sent[0]["role"] == "system"
    assert sent[0]["content"].startswith("ORIGINAL")
    # Hebrew strict suffix appended
    assert "JSON תקין" in sent[0]["content"]
    # User/assistant turns intact
    assert sent[1] == {"role": "user", "content": "u1"}
    assert sent[2] == {"role": "assistant", "content": "a1"}
    assert sent[3] == {"role": "user", "content": "final"}
    # stream=False, format='json' (Ollama loose JSON mode, NOT format=schema)
    assert captured["stream"] is False
    assert captured["format"] == "json"
    assert captured["model"] == "dictalm3"
    # Generation options forwarded from settings
    assert "options" in captured
    assert "temperature" in captured["options"]


@pytest.mark.asyncio
async def test_retry_does_not_mutate_input_messages() -> None:
    """Suffix-mutation must not alter the caller's base_messages list (defensive copy)."""

    async def fake_chat(**_: Any) -> Any:
        return _mock_chat_response(
            '{"suggestions":[{"text":"x","confidence":0.1,"citation_ids":[]}]}'
        )

    client = MagicMock()
    client.chat = fake_chat

    base = [
        {"role": "system", "content": "ORIGINAL"},
        {"role": "user", "content": "u"},
    ]
    base_copy_first = dict(base[0])
    await retry_with_strict_json(client, "dictalm3", base)

    # Caller's copy still pristine — suffix went into a defensive copy
    assert base[0] == base_copy_first
    assert base[0]["content"] == "ORIGINAL"


@pytest.mark.asyncio
async def test_retry_returns_none_on_connect_error() -> None:
    """httpx.ConnectError during retry → None (caller falls back to canonical refusal)."""

    async def fake_chat(**_: Any) -> Any:
        raise httpx.ConnectError("refused")

    client = MagicMock()
    client.chat = fake_chat

    base = [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}]
    assert await retry_with_strict_json(client, "dictalm3", base) is None


@pytest.mark.asyncio
async def test_retry_returns_none_on_read_timeout() -> None:
    """httpx.ReadTimeout during retry → None."""

    async def fake_chat(**_: Any) -> Any:
        raise httpx.ReadTimeout("timed out")

    client = MagicMock()
    client.chat = fake_chat

    base = [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}]
    assert await retry_with_strict_json(client, "dictalm3", base) is None


@pytest.mark.asyncio
async def test_retry_returns_none_on_empty_completion() -> None:
    """Empty .message.content → None, not empty-string success."""

    async def fake_chat(**_: Any) -> Any:
        return _mock_chat_response("")

    client = MagicMock()
    client.chat = fake_chat

    base = [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}]
    assert await retry_with_strict_json(client, "dictalm3", base) is None


@pytest.mark.asyncio
async def test_retry_returns_none_when_no_system_message() -> None:
    """Defensive: if base_messages does not start with system, short-circuit None."""
    client = MagicMock()
    client.chat = AsyncMock()  # should never be called
    base = [{"role": "user", "content": "u"}]
    assert await retry_with_strict_json(client, "dictalm3", base) is None
    client.chat.assert_not_called()


@pytest.mark.asyncio
async def test_retry_returns_none_on_empty_message_list() -> None:
    """Empty list → None, no chat call."""
    client = MagicMock()
    client.chat = AsyncMock()
    assert await retry_with_strict_json(client, "dictalm3", []) is None
    client.chat.assert_not_called()


@pytest.mark.asyncio
async def test_retry_handles_dict_response_shape() -> None:
    """Old-API dict response {'message': {'content': ...}} also extracts content."""

    async def fake_chat(**_: Any) -> Any:
        return {"message": {"content": "{}"}}

    client = MagicMock()
    client.chat = fake_chat

    base = [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}]
    out = await retry_with_strict_json(client, "dictalm3", base)
    assert out == "{}"


# --- exceptions: shape ----------------------------------------------------


def test_custom_exceptions_inherit_from_exception() -> None:
    """Both errors are plain Exception subclasses (NOT pydantic.BaseModel)."""
    from pydantic import BaseModel

    assert issubclass(OllamaModelMissingError, Exception)
    assert issubclass(OllamaUnreachableError, Exception)
    # Negative: must not be a pydantic model
    assert not issubclass(OllamaModelMissingError, BaseModel)
    assert not issubclass(OllamaUnreachableError, BaseModel)


def test_custom_exceptions_carry_message() -> None:
    """Exceptions carry the message string verbatim through str()."""
    e1 = OllamaModelMissingError("primary and fallback both missing")
    assert "missing" in str(e1)
    e2 = OllamaUnreachableError("connection refused")
    assert "refused" in str(e2)


# --- STT-isolation regression ---------------------------------------------


def test_client_module_does_not_import_receptra_stt() -> None:
    """``receptra.llm.client`` MUST NOT pull ``receptra.stt.*`` (LLM-06 prep).

    The autouse conftest already imports ``receptra.lifespan`` (which transitively
    imports ``receptra.stt.*``) for the Whisper/VAD stub patching. Therefore we
    must compare the DELTA introduced by importing ``receptra.llm.client`` —
    not the absolute set — to detect a regression.

    To avoid breaking other tests that compare class identity across the
    ``receptra.llm`` package boundary (e.g. ``test_package_reexports_public_surface``
    in ``test_schema.py``), we save and restore the original ``receptra.llm.*``
    entries instead of permanently dropping them.
    """
    # Save and drop the LLM cache so the import below actually re-executes.
    saved_llm: dict[str, Any] = {}
    for k in list(sys.modules):
        if k.startswith("receptra.llm"):
            saved_llm[k] = sys.modules.pop(k)
    try:
        stt_before = {k for k in sys.modules if k.startswith("receptra.stt")}

        import receptra.llm.client  # noqa: F401

        stt_after = {k for k in sys.modules if k.startswith("receptra.stt")}
        delta = stt_after - stt_before
        assert delta == set(), (
            f"`receptra.llm.client` must not introduce new receptra.stt imports; "
            f"new imports detected: {sorted(delta)}"
        )
    finally:
        # Restore original module identities so subsequent tests comparing
        # `receptra.llm.X is X` (e.g. test_package_reexports_public_surface)
        # see the same class objects they imported at module load time.
        for k in list(sys.modules):
            if k.startswith("receptra.llm"):
                del sys.modules[k]
        sys.modules.update(saved_llm)
