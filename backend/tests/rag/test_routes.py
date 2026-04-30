"""TDD GREEN tests for receptra.rag.routes (Plan 04-05, Task 2).

15 tests covering all 6 /api/kb/* endpoints — upload, ingest-text,
documents GET, documents DELETE, query, and health — across happy paths,
Pydantic validation errors, and extension/size rejection.

Chaos paths (Chroma-down / Ollama-down) live in test_chaos.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _meta(filename: str = "policy.md", idx: int = 0) -> dict:  # type: ignore[type-arg]
    return {
        "filename": filename,
        "chunk_index": idx,
        "char_start": 0,
        "char_end": 10,
        "doc_sha": "abcd1234",
        "ingested_at_iso": "2026-04-27T12:00:00+00:00",
        "tenant_id": None,
    }


# ---------------------------------------------------------------------------
# POST /api/kb/upload
# ---------------------------------------------------------------------------


def test_upload_rtf_returns_415(client: TestClient) -> None:
    """Unsupported extension → 415 Unsupported Media Type.

    Feature 2: .pdf and .docx are now accepted; .rtf remains unsupported.
    """
    resp = client.post(
        "/api/kb/upload",
        files={"file": ("report.rtf", b"rtf content", "application/rtf")},
    )
    assert resp.status_code == 415
    body = resp.json()
    assert body["detail"]["code"] == "unsupported_extension"


def test_upload_oversized_content_length_returns_413(client: TestClient) -> None:
    """Content-Length > 2x MAX_BYTES → 413 pre-rejection."""
    from receptra.rag.ingest import MAX_BYTES

    resp = client.post(
        "/api/kb/upload",
        files={"file": ("big.txt", b"x", "text/plain")},
        headers={"content-length": str(MAX_BYTES * 3)},
    )
    assert resp.status_code == 413
    body = resp.json()
    assert body["detail"]["code"] == "file_too_large"


def test_upload_happy_path(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """Valid .md multipart upload → 200 IngestResult."""
    content = "מדיניות החברה: שעות פתיחה הן 9 עד 17.".encode()
    resp = client.post(
        "/api/kb/upload",
        files={"file": ("policy.md", content, "text/markdown")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filename"] == "policy.md"
    assert body["chunks_added"] >= 1
    assert body["bytes_ingested"] == len(content)
    # collection.add must have been called
    fake_collection.add.assert_called()


# ---------------------------------------------------------------------------
# POST /api/kb/ingest-text
# ---------------------------------------------------------------------------


def test_ingest_text_happy_path(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """JSON ingest with valid .txt content → 200 IngestResult."""
    resp = client.post(
        "/api/kb/ingest-text",
        json={"filename": "faq.txt", "content": "שאלות נפוצות בנושא שירות לקוחות."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filename"] == "faq.txt"
    assert body["chunks_added"] >= 1
    fake_collection.add.assert_called()


def test_ingest_text_unsupported_ext_returns_415(client: TestClient) -> None:
    """Unsupported extension via JSON ingest → 415.

    Feature 2: .pdf and .docx are now accepted; .rtf remains unsupported.
    """
    resp = client.post(
        "/api/kb/ingest-text",
        json={"filename": "doc.rtf", "content": "some content"},
    )
    assert resp.status_code == 415
    assert resp.json()["detail"]["code"] == "unsupported_extension"


def test_ingest_text_empty_after_chunking_returns_422(
    client: TestClient,
) -> None:
    """Whitespace-only content → empty_after_chunking → 422."""
    resp = client.post(
        "/api/kb/ingest-text",
        json={"filename": "empty.md", "content": "   \n\n\t  "},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "empty_after_chunking"


# ---------------------------------------------------------------------------
# GET /api/kb/documents
# ---------------------------------------------------------------------------


def test_list_documents_empty(client: TestClient, fake_collection: MagicMock) -> None:
    """No chunks stored → empty list response."""
    fake_collection.get.return_value = {"metadatas": []}
    resp = client.get("/api/kb/documents")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_documents_with_data(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """Chunks present → grouped KbDocument list (sorted by filename)."""
    fake_collection.get.return_value = {
        "metadatas": [
            _meta("faq.md", 0),
            _meta("faq.md", 1),
            _meta("policy.md", 0),
        ]
    }
    resp = client.get("/api/kb/documents")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 2
    filenames = [d["filename"] for d in docs]
    assert filenames == sorted(filenames)  # sorted by filename
    faq = next(d for d in docs if d["filename"] == "faq.md")
    assert faq["chunk_count"] == 2
    policy = next(d for d in docs if d["filename"] == "policy.md")
    assert policy["chunk_count"] == 1


# ---------------------------------------------------------------------------
# DELETE /api/kb/documents/{filename}
# ---------------------------------------------------------------------------


def test_delete_document_deletes_chunks(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """Existing document → deleted IDs returned, collection.delete called."""
    fake_collection.get.return_value = {
        "ids": ["abc:0", "abc:1", "abc:2"],
        "documents": [], "metadatas": [], "distances": [],
    }
    resp = client.delete("/api/kb/documents/policy.md")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 3}
    fake_collection.delete.assert_called_once_with(ids=["abc:0", "abc:1", "abc:2"])


def test_delete_document_not_found_returns_zero(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """Filename not in collection → deleted: 0, no delete call."""
    fake_collection.get.return_value = {
        "ids": [], "documents": [], "metadatas": [], "distances": [],
    }
    resp = client.delete("/api/kb/documents/nonexistent.md")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 0}
    fake_collection.delete.assert_not_called()


# ---------------------------------------------------------------------------
# POST /api/kb/query
# ---------------------------------------------------------------------------


def test_query_returns_chunks(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """Valid query → list of chunk dicts with id/text/source."""
    fake_collection.query.return_value = {
        "ids": [["abc:0"]],
        "documents": [["תוכן רלוונטי"]],
        "metadatas": [[_meta("policy.md", 0)]],
        "distances": [[0.1]],
    }
    resp = client.post(
        "/api/kb/query",
        json={"query": "מה שעות הפתיחה?", "top_k": 1},
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()
    assert len(results) == 1
    assert results[0]["id"] == "abc:0"
    assert results[0]["text"] == "תוכן רלוונטי"
    assert results[0]["source"]["filename"] == "policy.md"


def test_query_empty_query_rejected(client: TestClient) -> None:
    """Empty query string → Pydantic validation → 422."""
    resp = client.post("/api/kb/query", json={"query": ""})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/kb/health
# ---------------------------------------------------------------------------


def test_health_both_ok(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """Chroma + Ollama both ready → ok statuses."""
    fake_collection.count.return_value = 42
    resp = client.get("/api/kb/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["chroma"] == "ok"
    assert body["ollama"] == "ok"
    assert body["collection_count"] == 42


def test_health_ollama_down(client: TestClient, app: FastAPI) -> None:
    """embedder is None → ollama: down."""
    app.state.embedder = None
    resp = client.get("/api/kb/health")
    assert resp.status_code == 200
    assert resp.json()["ollama"] == "down"


def test_health_chroma_down(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """collection.count raises → chroma: down, count: -1."""
    fake_collection.count.side_effect = Exception("chroma gone")
    resp = client.get("/api/kb/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["chroma"] == "down"
    assert body["collection_count"] == -1


# ---------------------------------------------------------------------------
# GET /api/kb/documents/{filename}/chunks  — admin inspector
# ---------------------------------------------------------------------------


def test_get_document_chunks_returns_sorted_by_index(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """Out-of-order chunks → sorted by chunk_index ascending."""
    fake_collection.get.return_value = {
        "ids": ["abc:2", "abc:0", "abc:1"],
        "documents": ["chunk-2-text", "chunk-0-text", "chunk-1-text"],
        "metadatas": [_meta("p.md", 2), _meta("p.md", 0), _meta("p.md", 1)],
    }
    resp = client.get("/api/kb/documents/p.md/chunks")
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["chunk_index"] for r in rows] == [0, 1, 2]
    assert rows[0]["text"] == "chunk-0-text"


def test_get_document_chunks_empty(
    client: TestClient, fake_collection: MagicMock
) -> None:
    fake_collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}
    resp = client.get("/api/kb/documents/missing.md/chunks")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /api/kb/bulk-delete
# ---------------------------------------------------------------------------


def test_bulk_delete_removes_all_listed_files(
    client: TestClient, fake_collection: MagicMock
) -> None:
    """Two filenames → two get() calls, two delete() calls, total counted."""
    fake_collection.get.side_effect = [
        {"ids": ["a:0", "a:1"]},
        {"ids": ["b:0"]},
    ]
    resp = client.post("/api/kb/bulk-delete", json={"filenames": ["a.md", "b.md"]})
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 3}
    assert fake_collection.delete.call_count == 2


def test_bulk_delete_empty_request_returns_zero(
    client: TestClient, fake_collection: MagicMock
) -> None:
    resp = client.post("/api/kb/bulk-delete", json={"filenames": []})
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 0}
    fake_collection.get.assert_not_called()


# ---------------------------------------------------------------------------
# GET /api/kb/stats
# ---------------------------------------------------------------------------


def test_kb_stats_aggregates_by_filename(
    client: TestClient, fake_collection: MagicMock
) -> None:
    fake_collection.get.return_value = {
        "documents": ["שלום עולם", "תוכן רלוונטי", "עוד תוכן"],
        "metadatas": [
            {**_meta("faq.md", 0), "ingested_at_iso": "2026-04-27T10:00:00+00:00"},
            {**_meta("faq.md", 1), "ingested_at_iso": "2026-04-27T10:00:00+00:00"},
            {**_meta("policy.md", 0), "ingested_at_iso": "2026-04-28T10:00:00+00:00"},
        ],
    }
    resp = client.get("/api/kb/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_documents"] == 2
    assert body["n_chunks"] == 3
    assert body["total_bytes"] > 0
    assert body["oldest_ingest"] == "2026-04-27T10:00:00+00:00"
    assert body["newest_ingest"] == "2026-04-28T10:00:00+00:00"


def test_kb_stats_empty_collection(
    client: TestClient, fake_collection: MagicMock
) -> None:
    fake_collection.get.return_value = {"documents": [], "metadatas": []}
    resp = client.get("/api/kb/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "n_documents": 0,
        "n_chunks": 0,
        "total_bytes": 0,
        "oldest_ingest": None,
        "newest_ingest": None,
    }
