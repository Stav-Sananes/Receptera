"""HTTP + WebSocket routes for /api/supervisor/* and /ws/supervisor.

GET  /api/supervisor/status — REST snapshot for non-WS clients.
WS   /ws/supervisor          — live event stream + initial snapshot.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from receptra.supervisor.bus import bus

router = APIRouter()


@router.get("/status")
async def supervisor_status() -> dict[str, Any]:
    """REST snapshot of all currently connected agents."""
    return {
        "n_agents": bus.n_agents,
        "n_supervisors": bus.n_subscribers,
        "agents": bus.snapshot(),
    }


async def supervisor_ws(websocket: WebSocket) -> None:
    """Live event stream for the supervisor dashboard.

    On connect: receives one ``snapshot`` event with the current roster,
    then a continuous stream of pub/sub events from the agent bus.
    """
    await websocket.accept()
    queue = await bus.subscribe()

    # Initial snapshot so the UI doesn't start blank.
    try:
        await websocket.send_json({"type": "snapshot", "agents": bus.snapshot()})
    except Exception:
        await bus.unsubscribe(queue)
        return

    try:
        while True:
            # Concurrently watch for client disconnect (recv) and new events.
            event_task = asyncio.create_task(queue.get())
            recv_task = asyncio.create_task(websocket.receive_text())
            done, pending = await asyncio.wait(
                {event_task, recv_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
            if recv_task in done:
                # Client sent something or disconnected — either way, exit
                # if it was a disconnect.
                try:
                    recv_task.result()
                except WebSocketDisconnect:
                    return
                except Exception:
                    return
                continue
            event = event_task.result()
            try:
                await websocket.send_json(event)
            except Exception:
                return
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.bind(event="supervisor.ws_error").exception({"err": str(exc)})
    finally:
        await bus.unsubscribe(queue)


__all__ = ["router"]
