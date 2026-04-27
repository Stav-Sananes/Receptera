# Plan 04-05 Summary — RAG Routes + Lifespan

**Status:** Complete  
**Commit pair:** RED `dc7bbeb` → GREEN `70d150a`

## Public Surfaces

### /api/kb/* endpoints (receptra.rag.routes)

| Method | Path | Status codes |
|--------|------|-------------|
| POST | /api/kb/upload | 200, 413, 415, 422, 400, 503 |
| POST | /api/kb/ingest-text | 200, 415, 422, 400, 503 |
| GET | /api/kb/documents | 200, 503 |
| DELETE | /api/kb/documents/{filename} | 200, 503 |
| POST | /api/kb/query | 200, 422, 503 |
| GET | /api/kb/health | 200 |

HTTP mapping: `unsupported_extension → 415`, `file_too_large → 413`,
`encoding_error → 400`, `empty_after_chunking → 422`,
`ollama_unreachable / chroma_unreachable / model_missing → 503`.
Wire remap: `model_missing → ollama_unreachable` on the wire.

### app.state additions (lifespan.py)

- `app.state.embedder: BgeM3Embedder | None` — None if bge-m3 unavailable
- `app.state.chroma_collection: Collection | None` — None if Chroma unreachable

RAG init is fail-soft: STT pipeline starts even if KB subsystem is not ready.

## Tests Added

| File | Tests | Focus |
|------|-------|-------|
| test_routes.py | 15 | upload/ingest-text/documents/query/health happy paths + validation |
| test_chaos.py | 6 | Chroma-down + Ollama-down 503 paths for write + read + list + delete |
| **Total new** | **21** | |

Full backend suite: **307 pass / 8 skip** (excluding pre-existing pcm_roundtrip crash).

## Fixture Architecture

```
tests/conftest.py._stub_heavy_loaders (autouse)
  → stubs WhisperModel, load_silero_vad, BgeM3Embedder, open_collection
  → prevents any STT or RAG test from reaching real services

tests/rag/conftest.py.client (overrides parent)
  → depends on fake_collection + fake_embedder
  → injects introspectable mocks into app.state AFTER lifespan startup
  → allows per-test assert_called() / side_effect mutation
```

## PII Boundary

- `event="rag.query"` logs `query_hash` (sha256[:16]) + n_results, never raw query text
- `event="rag.ingest"` logs filename + chunk counts + bytes, never chunk body

## Cross-Phase Handoff

Plan 04-06 (eval harness):
- Uses `POST /api/kb/ingest-text` to load fixtures via `eval_rag.py`
- Uses `POST /api/kb/query` to measure recall@5 against 10 adversarial questions
- Uses `GET /api/kb/documents` to verify fixture load counts
