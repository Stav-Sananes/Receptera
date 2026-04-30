"""Unit tests for receptra.webhooks.sender — HMAC, retry, 4xx vs 5xx."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from receptra.config import settings
from receptra.webhooks.schema import WebhookPayload, WebhookSummary
from receptra.webhooks.sender import _sign, send_webhook, verify_signature


def _payload() -> WebhookPayload:
    return WebhookPayload(
        call_id="t-1",
        ts_utc="2026-04-30T12:00:00+00:00",
        summary=WebhookSummary(
            topic="x", key_points=[], action_items=[], model="dictalm3", total_ms=10
        ),
    )


def test_sign_returns_sha256_prefix() -> None:
    sig = _sign(b"hello", "sekret")
    assert sig.startswith("sha256=")
    assert len(sig) == len("sha256=") + 64  # hex-encoded SHA-256


def test_verify_signature_round_trip() -> None:
    body = b'{"event":"call.summary"}'
    sig = _sign(body, "topsecret")
    assert verify_signature(body, sig, "topsecret") is True
    assert verify_signature(body, sig, "wrong-secret") is False
    assert verify_signature(body + b"x", sig, "topsecret") is False


def test_send_webhook_returns_false_when_url_empty(monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "")
    result = asyncio.run(send_webhook(_payload()))
    assert result is False


def test_send_webhook_2xx_returns_true(monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "https://hooks.example.com/x")
    monkeypatch.setattr(settings, "webhook_secret", "")

    fake_resp = httpx.Response(204)

    async def fake_post(self, url, **kw):
        return fake_resp

    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        result = asyncio.run(send_webhook(_payload()))
    assert result is True


def test_send_webhook_4xx_does_not_retry(monkeypatch) -> None:
    """403/422 from the receiver = misconfig. Don't retry, give up immediately."""
    monkeypatch.setattr(settings, "webhook_url", "https://hooks.example.com/x")

    n_calls = {"count": 0}

    async def fake_post(self, url, **kw):
        n_calls["count"] += 1
        return httpx.Response(403)

    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        result = asyncio.run(send_webhook(_payload()))

    assert result is False
    assert n_calls["count"] == 1, f"4xx should NOT retry; got {n_calls['count']} attempts"


def test_send_webhook_5xx_retries_three_times(monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "https://hooks.example.com/x")

    n_calls = {"count": 0}

    async def fake_post(self, url, **kw):
        n_calls["count"] += 1
        return httpx.Response(503)

    with (
        patch.object(httpx.AsyncClient, "post", new=fake_post),
        patch("receptra.webhooks.sender.asyncio.sleep", new=AsyncMock()),
    ):
        result = asyncio.run(send_webhook(_payload()))

    assert result is False
    assert n_calls["count"] == 3, f"5xx should retry to 3 attempts; got {n_calls['count']}"


def test_send_webhook_includes_signature_header_when_secret_set(monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "https://hooks.example.com/x")
    monkeypatch.setattr(settings, "webhook_secret", "supersecret")

    captured: dict = {}

    async def fake_post(self, url, **kw):
        captured["headers"] = dict(kw.get("headers") or {})
        return httpx.Response(200)

    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        result = asyncio.run(send_webhook(_payload()))

    assert result is True
    assert "X-Receptra-Signature" in captured["headers"]
    assert captured["headers"]["X-Receptra-Signature"].startswith("sha256=")


def test_send_webhook_omits_signature_when_secret_empty(monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "https://hooks.example.com/x")
    monkeypatch.setattr(settings, "webhook_secret", "")

    captured: dict = {}

    async def fake_post(self, url, **kw):
        captured["headers"] = dict(kw.get("headers") or {})
        return httpx.Response(200)

    with patch.object(httpx.AsyncClient, "post", new=fake_post):
        asyncio.run(send_webhook(_payload()))

    assert "X-Receptra-Signature" not in captured["headers"]


def test_send_webhook_network_error_retries_then_gives_up(monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "https://hooks.example.com/x")

    n_calls = {"count": 0}

    async def fake_post(self, url, **kw):
        n_calls["count"] += 1
        raise httpx.ConnectError("dns failed")

    with (
        patch.object(httpx.AsyncClient, "post", new=fake_post),
        patch("receptra.webhooks.sender.asyncio.sleep", new=AsyncMock()),
    ):
        result = asyncio.run(send_webhook(_payload()))

    assert result is False
    assert n_calls["count"] == 3
