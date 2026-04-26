---
phase: 04-hebrew-rag-knowledge-base
plan: 03
subsystem: rag
tags:
  - rag
  - hebrew
  - embeddings
  - bge-m3
  - chromadb
  - vector-store
  - tdd
requires:
  - receptra.config.settings.ollama_host (Plan 04-01)
  - receptra.config.settings.chroma_host (Plan 04-01)
  - receptra.config.settings.rag_embed_batch_size (Plan 04-01)
  - receptra.rag.errors.RagInitError (Plan 04-01)
  - ollama.AsyncClient (Plan 03-01 dep lock)
  - chromadb.HttpClient + chromadb.api.models.Collection.Collection (Plan 04-01 dep lock)
provides:
  - receptra.rag.embeddings.BgeM3Embedder (DIM=1024 + MODEL='bge-m3' + create_and_verify + embed_one + embed_batch)
  - receptra.rag.vector_store.COLLECTION_NAME ('receptra_kb')
  - receptra.rag.vector_store.parse_chroma_host (URL → (host, port))
  - receptra.rag.vector_store.open_collection (heartbeat-first idempotent open with cosine metadata)
affects:
  - backend/src/receptra/rag/embeddings.py (NEW)
  - backend/src/receptra/rag/vector_store.py (NEW)
  - backend/tests/rag/test_embeddings.py (NEW — 8 mocked tests)
  - backend/tests/rag/test_vector_store.py (NEW — 8 mocked tests)
  - backend/tests/rag/test_embeddings_live.py (NEW — 2 live round-trips, RECEPTRA_RAG_LIVE_TEST gated)
tech_stack_added: []
patterns:
  - Phase 3 LLM client pattern mirrored byte-for-byte: typed errors, fail-fast classmethod, no global state, no logging in hot path
  - Symbol-import-site monkeypatch (Plan 03-05 lock): patch AsyncClient + chromadb on the *imported* symbol inside receptra.rag.embeddings / receptra.rag.vector_store, NOT via string paths (string paths break under full-suite alphabetical ordering once tests/llm/test_client.py mutates sys.modules)
  - Settings monkeypatch via shared singleton (Plan 03-05 canonical): `from receptra.config import settings as receptra_settings; monkeypatch.setattr(receptra_settings, "rag_embed_batch_size", 4)`
  - Cosine distance via legacy `metadata={"hnsw:space": "cosine"}` form (NOT `configuration={...}`) per RESEARCH §Cluster 1 ("survives across all 1.x versions")
  - Inner `except RagInitError: raise` clause prevents double-wrapping when parse_chroma_host raises before the broad `except Exception`
  - keep_alive='5m' (NOT -1) — RESEARCH §Cluster 2: amortizes intra-job + query-session calls without parking VRAM forever
  - client.embed() (NOT deprecated client.embeddings()) — RESEARCH §Cluster 2 explicit lock for ollama 0.6.x
  - Sync chromadb HttpClient + asyncio.to_thread at consumer site (D-03 lock); Plan 04-04/05 wrap blocking calls
  - Test cast helper `_fake_client(embedder) -> _FakeAsyncClient` keeps mypy strict satisfied while letting tests assert on fake-only state (queue_embed_response, embed_calls, etc.)
key_files:
  created:
    - backend/src/receptra/rag/embeddings.py
    - backend/src/receptra/rag/vector_store.py
    - backend/tests/rag/test_embeddings.py
    - backend/tests/rag/test_vector_store.py
    - backend/tests/rag/test_embeddings_live.py
  modified: []
decisions:
  - D-01 confirmed: chromadb-client>=1.5.8,<2 is the only Phase 4 dep added (Plan 04-01 already pinned in pyproject.toml; this plan consumes it)
  - D-02 confirmed: BGE-M3 via Ollama Python `embed()` (NOT deprecated `embeddings()`) — locked in client.embed(model=..., input=..., keep_alive='5m')
  - D-03 confirmed: Sync HttpClient + asyncio.to_thread at consumer; embedder stays async — Plan 04-05 lifespan owns the asyncio.to_thread wrap (T-04-03-08 mitigation)
  - D-12 confirmed: Lifespan loads collection at startup, fail-fast on unreachable — heartbeat() before get_or_create_collection produces clean RagInitError(chroma_unreachable)
  - Cosine distance pinned via metadata={"hnsw:space": "cosine"} legacy form (RESEARCH §Cluster 1 explicit choice over configuration={...})
  - keep_alive='5m' locked as `_KEEP_ALIVE` class constant (private; not env-tunable in v1 — adjustment requires plan amendment)
  - Default batch_size flows from `settings.rag_embed_batch_size` (Plan 04-01 default = 16); per-call kwarg override allowed for tests
  - test_embeddings.py: introduced `_fake_client(embedder)` cast helper (Rule 3 auto-fix) so mypy strict stays clean while runtime tests use the fake's introspection surface
metrics:
  duration: 8min
  tasks_completed: 2
  files_changed: 5
  completed_date: "2026-04-26"
---

# Phase 04 Plan 03: BgeM3Embedder + ChromaDB Wrapper Summary

BGE-M3 embedder (1024-dim Hebrew vectors via Ollama AsyncClient with 5-minute keep-alive) and ChromaDB collection wrapper (cosine-distance pinned, heartbeat-first idempotent open) — Phase 3 LLM-client pattern mirrored byte-for-byte. Closes RAG-01 + RAG-02.

## Commits

| Type | SHA | Message |
|------|-----|---------|
| RED  | `3a3f8c9` | test(04-03): add failing tests for receptra.rag.embeddings + vector_store (mocked Ollama + Chroma) |
| GREEN | `fb000d3` | feat(04-03): implement BgeM3Embedder + open_collection (RAG-01 + RAG-02) |

TDD gate sequence verified: 16 failing tests → 16 passing tests (`receptra.rag.embeddings` + `receptra.rag.vector_store` symbols added in GREEN).

## Public Surface

**`receptra.rag.embeddings`** (RAG-01):

```python
from receptra.rag.embeddings import BgeM3Embedder

class BgeM3Embedder:
    DIM: int = 1024            # Plan 04-04/05 health endpoint imports
    MODEL: str = "bge-m3"      # Plan 04-04 ingest imports

    @classmethod
    async def create_and_verify(cls) -> BgeM3Embedder: ...
    # ↑ Plan 04-05 FastAPI lifespan: app.state.embedder = await BgeM3Embedder.create_and_verify()

    async def embed_one(self, text: str) -> list[float]: ...
    # ↑ 1024 floats; client.embed(model='bge-m3', input=text, keep_alive='5m')

    async def embed_batch(
        self,
        texts: Sequence[str],
        batch_size: int | None = None,  # default = settings.rag_embed_batch_size (16)
    ) -> list[list[float]]: ...
```

**`receptra.rag.vector_store`** (RAG-02):

```python
from receptra.rag.vector_store import (
    COLLECTION_NAME,        # = "receptra_kb"
    parse_chroma_host,
    open_collection,
)

def parse_chroma_host(host_url: str) -> tuple[str, int]: ...
# ↑ "http://chromadb:8000" → ("chromadb", 8000); raises RagInitError(chroma_unreachable) on bad URL

def open_collection() -> Collection: ...
# ↑ Plan 04-05 lifespan: app.state.chroma_collection = await asyncio.to_thread(open_collection)
#   Returns receptra_kb Collection with metadata={"hnsw:space": "cosine"}.
#   Idempotent — chromadb 1.5+ get_or_create_collection returns existing without overwriting.
```

## Tests Added (18 total)

**Mocked unit tests (16):**

| # | File | Test | Pins |
|---|------|------|------|
| 1 | test_embeddings.py | test_class_constants | DIM=1024 + MODEL='bge-m3' |
| 2 | test_embeddings.py | test_create_and_verify_success | Happy-path show('bge-m3') |
| 3 | test_embeddings.py | test_create_and_verify_raises_model_missing | RagInitError(model_missing), detail mentions `make models-bge` |
| 4 | test_embeddings.py | test_embed_one_returns_1024_floats | 1024 floats + verbatim kwargs (model, input, keep_alive='5m') — T-04-03-01 guard |
| 5 | test_embeddings.py | test_embed_batch_chunks_by_batch_size | 5 inputs / batch=2 → 3 calls of (2, 2, 1) |
| 6 | test_embeddings.py | test_embed_batch_uses_settings_default | No kwarg → settings.rag_embed_batch_size (4 in test, 16 in prod) |
| 7 | test_embeddings.py | test_embed_batch_preserves_order | Sentinel-encoded vectors verify cross-batch ordering |
| 8 | test_embeddings.py | test_embed_one_propagates_httpx_errors | httpx.ConnectError NOT swallowed (Plan 04-05 wraps to 503) |
| 9 | test_vector_store.py | test_collection_name_constant | COLLECTION_NAME = 'receptra_kb' |
| 10 | test_vector_store.py | test_parse_chroma_host_compose | 'http://chromadb:8000' → ('chromadb', 8000) |
| 11 | test_vector_store.py | test_parse_chroma_host_localhost | 'http://localhost:8000' → ('localhost', 8000) |
| 12 | test_vector_store.py | test_parse_chroma_host_default_port | 'http://chromadb' → port 8000 |
| 13 | test_vector_store.py | test_parse_chroma_host_invalid | Empty / 'not-a-url' → RagInitError(chroma_unreachable) — T-04-03-05 |
| 14 | test_vector_store.py | test_open_collection_happy_path | heartbeat() called; get_or_create called with verbatim cosine metadata — T-04-03-04 |
| 15 | test_vector_store.py | test_open_collection_unreachable | heartbeat raises → RagInitError(chroma_unreachable), detail has host:port |
| 16 | test_vector_store.py | test_open_collection_idempotent | Two calls → identical kwargs both times (chromadb 1.5+ get_or_create idempotency) |

**Live tests (2, RECEPTRA_RAG_LIVE_TEST=1 gate):**

| # | File | Test | Behavior |
|---|------|------|----------|
| 17 | test_embeddings_live.py | test_bge_m3_embed_one_round_trip | Real Ollama + bge-m3 → 1024 floats for "שלום עולם" |
| 18 | test_embeddings_live.py | test_bge_m3_embed_batch_round_trip | Real Ollama → 3 vectors of 1024 floats for 3 Hebrew prompts (batch=2) |

Both live tests triple-gate skip: `RECEPTRA_RAG_LIVE_TEST=1` env var + `ollama` binary on PATH + bge-m3 actually pulled (caught via `RagInitError`). Cleanly self-skip on every CI executor.

**Full backend suite delta:** 234 pass → 250 pass (+16 mocked); 8 skip (+ 2 new live skips, both RECEPTRA_RAG_LIVE_TEST gated). Ruff + mypy strict clean across 65 source files.

## Smoke Verification

```
$ uv run python -c "from receptra.rag.embeddings import BgeM3Embedder; \
  from receptra.rag.vector_store import open_collection, parse_chroma_host, COLLECTION_NAME; \
  print(BgeM3Embedder.DIM, BgeM3Embedder.MODEL, COLLECTION_NAME); \
  print(parse_chroma_host('http://chromadb:8000'))"
1024 bge-m3 receptra_kb
('chromadb', 8000)
```

## Cross-Phase Handoff

**Plan 04-04 (RAG-04 ingest pipeline + retriever)** consumes:

```python
from receptra.rag.embeddings import BgeM3Embedder
from receptra.rag.vector_store import COLLECTION_NAME
from chromadb.api.models.Collection import Collection

async def ingest(text: str, embedder: BgeM3Embedder, collection: Collection) -> None:
    chunks = chunk_hebrew(text)                                  # Plan 04-02
    vectors = await embedder.embed_batch([c.text for c in chunks])  # Plan 04-03 — this plan
    await asyncio.to_thread(                                     # D-03: sync chromadb wrapped at consumer
        collection.upsert,
        ids=[f"{doc_sha[:8]}:{c.chunk_index}" for c in chunks],
        embeddings=vectors,
        documents=[c.text for c in chunks],
    )
```

**Plan 04-05 (FastAPI router + lifespan)** consumes:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.embedder = await BgeM3Embedder.create_and_verify()                # async
    app.state.chroma_collection = await asyncio.to_thread(open_collection)      # T-04-03-08 mitigation
    yield
```

`open_collection()` is sync (D-03 lock) so the lifespan wraps it in `asyncio.to_thread` to keep the FastAPI event loop responsive during startup heartbeat (T-04-03-08).

## Threat Model Reconciliation

All 8 threats from PLAN.md `<threat_model>` are addressed:

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-04-03-01 (Tampering — embeddings() typo) | mitigate | DONE — `test_embed_one_returns_1024_floats` asserts on `client.embed(...)` keyword args verbatim (model, input, keep_alive='5m') |
| T-04-03-02 (DoS — oversized batch) | mitigate | DONE — `test_embed_batch_uses_settings_default` pins batch_size=settings.rag_embed_batch_size (16); test_embed_batch_chunks_by_batch_size verifies chunking actually happens |
| T-04-03-03 (Info disclosure — host in error) | accept | DONE — RagInitError detail includes "{host}:{port}"; v1 single-tenant local install, operator already knows their own config; Plan 04-05 sanitizes for HTTP responses |
| T-04-03-04 (Tampering — distance metric swap) | mitigate | DONE — `test_open_collection_happy_path` asserts the literal `{"hnsw:space": "cosine"}` metadata dict, blocking any silent legacy↔new-form rename |
| T-04-03-05 (Spoofing — malformed CHROMA_HOST) | mitigate | DONE — `test_parse_chroma_host_invalid` covers empty + "not-a-url", both raise RagInitError(chroma_unreachable) |
| T-04-03-06 (Repudiation — no fail-fast logging) | accept | NO logging calls in either wrapper (Phase 3 client.py precedent — Plan 04-05 lifespan logs RagInitError at the catch site) |
| T-04-03-07 (Elevation of Privilege — vector smuggling) | mitigate | DONE — embedder API only accepts `text: str` / `texts: Sequence[str]`; no client-supplied embeddings field anywhere in the surface |
| T-04-03-08 (DoS — blocking heartbeat) | mitigate | Documented in vector_store module docstring AND in Plan 04-05 cross-phase handoff: `asyncio.to_thread(open_collection)` at consumer site keeps the FastAPI event loop responsive during startup |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] mypy strict failed on tests/rag/test_embeddings.py — `embedder._client` typed as `ollama.AsyncClient` lacks fake-only methods**

- **Found during:** Task 2 GREEN final mypy sweep (19 errors in test_embeddings.py: `"AsyncClient" has no attribute "queue_embed_response"`, `"embed_calls"`, `"make_embed_raise"`)
- **Issue:** Tests inject a `_FakeAsyncClient` via monkeypatch and then access fake-only methods (`queue_embed_response`, `embed_calls`, `make_embed_raise`) on `embedder._client`. mypy strict types `_client` as the real `ollama.AsyncClient`, so the fake-only attributes triggered `attr-defined` errors.
- **Fix:** Added a small test helper `_fake_client(embedder: BgeM3Embedder) -> _FakeAsyncClient` that performs `assert isinstance(embedder._client, _FakeAsyncClient)` at runtime + `cast(_FakeAsyncClient, ...)` for the type checker. Rewrote each test that introspects the fake to use `client = _fake_client(embedder)` and operate on `client.queue_embed_response(...)` etc. Mypy clean afterwards (Success: no issues found in 65 source files).
- **Files modified:** `backend/tests/rag/test_embeddings.py`
- **Commit:** Folded into the GREEN commit `fb000d3`.

**2. [Rule 3 — Blocking] ruff lint cleanup: RUF012 (mutable class default), RUF100 (unused noqa), I001 (import sort), E501 (line length), SIM114 (combine if branches)**

- **Found during:** Task 1 RED initial ruff sweep + Task 2 GREEN final ruff sweep
- **Issue:** Initial test files used `last_init_kwargs: dict[str, Any] = {}` (RUF012), `# noqa: PLC0415` directives for non-enabled rules (RUF100), unsorted imports in test_vector_store.py (I001), and an inline lambda exceeded 100 columns when used inside `monkeypatch.setattr(... classmethod(lambda ...))` (E501). After the `_fake_client` refactor, an `if/elif/else` block triggered SIM114.
- **Fix:** Annotated class attributes with `ClassVar[dict[str, Any]] = {}`; removed unused `noqa: PLC0415` comments (PLC0415 is not in the project's enabled rule set); reorganized test_vector_store.py imports; extracted the verbose lambda into named helpers `_install_http_client_with_collection` + `_install_http_client_with_heartbeat_failure` (eliminates E501 + improves readability); collapsed the `if isinstance(inp, str): n=1; elif inp is None: n=1; else: ...` into a single ternary `n = 1 if isinstance(inp, str) or inp is None else len(list(inp))`.
- **Files modified:** `backend/tests/rag/test_embeddings.py`, `backend/tests/rag/test_vector_store.py`
- **Commit:** Folded into RED commit `3a3f8c9` (initial cleanup) + GREEN commit `fb000d3` (post-refactor SIM114 fix).

No architectural deviations. No authentication gates. No checkpoints.

## Self-Check: PASSED

- backend/src/receptra/rag/embeddings.py: FOUND
- backend/src/receptra/rag/vector_store.py: FOUND
- backend/tests/rag/test_embeddings.py: FOUND
- backend/tests/rag/test_vector_store.py: FOUND
- backend/tests/rag/test_embeddings_live.py: FOUND
- 3a3f8c9 (RED): FOUND in git log
- fb000d3 (GREEN): FOUND in git log
- All 16 mocked tests pass; 2 live tests self-skip; full backend suite 250 pass / 8 skip; ruff + mypy strict clean.
