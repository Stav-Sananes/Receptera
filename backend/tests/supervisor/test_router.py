"""Tests for /api/supervisor/* + /ws/supervisor."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from receptra.supervisor.bus import bus


def test_status_endpoint_empty(client: TestClient) -> None:
    # Reset bus between tests — module-level singleton.
    bus._agents.clear()
    resp = client.get("/api/supervisor/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_agents"] == 0
    assert body["agents"] == []


def test_status_endpoint_with_agents(client: TestClient) -> None:
    bus._agents.clear()
    asyncio.run(
        bus.publish(
            {"type": "agent_connected", "agent_id": "agent-x", "ts_utc": "t"}
        )
    )
    resp = client.get("/api/supervisor/status")
    body = resp.json()
    assert body["n_agents"] == 1
    assert body["agents"][0]["agent_id"] == "agent-x"


def test_supervisor_ws_receives_initial_snapshot(client: TestClient) -> None:
    bus._agents.clear()
    asyncio.run(
        bus.publish(
            {"type": "agent_connected", "agent_id": "abc", "ts_utc": "t"}
        )
    )
    with client.websocket_connect("/ws/supervisor") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        assert any(a["agent_id"] == "abc" for a in msg["agents"])
