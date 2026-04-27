"""Receptra FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI, WebSocket

from receptra.lifespan import lifespan
from receptra.rag.routes import router as kb_router
from receptra.stt.pipeline import websocket_stt_endpoint

app = FastAPI(
    title="Receptra",
    version="0.1.0",
    description="Hebrew-first local voice co-pilot backend.",
    lifespan=lifespan,
)

# RAG knowledge-base API (Plan 04-05 — RAG-03 + RAG-04 + RAG-06)
app.include_router(kb_router, prefix="/api/kb", tags=["kb"])


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe consumed by Docker healthcheck and CI smoke tests."""
    return {"status": "ok"}


@app.websocket("/ws/stt")
async def ws_stt(websocket: WebSocket) -> None:
    """Hebrew streaming STT endpoint (Plan 02-04 — STT-03 + STT-04).

    Wire contract: client sends 1024-byte int16 LE PCM frames; server
    sends JSON text frames per ``receptra.stt.events`` schema.
    Implementation lives in ``receptra.stt.pipeline.websocket_stt_endpoint``
    so Plan 02-06 can wrap the inner ``run_utterance_loop`` with metrics
    + audit-log instrumentation without touching this route definition.
    """
    await websocket_stt_endpoint(websocket)
