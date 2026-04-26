"""ChunkRef class identity tests for Phase 4 Wave-0.

The cross-phase contract: receptra.rag.types.ChunkRef MUST be the SAME
class object as receptra.llm.schema.ChunkRef. Phase 3 (Plan 03-02) is the
canonical owner; Phase 4 only re-exports. Phase 5 hot-path code that
imports from either module must see the same dataclass — `is` identity, not
just equality.
"""

from __future__ import annotations


def test_chunkref_class_identity() -> None:
    from receptra.llm.schema import ChunkRef as LlmChunkRef
    from receptra.rag.types import ChunkRef as RagChunkRef

    assert RagChunkRef is LlmChunkRef


def test_chunkref_constructable_via_rag_alias() -> None:
    from receptra.rag.types import ChunkRef

    ref = ChunkRef(id="c1", text="שלום", source={"filename": "a.md"})
    assert ref.id == "c1"
    assert ref.text == "שלום"
    assert ref.source == {"filename": "a.md"}


def test_chunkref_source_optional() -> None:
    from receptra.rag.types import ChunkRef

    ref = ChunkRef(id="c2", text="עולם")
    assert ref.source is None
