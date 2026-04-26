"""ChromaDB collection wrapper (RAG-02).

Sync HttpClient (D-03 lock) + ``asyncio.to_thread`` at the consumer site
(routes / ingest). The ``receptra_kb`` collection is the single-tenant v1
store; v2 multi-tenant adds tenant_id metadata filtering on top of this.

Plan 04-05 lifespan calls ``open_collection()`` once at startup;
consumers (Plan 04-04 ingest + retriever) receive the Collection via
``app.state.chroma_collection``.

Locks (RESEARCH §ChromaDB Pattern + Plan 04-01 settings):
- ``COLLECTION_NAME = "receptra_kb"`` — single v1 collection (Plan 04-04
  + 04-05 import this constant; renaming requires plan amendment).
- Cosine distance via ``metadata={"hnsw:space": "cosine"}`` — legacy form
  chosen over ``configuration={"hnsw": {"space": "cosine"}}`` per
  RESEARCH §Cluster 1 ("survives across all 1.x versions").
- BGE-M3 emits L2-normalized vectors per its model card → cosine distance
  maps directly to ``1 - cos_sim``.
- ``client.heartbeat()`` BEFORE ``get_or_create_collection`` so the fail
  path is "ChromaDB unreachable", not "collection create failed mid-flight".
- ``get_or_create_collection`` is idempotent on chromadb 1.5+ — returns
  the existing collection without overwriting metadata if the name is
  already present (RESEARCH §Cluster 1 citing chroma-core/chroma
  migration.mdx). Safe to call at every backend startup.
"""
from __future__ import annotations

from urllib.parse import urlparse

import chromadb
from chromadb.api.models.Collection import Collection

from receptra.config import settings
from receptra.rag.errors import RagInitError

COLLECTION_NAME = "receptra_kb"


def parse_chroma_host(host_url: str) -> tuple[str, int]:
    """Split ``'http://chromadb:8000'`` into ``('chromadb', 8000)``.

    Required because Phase 1 (``settings.chroma_host``) pinned the FULL
    URL form; ``chromadb.HttpClient`` takes ``(host, port)`` separately.
    Defaults port to 8000 when the URL omits an explicit port.

    Raises:
        RagInitError(code='chroma_unreachable'): on empty / malformed input.
    """
    parsed = urlparse(host_url)
    if not parsed.hostname:
        raise RagInitError(
            code="chroma_unreachable",
            detail=f"Invalid CHROMA_HOST: {host_url!r}",
        )
    return parsed.hostname, parsed.port or 8000


def open_collection() -> Collection:
    """Idempotent collection open with fail-fast heartbeat.

    Returns:
        The ``receptra_kb`` Collection from ``get_or_create_collection``
        with cosine distance metadata.

    Raises:
        RagInitError(code='chroma_unreachable'): on heartbeat failure or
            malformed CHROMA_HOST.
    """
    host, port = parse_chroma_host(settings.chroma_host)
    try:
        client = chromadb.HttpClient(host=host, port=port)
        client.heartbeat()  # raises on unreachable
    except RagInitError:
        # parse_chroma_host can raise RagInitError; do NOT double-wrap.
        raise
    except Exception as e:
        raise RagInitError(
            code="chroma_unreachable",
            detail=f"ChromaDB not reachable at {host}:{port}: {e}",
        ) from e
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


__all__ = ["COLLECTION_NAME", "open_collection", "parse_chroma_host"]
