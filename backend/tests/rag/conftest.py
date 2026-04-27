"""RAG-test scaffolding for Phase 4.

The ``live`` marker is registered in tests/conftest.py (Plan 04-01).
This module publishes ``rag_live_test_enabled()`` gated on the SEPARATE
env var ``RECEPTRA_RAG_LIVE_TEST`` so RAG and LLM live tests can be
toggled independently — RAG live tests need ChromaDB up + bge-m3 pulled,
LLM live tests need DictaLM pulled.

Plan 04-05: adds ``fake_collection``, ``fake_embedder``, and a ``client``
fixture override that injects them into ``app.state`` after lifespan startup.
The global ``_stub_heavy_loaders`` (tests/conftest.py) already stubs the
real init; here we replace the generic stubs with introspectable mocks so
route tests can assert on collection/embedder calls.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def rag_live_test_enabled() -> bool:
    """True iff the developer opted into live RAG (Chroma + Ollama-bge-m3) tests."""
    return bool(os.getenv("RECEPTRA_RAG_LIVE_TEST"))


# ---------------------------------------------------------------------------
# Plan 04-05 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_collection() -> MagicMock:
    """Introspectable ChromaDB Collection stand-in for route tests."""
    c = MagicMock(name="chroma.Collection")
    c.get.return_value = {
        "ids": [],
        "documents": [],
        "metadatas": [],
        "distances": [],
    }
    c.count.return_value = 0
    c.query.return_value = {
        "ids": [[]],
        "documents": [[]],
        "metadatas": [[]],
        "distances": [[]],
    }
    c.add.return_value = None
    c.delete.return_value = None
    return c


@pytest.fixture
def fake_embedder() -> AsyncMock:
    """Introspectable BgeM3Embedder stand-in for route tests.

    embed_batch uses side_effect so it returns N vectors for N input texts,
    regardless of how many chunks ingest_document produces.
    """
    e = AsyncMock(name="BgeM3Embedder")
    e.embed_one.return_value = [0.0] * 1024
    e.embed_batch.side_effect = lambda texts: [[0.0] * 1024] * len(texts)
    return e


@pytest.fixture
def client(
    app: FastAPI,
    fake_collection: MagicMock,
    fake_embedder: AsyncMock,
) -> Iterator[TestClient]:
    """TestClient with introspectable RAG state for route + chaos tests.

    Overrides the parent-conftest ``client`` fixture for tests inside
    ``tests/rag/``. Lifespan runs first (with global stubs), then we
    replace ``app.state`` RAG singletons with our specific mocks so
    individual tests can assert on collection/embedder interactions.
    """
    with TestClient(app) as test_client:
        # Replace generic stubs from _stub_heavy_loaders with introspectable mocks.
        app.state.chroma_collection = fake_collection
        app.state.embedder = fake_embedder
        yield test_client
