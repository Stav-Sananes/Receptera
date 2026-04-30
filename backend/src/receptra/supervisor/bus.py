"""In-process event bus + agent state registry.

Two responsibilities:

1. **Pub/sub**: agents publish events; supervisors subscribe via async queues.
2. **Snapshot state**: a new supervisor connection asks for the current
   roster (which agents are live, last intent, last transcript) so the UI
   doesn't start blank.

Both use only stdlib asyncio — no Redis, no Celery, no extra deps.

Per-supervisor queue is bounded (maxsize=100) — slow supervisor → drop oldest.
We never block the agent hot path.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from loguru import logger


@dataclass
class AgentSnapshot:
    """Per-agent state cached in memory, surfaced to new supervisors."""

    agent_id: str
    connected_at: str
    last_intent: dict[str, str] | None = None
    last_intent_at: str | None = None
    last_final_text: str = ""
    last_final_at: str | None = None
    n_finals: int = 0
    last_e2e_ms: int | None = None


@dataclass
class EventBus:
    """One bus per process. Hot path is `publish()`; never blocks."""

    _subscribers: list[asyncio.Queue[dict[str, Any]]] = field(default_factory=list)
    _agents: dict[str, AgentSnapshot] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Add a new supervisor subscriber. Returns its inbox queue."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        import contextlib

        async with self._lock:
            with contextlib.suppress(ValueError):
                self._subscribers.remove(q)

    async def publish(self, event: dict[str, Any]) -> None:
        """Fan-out one event to every connected supervisor.

        Mutates the per-agent snapshot in place so a new subscriber's
        ``snapshot()`` call returns up-to-date state.

        Drops events on a slow supervisor (queue full) — we never block
        the agent hot path on supervisor lag.
        """
        self._update_snapshot(event)
        async with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.bind(event="supervisor.dropped").warning(
                    {"reason": "subscriber queue full"}
                )

    def _update_snapshot(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        agent_id = event.get("agent_id")
        if not agent_id:
            return
        ts = event.get("ts_utc") or datetime.now(UTC).isoformat()

        if kind == "agent_connected":
            self._agents[agent_id] = AgentSnapshot(
                agent_id=agent_id, connected_at=ts
            )
        elif kind == "agent_disconnected":
            self._agents.pop(agent_id, None)
        elif kind == "utterance_final":
            snap = self._agents.get(agent_id)
            if snap:
                snap.last_final_text = event.get("text", "")
                snap.last_final_at = ts
                snap.n_finals += 1
        elif kind == "intent_detected":
            snap = self._agents.get(agent_id)
            if snap:
                snap.last_intent = {
                    "label": event.get("label", "other"),
                    "label_he": event.get("label_he", "אחר"),
                }
                snap.last_intent_at = ts
        elif kind == "suggestion_complete":
            snap = self._agents.get(agent_id)
            if snap:
                snap.last_e2e_ms = event.get("e2e_latency_ms")

    def snapshot(self) -> list[dict[str, Any]]:
        """Return per-agent state for a freshly subscribed supervisor."""
        return [
            {
                "agent_id": s.agent_id,
                "connected_at": s.connected_at,
                "last_intent": s.last_intent,
                "last_intent_at": s.last_intent_at,
                "last_final_text": s.last_final_text,
                "last_final_at": s.last_final_at,
                "n_finals": s.n_finals,
                "last_e2e_ms": s.last_e2e_ms,
            }
            for s in self._agents.values()
        ]

    @property
    def n_agents(self) -> int:
        return len(self._agents)

    @property
    def n_subscribers(self) -> int:
        return len(self._subscribers)


# Module-level singleton — one bus per process.
bus = EventBus()


__all__ = ["AgentSnapshot", "EventBus", "bus"]
