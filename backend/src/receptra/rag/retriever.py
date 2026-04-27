"""Hebrew RAG retriever (RAG-04).

query → embed → ChromaDB.query → similarity filter → list[ChunkRef].

Returns ChunkRef instances from receptra.llm.schema (canonical class
identity preserved per Plan 04-01 contract — receptra.rag.types.ChunkRef
is the same class object). Phase 3 generate_suggestions short-circuits on
empty list[ChunkRef] to canonical "אין לי מספיק מידע" refusal.

D-03 lock: collection.query wrapped via asyncio.to_thread (sync HttpClient).
D-10 lock: min_similarity default from settings.rag_min_similarity (0.35).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from receptra.config import settings
from receptra.llm.schema import ChunkRef

if TYPE_CHECKING:
    from chromadb.api.models.Collection import Collection

    from receptra.rag.embeddings import BgeM3Embedder


async def retrieve(
    *,
    query: str,
    top_k: int = 5,
    embedder: BgeM3Embedder,
    collection: Collection,
    min_similarity: float | None = None,
) -> list[ChunkRef]:
    """Return top-K ChunkRefs above the cosine-similarity threshold.

    Args:
        query: Hebrew query string.
        top_k: max chunks to retrieve (ChromaDB n_results).
        embedder: BgeM3Embedder instance (injected by routes / test).
        collection: ChromaDB Collection (injected by routes / test).
        min_similarity: cosine similarity floor (0.0-1.0); chunks below
            threshold are silently dropped. Defaults to
            settings.rag_min_similarity (0.35 from Plan 04-01).

    Returns:
        list[ChunkRef] — empty list if no chunks pass threshold.
        Phase 3 generate_suggestions short-circuits empty list to refusal.
    """
    threshold = (
        min_similarity if min_similarity is not None else settings.rag_min_similarity
    )

    qvec = await embedder.embed_one(query)
    res = await asyncio.to_thread(
        collection.query,
        query_embeddings=[qvec],  # type: ignore[arg-type]
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    ids_list = (res["ids"] or [[]])[0]
    docs_list = (res["documents"] or [[]])[0]
    metas_list = (res["metadatas"] or [[]])[0]
    dists_list = (res["distances"] or [[]])[0]

    out: list[ChunkRef] = []
    for cid, doc, meta, dist in zip(
        ids_list,
        docs_list,
        metas_list,
        dists_list,
        strict=True,
    ):
        similarity = 1.0 - float(dist)  # cosine: distance → similarity
        if similarity < threshold:
            continue
        out.append(
            ChunkRef(
                id=cid,
                text=doc,
                source={
                    "filename": str(meta["filename"]),
                    "chunk_index": str(meta["chunk_index"]),
                    "char_start": str(meta["char_start"]),
                    "char_end": str(meta["char_end"]),
                    "similarity": f"{similarity:.3f}",
                },
            )
        )
    return out


__all__ = ["retrieve"]
