"""Tests for receptra.supervisor.bus — pub/sub + agent state snapshot."""

from __future__ import annotations

import asyncio

from receptra.supervisor.bus import EventBus


def test_subscribe_returns_queue() -> None:
    bus = EventBus()
    q = asyncio.run(bus.subscribe())
    assert isinstance(q, asyncio.Queue)
    assert bus.n_subscribers == 1


def test_publish_fans_out_to_all_subscribers() -> None:
    bus = EventBus()

    async def run():
        q1 = await bus.subscribe()
        q2 = await bus.subscribe()
        await bus.publish({"type": "agent_connected", "agent_id": "a1", "ts_utc": "t"})
        e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        assert e1["agent_id"] == "a1"
        assert e2["agent_id"] == "a1"

    asyncio.run(run())


def test_unsubscribe_removes_subscriber() -> None:
    bus = EventBus()

    async def run():
        q = await bus.subscribe()
        assert bus.n_subscribers == 1
        await bus.unsubscribe(q)
        assert bus.n_subscribers == 0

    asyncio.run(run())


def test_snapshot_tracks_agent_lifecycle() -> None:
    bus = EventBus()

    async def run():
        await bus.publish(
            {"type": "agent_connected", "agent_id": "a1", "ts_utc": "2026-04-30T12:00:00Z"}
        )
        await bus.publish(
            {"type": "agent_connected", "agent_id": "a2", "ts_utc": "2026-04-30T12:00:01Z"}
        )
        await bus.publish(
            {
                "type": "utterance_final",
                "agent_id": "a1",
                "text": "שלום",
                "stt_latency_ms": 400,
                "duration_ms": 1500,
            }
        )
        await bus.publish(
            {
                "type": "intent_detected",
                "agent_id": "a1",
                "label": "booking",
                "label_he": "הזמנה",
            }
        )
        await bus.publish({"type": "agent_disconnected", "agent_id": "a2"})

    asyncio.run(run())

    snapshot = bus.snapshot()
    assert len(snapshot) == 1  # a2 disconnected
    a1 = snapshot[0]
    assert a1["agent_id"] == "a1"
    assert a1["last_final_text"] == "שלום"
    assert a1["n_finals"] == 1
    assert a1["last_intent"] == {"label": "booking", "label_he": "הזמנה"}


def test_publish_drops_event_when_subscriber_queue_full() -> None:
    """Slow supervisor must not block the agent hot path."""
    bus = EventBus()

    async def run():
        q = await bus.subscribe()
        # Fill queue to its 100-item cap.
        for i in range(100):
            q.put_nowait({"i": i})
        # 101st publish should be silently dropped, not block.
        await asyncio.wait_for(
            bus.publish({"type": "agent_connected", "agent_id": "x", "ts_utc": "t"}),
            timeout=1.0,
        )
        assert q.qsize() == 100  # nothing added

    asyncio.run(run())


def test_suggestion_complete_updates_e2e_latency() -> None:
    bus = EventBus()

    async def run():
        await bus.publish(
            {"type": "agent_connected", "agent_id": "a1", "ts_utc": "t"}
        )
        await bus.publish(
            {
                "type": "suggestion_complete",
                "agent_id": "a1",
                "e2e_latency_ms": 1234,
                "rag_low_confidence": False,
                "n_suggestions": 1,
            }
        )

    asyncio.run(run())
    assert bus.snapshot()[0]["last_e2e_ms"] == 1234
