"""Chaos tests for receptra.rag.routes (Plan 04-05, Task 3).

6 tests exercising the two failure surfaces on all write/read paths:
  - ollama_unreachable: embedder raises httpx.HTTPError → 503
  - chroma_unreachable: collection op raises Exception → 503

Wire contract validated per RESEARCH §REST API + routes.py status mapping.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Upload + ingest-text — embedder failure
# ---------------------------------------------------------------------------


def test_upload_embedder_unreachable_returns_503(
    client: TestClient, fake_embedder: MagicMock
) -> None:
    """embed_batch raises HTTPError → 503 ollama_unreachable."""
    fake_embedder.embed_batch.side_effect = httpx.ConnectError("no ollama")
    resp = client.post(
        "/api/kb/upload",
        files={"file": ("p.md", b"content for test", "text/markdown")},
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["code"] == "ollama_unreachable"


def test_upload_chroma_unreachable_returns_503(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """collection.add raises Exception → 503 chroma_unreachable."""
    fake_collection.add.side_effect = Exception("chroma gone")
    resp = client.post(
        "/api/kb/upload",
        files={"file": ("p.md", b"content for test", "text/markdown")},
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["code"] == "chroma_unreachable"


# ---------------------------------------------------------------------------
# Query — embedder / chroma failure
# ---------------------------------------------------------------------------


def test_query_embedder_unreachable_returns_503(
    client: TestClient, fake_embedder: MagicMock
) -> None:
    """embed_one raises HTTPError → 503 ollama_unreachable."""
    fake_embedder.embed_one.side_effect = httpx.ConnectError("no ollama")
    resp = client.post(
        "/api/kb/query",
        json={"query": "מה שעות הפתיחה?"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "ollama_unreachable"


def test_query_chroma_unreachable_returns_503(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """collection.query raises Exception → 503 chroma_unreachable."""
    fake_collection.query.side_effect = Exception("chroma gone")
    resp = client.post(
        "/api/kb/query",
        json={"query": "מה שעות הפתיחה?"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "chroma_unreachable"


# ---------------------------------------------------------------------------
# List documents — chroma failure
# ---------------------------------------------------------------------------


def test_list_documents_chroma_down_returns_503(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """collection.get raises Exception → 503 chroma_unreachable."""
    fake_collection.get.side_effect = Exception("chroma gone")
    resp = client.get("/api/kb/documents")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "chroma_unreachable"


# ---------------------------------------------------------------------------
# Delete — chroma failure
# ---------------------------------------------------------------------------


def test_delete_chroma_down_returns_503(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """collection.get raises Exception during delete → 503 chroma_unreachable."""
    fake_collection.get.side_effect = Exception("chroma gone")
    resp = client.delete("/api/kb/documents/policy.md")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "chroma_unreachable"
