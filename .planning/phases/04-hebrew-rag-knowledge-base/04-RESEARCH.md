# Phase 4: Hebrew RAG Knowledge Base — Research

**Researched:** 2026-04-26
**Domain:** Hebrew document ingestion + dense retrieval (BGE-M3 via Ollama + ChromaDB v2)
**Confidence:** HIGH for stack choices and ChromaDB / Ollama-Python APIs (Context7-verified). MEDIUM for Hebrew chunking strategy (no off-the-shelf Hebrew sentence-splitter library found in our license window — must implement). MEDIUM for recall@5 baseline (no public Hebrew-on-BGE-M3 benchmark; we set our own baseline).

> No CONTEXT.md was authored for this phase. Phase 4 inherits constraints from `CLAUDE.md` and `.planning/PROJECT.md`. The locked decisions are reproduced under **Project Constraints (from CLAUDE.md)** below.

## Summary

Phase 4 stands up the third hot-path leg next to Phase 2 (STT) and Phase 3 (LLM): a Hebrew-aware ingest → embed → store → retrieve loop, exposed under `/api/kb/*` REST endpoints, returning `ChunkRef[]` instances that Phase 3's `generate_suggestions` already consumes. The stack is fully locked by upstream phases — `chromadb/chroma:1.5.8` is already in `docker-compose.yml`, `ollama pull bge-m3` is already in `scripts/download_models.sh`, and `receptra.llm.schema.ChunkRef` is the cross-phase contract — so this phase is plumbing-and-adapter work rather than stack discovery.

The two open technical decisions that drove research were (a) **Hebrew sentence chunking** — no Apache/MIT-licensed Hebrew sentence-splitter library exists; we must implement one following the `hebrew-nlp-toolkit` SKILL.md preprocessing patterns and Hebrew punctuation rules, and (b) **eval fixture sourcing** — the obvious public Hebrew QA benchmark (Webiks-Hebrew-RAGbot KolZchut) is **CC-BY-NC-SA**, which violates v1's permissive-licensing constraint, so we must hand-craft 10 docs + 10 adversarial questions via the `hebrew-document-generator` skill.

**Primary recommendation:** Add `chromadb-client>=1.5.8` (NOT the full `chromadb` package — server runs in its own container) to backend deps; build `receptra.rag.{embeddings,chunker,vector_store,ingest,retriever,routes}` as a six-module package mirroring the layout of `receptra.stt.*` and `receptra.llm.*`; lock cosine distance with `metadata={"hnsw:space":"cosine"}` on `get_or_create_collection`; chunk at 512-token windows with 64-token overlap on Hebrew sentence boundaries (`. ! ? : \n\n` minus gershayim/geresh-flagged abbreviations); reject `.pdf` at the FastAPI route layer per Pitfall #13; gate the live recall@5 eval behind `@pytest.mark.live` (requires Ollama + Chroma) and surface results under `make eval-rag`.

## Project Constraints (from CLAUDE.md)

These are inherited directives; the planner MUST honor them in every plan emitted for this phase.

- **Hebrew-first.** Every chunker/retriever choice must work in Hebrew before any English optimization.
- **Apple Silicon M2+ floor; no CUDA.** Embedding + DB inference must run locally via Metal/MLX. Ollama on the host (per `docker-compose.yml` comment) handles BGE-M3.
- **Permissive licensing only.** Apache 2.0 / MIT / BSD or explicit free-for-commercial. **No GPL, no AGPL, no NC, no research-only deps in v1.** This blocks the obvious Webiks KolZchut Hebrew QA dataset (CC-BY-NC-SA 2.5) — see Eval Fixture Plan.
- **Zero cloud dependency.** Ingest, embedding, storage, and retrieval must work air-gapped. No HuggingFace API call at runtime; BGE-M3 is `ollama pull`-ed once.
- **Latency.** Phase 4 owns the RAG slice of the <2s budget. Per EXTERNAL-PLAN-REFERENCE.md (Phase 5 stage budget) RAG has ~1s of headroom. Single-doc retrieval should land well under 200ms TTFB.
- **One-command deploy.** `docker compose up` must keep working. ChromaDB is already in compose; nothing else gets added to compose for v1.
- **GSD workflow enforcement.** All edits go through `/gsd-execute-phase`.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RAG-01 | BGE-M3 embeddings via Ollama produce vectors for Hebrew text | §BGE-M3 Pattern; Hebrew is one of bge-m3's 100+ supported languages [CITED: ollama.com/library/bge-m3] |
| RAG-02 | ChromaDB persists embeddings to mounted volume; survives container restarts | §ChromaDB Pattern + existing `docker-compose.yml` already mounts `./data/chroma:/data` [VERIFIED: docker-compose.yml] |
| RAG-03 | KB ingest pipeline accepts `.md`/`.txt`, uses Hebrew-aware sentence chunking, embeds, stores | §Hebrew Chunking Strategy; `hebrew-nlp-toolkit` SKILL.md provides preprocessing rules (NFC, niqqud strip), implementation owned by us |
| RAG-04 | Retrieval endpoint returns top-K chunks with source metadata for Hebrew query | §REST API schema; returns `ChunkRef` objects with `source={"filename","chunk_index","char_start","char_end"}` [VERIFIED: receptra.llm.schema.ChunkRef] |
| RAG-05 | Recall@5 verified on seeded Hebrew KB with 10 adversarial questions | §Eval Fixture Plan; hand-crafted (Webiks dataset license-blocked) [VERIFIED: github.com/NNLP-IL/Webiks-Hebrew-RAGbot-KolZchut-Paragraph-Corpus license CC-BY-NC-SA 2.5] |
| RAG-06 | Ingest exposed via REST endpoint frontend can call | §REST API schema; `/api/kb/upload` (multipart) + `/api/kb/ingest-text` (JSON) |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Hebrew text preprocessing (NFC, niqqud strip) | API / Backend | — | Pure Python, runs once at ingest. Browser cannot validate file content reliably. |
| Sentence-aware chunking | API / Backend | — | Stateless transformation; same module needs to be importable from CLI eval harness. |
| Embedding generation (BGE-M3) | API / Backend (calls Ollama on host) | Ollama runtime | Ollama owns Metal acceleration; backend is the orchestrator. Same pattern as Phase 3 LLM. |
| Vector persistence + ANN search | Database / Storage (ChromaDB container) | API / Backend (HTTP client) | ChromaDB owns HNSW index; backend is a thin HTTP client per `chromadb-client` pattern. |
| File upload endpoint | API / Backend | Frontend Server (calls from browser) | FastAPI multipart route. Browser POSTs from KB-upload form (Phase 6 FE-06). |
| Citation metadata round-trip | API / Backend → LLM module | Frontend (renders chips, Phase 6) | `ChunkRef.source` dict survives the entire pipeline; Phase 3 already accepts `list[ChunkRef]` as input. |
| Recall@5 evaluation | CLI / dev-tool | — | Lives in `scripts/eval_rag.py` mirroring `scripts/eval_llm.py` (Plan 03-06); not a runtime concern. |

## Findings (per cluster)

### Cluster 1 — ChromaDB Python client

**Server:** `chromadb/chroma:1.5.8` already pinned in `docker-compose.yml` with healthcheck at `/api/v2/heartbeat`, persistence volume `./data/chroma:/data`, port 8000. Healthcheck path is the v2 path — already correct per EXTERNAL-PLAN-REFERENCE.md Pitfall 6.

**Client choice — use `chromadb-client` (thin), NOT `chromadb` (full):** [VERIFIED: pypi.org/project/chromadb-client v1.5.8, uploaded 2026-04-16]
- `chromadb-client` is a "lightweight HTTP client for the server with a minimal dependency footprint" intentionally excluding default embedding functions [CITED: docs.trychroma.com/guides/deploy/python-thin-client]. We supply our own embeddings via Ollama anyway, so the embedding-function exclusion is a feature, not a limitation.
- The full `chromadb` package pulls in `onnxruntime`, `pulsar-client`, `tokenizers`, `pypika`, etc. — irrelevant in client-server mode and a backend bloat we don't need (and onnxruntime arm64 has historical issues, see Phase 2 lifespan note).
- Both packages publish identical version `1.5.8` and provide identical `HttpClient` API.

**Connection pattern (verified against Context7 /chroma-core/chroma):**
```python
import chromadb
# Backend container -> chromadb container (compose service name)
client = chromadb.HttpClient(host="chromadb", port=8000)
# Or local dev (Chroma running on host port 8000)
client = chromadb.HttpClient(host="localhost", port=8000)
heartbeat_ns = client.heartbeat()  # raises on connection failure
```

**Async client is available** (`chromadb.AsyncHttpClient`) [CITED: docs.trychroma.com python-thin-client], BUT the underlying ChromaDB API is fast and our latency budget is ~1s — we can stay on the sync `HttpClient` and call it via `asyncio.to_thread` to keep parity with Phase 2's `transcribe_hebrew` pattern. This avoids a second async-client lifecycle in lifespan and is the safer call for v1.

**Collection management:**
```python
collection = client.get_or_create_collection(
    name="receptra_kb",
    metadata={"hnsw:space": "cosine"},  # cosine matches BGE-M3 normalization
)
```
- `get_or_create_collection` returns the existing collection without overwriting its metadata if it already exists (changed in 0.5.11) [CITED: chroma-core/chroma migration.mdx]. Safe to call at every backend startup.
- `metadata={"hnsw:space": "cosine"}` is the v0.4-compatible legacy form. The newer `configuration={"hnsw":{"space":"cosine"}}` form (Context7 §VectorIndex Configuration) is also valid. Both work on 1.5.x server. **Use legacy `metadata=` form** — it survives across all 1.x versions and has zero risk of being silently rejected if ChromaDB introduces a `configuration_json` parameter rename in a patch release.

**Add documents:**
```python
collection.add(
    ids=[chunk_id],            # we generate stable IDs (sha256(filename + offset))
    documents=[chunk_text],    # raw Hebrew text — only needed for $contains filtering
    embeddings=[vector],       # 1024-dim float list from BGE-M3
    metadatas=[{"filename": "policy.md", "chunk_index": 0, "char_start": 0, "char_end": 487}],
)
```
- Pass `embeddings` explicitly. With `chromadb-client` and no embedding-function configured, omitting this would raise.
- IDs MUST be stable across re-ingest of the same document, so users can re-upload an updated `.md` and we can `upsert` cleanly. `sha256(filename + ":" + chunk_index)[:16]` is a safe ID scheme.

**Query:**
```python
result = collection.query(
    query_embeddings=[query_vector],
    n_results=5,
    include=["documents", "metadatas", "distances"],
)
# result["distances"][0] is a list[float]; for cosine space chroma returns 1 - cos_sim,
# so similarity = 1 - distance. Filter chunks where distance > 0.65 (similarity < 0.35).
```
- The shape is `dict[str, list[list[T]]]` — outer list is per-query (we always send 1), inner list is per-result.

**Where filter** (for multi-tenant in v2; v1 single-tenant keeps it simple):
- Use `where={"filename": {"$eq": "policy.md"}}` for document-scoped queries.
- We do NOT need `where_document` ($contains) for v1 — the embedding similarity does the work.

**Version compatibility:** ChromaDB had a breaking client/server protocol change in 0.5.1 [CITED: chroma-core/chroma issue #2377]. We pin both client and server to 1.5.x, so we're safe. The thin client does NOT issue a noisy warning when the local Python `chromadb-client` minor version differs from the server within 1.x. Lock both via `pyproject.toml` and Compose; bump in lockstep.

### Cluster 2 — BGE-M3 embeddings via Ollama

**Model:** `bge-m3` from Ollama library [CITED: ollama.com/library/bge-m3]
- 568M parameters, 1.2 GB on disk, **1024-dim dense vectors**
- 8192-token context window
- Multilingual: 100+ languages including Hebrew
- License: MIT (BAAI base model) [CITED: huggingface.co/BAAI/bge-m3]
- Already integrated: `make models-bge` -> `ollama pull bge-m3` (verified in `scripts/download_models.sh`)

**Critical Hebrew note:** BGE-M3 was trained on a multilingual corpus including Hebrew. No public Recall@k benchmark on Hebrew vs Hebrew-fine-tuned alternatives (`imvladikon/sentence-transformers-alephbert`, `Webiks/Hebrew-RAGbot-KolZchut-QA-Embedder`) was found. EXTERNAL-PLAN-REFERENCE.md §Phase 4 advises: "Start with BGE-M3, swap only if Recall@5 benchmark demands." We adopt that posture. `[ASSUMED]` BGE-M3 will hit recall@5 ≥ 0.7 on our seeded fixtures. If not, the swap target is a Hebrew-tuned alternative that has a permissive license (Webiks embedder model itself is published Apache-2.0; only the *training dataset* is NC) — **note this fork is open and the swap is non-trivial** because the alternative requires running outside Ollama.

**Ollama Python `embed` API (verified Context7 /ollama/ollama-python):**
```python
from ollama import AsyncClient

client = AsyncClient(host=settings.ollama_host)

# Single text
resp = await client.embed(model="bge-m3", input="שלום עולם")
vector: list[float] = resp.embeddings[0]   # 1024 floats

# Batch (recommended for ingest)
resp = await client.embed(
    model="bge-m3",
    input=["chunk 1 text", "chunk 2 text", "chunk 3 text"],
    keep_alive="5m",          # keep BGE-M3 loaded in Ollama for 5 min after last use
)
vectors: list[list[float]] = resp.embeddings   # list of 1024-float lists
```
- `embed()` (NOT the deprecated `embeddings()`) is the current API in `ollama` 0.6.x [CITED: github.com/ollama/ollama-python README].
- Batching: Ollama processes the input list as a true batch; for ingest, send 8–32 chunks per call. Larger batches risk Ollama context-overflow errors on docs with ≥ 32 chunks all >2k tokens.
- `keep_alive` is the same lever Phase 3 uses for DictaLM (EXTERNAL-PLAN-REFERENCE.md §Phase 3). For embeddings we don't need `keep_alive=-1` (infinite) — embedding is fast and BGE-M3 only weighs 1.2 GB; "5m" amortizes calls within an ingest job and a query session without parking VRAM forever.
- **Normalization**: BGE-M3 dense embeddings are already L2-normalized per the upstream model card — no client-side `numpy.linalg.norm` needed when using cosine distance in Chroma. `[CITED: huggingface.co/BAAI/bge-m3]`

**No Hebrew preprocessing required for BGE-M3 input:** the model handles Unicode natively. NFC normalization (per `hebrew-nlp-toolkit` SKILL.md Step 3) is still good hygiene at chunk-creation time so chunks are byte-stable across re-ingest, but it's not a correctness requirement for the embedding step.

**Healthcheck:** Reuse the Phase 3 Ollama probe pattern (`receptra.llm.client.select_model` already calls `ollama list` to verify model availability). Add a parallel `verify_embedding_model()` that calls `client.show("bge-m3")` at backend lifespan startup; fail-fast with a typed `RagInitError("ollama_unreachable" | "model_missing")` if BGE-M3 is not pulled.

### Cluster 3 — Hebrew-aware chunking

**`hebrew-nlp-toolkit` skill is documentation, not a runtime package.** Reading SKILL.md confirms: it gives preprocessing recipes (NFC normalization, niqqud strip via regex `r'[֑-ׇ]'`, whitespace collapse) and a model-selection table, but no Python `import` boundary. We implement the chunker following its rules.

**Hebrew sentence-boundary rules** [CITED: en.wikipedia.org/wiki/Hebrew_punctuation, simple.wikipedia.org/wiki/Geresh_and_Gershayim, hebrewtype.com The Mysterious Gershayim]:

1. Sentence-ending punctuation in modern Hebrew is the same as English: `. ? !` followed by whitespace or end-of-string.
2. **Colon (`:`)** can end a sentence, especially in religious/biblical text. We treat it as a soft boundary (preferred to mid-clause splits, but not required).
3. **Newline boundaries:** double-newline (`\n\n`) is a paragraph boundary in Markdown — strongest split signal.
4. **Gershayim (U+05F4 ״) and geresh (U+05F3 ׳)** mark abbreviations and Hebrew numerals (e.g., `ע״מ` "by", `י״ח` "18"). Online they are usually replaced by ASCII `"` and `'`. **An abbreviation never ends a sentence** — these glyphs must NOT be treated as boundaries even when adjacent to whitespace.
5. **Period inside an abbreviation** is rare in Hebrew because gershayim replaces it [CITED: en.wikipedia.org/wiki/Gershayim]. But code-mixed Hebrew/English text can still contain `Ph.D.`-style English abbreviations — common-English-abbreviation list (`vs.`, `etc.`, `Dr.`, `Inc.`, `Mr.`, `Mrs.`, `e.g.`, `i.e.`) protects those.
6. **Hebrew has no capital letters** [VERIFIED: hebrew-nlp-toolkit SKILL.md Gotchas]. Therefore the English heuristic "next char is uppercase → real sentence end" does NOT apply. Use whitespace+printable-glyph as the next-char test instead.

**Chunking strategy (recommended):**

- **Algorithm:** sentence-boundary regex split → greedy pack into chunks until target token count → carry final K tokens as overlap.
- **Target chunk size:** ~512 tokens with 64-token overlap. BGE-M3's max context is 8192, but 512 is the canonical RAG chunk size [CITED: BAAI/bge-m3 model card; Webiks corpus paragraphs were also packed to ≤512 me5-large tokens]. 64-token overlap (≈12% of chunk) is the textbook value [CITED: pinecone.io/learn/chunking-strategies, weaviate.io/blog/chunking-strategies-for-rag].
- **Token approximation:** BGE-M3's tokenizer is XLMRoberta-based; loading it just to count tokens at ingest time would add `transformers` + `sentencepiece` to the dep tree. **Use a simple word/char heuristic** instead: 1 Hebrew token ≈ 3.0 chars (Hebrew morphology compresses prefixes), so ~1500 chars ≈ 500 tokens. Validate with a one-time spike (Wave-0 task) that the heuristic stays within ±20% of the real BGE-M3 tokenizer count on 5 sample Hebrew docs.
- **NEVER split mid-word.** Always cut on whitespace.
- **Markdown structure preservation:** detect `\n#`, `\n##`, `\n\n` as preferred boundaries before falling through to sentence-level. This addresses Pitfall #8.

**Reference algorithm (skeleton):**
```python
import re
import unicodedata

# Hebrew + ASCII sentence-end glyphs. Excludes ":" (soft boundary, used as fallback).
_SENT_END = re.compile(r"(?<=[.!?])\s+")
_PARA_END = re.compile(r"\n\s*\n")
_NIQQUD   = re.compile(r"[֑-ׇ]")
_EN_ABBR  = re.compile(r"\b(?:Dr|Mr|Mrs|Ph\.D|vs|etc|e\.g|i\.e|Inc|Ltd)\.\s*$", re.I)

def normalize_hebrew(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = _NIQQUD.sub("", text)            # strip vowel diacritics (rare; safe)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in _PARA_END.split(text) if p.strip()]

def split_sentences(paragraph: str) -> list[str]:
    # Pre-pass: protect English abbreviation periods so we don't split mid-abbrev.
    # Hebrew gershayim ״/׳ are NOT periods, so the English-only abbr list is enough.
    parts = _SENT_END.split(paragraph)
    # Re-glue accidental splits caused by trailing English abbr.
    glued: list[str] = []
    for p in parts:
        if glued and _EN_ABBR.search(glued[-1]):
            glued[-1] = glued[-1] + " " + p
        else:
            glued.append(p)
    return [s.strip() for s in glued if s.strip()]
```

**License:** Implementation is original code; depends only on `re`/`unicodedata` (Python stdlib). Zero license risk.

### Cluster 4 — REST ingest API

See **§REST API schema** below for the full endpoint matrix. Decisions:

- **Sync ingest only in v1.** Files are bounded to 1 MiB and chunked sentence-by-sentence; even a 1 MiB Hebrew doc fits in well under 200 chunks, embedded in 1–2 batches in <2s on M2. No Celery, no job queue. Defer async-ingest to v2.
- **Multipart upload OR JSON body**, both endpoints accepted. The multipart path is what FE-06 (Phase 6) calls; the JSON path is what `scripts/eval_rag.py` and CI smoke tests call.
- **Strict extension allowlist** — `.md`, `.txt` only. PDF rejected with HTTP 415 + Hebrew-localized message per Pitfall #13.
- **Size limit enforcement** — FastAPI cannot validate `UploadFile` size via Pydantic [CITED: fastapi/fastapi discussion #11750]. Use **Content-Length pre-check + chunked-read with running-total guard** [CITED: fastapi/fastapi issue #362, sqlpey.com/python/optimizing-fastapi-file-uploads]. Reject with 413 if file exceeds `RECEPTRA_KB_MAX_BYTES` (default 1_048_576).
- **Encoding:** read file as UTF-8 with `errors="strict"`. If the user uploads a CP1255 / ISO-8859-8 Hebrew file (rare but possible from old Word exports), reject with a clear 400 error. Don't auto-decode — silent encoding fallback corrupts Hebrew character mapping.

### Cluster 5 — RAG retrieval

**Flow:** Hebrew query string → `normalize_hebrew()` → `client.embed(model="bge-m3", input=query)` → `collection.query(query_embeddings=[v], n_results=5)` → filter chunks where `distance > 0.65` (cosine; ≈ similarity < 0.35 — the EXTERNAL-PLAN-REFERENCE.md threshold) → wrap into `ChunkRef(id=..., text=..., source=...)` → return.

**ChunkRef contract is already defined** in `receptra.llm.schema` (Phase 3, plan 03-02). Field shape:
```python
@dataclass(frozen=True)
class ChunkRef:
    id: str
    text: str
    source: dict[str, str] | None = None
```
Phase 4 SHALL re-export ChunkRef from `receptra.rag.types` (per the docstring in `schema.py`) so consumers can switch their import path without breaking on the eventual cycle-break refactor. v1 keeps the canonical class in `receptra.llm.schema` and the rag module exports an alias.

**Distance threshold (0.65 cosine distance ≈ 0.35 similarity):** carried over from EXTERNAL-PLAN-REFERENCE.md §Phase 4 ("BGE-M3 via Ollama: dense-only … semantic chunking per-entity for structured KBs"). The 0.35 number is a working default; **the recall@5 eval (RAG-05) is the authoritative tuning lever** — if we see good chunks being filtered out, raise the threshold (or drop the filter entirely and rely on top-K). A configurable knob `RECEPTRA_RAG_MIN_SIMILARITY` (default 0.35) ships in Settings.

**No-hit path:** if zero chunks pass the threshold, the retriever returns `[]`. Phase 3's `generate_suggestions` already short-circuits empty `list[ChunkRef]` to the canonical `"אין לי מספיק מידע"` refusal (LLM-03 lock). This is the "graceful empty KB" branch of INT-04 in Phase 5.

### Cluster 6 — Recall@5 eval

**Methodology:** classical recall@k. For each adversarial Hebrew question, manually annotate which chunk_id IS the gold answer. After ingest, run the question through the retriever; recall@5 = (# questions where gold_chunk_id ∈ top-5) / total. Aggregate over 10 questions.

**Fixture sourcing — KEY DECISION:**
- The natural choice (Webiks-Hebrew-RAGbot-KolZchut-Paragraph-Corpus + Q&A training set, NNLP-IL/MAFAT) is **CC-BY-NC-SA 2.5** [VERIFIED: github.com/NNLP-IL/Webiks-Hebrew-RAGbot-KolZchut-Paragraph-Corpus]. The NC ("NonCommercial") clause violates Receptra's permissive-only constraint. **Cannot vendor this dataset.**
- We MAY use it for an internal eval if we don't redistribute (CC-NC permits non-commercial use for evaluation), but committing it to the public OSS repo is the redistribution event that triggers the violation. Safer rule: **don't put it in the repo**.
- Alternative: **hand-craft 10 Hebrew docs covering common SMB receptionist scenarios** (hours, returns, prices, location, hold-music, callback policy, payment, holidays, complaints, address) using the `hebrew-document-generator` skill. Hand-craft 10 Hebrew adversarial questions, each pointing at a specific chunk in those docs. License: project's own Apache 2.0. Total volume ≈ 5 KB raw text — fits trivially in `fixtures/rag/`.
- The 10 questions should include Pitfall-#5 adversarial classes: questions whose answer is NOT in the KB at all (gold_chunk_id = None — recall = 1 only if retriever returns nothing above threshold), questions phrased with morphological variation from the doc text, questions with synonyms, questions that mix Hebrew + English brand name.

**Eval gating:** `@pytest.mark.live` (requires Ollama + ChromaDB up) — same pattern Phase 3 uses for `test_engine_live.py`. Off by default in `pytest`; on for `make eval-rag` and a manual GitHub Actions workflow. Recall@5 baseline gets recorded into the phase-completion summary the same way Phase 2 STT-05 records its WER baseline.

### Cluster 7 — Backend integration & lifespan

**Module layout** (mirrors `receptra.stt.*` and `receptra.llm.*`):
```
backend/src/receptra/rag/
├── __init__.py
├── chunker.py       # Hebrew normalize + sentence-aware split
├── embeddings.py    # BGE-M3 wrapper (Ollama AsyncClient)
├── vector_store.py  # ChromaDB HttpClient wrapper (singleton in app.state)
├── ingest.py        # bytes → chunks → embed → upsert flow
├── retriever.py     # query → embed → query Chroma → ChunkRef[]
├── routes.py        # FastAPI APIRouter for /api/kb/*
├── types.py         # re-export of ChunkRef
└── errors.py        # typed errors (RagInitError, IngestRejected, …)
```

**Lifespan extension:** `lifespan.py` already loads Whisper + Silero VAD. Phase 4 adds:
1. `chroma = chromadb.HttpClient(host=settings.chroma_host_only, port=settings.chroma_port)` — note: existing `settings.chroma_host` is `http://chromadb:8000` (full URL); add a derived helper to split into host+port, OR add new `chroma_port: int = 8000` and parse the existing URL.
2. `chroma.heartbeat()` — fail-fast on unreachable.
3. `collection = chroma.get_or_create_collection("receptra_kb", metadata={"hnsw:space":"cosine"})`.
4. Verify Ollama has BGE-M3: `ollama_client.show("bge-m3")` — fail-fast otherwise.
5. Stash `app.state.chroma_collection`, `app.state.embedder` for the route handlers.

**Test stubs:** `conftest.py` already monkeypatches `WhisperModel` and `load_silero_vad` to avoid loading real weights. Phase 4 adds parallel monkeypatches for `chromadb.HttpClient` and the `AsyncClient.embed` so tests run offline. Live tests (`test_*_live.py`) skip via `@pytest.mark.live` unless explicitly enabled.

## Recommended Dependencies

Verified against PyPI on 2026-04-26.

| Package | Version | Purpose | License | Verified |
|---------|---------|---------|---------|----------|
| `chromadb-client` | `>=1.5.8,<2` | Thin HTTP client for ChromaDB server | Apache 2.0 | [VERIFIED: pypi.org/project/chromadb-client v1.5.8 uploaded 2026-04-16] |
| `ollama` | (already pinned `>=0.6.1,<1`) | BGE-M3 embed API + DictaLM chat (shared) | MIT | [VERIFIED: pypi.org/project/ollama v0.6.1 (Phase 3)] |
| `python-multipart` | (already pinned `>=0.0.20`) | FastAPI multipart upload | MIT/Apache 2.0 | [VERIFIED: pyproject.toml] |

**No new dev deps required.** Existing `pytest`, `pytest-asyncio`, `httpx` cover route + retriever + chunker tests. `mypy`/`ruff` already enforce.

**Installation diff for `pyproject.toml`:**
```toml
dependencies = [
    # ... existing ...
    # Phase 4 (Hebrew RAG Knowledge Base) additions:
    "chromadb-client>=1.5.8,<2",
]
```

**Version verification commands** (planner re-run before locking):
```bash
curl -s https://pypi.org/pypi/chromadb-client/json | python3 -c "import sys,json;print(json.load(sys.stdin)['info']['version'])"
# expected: 1.5.8
```

## REST API schema

All routes mounted under `/api/kb` via `APIRouter`. Pydantic v2 request/response models live alongside the existing `receptra.llm.schema` style (frozen, extra="forbid").

| Method | Path | Body | Response | Purpose |
|--------|------|------|----------|---------|
| `POST` | `/api/kb/upload` | `multipart/form-data` (`file: UploadFile`) | `IngestResult` | Upload `.md`/`.txt` from frontend (FE-06). |
| `POST` | `/api/kb/ingest-text` | `IngestTextRequest` (JSON) | `IngestResult` | Programmatic ingest from CLI / tests. |
| `GET` | `/api/kb/documents` | — | `list[KbDocument]` | List ingested docs (filename + chunk_count + ingested_at). |
| `DELETE` | `/api/kb/documents/{filename}` | — | `{"deleted": int}` | Remove all chunks with `metadatas.filename == filename`. |
| `POST` | `/api/kb/query` | `KbQueryRequest` (JSON: `query`, `top_k=5`) | `list[ChunkRef]` (as JSON dicts) | Retrieval endpoint (RAG-04). |
| `GET` | `/api/kb/health` | — | `{"chroma":"ok","ollama":"ok","collection_count":N}` | Per-subsystem readiness for FE + Phase 5. |

**Schemas:**
```python
class IngestTextRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    filename: str = Field(..., min_length=1, max_length=255)
    content: str  = Field(..., max_length=1_048_576)  # 1 MiB

class IngestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    filename: str
    chunks_added: int
    chunks_replaced: int       # if filename existed before, count of overwritten chunks
    bytes_ingested: int

class KbDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    filename: str
    chunk_count: int
    ingested_at_iso: str       # ISO-8601 from chunk metadata

class KbQueryRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    query: str = Field(..., min_length=1, max_length=2_000)
    top_k:  int = Field(default=5, ge=1, le=20)
```

**Error responses (typed envelope mirroring `LlmErrorEvent`):**
```python
class KbErrorResponse(BaseModel):
    code: Literal["unsupported_extension","file_too_large","encoding_error",
                  "ollama_unreachable","chroma_unreachable","empty_after_chunking"]
    detail: str
```
HTTP status mapping:
- `unsupported_extension` → 415, `file_too_large` → 413, `encoding_error` → 400
- `ollama_unreachable` / `chroma_unreachable` → 503
- `empty_after_chunking` → 422

## Hebrew Chunking Strategy

**Pipeline (per file, in order):**

1. **Decode** UTF-8 strict; reject on `UnicodeDecodeError`.
2. **Normalize** via `normalize_hebrew()` — NFC + niqqud strip + whitespace collapse. Per `hebrew-nlp-toolkit` SKILL.md Step 3.
3. **Split into paragraphs** on `\n\n+`.
4. **For each paragraph, split into sentences** using the regex pipeline above. Re-glue any split that ended in a known English abbreviation. Hebrew gershayim/geresh do NOT appear in our split regex — they cannot trigger a false-positive sentence boundary.
5. **Greedy pack sentences into chunks** until cumulative `len(chunk)` exceeds `target_chars` (default 1500 ≈ 500 BGE-M3 tokens). Emit chunk; carry the trailing `overlap_chars` (default 200 ≈ 65 tokens) into the start of the next chunk.
6. **Emit chunk metadata** per chunk: `filename`, `chunk_index`, `char_start`, `char_end`, `ingested_at_iso`, `sha256_doc` (for the whole-doc hash, useful for delete-by-doc-version).
7. **Stable chunk_id**: `f"{doc_sha256[:8]}:{chunk_index}"` — stable across re-ingest of same file content; changes when content changes (so re-ingest replaces cleanly).

**Edge-case handling:**

- **Single-line file with no sentences** (e.g., a 4 KB chunk of legal Hebrew with no `.`/`?`/`!`) — fall through to char-level greedy split at whitespace boundaries.
- **Empty file** — return `IngestResult(chunks_added=0, ...)` rather than raising.
- **Code block in Markdown** — preserve as a single chunk if it fits; do NOT sentence-split inside ` ``` ` fences (a regex pre-pass replaces fenced blocks with placeholders, restored after sentence split).
- **Mixed Hebrew/English line** — no special handling. BGE-M3 handles code-mix.

**What we explicitly do NOT do (defer to v2):**
- Morphological-aware chunking (would need Dicta morph analyzer — Apache 2.0 but heavy dep).
- Semantic chunking (LLM-based) — too slow for a "drop a file, see chunks" UX.
- Recursive chunking with multiple granularities — single granularity until eval shows recall problems.

## BGE-M3 Pattern

```python
# receptra/rag/embeddings.py
from __future__ import annotations
from collections.abc import Sequence
from ollama import AsyncClient
from receptra.config import settings
from receptra.rag.errors import RagInitError

class BgeM3Embedder:
    """BGE-M3 embedder via Ollama. 1024-dim cosine-normalized vectors."""

    DIM = 1024
    MODEL = "bge-m3"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    @classmethod
    async def create_and_verify(cls) -> "BgeM3Embedder":
        client = AsyncClient(host=settings.ollama_host)
        try:
            await client.show(cls.MODEL)   # raises if model not pulled
        except Exception as e:
            raise RagInitError(
                code="model_missing",
                detail=f"Ollama model '{cls.MODEL}' not available. Run: make models-bge",
            ) from e
        return cls(client)

    async def embed_one(self, text: str) -> list[float]:
        resp = await self._client.embed(
            model=self.MODEL, input=text, keep_alive="5m",
        )
        return list(resp.embeddings[0])

    async def embed_batch(self, texts: Sequence[str], batch_size: int = 16) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = list(texts[i : i + batch_size])
            resp = await self._client.embed(
                model=self.MODEL, input=batch, keep_alive="5m",
            )
            out.extend(list(v) for v in resp.embeddings)
        return out
```

**Why batch_size=16 (not 32):** Ollama's batch path holds the full batch in process memory before returning. With 16 chunks × 1500 chars ≈ 24 KB of input plus the 1024-float-per-chunk output, stays comfortably under any per-request limit. Larger batches risk timeouts on large docs. Adjust via env var if Wave-0 spike shows we can push higher.

## ChromaDB Pattern

```python
# receptra/rag/vector_store.py
from __future__ import annotations
import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from receptra.config import settings
from receptra.rag.errors import RagInitError

COLLECTION_NAME = "receptra_kb"

def parse_chroma_host(host_url: str) -> tuple[str, int]:
    """Split 'http://chromadb:8000' into ('chromadb', 8000)."""
    from urllib.parse import urlparse
    parsed = urlparse(host_url)
    if not parsed.hostname:
        raise RagInitError(code="chroma_unreachable",
                           detail=f"Invalid CHROMA_HOST: {host_url!r}")
    return parsed.hostname, parsed.port or 8000

def open_collection() -> Collection:
    host, port = parse_chroma_host(settings.chroma_host)
    try:
        client = chromadb.HttpClient(host=host, port=port)
        client.heartbeat()  # raises on unreachable
    except Exception as e:
        raise RagInitError(
            code="chroma_unreachable",
            detail=f"ChromaDB not reachable at {host}:{port}: {e}",
        ) from e
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
```

**Persistence verification:** Chroma container mounts `./data/chroma:/data` (verified in `docker-compose.yml`). On restart, `get_or_create_collection` returns the existing collection with all chunks intact. RAG-02 verification step: ingest 1 doc → `docker compose restart chromadb` → query returns same chunks.

**Identity invariants for tests:**
- `client.heartbeat()` returns nanosecond `int` — non-zero on success.
- `collection.count()` is the public API for the chunk count (tests assert on it post-ingest).

## Eval Fixture Plan

**RAG-05 deliverables, all hand-crafted in this repo (Apache 2.0 only):**

1. **`fixtures/rag/seed_kb/`** — 10 hand-crafted Hebrew Markdown documents, ~500–1000 chars each. Topics: (1) שעות פתיחה, (2) מדיניות החזרות, (3) מחירון בסיסי, (4) כתובת + הוראות הגעה, (5) מדיניות תור המתנה / שיחה חוזרת, (6) אמצעי תשלום, (7) חגים ומועדים מיוחדים, (8) טיפול בתלונות, (9) פרטי קשר, (10) מדיניות פרטיות.
2. **`fixtures/rag/eval_questions.jsonl`** — 10 entries:
   ```jsonl
   {"question": "מה שעות הפתיחה ביום שישי?", "gold_filename": "01_hours.md", "gold_chunk_match": "שישי"}
   ...
   {"question": "האם אתם פתוחים בשבת?", "gold_filename": null, "gold_chunk_match": null}
   ```
   `gold_chunk_match` is a substring the gold chunk is required to contain (more robust than `gold_chunk_id` which depends on chunker output). `null` answers measure refusal correctness.
3. **`scripts/eval_rag.py`** — CLI mirroring `scripts/eval_llm.py` (Plan 03-06). Args: `--seed-only` (re-ingest fixtures), `--query-only` (run questions against existing collection), `--full` (ingest + query). Emits JSON: `{"recall_at_5": 0.7, "details": [...]}`.
4. **`tests/rag/test_recall_live.py`** — `@pytest.mark.live`; runs `eval_rag.py --full` and asserts `recall_at_5 >= 0.6` (initial baseline; bump after first measurement).
5. **`make eval-rag`** — convenience target.

**Generation hint:** the `hebrew-document-generator` skill provides Hebrew document templates with proper RTL/typography. We're outputting `.md` plain text (no PDF), so we just borrow the topic/phrasing patterns, not the docx/PDF generators.

**Why not Webiks dataset:** CC-BY-NC-SA license violates v1's permissive-only constraint. Bundling it in the public OSS repo would make Receptra non-redistributable for commercial users — a constraint violation that propagates through every downstream consumer. We can mention the dataset in `docs/rag.md` as an "external benchmark you may run yourself" with a one-line wget instruction, but the file does NOT enter `fixtures/`.

## Open Decisions

1. **Token-count heuristic vs real BGE-M3 tokenizer.**
   - What we know: `transformers + sentencepiece` would give exact counts but adds ~80 MB to the backend image and arm64 wheel pain.
   - What's unclear: how much recall@5 degrades when our 1500-char ≈ 500-token heuristic mis-estimates by 20% on docs with heavy English code-mix.
   - Recommendation: **ship with char-heuristic; add a Wave-0 spike** that measures real-tokenizer counts on 5 sample Hebrew docs and adjusts `target_chars` if heuristic deviation exceeds 20%.

2. **Cosine similarity threshold (0.35).**
   - Default carried from EXTERNAL-PLAN-REFERENCE.md but never tuned for Hebrew.
   - Recommendation: **make it a Settings knob** (`RECEPTRA_RAG_MIN_SIMILARITY=0.35`) and let RAG-05 eval surface the right value. May converge on 0.25–0.45.

3. **Async vs sync ChromaDB client.**
   - `chromadb.AsyncHttpClient` exists but adds an extra lifecycle to manage.
   - Recommendation: **sync client + `asyncio.to_thread`** in routes. Same pattern as `transcribe_hebrew`. Re-evaluate only if profiling shows the sync calls block the FastAPI event loop (unlikely for v1 traffic).

4. **Multi-collection vs single-collection (multi-doc-set support).**
   - v1 single-tenant ⇒ one collection (`receptra_kb`) with `metadatas.filename` for filtering.
   - v2 deferred: per-business collections. v1 metadata schema must keep `filename` and a forward-looking `tenant_id` field nullable so v2 swap is non-breaking.
   - Recommendation: include `tenant_id: str | None = None` in metadata from day one; lock it `None` for v1.

5. **DictaLM-3.0 has its own bilingual embedder (`dicta-il/neodictabert-bilingual-embed`, 400M).**
   - Listed in `hebrew-nlp-toolkit` SKILL.md Step 1.
   - Not on Ollama. Would require a separate Python serving path.
   - Recommendation: **defer.** Keep BGE-M3 v1; revisit if recall@5 falls below 0.6 on the eval set.

## Common Pitfalls

### Pitfall 1: Mid-sentence chunking breaks Hebrew retrieval (Receptra Pitfall #8)
**What goes wrong:** A character-count chunker splits "אנחנו פתוחים מ-9:00 עד 18:00" into "...מ-9" + ":00 עד 18:00". Embedding loses the operating-hours signal entirely.
**Why it happens:** Naive `chunk = text[i:i+1500]` ignores word/sentence boundaries.
**How to avoid:** Sentence-aware split (above). Always cut on whitespace minimum; on punctuation preferred.
**Warning signs:** Recall@5 < 0.5 on a question whose answer text is verbatim in the KB.

### Pitfall 2: Treating gershayim as sentence-end punctuation
**What goes wrong:** "ע״מ 30 לחודש." gets split into "ע" + "מ 30 לחודש." because the gershayim ASCII-equivalent `"` looks like an end-quote, OR the period after the abbreviation is not a real sentence end and shouldn't trigger a split if "ע״מ" is part of a longer clause.
**Why it happens:** English-trained sentence splitters (NLTK punkt without Hebrew model) misclassify gershayim/geresh.
**How to avoid:** Our split regex uses `[.!?]` only — does NOT include `"` or `'` or U+05F3 / U+05F4.
**Warning signs:** Splitter emits 1-character chunks; chunks start mid-word with a stray Hebrew letter.

### Pitfall 3: PDF flakiness (Receptra Pitfall #13)
**What goes wrong:** User uploads a PDF; pypdf extracts gibberish on Hebrew embedded fonts, OR returns empty string on scanned PDFs.
**How to avoid:** **Reject `.pdf` at the route layer with HTTP 415 + Hebrew error message** in v1. Document scope as ".md and .txt only."
**Warning signs:** Phase 4 was only meant to land RAG; if a "PDF support" task creeps in, push back.

### Pitfall 4: Container hostname vs localhost
**What goes wrong:** `chromadb.HttpClient(host="localhost", port=8000)` from inside the backend container fails — `localhost` resolves to the backend container itself, not the chromadb service.
**How to avoid:** Use compose service name (`chromadb`). Already correct in `docker-compose.yml` (RECEPTRA_CHROMA_HOST=http://chromadb:8000); the parser must split URL → host+port. Tests outside Docker use `localhost`.
**Warning signs:** `ConnectionRefusedError` immediately on lifespan startup inside compose; works fine on bare-metal dev.

### Pitfall 5: Lockstep version drift between client and server
**What goes wrong:** Bump `chromadb-client` to 1.6.x; forget to bump `chromadb/chroma` Compose tag; protocol mismatch.
**How to avoid:** **Pin both** in the same commit. Add a CI check that greps the Compose image tag major+minor against `pyproject.toml`'s `chromadb-client` version range.
**Warning signs:** Heartbeat works but `add()` returns 422.

### Pitfall 6: Embedding dimension drift on model swap
**What goes wrong:** Future swap from BGE-M3 (1024-dim) to `imvladikon/sentence-transformers-alephbert` (768-dim). New chunks added; existing collection has 1024-dim vectors; query crashes.
**How to avoid:** Encode embedding model name in the collection name (`receptra_kb_bge_m3`) OR fail-fast on model change by checking `collection.metadata["embedding_model"]` at startup.
**Warning signs:** Mysterious "dimension mismatch" errors from Chroma weeks after a model swap.

### Pitfall 7: User uploads CP1255 / ISO-8859-8 Hebrew file
**What goes wrong:** Old MS-Word-exported `.txt` files use Windows-1255 (Hebrew). Strict UTF-8 decode fails; chunker sees moji-bake.
**How to avoid:** Reject with explicit 400 + "save as UTF-8 and re-upload" message. **Do not auto-detect encoding** — silent fallback is worse than rejection because Hebrew PII gets re-encoded incorrectly into the audit log.
**Warning signs:** Chunks contain `???` or sequences of unexpected Latin letters.

### Pitfall 8: Re-ingest doubles chunk count
**What goes wrong:** User re-uploads the same `policy.md` after editing. Old chunks remain; new chunks added. Retrieval returns mix of stale + fresh.
**How to avoid:** `ingest()` must DELETE existing chunks `where filename == new_filename` before adding new chunks. Track `chunks_replaced` in the response.
**Warning signs:** `collection.count()` grows on every re-upload; old answers leak into queries.

## Code Examples

### Ingest one document end-to-end
```python
# receptra/rag/ingest.py
import hashlib
from datetime import UTC, datetime
from receptra.rag.chunker import chunk_hebrew
from receptra.rag.embeddings import BgeM3Embedder
from receptra.rag.errors import IngestRejected

ALLOWED_EXTS = {".md", ".txt"}
MAX_BYTES = 1_048_576

async def ingest_document(
    *, filename: str, content: bytes,
    embedder: BgeM3Embedder, collection,
) -> IngestResult:
    if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTS):
        raise IngestRejected(code="unsupported_extension",
                             detail=f"Only {sorted(ALLOWED_EXTS)} accepted in v1")
    if len(content) > MAX_BYTES:
        raise IngestRejected(code="file_too_large",
                             detail=f"{len(content)} > {MAX_BYTES}")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise IngestRejected(code="encoding_error",
                             detail="File must be UTF-8") from e

    doc_sha = hashlib.sha256(content).hexdigest()
    chunks = chunk_hebrew(text)
    if not chunks:
        raise IngestRejected(code="empty_after_chunking",
                             detail="No content after normalization")

    # Replace any prior version of this filename
    existing = collection.get(where={"filename": filename})
    chunks_replaced = len(existing["ids"])
    if chunks_replaced:
        collection.delete(ids=existing["ids"])

    embeddings = await embedder.embed_batch([c.text for c in chunks])
    ingested_at = datetime.now(UTC).isoformat()
    collection.add(
        ids=[f"{doc_sha[:8]}:{c.chunk_index}" for c in chunks],
        documents=[c.text for c in chunks],
        embeddings=embeddings,
        metadatas=[{
            "filename": filename,
            "chunk_index": c.chunk_index,
            "char_start": c.char_start,
            "char_end":   c.char_end,
            "doc_sha":    doc_sha,
            "ingested_at_iso": ingested_at,
            "tenant_id": None,   # v2 forward-compat
        } for c in chunks],
    )
    return IngestResult(filename=filename, chunks_added=len(chunks),
                        chunks_replaced=chunks_replaced,
                        bytes_ingested=len(content))
```

### Retrieve top-K
```python
# receptra/rag/retriever.py
from receptra.llm.schema import ChunkRef
from receptra.rag.embeddings import BgeM3Embedder

async def retrieve(
    *, query: str, top_k: int,
    embedder: BgeM3Embedder, collection,
    min_similarity: float = 0.35,
) -> list[ChunkRef]:
    qvec = await embedder.embed_one(query)
    res = collection.query(
        query_embeddings=[qvec], n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    out: list[ChunkRef] = []
    for cid, doc, meta, dist in zip(
        res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0],
        strict=True,
    ):
        similarity = 1.0 - float(dist)   # cosine distance -> similarity
        if similarity < min_similarity:
            continue
        out.append(ChunkRef(
            id=cid, text=doc,
            source={
                "filename": meta["filename"],
                "chunk_index": str(meta["chunk_index"]),
                "char_start": str(meta["char_start"]),
                "char_end":   str(meta["char_end"]),
                "similarity": f"{similarity:.3f}",
            },
        ))
    return out
```

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (auto mode) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` (already configured) |
| Quick run command | `cd backend && uv run pytest tests/rag -x -q` |
| Full suite command | `cd backend && uv run pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RAG-01 | BGE-M3 returns 1024-dim vector for Hebrew text | unit (mocked Ollama) + live | `uv run pytest tests/rag/test_embeddings.py -x` | ❌ Wave 0 |
| RAG-01 | (live) `embed("שלום")` returns 1024 floats | live | `uv run pytest -m live tests/rag/test_embeddings_live.py -x` | ❌ Wave 0 |
| RAG-02 | Chunks survive `docker compose restart chromadb` | integration | `bash scripts/test_persistence.sh` (Wave-0) OR manual | ❌ Wave 0 |
| RAG-02 | `get_or_create_collection` returns existing on second call | unit (mocked Chroma) | `uv run pytest tests/rag/test_vector_store.py::test_idempotent_open -x` | ❌ Wave 0 |
| RAG-03 | `.pdf` rejected with 415 | unit (TestClient) | `uv run pytest tests/rag/test_routes.py::test_rejects_pdf -x` | ❌ Wave 0 |
| RAG-03 | Hebrew chunker splits on sentence boundaries, never mid-word | unit | `uv run pytest tests/rag/test_chunker.py -x` | ❌ Wave 0 |
| RAG-03 | Chunker handles gershayim without false split | unit | `uv run pytest tests/rag/test_chunker.py::test_gershayim_not_boundary -x` | ❌ Wave 0 |
| RAG-04 | `/api/kb/query` returns `ChunkRef[]` shape with source metadata | unit (mocked) | `uv run pytest tests/rag/test_routes.py::test_query_returns_chunkrefs -x` | ❌ Wave 0 |
| RAG-04 | Schema serialization matches `receptra.llm.schema.ChunkRef` | unit | `uv run pytest tests/rag/test_types.py -x` | ❌ Wave 0 |
| RAG-05 | recall@5 ≥ 0.6 on 10 adversarial Hebrew questions | live | `uv run pytest -m live tests/rag/test_recall_live.py -x` | ❌ Wave 0 |
| RAG-06 | `/api/kb/upload` accepts multipart and persists | integration | `uv run pytest tests/rag/test_routes.py::test_upload_persists -x` | ❌ Wave 0 |
| Chaos | Chroma unreachable → 503 from `/api/kb/query` | unit (mocked failure) | `uv run pytest tests/rag/test_chaos.py -x` | ❌ Wave 0 |
| Regression | All Phase 2/3 tests still pass | full suite | `uv run pytest -x` | ✅ |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/rag -x -q` (offline only — no `-m live`)
- **Per wave merge:** `uv run pytest -x` (full backend suite, still offline)
- **Phase gate:** `uv run pytest -x` GREEN + `make eval-rag` reports recall@5 ≥ 0.6 baseline + manual `docker compose restart chromadb` persistence check.

### Wave 0 Gaps

- [ ] `backend/tests/rag/__init__.py` — empty marker
- [ ] `backend/tests/rag/conftest.py` — fixtures: `fake_collection`, `fake_embedder` mocks
- [ ] `backend/tests/rag/test_chunker.py` — pure-Python unit tests (no services)
- [ ] `backend/tests/rag/test_embeddings.py` — mocked Ollama AsyncClient
- [ ] `backend/tests/rag/test_vector_store.py` — mocked `chromadb.HttpClient`
- [ ] `backend/tests/rag/test_routes.py` — TestClient against `/api/kb/*`
- [ ] `backend/tests/rag/test_chaos.py` — error-path coverage
- [ ] `backend/tests/rag/test_types.py` — ChunkRef cross-module identity
- [ ] `backend/tests/rag/test_embeddings_live.py` — `@pytest.mark.live`
- [ ] `backend/tests/rag/test_recall_live.py` — `@pytest.mark.live`
- [ ] `fixtures/rag/seed_kb/01_hours.md` … `10_privacy.md` — 10 hand-crafted Hebrew docs
- [ ] `fixtures/rag/eval_questions.jsonl` — 10 adversarial Q + gold mapping
- [ ] `scripts/eval_rag.py` — CLI harness mirroring `scripts/eval_llm.py`
- [ ] `Makefile`: add `eval-rag` target
- [ ] `pyproject.toml`: add `chromadb-client>=1.5.8,<2`
- [ ] `pyproject.toml` `pytest.ini_options`: add `live` marker if not already present (Phase 3 may have added it; check `markers = [...]`)
- [ ] `docs/rag.md` — parallel to `docs/llm.md` and `docs/stt.md`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | v1 single-tenant local install; no auth |
| V3 Session Management | no | local-only; no sessions |
| V4 Access Control | partial | `tenant_id` field reserved but unused in v1 |
| V5 Input Validation | yes | Pydantic v2 `frozen=True, extra="forbid"` schemas; size limits; extension allowlist |
| V6 Cryptography | yes (passive) | sha256 for chunk_id only — never auth |
| V12 File Handling | yes | extension allowlist, size cap, UTF-8 strict decode, no path-traversal (filename stored as opaque metadata, not a filesystem path) |
| V13 API Security | yes | route-level error envelopes; typed `KbErrorResponse` |

### Known Threat Patterns for Hebrew RAG

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via filename (`../../etc/passwd`) | Tampering | Filename stored as metadata only — never used as filesystem path. ChromaDB stores it as a string; we never `open(filename)`. |
| Oversized upload DoS (RAM exhaustion) | DoS | Content-Length pre-check + chunked-read with running total → 413. |
| Encoding-mismatch corruption | Tampering | Strict UTF-8 decode; reject on `UnicodeDecodeError`. |
| Hebrew transcript leak via audit log | Information Disclosure | Same `RECEPTRA_*_LOG_TEXT_REDACTION_DISABLED=false` default as Phase 2/3. KB content is PII; redact by default. |
| Embedding-model tampering (user-supplied vector) | Tampering | `embeddings` field on `/api/kb/*` is server-computed only; never accepted from client. |
| Prompt injection via doc content reaching LLM | Tampering | Phase 3 already wraps `ChunkRef.text` inside `[CONTEXT]...[/CONTEXT]` and the system prompt mandates "use only context, refuse if insufficient." Phase 4 inherits that boundary; do NOT add a path that bypasses it. |
| Stale-content leak after delete | Information Disclosure | DELETE endpoint must remove ALL chunks for a filename (loop over `where`-filtered ids). Verify with a unit test that `collection.count()` decrements correctly. |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Engine | `docker compose up` | ✓ | 29.1.3 | — |
| `uv` (Python package manager) | backend dev | ✓ | 0.11.7 | pip + venv |
| Python (host) | backend dev | ✓ | 3.14.2 host; `>=3.12` required by `pyproject.toml` (uv selects appropriate venv) | — |
| Ollama (host) | BGE-M3 embed; DictaLM (Phase 3) | ✗ on agent PATH (likely installed for user — agent sandbox can't see it) | unknown | none — REQUIRED |
| `bge-m3` model in Ollama | RAG-01 | ✗ (Ollama not invokable from agent shell) | unknown | `make models-bge` (already in Makefile) |
| `chromadb/chroma:1.5.8` Docker image | RAG-02 | ✓ (pinned in compose) | 1.5.8 | — |
| `chromadb-client` PyPI | backend HTTP client | ✓ available on PyPI | 1.5.8 (2026-04-16) | — |

**Missing dependencies with no fallback:**
- Ollama on the developer machine — required for BGE-M3 + DictaLM. Already documented in `docker-compose.yml` and `.env.example`. Phase 4 inherits this requirement; no new install step beyond the Phase 1 `make setup`.
- `bge-m3` model pulled — `make models-bge` already exists. The phase plans must include a verification step (`ollama show bge-m3`) before declaring Wave 0 done on the user's machine.

**Missing dependencies with fallback:**
- None. There is no fallback embedder for v1 (DictaLM bilingual embed is deferred per Open Decision 5).

## Sources

### Primary (HIGH confidence)
- Context7 `/chroma-core/chroma` — HttpClient, get_or_create_collection, metadata filtering, HNSW configuration, thin-client docs (multiple snippets fetched 2026-04-26)
- Context7 `/ollama/ollama-python` — embed API, batch input, AsyncClient, options
- `pypi.org/project/chromadb-client` — version 1.5.8 verified 2026-04-26, upload time 2026-04-16
- `pypi.org/project/ollama` — version 0.6.1 verified
- `docs.trychroma.com/guides/deploy/python-thin-client` — thin-client limits and embedding-function caveat
- `ollama.com/library/bge-m3` — model card, dimensions, supported languages
- `huggingface.co/BAAI/bge-m3` — multilingual coverage, normalization, license
- `github.com/NNLP-IL/Webiks-Hebrew-RAGbot-KolZchut-Paragraph-Corpus` — license verification (CC-BY-NC-SA 2.5)
- `en.wikipedia.org/wiki/Gershayim` + `en.wikipedia.org/wiki/Hebrew_punctuation` — Hebrew sentence-boundary rules
- Local files: `docker-compose.yml`, `backend/pyproject.toml`, `backend/src/receptra/config.py`, `backend/src/receptra/llm/schema.py`, `scripts/download_models.sh`, `Makefile`, `~/.claude/skills/hebrew-nlp-toolkit/SKILL.md`, `~/.claude/skills/hebrew-document-generator/SKILL.md`
- Cross-phase: `.planning/research/EXTERNAL-PLAN-REFERENCE.md`, `.planning/research/PITFALLS.md`, `.planning/research/STACK.md`

### Secondary (MEDIUM confidence)
- `pinecone.io/learn/chunking-strategies` — 512-token / 12% overlap rule of thumb (cross-verified by `weaviate.io/blog/chunking-strategies-for-rag`)
- `fastapi/fastapi` discussions #11750, #8167, #362 — UploadFile size-validation patterns
- `cookbook.chromadb.dev/core/clients/` — client-mode guidance

### Tertiary (LOW confidence)
- `[ASSUMED]` — BGE-M3 will hit recall@5 ≥ 0.6 on hand-crafted Hebrew SMB-receptionist fixtures. Tagged for confirmation by RAG-05 measurement.
- `[ASSUMED]` — 1500-char chunks ≈ 500 BGE-M3 tokens within ±20%. Wave-0 spike confirms.
- `[ASSUMED]` — `keep_alive="5m"` for BGE-M3 is appropriate (vs `-1`). Pattern parallel to Phase 3 LLM but unverified for embeddings specifically.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | BGE-M3 hits recall@5 ≥ 0.6 on hand-crafted Hebrew fixtures | §Eval Fixture Plan | Phase exit gate slips; need to swap embedder (Webiks/AlephBERT path) — non-trivial |
| A2 | 1500 chars ≈ 500 BGE-M3 tokens within ±20% | §Hebrew Chunking Strategy | Chunks oversize → context overflow OR undersize → recall drop |
| A3 | `keep_alive="5m"` is the right embed cache window | §BGE-M3 Pattern | VRAM pressure if too long; cold-start tax if too short |
| A4 | Sync `HttpClient` + `asyncio.to_thread` is fast enough | §Findings Cluster 1 + §Open Decisions | Latency over budget; switch to `AsyncHttpClient` |
| A5 | English abbreviation list (`Dr/Mr/etc.`) is sufficient for the chunker | §Cluster 3 | False sentence splits inside English-mixed Hebrew docs |
| A6 | `RECEPTRA_RAG_MIN_SIMILARITY=0.35` default is sane for Hebrew BGE-M3 | §Cluster 5 + §Open Decisions | Either too many no-hit responses (threshold too high) or noisy retrieval (too low) |

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every dep verified against PyPI on 2026-04-26 + Context7 docs
- Architecture: HIGH — module layout mirrors existing Phase 2/3 patterns; cross-phase contracts already locked (`ChunkRef`)
- Pitfalls: MEDIUM-HIGH — Hebrew-specific gotchas drawn from Wikipedia/SKILL.md + Receptra PITFALLS.md; chunker correctness depends on Wave-0 chunker tests
- Eval methodology: MEDIUM — recall@5 is well-defined but the baseline number is unknown until first measurement

**Research date:** 2026-04-26
**Valid until:** 2026-05-26 (30 days — stack is stable; ChromaDB and Ollama-Python both released within 6 months and unlikely to break)
