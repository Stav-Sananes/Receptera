---
phase: 04-hebrew-rag-knowledge-base
plan: 02
subsystem: rag
tags:
  - rag
  - hebrew
  - chunker
  - tdd
  - hebrew-nlp-toolkit
requires:
  - receptra.config.settings (rag_chunk_target_chars + rag_chunk_overlap_chars from Plan 04-01)
provides:
  - receptra.rag.chunker.Chunk (frozen dataclass)
  - receptra.rag.chunker.normalize_hebrew (NFC + niqqud strip + whitespace collapse)
  - receptra.rag.chunker.chunk_hebrew (sentence-aware greedy packer with overlap)
affects:
  - backend/pyproject.toml ([tool.ruff.lint.per-file-ignores] extended for src/receptra/rag/chunker.py + tests/rag/test_chunker.py)
  - backend/src/receptra/rag/chunker.py (NEW)
  - backend/tests/rag/test_chunker.py (NEW)
tech_stack_added: []
patterns:
  - Pure-stdlib enforcement: introspection test reads chunker.py source and fails CI on imports outside allowlist (re, unicodedata, dataclasses, typing, __future__, receptra.config)
  - Hebrew sentence regex `[.!?]` excludes gershayim ״ U+05F4 + geresh ׳ U+05F3 by construction (Pitfall 2 mitigation, regression-tested)
  - English abbreviation re-glue (Dr./Mr./Mrs./Ph.D./vs./etc./e.g./i.e./Inc./Ltd.) protects mixed Hebrew+English docs
  - Defensive sole-unit emit on pathological >target tokens (Pitfall 8 / DoS T-04-02-01) — prevents infinite loop AND duplicate emission
  - Char offsets into NORMALIZED text (not raw input); short-doc shortcut path satisfies normalized[start:end] == text exactly
  - Chunker normalize_hebrew INTENTIONALLY diverges from receptra.stt.wer.normalise_hebrew on punctuation handling (chunker preserves .!?,:; for sentence detection; WER scorer collapses to whitespace for word-level edit distance)
key_files:
  created:
    - backend/src/receptra/rag/chunker.py
    - backend/tests/rag/test_chunker.py
  modified:
    - backend/pyproject.toml
decisions:
  - D-04 confirmed: Hebrew chunking via regex `[.!?]` + paragraph splits, gershayim/geresh excluded
  - D-05 confirmed: NFC + niqqud strip mirrors receptra.stt.wer normalize shape (diacritic ranges identical; punctuation handling intentionally diverges)
  - D-06 confirmed: 1500-char target / 200-char overlap defaults flow from settings
  - chunker.py per-file-ignore: RUF001/RUF002/RUF003 (Hebrew literals appear in module docstring documenting the gershayim/geresh regression contract)
  - test_chunker.py per-file-ignore: S101 + RUF001/RUF002/RUF003 (Hebrew test fixtures + comments; same precedent as tests/llm/test_prompts.py from Plan 03-02)
metrics:
  duration: 4min
  tasks_completed: 2
  files_changed: 3
  completed_date: "2026-04-26"
---

# Phase 04 Plan 02: Hebrew Chunker Summary

Sentence-aware Hebrew chunker with gershayim/geresh defense, NFC + niqqud preprocessing, and 1500/200-char greedy packing — pure stdlib, zero new dependencies. Closes RAG-03 chunker layer.

## Commits

| Type | SHA | Message |
|------|-----|---------|
| RED  | `733e7b1` | test(04-02): add failing tests for receptra.rag.chunker (Hebrew sentence + gershayim + overlap) |
| GREEN | `1745323` | feat(04-02): implement Hebrew chunker (sentence-aware + gershayim defense + overlap) |

TDD gate sequence verified: 17 failing tests → 17 passing tests (`receptra.rag.chunker` symbols added in GREEN).

## Public Surface

```python
from receptra.rag.chunker import Chunk, chunk_hebrew, normalize_hebrew

@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    char_start: int    # offset into normalized text
    char_end: int      # exclusive
    text: str          # always non-empty

def normalize_hebrew(text: str) -> str: ...
def chunk_hebrew(
    text: str,
    *,
    target_chars: int | None = None,   # default settings.rag_chunk_target_chars
    overlap_chars: int | None = None,  # default settings.rag_chunk_overlap_chars
) -> list[Chunk]: ...
```

## Tests Added (17 total)

| # | Test | Pins |
|---|------|------|
| 1 | test_normalize_hebrew_nfc | NFC composition + idempotence |
| 2 | test_normalize_hebrew_strips_niqqud | Diacritics → empty (intra-word integrity) |
| 3 | test_normalize_hebrew_collapses_whitespace | `\n\n` paragraph breaks survive; intra-paragraph collapses |
| 4 | test_chunk_hebrew_empty | Empty + whitespace-only → `[]` |
| 5 | test_chunk_hebrew_single_short_doc | Short doc → 1 chunk; `normalized[s:e] == text` |
| 6 | test_chunk_hebrew_paragraph_split | Multi-paragraph respects `\n\n` boundaries |
| 7 | test_chunk_hebrew_sentence_split | Long paragraph splits at `[.!?]` boundaries |
| 8 | **test_gershayim_not_boundary** | REGRESSION: ע״מ stays intact (Pitfall 2) |
| 9 | **test_geresh_not_boundary** | REGRESSION: מס׳ stays intact (Pitfall 2) |
| 10 | test_english_abbreviation_protected | `Dr. Cohen` re-glued (no spurious split) |
| 11 | **test_no_mid_word_split** | DoS guard: 3000-char single token → 1 sole-unit chunk (Pitfall 8) |
| 12 | test_overlap_carryover | Tail of chunk[N] appears at start of chunk[N+1] |
| 13 | test_chunk_index_monotonic | chunk_index = 0..N-1 in order |
| 14 | test_char_offsets_into_normalized_text | Contract: short-doc path slices normalized exactly |
| 15 | test_chunk_hebrew_uses_settings_defaults | Settings → kwargs → defaults precedence |
| 16 | test_normalize_diverges_from_wer | Documents intentional divergence from Phase 2 normalise_hebrew |
| 17 | **test_chunk_hebrew_pure_stdlib** | License/dep-creep guard: introspects chunker.py source |

Full backend suite delta: 217 pass → 234 pass (+17); 6 skip unchanged. Ruff + mypy strict clean across 60 source files.

## Stdlib-Only Confirmation

```
$ grep -E "^(from|import)" backend/src/receptra/rag/chunker.py
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from receptra.config import settings
```

Allowlist enforced by `test_chunk_hebrew_pure_stdlib`: any future contributor adding `transformers`, `tokenizers`, `nltk`, `regex`, `hebrew_tokenizer`, etc., flips the test RED. Threat T-04-02-02 (license / dep-creep) is structurally mitigated.

## Smoke Verification

```
$ uv run python -c "from receptra.rag.chunker import chunk_hebrew; \
  chunks = chunk_hebrew('שלום עולם. ' * 200, target_chars=400); \
  print(f'{len(chunks)} chunks')"
11 chunks
first chunk_index=0 len=395
last chunk_index=10 len=219
```

11-chunk emission with monotonic indices and target-respecting lengths confirms the greedy packer + overlap carry path round-trips correctly.

## Cross-Phase Handoff

Plan 04-04 (RAG-04 ingest pipeline) consumes this surface verbatim:

```python
from receptra.rag.chunker import chunk_hebrew, Chunk

for chunk in chunk_hebrew(content_str):
    # chunk.chunk_index → ChunkRef.chunk_index
    # chunk.text        → ChunkRef.text + embedding input
    # chunk.char_start / char_end → opaque to LLM, used for source-anchor display
    embedding = embed(chunk.text)
    upsert(chunk, embedding)
```

`Chunk` is a frozen dataclass — Plan 04-04 must NOT extend the surface; if extra fields are needed (doc_id, char_hash) they belong on the ChunkRef wrapper, not on Chunk.

## Threat Model Reconciliation

All 6 threats from PLAN.md `<threat_model>` are addressed:

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-04-02-01 (DoS — pathological single token) | mitigate | DONE — sole-unit emit branch, regression-tested by `test_no_mid_word_split` |
| T-04-02-02 (license / dep-creep) | mitigate | DONE — `test_chunk_hebrew_pure_stdlib` introspection guard |
| T-04-02-03 (gershayim drift) | mitigate | DONE — `test_gershayim_not_boundary` + `test_geresh_not_boundary` |
| T-04-02-04 (PII leak via DEBUG log) | accept | NO logging calls in chunker (PII boundary stays at Plan 04-05 routes layer) |
| T-04-02-05 (offset drift) | mitigate | DONE — `test_char_offsets_into_normalized_text` (short-doc path); long-doc path documented in `Chunk` docstring |
| T-04-02-06 (settings frozen at import) | accept | DONE — `test_chunk_hebrew_uses_settings_defaults` proves runtime monkeypatch via singleton attribute mutation |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Defensive sole-unit emission was emitting twice on oversized tokens**

- **Found during:** Task 2 GREEN initial run (`test_no_mid_word_split` failed with `assert 2 == 1`)
- **Issue:** The original branch `if len(u) > target and len(cur_units) == 1: emit()` emitted the oversized chunk via `emit()`, but `emit()`'s overlap-carry logic preserved the same sole unit in `cur_units`, which then got emitted again at end-of-loop — producing 2 identical chunks of the same 3000-char string.
- **Fix:** Replaced with an explicit sole-unit fast path that appends the chunk directly (no overlap carry — the unit IS the chunk) and resets `cur_units = []`, ensuring loop termination AND single emission.
- **Files modified:** `backend/src/receptra/rag/chunker.py`
- **Commit:** Folded into the GREEN commit `1745323`.

**2. [Rule 3 — Blocking] RUF002/RUF003 ambiguous-glyph errors in chunker.py module docstring**

- **Found during:** Task 2 final ruff sweep
- **Issue:** Module docstring documents the gershayim ״ + geresh ׳ regression contract using the actual Unicode codepoints. Ruff RUF002 (docstring) + RUF003 (comment) flagged them as ambiguous.
- **Fix:** Added `src/receptra/rag/chunker.py = ["RUF001", "RUF002", "RUF003"]` to `[tool.ruff.lint.per-file-ignores]` — same precedent as `src/receptra/llm/prompts.py` from Plan 03-02 (Hebrew content in source forces this allowance).
- **Files modified:** `backend/pyproject.toml`
- **Commit:** Folded into the GREEN commit `1745323`.

No architectural deviations. No authentication gates. No checkpoints.

## Self-Check: PASSED

- backend/src/receptra/rag/chunker.py: FOUND
- backend/tests/rag/test_chunker.py: FOUND
- 733e7b1 (RED): FOUND
- 1745323 (GREEN): FOUND
- All 17 chunker tests pass; full backend suite 234 pass / 6 skip; ruff + mypy strict clean.
