"""Re-export of ChunkRef.

Phase 3 (Plan 03-02) is the canonical owner of ChunkRef; this module
publishes the type under ``receptra.rag.types`` so Phase 4 ingest +
retriever code can import from a domain-aligned path. The class object
is the SAME — ``receptra.rag.types.ChunkRef is receptra.llm.schema.ChunkRef``.
Phase 5 + Phase 6 may import from either module without identity drift.
"""

from __future__ import annotations

from receptra.llm.schema import ChunkRef

__all__ = ["ChunkRef"]
