"""Tests for POST /api/summary (Feature 3)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_ollama_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    resp = MagicMock()
    resp.message = msg
    return resp


SAMPLE_SUMMARY_JSON = json.dumps(
    {
        "topic": "שאילתת שעות פתיחה",
        "key_points": ["הלקוח שאל על שעות ביום שישי"],
        "action_items": [],
    }
)


@pytest.fixture
def summary_client(client: TestClient) -> TestClient:
    return client


def test_summary_endpoint_registered(summary_client: TestClient) -> None:
    """POST /api/summary exists (405 when body missing, not 404)."""
    r = summary_client.post("/api/summary", json={})
    assert r.status_code != 404


def test_summary_returns_structured_response(summary_client: TestClient) -> None:
    """POST /api/summary returns CallSummary schema."""
    mock_client = AsyncMock()
    mock_client.chat = AsyncMock(return_value=_make_ollama_response(SAMPLE_SUMMARY_JSON))

    with (
        patch("receptra.summary.router.get_async_client", return_value=mock_client),
        patch("receptra.summary.router.select_model", new=AsyncMock(return_value="dictalm3")),
    ):
        r = summary_client.post(
            "/api/summary",
            json={"transcript_lines": ["לקוח: מה שעות הפתיחה?", "סוכן: ראשון-חמישי 9-18"]},
        )
    assert r.status_code == 200
    body = r.json()
    assert "topic" in body
    assert "key_points" in body
    assert "action_items" in body
    assert "total_ms" in body


def test_summary_rejects_empty_transcript(summary_client: TestClient) -> None:
    r = summary_client.post("/api/summary", json={"transcript_lines": []})
    assert r.status_code == 422


def test_build_summary_messages_truncates_long_transcript() -> None:
    from receptra.summary.prompts import MAX_SUMMARY_TRANSCRIPT_CHARS, build_summary_messages

    long_transcript = "x" * (MAX_SUMMARY_TRANSCRIPT_CHARS + 5000)
    messages = build_summary_messages(long_transcript)
    last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
    assert len(last_user) <= MAX_SUMMARY_TRANSCRIPT_CHARS + 50  # +50 for <transcript> tags
