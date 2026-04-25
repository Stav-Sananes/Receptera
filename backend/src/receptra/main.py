"""Receptra FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI

from receptra.lifespan import lifespan

app = FastAPI(
    title="Receptra",
    version="0.1.0",
    description="Hebrew-first local voice co-pilot backend.",
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe consumed by Docker healthcheck and CI smoke tests."""
    return {"status": "ok"}
