"""Shared fixtures for pipeline tests.

Provides a fake WebSocket that records sent JSON frames, used to assert
pipeline event emission without a real ASGI connection.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeWs:
    """Captures send_json calls; raises on send_bytes (not used in pipeline)."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, data: dict[str, Any]) -> None:  # noqa: D401
        self.sent.append(data)

    async def send_bytes(self, data: bytes) -> None:
        raise AssertionError("send_bytes not expected in pipeline tests")  # pragma: no cover


@pytest.fixture
def fake_ws() -> _FakeWs:
    """Return a lightweight fake WebSocket that records send_json calls."""
    return _FakeWs()


@pytest.fixture
def fake_embedder() -> AsyncMock:
    """Async mock BgeM3Embedder returning a zero 1024-dim vector."""
    e = AsyncMock(name="BgeM3Embedder")
    e.embed_one.return_value = [0.0] * 1024
    e.embed_batch.side_effect = lambda texts: [[0.0] * 1024] * len(texts)
    return e


@pytest.fixture
def fake_collection() -> MagicMock:
    """Synchronous MagicMock ChromaDB Collection returning empty results by default."""
    c = MagicMock(name="chroma.Collection")
    c.get.return_value = {"ids": [], "documents": [], "metadatas": [], "distances": []}
    c.count.return_value = 0
    c.query.return_value = {
        "ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]
    }
    return c


@pytest.fixture
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Provide a fresh event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
