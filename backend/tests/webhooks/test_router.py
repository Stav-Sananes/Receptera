"""Tests for /api/webhooks/* routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from receptra.config import settings


def test_status_unconfigured(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "")
    monkeypatch.setattr(settings, "webhook_secret", "")
    resp = client.get("/api/webhooks/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"configured": False, "signed": False, "url_host": ""}


def test_status_configured(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "https://hooks.zapier.com/abc/def")
    monkeypatch.setattr(settings, "webhook_secret", "shh")
    resp = client.get("/api/webhooks/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["signed"] is True
    assert body["url_host"] == "hooks.zapier.com"


def test_test_endpoint_short_circuits_when_url_empty(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "")
    resp = client.post("/api/webhooks/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "not configured" in body["reason"]


def test_test_endpoint_dispatches_synthetic_payload(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_url", "https://hooks.example.com/x")

    with patch("receptra.webhooks.router.send_webhook", new=AsyncMock(return_value=True)):
        resp = client.post("/api/webhooks/test")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
