# Plan 04-04 Summary — RAG Ingest + Retriever

**Status:** Complete  
**Commit pair:** RED `db42355` → GREEN `a998db6`

## Public Surfaces

### receptra.rag.schema (5 Pydantic v2 models)
- `IngestTextRequest(filename: str[1..255], content: str[0..1MiB])` — JSON ingest body
- `IngestResult(filename, chunks_added, chunks_replaced, bytes_ingested)` — success envelope
- `KbDocument(filename, chunk_count, ingested_at_iso)` — list-response item
- `KbQueryRequest(query: str[1..2000], top_k: int[1..20]=5)` — query body
- `KbErrorResponse(code: Literal[6], detail: str)` — typed error envelope

All `frozen=True, extra="forbid"` — mirrors `receptra.llm.schema` (Plan 03-02 lock).

### receptra.rag.ingest
```python
async def ingest_document(
    *, filename: str, content: bytes,
    embedder: BgeM3Embedder, collection: Collection,
) -> IngestResult
```
Constants: `ALLOWED_EXTS = frozenset({".md", ".txt"})`, `MAX_BYTES = 1_048_576`

### receptra.rag.retriever
```python
async def retrieve(
    *, query: str, top_k: int = 5,
    embedder: BgeM3Embedder, collection: Collection,
    min_similarity: float | None = None,
) -> list[ChunkRef]
```

## Tests Added

| File | Tests | Focus |
|------|-------|-------|
| test_04_schema.py | 8 | model construction, bounds, frozen, extra='forbid' |
| test_04_ingest.py | 12 | ext allowlist, size cap, UTF-8 strict, happy path, Pitfall #8, D-03, v2 forward-compat |
| test_04_retriever.py | 10 | ChunkRef identity, query/top_k passthrough, similarity filter, source metadata, D-03 |
| **Total new** | **30** | + 8 from 04-03-era test_schema.py |

Full backend suite: 289 pass / 8 skip (before 04-05 routes).

## Chunk ID Format
`{sha256(content)[:8]}:{chunk_index}` — stable across re-ingests of identical content.

## Metadata Schema
```python
{
    "filename": str,       # stored as metadata only — NEVER used as filesystem path
    "chunk_index": int,    # 0-based ordinal
    "char_start": int,     # offset into normalized text
    "char_end": int,       # exclusive offset
    "doc_sha": str,        # full sha256 hex
    "ingested_at_iso": str,# datetime.now(UTC).isoformat()
    "tenant_id": None,     # RESEARCH §Open Decision 4 v2 forward-compat
}
```

## Cross-Phase Handoff

Plan 04-05 (routes layer) imports:
- `ingest_document`, `ALLOWED_EXTS`, `MAX_BYTES` from `receptra.rag.ingest`
- `retrieve` from `receptra.rag.retriever`
- All 5 schema models from `receptra.rag.schema`
- `IngestRejected`, `RagInitError` from `receptra.rag.errors`

Phase 3 `generate_suggestions` receives `list[ChunkRef]` from `retrieve`; empty list → canonical refusal.

## Deviations
None. Implementation matches RESEARCH §Code Examples (lines 562-657) verbatim.
