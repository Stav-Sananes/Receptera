"""Receptra FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI

from receptra.config import settings

app = FastAPI(
    title="Receptra",
    version="0.1.0",
    description="Hebrew-first local voice co-pilot backend.",
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe consumed by Docker healthcheck and CI smoke tests."""
    return {"status": "ok"}


@app.on_event("startup")
async def _log_config() -> None:
    """Log non-secret config on startup to aid debugging."""
    import logging

    logging.basicConfig(level=settings.log_level.upper())
    logger = logging.getLogger("receptra")
    logger.info(
        "receptra starting model_dir=%s ollama_host=%s chroma_host=%s",
        settings.model_dir,
        settings.ollama_host,
        settings.chroma_host,
    )
