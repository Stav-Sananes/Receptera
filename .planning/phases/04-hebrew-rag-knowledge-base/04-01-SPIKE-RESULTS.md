---
phase: 04-hebrew-rag-knowledge-base
plan: 01
artifact: chunk-token-ratio-spike
status: UNMEASURED
chars_per_token: 3.0
sample_count: 5
---

# Hebrew Chunk → BGE-M3 Token Ratio — Spike Results

**Heuristic:** 3.0 chars/token (RESEARCH §Hebrew Chunking Strategy).
**Tolerance:** ±20.0% before chunk size needs retuning.
**Status:** UNMEASURED

## Per-sample measurement

| sample | chars | tokens | chars/token |
|--------|-------|--------|-------------|
| hours_500 | 397 | — | — |
| returns_1000 | 708 | — | — |
| prices_1500 | 1222 | — | — |
| address_2000 | 1517 | — | — |
| complaints_3000 | 2125 | — | — |

## Decision
- heuristic_within_tolerance: None
- rag_chunk_target_chars locked at: 1500 (default)
- airgap: transformers/sentencepiece not installed or BGE-M3 not cached — airgap mode. First Mac contributor with `pip install transformers sentencepiece` + `make models-bge` (BGE-M3 weights) re-runs to write MEASURED.
