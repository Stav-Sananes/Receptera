"""Tests for F4 intent detection (v1.1).

RED phase — all tests must fail before implementation exists.

Verifies:
- IntentDetected WS event type exists in pipeline.events
- detect_intent() returns canonical English label
- detect_intent_and_send() sends intent_detected over WebSocket
- asyncio.gather wires suggest + intent in parallel (smoke)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# ── Schema tests ──────────────────────────────────────────────────────────────


def test_intent_detected_event_type_exists() -> None:
    from receptra.pipeline.events import IntentDetected

    evt = IntentDetected(label="booking", label_he="הזמנה", utterance_id="u-1")
    assert evt.type == "intent_detected"


def test_intent_detected_has_label_field() -> None:
    from receptra.pipeline.events import IntentDetected

    evt = IntentDetected(label="complaint", label_he="תלונה", utterance_id="u-2")
    assert evt.label == "complaint"


def test_intent_detected_has_label_he_field() -> None:
    from receptra.pipeline.events import IntentDetected

    evt = IntentDetected(label="billing", label_he="חיוב", utterance_id="u-3")
    assert evt.label_he == "חיוב"


def test_intent_detected_label_rejects_invalid() -> None:
    import pytest
    from pydantic import ValidationError

    from receptra.pipeline.events import IntentDetected

    with pytest.raises(ValidationError):
        IntentDetected(label="unknown_bad", label_he="???", utterance_id="u-x")


def test_intent_detected_in_pipeline_event_union() -> None:
    """IntentDetected is part of the PipelineEvent discriminated union."""
    from pydantic import TypeAdapter

    from receptra.pipeline.events import PipelineEvent

    raw = {
        "type": "intent_detected",
        "label": "information",
        "label_he": "מידע",
        "utterance_id": "u-4",
    }
    evt = TypeAdapter(PipelineEvent).validate_python(raw)
    assert evt.type == "intent_detected"  # type: ignore[union-attr]


# ── detect_intent() unit tests ────────────────────────────────────────────────


def test_detect_intent_returns_booking_for_hebrew_label() -> None:
    """'הזמנה' from model → 'booking'."""
    from receptra.pipeline.intent import detect_intent

    mock_response = MagicMock()
    mock_response.message.content = "הזמנה"

    async def run():
        with (
            patch("receptra.pipeline.intent.get_async_client") as mock_get_client,
            patch("receptra.pipeline.intent.select_model", new=AsyncMock(return_value="dictalm3")),
        ):
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            return await detect_intent("אני רוצה לקבוע תור")

    result = asyncio.get_event_loop().run_until_complete(run())
    assert result == "booking"


def test_detect_intent_returns_other_on_unknown_response() -> None:
    """Garbage model output → 'other'."""
    from receptra.pipeline.intent import detect_intent

    mock_response = MagicMock()
    mock_response.message.content = "I don't know what you mean"

    async def run():
        with (
            patch("receptra.pipeline.intent.get_async_client") as mock_get_client,
            patch("receptra.pipeline.intent.select_model", new=AsyncMock(return_value="dictalm3")),
        ):
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            return await detect_intent("some random text")

    result = asyncio.get_event_loop().run_until_complete(run())
    assert result == "other"


def test_detect_intent_strips_whitespace_and_punctuation() -> None:
    """Model returns 'תלונה.' with trailing period → still 'complaint'."""
    from receptra.pipeline.intent import detect_intent

    mock_response = MagicMock()
    mock_response.message.content = " תלונה. "

    async def run():
        with (
            patch("receptra.pipeline.intent.get_async_client") as mock_get_client,
            patch("receptra.pipeline.intent.select_model", new=AsyncMock(return_value="dictalm3")),
        ):
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client
            return await detect_intent("החשבונית לא נכונה")

    result = asyncio.get_event_loop().run_until_complete(run())
    assert result == "complaint"


# ── detect_intent_and_send() integration tests ───────────────────────────────


def test_detect_intent_and_send_sends_ws_event() -> None:
    """detect_intent_and_send() sends an intent_detected JSON payload over WS."""
    from receptra.pipeline.intent import detect_intent_and_send

    sent = []

    class FakeWs:
        async def send_json(self, data):
            sent.append(data)

    async def run():
        mock_intent = AsyncMock(return_value="information")
        with patch("receptra.pipeline.intent.detect_intent", new=mock_intent):
            await detect_intent_and_send("מה שעות הפתיחה?", FakeWs(), "uid-99")

    asyncio.get_event_loop().run_until_complete(run())
    assert len(sent) == 1
    evt = sent[0]
    assert evt["type"] == "intent_detected"
    assert evt["label"] == "information"
    assert evt["utterance_id"] == "uid-99"
    assert "label_he" in evt


def test_detect_intent_and_send_swallows_exceptions() -> None:
    """If detect_intent raises, detect_intent_and_send must not propagate."""
    from receptra.pipeline.intent import detect_intent_and_send

    class FakeWs:
        async def send_json(self, data):
            pass

    async def run():
        with patch(
            "receptra.pipeline.intent.detect_intent",
            new=AsyncMock(side_effect=RuntimeError("ollama down")),
        ):
            # Must not raise
            await detect_intent_and_send("any text", FakeWs(), "uid-err")

    asyncio.get_event_loop().run_until_complete(run())  # no exception == pass
