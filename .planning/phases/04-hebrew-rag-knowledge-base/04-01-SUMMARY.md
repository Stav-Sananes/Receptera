---
phase: 04-hebrew-rag-knowledge-base
plan: 01
subsystem: rag
tags:
  - rag
  - hebrew
  - dependencies
  - settings
  - scaffold
requires:
  - receptra.config.Settings (Phase 1 / Plan 03-01 extension pattern)
  - receptra.llm.schema.ChunkRef (Phase 3 / Plan 03-02 canonical owner)
provides:
  - chromadb-client>=1.5.8,<2 dep pin
  - 4 RECEPTRA_RAG_* Settings fields (rag_min_similarity, rag_chunk_target_chars, rag_chunk_overlap_chars, rag_embed_batch_size)
  - receptra.rag package (types/errors/__init__)
  - typed RAG exceptions (RagInitError + IngestRejected) with frozen Literal code allowlists
  - rag_live_test_enabled() helper (RECEPTRA_RAG_LIVE_TEST gate)
  - scripts/spike_chunk_token_ratio.py (char→BGE-M3-token ratio spike, airgap-tolerant)
  - 04-01-SPIKE-RESULTS.md (UNMEASURED on Wave-0 executor; chars_per_token=3.0 default)
  - top-level live pytest marker registration (hoisted from tests/llm/conftest.py)
affects:
  - .planning/phases/04-hebrew-rag-knowledge-base/04-01-SPIKE-RESULTS.md
  - backend/pyproject.toml ([project].dependencies + ruff per-file-ignore)
  - backend/uv.lock
  - backend/src/receptra/config.py
  - backend/src/receptra/rag/__init__.py
  - backend/src/receptra/rag/types.py
  - backend/src/receptra/rag/errors.py
  - backend/tests/conftest.py (live marker registration moved here)
  - backend/tests/llm/conftest.py (pytest_configure removed; live_test_enabled() unchanged)
  - backend/tests/rag/__init__.py
  - backend/tests/rag/conftest.py
  - backend/tests/rag/test_settings.py
  - backend/tests/rag/test_types.py
  - backend/tests/rag/test_errors.py
  - backend/tests/rag/test_ollama_embed_smoke.py
  - scripts/spike_chunk_token_ratio.py
  - scripts/check_licenses.sh (PY_ALLOW extended for chromadb-client transitive licenses)
  - .env.example
tech_stack_added:
  - chromadb-client==1.5.8 (Apache-2.0 — thin client only, full chromadb pkg explicitly NOT pinned)
  - transitive: grpcio, opentelemetry-{api,sdk,exporter-otlp-proto-{common,grpc}}, jsonschema, jsonschema-specifications, googleapis-common-protos, importlib-metadata, attrs, orjson, overrides, pybase64, referencing, rpds-py, tenacity, zipp, opentelemetry-{proto,semantic-conventions}, protobuf
patterns:
  - Spike-with-fallback: try transformers + sentencepiece import → HF cache lookup → MEASURED; on import or cache miss, write UNMEASURED placeholder + exit 0 (Plan 02-01 precedent)
  - Live-test triple-gate skip: RECEPTRA_RAG_LIVE_TEST=1 + ollama on PATH + client.show("bge-m3") (mirrors Plan 03-01 ChatML test)
  - ChunkRef cross-phase re-export (NOT redefinition): receptra.rag.types.ChunkRef IS receptra.llm.schema.ChunkRef (class identity preserved)
  - Typed RAG exceptions: frozen dataclass + Literal code allowlist matching RESEARCH §REST API KbErrorResponse (consumer switches stay total)
  - Top-level live marker registration: tests/conftest.py owns it; per-package conftests own their per-env helpers
key_files:
  created:
    - backend/src/receptra/rag/__init__.py
    - backend/src/receptra/rag/types.py
    - backend/src/receptra/rag/errors.py
    - backend/tests/rag/__init__.py
    - backend/tests/rag/conftest.py
    - backend/tests/rag/test_settings.py
    - backend/tests/rag/test_types.py
    - backend/tests/rag/test_errors.py
    - backend/tests/rag/test_ollama_embed_smoke.py
    - scripts/spike_chunk_token_ratio.py
    - .planning/phases/04-hebrew-rag-knowledge-base/04-01-SPIKE-RESULTS.md
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/src/receptra/config.py
    - backend/tests/conftest.py
    - backend/tests/llm/conftest.py
    - .env.example
    - scripts/check_licenses.sh
key_decisions:
  - "Pin chromadb-client (thin) NOT chromadb (full package): full chromadb pulls onnxruntime/pulsar-client/tokenizers (RESEARCH §Cluster 1 anti-pattern); ChromaDB server runs in its own container per docker-compose.yml. Both publish identical 1.5.8."
  - "Hoist `live` pytest marker registration from tests/llm/conftest.py to top-level tests/conftest.py: needed because `uv run pytest tests/rag` does not load tests/llm/conftest.py and would emit PytestUnknownMarkWarning under --strict-markers. Per-package live-test gates (RECEPTRA_LLM_LIVE_TEST vs RECEPTRA_RAG_LIVE_TEST) keep their separate env vars."
  - "Extend scripts/check_licenses.sh PY_ALLOW with `Apache License, Version 2.0` (overrides 7.7.0 variant) and `MPL-2.0 AND (Apache-2.0 OR MIT)` (orjson 3.11.8 composite): chromadb-client transitive closure surfaced two valid SPDX-equivalent license formats not previously in the allowlist."
  - "Add ruff per-file-ignore N818 to src/receptra/rag/errors.py: IngestRejected is a contract-locked exception name aligned with RESEARCH §REST API KbErrorResponse.code semantics ('ingest was rejected'). The Error suffix N818 wants would invert past-tense semantics; RagInitError already follows the convention."
  - "ChunkRef class identity preserved (NOT redefined): receptra.rag.types.ChunkRef is receptra.llm.schema.ChunkRef. Phase 5 hot-path code may import from either module without identity drift; CI catches drift via test_chunkref_class_identity."
metrics:
  duration: "9 min"
  completed: "2026-04-26"
  tasks: 2
  files_created: 11
  files_modified: 7
  tests_added: 13
  test_suite_total: "217 pass / 6 skip"
---

# Phase 04 Plan 01: Wave-0 Dep Lock + RAG Settings + receptra.rag Scaffold + Char/Token Spike + Ollama BGE-M3 Smoke — Summary

**One-liner:** Pinned thin-client `chromadb-client>=1.5.8,<2`; published 4 `RECEPTRA_RAG_*` Settings; scaffolded `receptra.rag` (types re-exports ChunkRef from `receptra.llm.schema` with class identity preserved; errors publishes RagInitError + IngestRejected with frozen Literal allowlists matching RESEARCH §REST API); scaffolded `tests/rag/` with `rag_live_test_enabled()` helper on `RECEPTRA_RAG_LIVE_TEST`; shipped char→BGE-M3-token ratio spike with airgap fallback (UNMEASURED on Wave-0 executor) and triple-gated Ollama BGE-M3 smoke test (1024-dim Hebrew embedding).

## What Was Built

### 1. Dependency lock (D-01)

`backend/pyproject.toml` — added `chromadb-client>=1.5.8,<2` to `[project].dependencies`. Resolved `chromadb-client==1.5.8` (per `uv.lock`). Pulls 22 transitive packages (grpcio, opentelemetry stack, orjson, jsonschema, etc.) — all permissively licensed and in the allowlist after the two new variants were added (`Apache License, Version 2.0` and `MPL-2.0 AND (Apache-2.0 OR MIT)`).

A guard test (`test_chromadb_client_pinned`) parses `pyproject.toml` at runtime and asserts:
1. `chromadb-client` is in `[project].dependencies`.
2. The version spec contains `>=1.5.8`.
3. The full `chromadb` package is NOT pinned (anti-pattern per RESEARCH §Cluster 1).

### 2. RAG Settings (4 fields)

`backend/src/receptra/config.py` extends the existing `Settings` class with a Phase 4 block (mirrors the Phase 3 LLM block byte-for-byte):

| Field | Default | Source | Notes |
|-------|---------|--------|-------|
| `rag_min_similarity` | `0.35` | RESEARCH §Cluster 5 | Cosine-similarity floor for retrieved chunks; Plan 04-06 retunes via recall@5 eval |
| `rag_chunk_target_chars` | `1500` | RESEARCH §Hebrew Chunking Strategy | ≈500 BGE-M3 tokens via 1-token≈3-Hebrew-char heuristic |
| `rag_chunk_overlap_chars` | `200` | RESEARCH §Hebrew Chunking Strategy | ≈12% overlap (textbook RAG default) |
| `rag_embed_batch_size` | `16` | RESEARCH §BGE-M3 Pattern | Memory-stable on 16GB Mac; 32 risks Ollama context-overflow |

All RECEPTRA_RAG_* env-tunable. Existing `chroma_host` (Phase 1) is unchanged; Plan 04-03 will `urlparse()` it.

### 3. `receptra.rag` package scaffold

| File | Provides |
|------|----------|
| `__init__.py` | Package marker (no eager submodule imports per RESEARCH §Cluster 7 lifespan pattern) |
| `types.py` | Re-export `ChunkRef` from `receptra.llm.schema` — class identity preserved |
| `errors.py` | `RagInitError` (codes: `ollama_unreachable` / `model_missing` / `chroma_unreachable`) + `IngestRejected` (codes: `unsupported_extension` / `file_too_large` / `encoding_error` / `empty_after_chunking`) — both `@dataclass(frozen=True) class …(Exception)` with `Literal` `code` field matching RESEARCH §REST API `KbErrorResponse.code` |

Class-identity test (`test_chunkref_class_identity`):
```python
from receptra.llm.schema import ChunkRef as LlmChunkRef
from receptra.rag.types import ChunkRef as RagChunkRef
assert RagChunkRef is LlmChunkRef
```

### 4. `tests/rag/` scaffold

| File | Provides |
|------|----------|
| `__init__.py` | Package marker |
| `conftest.py` | `rag_live_test_enabled()` helper (gated on `RECEPTRA_RAG_LIVE_TEST=1`) |
| `test_settings.py` | 5 tests: 4 RAG defaults, RECEPTRA_RAG_* env override, chunk-size override, chromadb-client pin guard, Python 3.12 marker |
| `test_types.py` | 3 tests: ChunkRef class identity, constructable via RAG alias, source-optional |
| `test_errors.py` | 4 tests: RagInitError codes, IngestRejected codes, Exception subclass, frozen=True immutability |
| `test_ollama_embed_smoke.py` | 1 opt-in live test (triple-gated; skips on Wave-0 executor) |

13 tests collected; 12 pass, 1 smoke skips on `RECEPTRA_RAG_LIVE_TEST` gate.

### 5. Char→BGE-M3-token ratio spike

`scripts/spike_chunk_token_ratio.py` — 5 hand-crafted Hebrew samples (hours / returns / prices / address / complaints — domain-aligned with eventual Plan 04-06 KB fixtures) at lengths spanning ~500 / ~1000 / ~1500 / ~2000 / ~3000 chars.

Spike-with-fallback (Plan 02-01 precedent): tries `from transformers import AutoTokenizer; tok = AutoTokenizer.from_pretrained("BAAI/bge-m3")`; on `ImportError` (no transformers/sentencepiece) OR HF cache miss / offline, writes UNMEASURED placeholder + exits 0. `transformers`/`sentencepiece` intentionally NOT in `pyproject.toml` (regen-only opt-in dep — Plan 02-05 lock against silent runtime dep additions).

CLI: `--out FILE`, `--json`, `--no-md`. Default output path: `.planning/phases/04-hebrew-rag-knowledge-base/04-01-SPIKE-RESULTS.md`.

### 6. Spike artifact

`.planning/phases/04-hebrew-rag-knowledge-base/04-01-SPIKE-RESULTS.md`:

```yaml
status: UNMEASURED
chars_per_token: 3.0
sample_count: 5
```

Wave-0 executor wrote the UNMEASURED variant. First Mac contributor with `pip install transformers sentencepiece` + `make models-bge` re-runs to overwrite with MEASURED. Per-sample char counts are recorded in the file (tokens/ratio columns are `—` until measured).

### 7. Ollama BGE-M3 smoke test

`backend/tests/rag/test_ollama_embed_smoke.py` — opt-in live test gated by triple-skip (mirrors Plan 03-01 ChatML test pattern):
1. `RECEPTRA_RAG_LIVE_TEST=1` (RAG live-test gate, separate from LLM gate)
2. `ollama` binary on PATH
3. `client.show("bge-m3")` round-trip

Verifies `await client.embed(model="bge-m3", input="שלום עולם")` returns `len(embeddings[0]) == 1024` per RESEARCH §Cluster 2.

### 8. Live marker hoist

The `live` pytest marker was registered in `tests/llm/conftest.py` (Plan 03-01). When `uv run pytest tests/rag` runs in isolation, that conftest is NOT loaded (sibling, not ancestor) — the new bge-m3 smoke test would emit `PytestUnknownMarkWarning` under `--strict-markers`. Hoisted the registration to the top-level `tests/conftest.py`. `tests/llm/conftest.py` keeps its `live_test_enabled()` helper unchanged. No behavioral change for any existing test; same marker name + description text would have been re-registered.

### 9. License gate extension

`scripts/check_licenses.sh` — extended `PY_ALLOW` with two valid SPDX-equivalent license formats surfaced by chromadb-client transitive closure:
- `Apache License, Version 2.0` (`overrides 7.7.0`)
- `MPL-2.0 AND (Apache-2.0 OR MIT)` (`orjson 3.11.8` composite)

Both are within the existing license posture (Apache-2.0 / MPL-2.0 — already in allowlist via other variants); no new license category was introduced.

### 10. .env.example

Appended a `# Phase 4 RAG …` block documenting the 4 `RECEPTRA_RAG_*` env vars + the `RECEPTRA_RAG_LIVE_TEST` toggle.

## Cross-phase Handoffs (Plan 04-01 contract surface)

| Plan | Imports |
|------|---------|
| 04-02 (chunker) | `settings.rag_chunk_target_chars`, `settings.rag_chunk_overlap_chars` |
| 04-03 (embedder + Chroma client) | `settings.rag_embed_batch_size`, `settings.chroma_host` (Phase 1), `chromadb-client` thin-client API |
| 04-04 (ingest pipeline) | `from receptra.rag.errors import IngestRejected`, `settings.rag_min_similarity` (retriever), `from receptra.rag.types import ChunkRef` |
| 04-05 (FastAPI router) | `from receptra.rag.errors import RagInitError, IngestRejected` (HTTP status mapping) |
| 04-06 (eval harness + docs) | `scripts/spike_chunk_token_ratio.py` re-run with MEASURED status; STT-isolation regression mirrors Plan 03-06 pattern |

All four contract surfaces (Settings field name, ChunkRef class identity, error code Literal allowlists, live-test env var) are pinned by structural tests in `tests/rag/`. Plan 04-02..06 will fail loudly at import time if any of these drift.

## Verification Results

| Gate | Result |
|------|--------|
| `cd backend && uv sync` | green (chromadb-client + 21 transitive deps installed; uv.lock updated) |
| `cd backend && uv run pytest tests/rag -x -q` | 12 pass, 1 skip (smoke) |
| `cd backend && uv run pytest -q` (full backend) | 217 pass / 6 skip / 10 warnings |
| `cd backend && uv run ruff check src tests` | All checks passed |
| `cd backend && uv run mypy` | 58 source files, no issues |
| `bash scripts/check_licenses.sh` | green (after PY_ALLOW extension) |
| `python3 scripts/spike_chunk_token_ratio.py --json` | exit 0, UNMEASURED status |
| `cat .planning/phases/04-hebrew-rag-knowledge-base/04-01-SPIKE-RESULTS.md` | valid frontmatter + per-sample char counts |

## Test Count Delta

Full backend suite: previous 205 pass / 5 skip → **217 pass / 6 skip** (Δ +12 pass, +1 skip).

New tests (13 collected, distributed below):

| File | Tests | Pass | Skip |
|------|-------|------|------|
| `tests/rag/test_settings.py` | 5 | 5 | 0 |
| `tests/rag/test_types.py` | 3 | 3 | 0 |
| `tests/rag/test_errors.py` | 4 | 4 | 0 |
| `tests/rag/test_ollama_embed_smoke.py` | 1 | 0 | 1 (RECEPTRA_RAG_LIVE_TEST gate) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] License allowlist drift on chromadb-client transitive closure**
- **Found during:** Task 1 (post-install license gate)
- **Issue:** `bash scripts/check_licenses.sh` failed with two new license strings: `Apache License, Version 2.0` (overrides 7.7.0) and `MPL-2.0 AND (Apache-2.0 OR MIT)` (orjson 3.11.8). Both are valid SPDX-equivalent variants of licenses already accepted (Apache-2.0 / MPL-2.0); pip-licenses just spells them differently.
- **Fix:** Extended `PY_ALLOW` in `scripts/check_licenses.sh` with both variants. Same pattern Plans 02-01/03-01 used when Phase 2/3 deps surfaced new license formats.
- **Files modified:** `scripts/check_licenses.sh`
- **Commit:** `97ec1cc` (folded into Task 1 GREEN)

**2. [Rule 3 - Blocking] Ruff N818 on contract-locked exception name `IngestRejected`**
- **Found during:** Task 1 (ruff gate)
- **Issue:** Ruff N818 wants exception class names to end with `Error`. `IngestRejected` is a contract-locked name aligned with RESEARCH §REST API `KbErrorResponse.code` semantics ("ingest was rejected" — past tense). Renaming to `IngestRejectedError` would invert the semantics.
- **Fix:** Added `"src/receptra/rag/errors.py" = ["N818"]` to `[tool.ruff.lint.per-file-ignores]` with comment explaining the contract.
- **Files modified:** `backend/pyproject.toml`
- **Commit:** `97ec1cc` (folded into Task 1 GREEN)

**3. [Rule 3 - Blocking] PytestUnknownMarkWarning on bge-m3 smoke when running tests/rag in isolation**
- **Found during:** Task 2 (verifying smoke test self-skips cleanly)
- **Issue:** The `live` pytest marker was registered in `tests/llm/conftest.py` (Plan 03-01). When `uv run pytest tests/rag` runs in isolation, pytest does not load `tests/llm/conftest.py` (sibling, not ancestor). Under `--strict-markers`, the bge-m3 smoke test emitted `PytestUnknownMarkWarning`.
- **Fix:** Hoisted the `live` marker registration to the top-level `tests/conftest.py`. `tests/llm/conftest.py` keeps its `live_test_enabled()` helper unchanged. The plan's original guidance ("do NOT re-register the live marker — pytest will warn on duplicate addinivalue_line") is honored: there is now one registration, not two.
- **Files modified:** `backend/tests/conftest.py`, `backend/tests/llm/conftest.py`
- **Commit:** `259cfec` (folded into Task 2)

**4. [Rule 3 - Blocking] Mypy unused-ignore on test_errors.py + test_ollama_embed_smoke.py**
- **Found during:** Task 1 + Task 2 (mypy gate)
- **Issue:** Two `# type: ignore[arg-type]` comments on the for-loop iterating literal tuples in `test_errors.py` were unused (mypy preserves Literal types in tuple iteration). One `# type: ignore[import-untyped]` on `from ollama import AsyncClient` was unused (the ollama package now ships .pyi stubs).
- **Fix:** Removed all three ignores.
- **Files modified:** `backend/tests/rag/test_errors.py`, `backend/tests/rag/test_ollama_embed_smoke.py`
- **Commit:** `97ec1cc` + `259cfec`

### Deferred Issues

None. All in-scope work green.

## Authentication Gates

None encountered. The bge-m3 smoke test self-skips on the Wave-0 executor (no `RECEPTRA_RAG_LIVE_TEST` env, no host Ollama configured); the spike script self-skips to UNMEASURED airgap mode (no transformers/sentencepiece, no HF cache).

## TDD Gate Compliance

This plan executed Task 1 as RED → GREEN:
- **RED:** `77a5d3c` — `test(04-01): add failing tests for receptra.rag scaffold + RAG Settings + chromadb-client pin` (12 tests collected, all failing on `ModuleNotFoundError: receptra.rag.errors`)
- **GREEN:** `97ec1cc` — `feat(04-01): pin chromadb-client + 4 RAG Settings + receptra.rag scaffold (types/errors)` (12 tests pass, ruff + mypy clean, license gate green)
- **No REFACTOR** required.

Task 2 was non-TDD per plan frontmatter — direct `feat` commit `259cfec`.

## Self-Check: PASSED

- `backend/pyproject.toml` chromadb-client>=1.5.8,<2 — FOUND
- `backend/src/receptra/rag/__init__.py` — FOUND
- `backend/src/receptra/rag/types.py` — FOUND
- `backend/src/receptra/rag/errors.py` — FOUND
- `backend/tests/rag/__init__.py` — FOUND
- `backend/tests/rag/conftest.py` — FOUND
- `backend/tests/rag/test_settings.py` — FOUND
- `backend/tests/rag/test_types.py` — FOUND
- `backend/tests/rag/test_errors.py` — FOUND
- `backend/tests/rag/test_ollama_embed_smoke.py` — FOUND
- `scripts/spike_chunk_token_ratio.py` — FOUND
- `.planning/phases/04-hebrew-rag-knowledge-base/04-01-SPIKE-RESULTS.md` — FOUND
- Commit `77a5d3c` (RED) — FOUND
- Commit `97ec1cc` (GREEN) — FOUND
- Commit `259cfec` (Task 2) — FOUND
