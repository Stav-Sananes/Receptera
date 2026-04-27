---
title: "Receptra RAG — Hebrew Knowledge Base"
phase: 04-hebrew-rag-knowledge-base
status: live
---

# Receptra RAG — Hebrew Knowledge Base

Phase 4 delivers a local, zero-cloud-dependency Retrieval-Augmented Generation (RAG)
pipeline for Hebrew business documents. It slots between the STT transcription
(Phase 2) and the LLM suggestion engine (Phase 3), providing grounded context
so DictaLM does not hallucinate KB answers.

## Overview

The RAG subsystem ingests `.md` and `.txt` knowledge-base documents, embeds
them with BGE-M3 (1024-dim, multilingual), stores them in ChromaDB, and at
query time retrieves the top-K most relevant chunks to pass as context to
`generate_suggestions`.

**Latency budget:** the RAG query path (`embed_one` + ChromaDB HNSW scan)
targets ≤ 500 ms on Apple Silicon M2 with a local BGE-M3 model loaded in Ollama.
This leaves ~1.5 s of the 2 s end-to-end target for STT + LLM TTFT combined.

**Key design choices (locked by Plan 04-RESEARCH.md):**

- BGE-M3 via Ollama — `ollama pull bge-m3`; Metal-accelerated on Apple Silicon.
- ChromaDB HttpClient with cosine distance (`hnsw:space: cosine`); L2-normalized
  BGE-M3 vectors map directly to `1 - cos_sim`.
- All sync ChromaDB calls wrapped in `asyncio.to_thread` (D-03 lock).
- Delete-before-add on re-ingest (Pitfall #8 mitigation).
- Single-tenant v1; `tenant_id: None` stored in every chunk metadata for v2 forward
  compatibility.

## Wire Contract

Six HTTP endpoints under `/api/kb`:

| Method | Path | Request body | Response |
|--------|------|-------------|----------|
| POST | `/api/kb/upload` | multipart `file` | `IngestResult` |
| POST | `/api/kb/ingest-text` | `IngestTextRequest` JSON | `IngestResult` |
| GET | `/api/kb/documents` | — | `list[KbDocument]` |
| DELETE | `/api/kb/documents/{filename}` | — | `{"deleted": int}` |
| POST | `/api/kb/query` | `KbQueryRequest` JSON | `list[ChunkRef-dict]` |
| GET | `/api/kb/health` | — | `{"chroma": str, "ollama": str, "collection_count": int}` |

**HTTP status mapping:**

| Error code | HTTP status | Trigger |
|-----------|------------|---------|
| `unsupported_extension` | 415 | Filename extension not in `{".md", ".txt"}` |
| `file_too_large` | 413 | Body > 1 MiB (1,048,576 bytes) |
| `encoding_error` | 400 | File content fails strict UTF-8 decode |
| `empty_after_chunking` | 422 | All text is whitespace — zero chunks produced |
| `ollama_unreachable` | 503 | `httpx.HTTPError` from Ollama embedding calls |
| `chroma_unreachable` | 503 | Any exception from ChromaDB operations |

Note: `model_missing` (bge-m3 not pulled) collapses to `ollama_unreachable`
on the wire for simplicity.

**ChunkRef dict shape** (each item in `/api/kb/query` response):

```json
{
  "id": "a1b2c3d4:0",
  "text": "המדיניות שלנו מאפשרת החזרה תוך 14 יום.",
  "source": {
    "filename": "02_returns.md",
    "chunk_index": "0",
    "char_start": "0",
    "char_end": "42",
    "similarity": "0.872"
  }
}
```

## Schema

All Pydantic v2 models in `receptra.rag.schema`; `frozen=True, extra="forbid"`.

```python
class IngestTextRequest(BaseModel):
    filename: str          # 1–255 chars; extension validated in ingest_document
    content: str           # 0–1,048,576 chars (Pydantic cap; size enforced in bytes too)

class IngestResult(BaseModel):
    filename: str
    chunks_added: int      # chunks stored this call
    chunks_replaced: int   # chunks deleted (prior version of same filename)
    bytes_ingested: int    # raw byte count of the content

class KbDocument(BaseModel):
    filename: str
    chunk_count: int       # aggregated from chunk metadata
    ingested_at_iso: str   # last-seen ingested_at across all chunks

class KbQueryRequest(BaseModel):
    query: str             # 1–2000 chars; Hebrew or mixed
    top_k: int = 5         # 1–20

class KbErrorResponse(BaseModel):
    code: Literal["unsupported_extension", "file_too_large", "encoding_error",
                  "ollama_unreachable", "chroma_unreachable", "empty_after_chunking"]
    detail: str
```

## Hebrew Chunking Strategy

Implemented in `receptra.rag.chunker` (Plan 04-03). Design choices (RESEARCH
§Hebrew Chunking Strategy, locked):

**Preprocessing:**
1. Unicode NFC normalization.
2. Niqqud strip (`ְ`–`ׇ` range removed) — BGE-M3 is trained without
   niqqud; stripping improves embedding alignment.

**Sentence splitting:**
- Primary: split on `[.!?]+` followed by whitespace or end-of-string.
- Gershayim (`״`, U+05F4) is excluded from split triggers — Hebrew abbreviations
  like `ע״מ` (VAT number) or `ש״ח` (shekels) must not be split mid-token.
- English abbreviations (e.g., `Dr.`, `Inc.`) are re-glued when the next token
  starts with a capital letter.

**Chunking:**
- Target chunk size: 1,500 characters; overlap: 200 characters.
- A sentence is never split mid-word (the regex boundary ensures whole sentences
  are absorbed into a chunk or deferred to the next).
- Chunks carry `char_start` / `char_end` offsets into the NFC-normalized text
  for citation highlighting in the Phase 6 frontend.

**Chunk ID scheme:** `{sha256(content)[:8]}:{chunk_index}` — stable across
re-ingests of identical content (Pitfall #8 mitigation).

## Recall@5 Baseline

**Current status: UNMEASURED** — first Mac contributor measurement pending.

Run `make eval-rag` on a machine with bge-m3 pulled + ChromaDB up to measure:

```bash
make models-bge          # ollama pull bge-m3 (~1.2 GB)
docker compose up -d     # starts ChromaDB + backend
make eval-rag            # seeds 10 fixtures, queries 10 questions, prints recall@5
```

Expected output shape:

```json
{
  "recall_at_5": 0.0,
  "n_questions": 10,
  "n_with_gold": 8,
  "n_no_gold": 2,
  "refusal_correct": 0,
  "hits": 0
}
```

The initial target is `recall_at_5 >= 0.6`. If the first measurement shows lower,
run `scripts/eval_rag.py --query-only --out-jsonl /tmp/results.jsonl` to inspect
per-question results and tune the similarity threshold in `settings.rag_min_similarity`.

Record the baseline in `.planning/phases/04-hebrew-rag-knowledge-base/04-06-SUMMARY.md`
and commit a bump to the `>= 0.6` assertion in `test_recall_live.py`.

## Audit Log + PII Warning

Four structured log events emitted via loguru `event=` binding:

| Event | Fields logged | Fields NEVER logged |
|-------|--------------|-------------------|
| `rag.ingest` | `filename`, `chunks_added`, `chunks_replaced`, `bytes_ingested` | chunk text body |
| `rag.query` | `query_hash` (sha256[:16]), `top_k`, `n_results` | raw query text |
| `rag.delete` | `filename`, `deleted` (chunk count) | chunk IDs, content |
| `rag.lifespan` | `msg` (startup/shutdown status) | model paths |

**WARNING — PII boundary:**

> Hebrew business documents and customer query transcripts are potentially sensitive.
> The audit log is designed to carry structural metadata only — never raw text.
>
> **Do NOT attach raw audit log lines to GitHub issues.** Capture only event
> names (`rag.ingest`, `rag.query`) and structural fields (`filename`,
> `n_results`). The `query_hash` is a one-way fingerprint for correlation;
> it cannot be reversed to recover the original query.
>
> If you need to debug a specific query result, use `scripts/eval_rag.py
> --query-only --out-jsonl /tmp/debug.jsonl` locally and delete the file
> after inspection.

This boundary mirrors the Phase 2 STT audit log (docs/stt.md) and Phase 3
LLM audit log (docs/llm.md).

## Running the Recall Eval

Three usage modes for `scripts/eval_rag.py`:

### In-process (offline CI / harness wiring verification)

```bash
# From repo root:
make eval-rag

# Equivalent:
cd backend && uv run python ../scripts/eval_rag.py --full --testclient
```

When invoked from inside pytest (via `test_recall_live.py`), the autouse
`_stub_heavy_loaders` fixture patches BGE-M3 + ChromaDB — retrieval returns
mock vectors and the recall number is mechanically low. This proves harness
wiring, not quality.

When invoked directly (outside pytest), the real lifespan fires. If Ollama
or ChromaDB is not running, `_health_check` detects the down subsystems and
exits with code 1.

### Live measurement (real recall@5)

```bash
# Prerequisite: bge-m3 pulled + ChromaDB + backend running
make models-bge
docker compose up -d
RECEPTRA_RAG_LIVE_TEST=1 pytest backend/tests/rag/test_recall_live.py -v -m live
```

### Per-question debugging

```bash
cd backend
uv run python ../scripts/eval_rag.py \
    --query-only \
    --out-jsonl /tmp/rag_results.jsonl
cat /tmp/rag_results.jsonl | python3 -m json.tool
```

Each JSONL line contains `question`, `gold_filename`, `retrieved_filenames`,
`n_results`, and `hit` (bool). Inspect which questions missed and compare
against `fixtures/rag/eval_questions.jsonl`.

**Exit codes:**
- `0` — success
- `1` — backend unreachable or subsystems down
- `2` — recall@5 below `--floor` (default 0.5)

## Known Limitations

**File format:** only `.md` and `.txt` accepted. PDF, DOCX, RTF return HTTP 415.
PDF parsing deferred to v2 (requires `pdfminer` or equivalent; adds ~80 MB dep).

**Size cap:** 1 MiB per document. Documents larger than this must be split before
ingestion. This cap is enforced both in the multipart upload (streaming pre-check)
and in `/api/kb/ingest-text` (Pydantic `max_length`).

**Sync ingest only:** `ingest_document` is an async function but internally calls
`chunk_hebrew` synchronously. For large batches, ingestion blocks the event loop
between `asyncio.to_thread` calls. An async job-queue API is deferred to v2.

**Single tenant:** all documents share the `receptra_kb` collection. v2 adds
`tenant_id` metadata filtering (forward-compat field already present, set to `None`).

**BGE-M3 recall floor:** if recall@5 < 0.6 on first measurement, the likely cause
is low cosine similarity scores due to query phrasing mismatch with BGE-M3. See
RESEARCH §Open Decision 5 for the `multilingual-e5-large` fallback option.

**Eval set provenance:** the 10 evaluation questions in `fixtures/rag/eval_questions.jsonl`
are hand-crafted (RESEARCH §Eval Fixture Plan lock). The Webiks Hebrew NLP corpus
is licensed CC-BY-NC-SA and cannot be used. A larger eval set (100+ questions) is
tracked as a Phase 7 stretch goal.

## Troubleshooting

**`chroma_unreachable` 503 on any KB endpoint:**
```bash
docker compose ps chromadb          # should show "running"
curl http://localhost:8000/api/v2/heartbeat   # should return {"nanosecond heartbeat": ...}
```
If ChromaDB is not running: `docker compose up -d chromadb`.
Check `docker compose logs chromadb` for startup errors.

**`ollama_unreachable` 503 on upload / query:**
```bash
ollama list                         # should list bge-m3
curl http://localhost:11434/api/tags | python3 -m json.tool
```
If Ollama is not running: `ollama serve` (or `make up` which starts it).
If bge-m3 is missing: `make models-bge`.

**`model_missing` (surfaced as `ollama_unreachable` on wire):**
bge-m3 is not pulled. Fix: `ollama pull bge-m3`. Check `ollama show bge-m3`
returns the model card.

**HTTP 415 on a `.md` file:**
Check filename extension casing — `Policy.MD` fails (extension is `.MD`, not `.md`).
`ingest_document._validate_extension` uses `pathlib.Path.suffix` which is
case-sensitive on Linux. Rename the file to lowercase extension.

**recall@5 below baseline:**
```bash
cd backend && uv run python ../scripts/eval_rag.py \
    --query-only --out-jsonl /tmp/debug.jsonl
python3 -c "
import json
rows = [json.loads(l) for l in open('/tmp/debug.jsonl')]
missed = [r for r in rows if not r['hit']]
for m in missed:
    print(m['question'], '->', m['retrieved_filenames'])
"
```
Compare against `fixtures/rag/eval_questions.jsonl` gold mappings. If the gold
filename is retrieved but the `gold_chunk_match` substring is missing from the
text, the chunk boundary may have split the relevant sentence — reduce
`settings.rag_chunk_size` or increase overlap.

**re-ingest count mismatch (`chunks_replaced` != prior `chunks_added`):**
The delete-before-add uses `collection.get(where={"filename": filename})` to find
prior chunk IDs. If the ChromaDB persistence volume (`./data/chroma`) was reset
between ingests, `chunks_replaced` will be 0 on re-ingest. Verify the Docker
volume is mounted: `docker compose config | grep chroma`.

## Cross-references

**Research:**
- `.planning/phases/04-hebrew-rag-knowledge-base/04-RESEARCH.md` — full
  decision log, pitfall register, literature survey.

**Plan summaries:**
- `04-01-SUMMARY.md` — settings + live tests framework
- `04-02-SUMMARY.md` — ChromaDB + BGE-M3 spike results
- `04-03-SUMMARY.md` — Hebrew chunker implementation
- `04-04-SUMMARY.md` — ingest + retriever public surfaces
- `04-05-SUMMARY.md` — route layer + lifespan fixture architecture
- `04-06-SUMMARY.md` — eval harness + recall baseline (this plan)

**Sibling docs:**
- `docs/stt.md` — Phase 2 Hebrew STT pipeline (audit log pattern origin)
- `docs/llm.md` — Phase 3 DictaLM suggestion engine (grounding contract)

**Downstream phases:**
- Phase 5 INT-04: graceful RAG degradation when ChromaDB is down
- Phase 5 INT-05: unified SQLite audit log consolidating STT + RAG + LLM events
- Phase 6 FE-06: React upload form → `POST /api/kb/upload`; document list →
  `GET /api/kb/documents`; real-time KB status → `GET /api/kb/health`
