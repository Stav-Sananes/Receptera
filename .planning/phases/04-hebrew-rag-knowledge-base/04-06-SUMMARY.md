# Plan 04-06 Summary — Eval Harness + Hebrew Fixtures

**Status:** Complete  
**Commit:** GREEN `4b1123b`

## Hebrew KB Fixtures (fixtures/rag/seed_kb/)

| File | Chars | Chunks | Topic |
|------|-------|--------|-------|
| 01_hours.md | 612 | 1 | שעות פתיחה |
| 02_returns.md | 746 | 1 | מדיניות החזרות |
| 03_pricing.md | 731 | 1 | מחירון בסיסי |
| 04_address.md | 705 | 1 | כתובת + הוראות הגעה |
| 05_callback.md | 814 | 1 | שיחה חוזרת |
| 06_payment.md | 802 | 1 | אמצעי תשלום |
| 07_holidays.md | 822 | 1 | חגים ומועדים |
| 08_complaints.md | 897 | 1 | טיפול בתלונות |
| 09_contact.md | 926 | 1 | פרטי קשר |
| 10_privacy.md | 993 | 1 | מדיניות פרטיות |

All Apache-2.0 (project-owned, hand-crafted). No real business data — fictional
demo placeholders ("רחוב הדמיוני 42", "050-DEMO-000").

## Eval Questions (fixtures/rag/eval_questions.jsonl)

10 questions: 8 grounded (gold_filename + gold_chunk_match), 2 refusal-correctness
(gold_filename: null).

| # | Type | Target |
|---|------|--------|
| 1 | Direct lookup | 01_hours.md — שישי |
| 2 | Morphological variation | 02_returns.md — ימים |
| 3 | Synonym | 03_pricing.md — ₪ |
| 4 | Address lookup | 04_address.md — רחוב |
| 5 | Callback policy | 05_callback.md — 24 |
| 6 | Hebrew+English code-mix | 06_payment.md — Bit |
| 7 | Holiday closure | 07_holidays.md — ראש השנה |
| 8 | Complaints escalation | 08_complaints.md — תלונה |
| 9 | Refusal (answer absent) | null |
| 10 | Refusal (Shabbat) | null |

## scripts/eval_rag.py

- **Line count:** ~280 lines
- **Flags:** 10 (--seed-only, --query-only, --full, --out-jsonl, --backend-url,
  --testclient, --seed-dir, --questions, --top-k, --floor)
- **Exit codes:** 0 success / 1 backend down / 2 recall@5 < floor
- **STT-isolation:** no receptra.stt / faster_whisper / torch / av imports
- **Template:** mirrors scripts/eval_llm.py (Plan 03-06) structure

## test_recall_live.py

2 tests added. Full backend suite: **307 pass / 10 skip**.

| Test | Gate | Behavior |
|------|------|---------|
| test_recall_at_5_meets_baseline | RECEPTRA_RAG_LIVE_TEST=1 | Runs harness subprocess; asserts valid JSON output |
| test_eval_rag_harness_module_is_stt_clean | RECEPTRA_RAG_LIVE_TEST=1 | Fresh subprocess STT isolation check |

## docs/rag.md

- **Line count:** ~360 lines
- **Sections (10):** Overview, Wire Contract, Schema, Hebrew Chunking Strategy,
  Recall@5 Baseline, Audit Log + PII Warning, Running the Recall Eval,
  Known Limitations, Troubleshooting (6 recipes), Cross-references
- **PII warning block:** byte-equivalent to docs/stt.md + docs/llm.md

## Recall@5 Baseline

**UNMEASURED** — this executor has no bge-m3 model or ChromaDB available.
Under mocked TestClient path, the stub collection returns no chunks above
threshold (fake zero-vectors score below default `rag_min_similarity`), so:
- 8 grounded questions → recall = 0
- 2 refusal questions → hit (zero results = correct refusal)
- Mocked recall_at_5 ≈ 0.2 (2/10)

**Real measurement required:** first Mac contributor with `make models-bge` +
`docker compose up chromadb` runs `RECEPTRA_RAG_LIVE_TEST=1 make eval-rag`.
Record result here and commit bump to `>= 0.6` assertion in test_recall_live.py.

## Phase 4 Closure

All RAG-* requirements structurally satisfied:

| Requirement | Plan | Status |
|-------------|------|--------|
| RAG-01: BGE-M3 embedder + vector store | 04-02, 04-03 | Complete |
| RAG-02: Hebrew chunker | 04-03 | Complete |
| RAG-03: Ingest pipeline | 04-04 | Complete |
| RAG-04: Retriever | 04-04 | Complete |
| RAG-05: Recall@5 evaluation | 04-06 | Structurally complete; numeric baseline pending |
| RAG-06: HTTP route layer | 04-05 | Complete |

## Cross-Phase Handoff

**Phase 5 INT-01:** wires STT → RAG → LLM hot path; `retrieve()` output
feeds directly into `generate_suggestions()` (contract established in Phase 4).

**Phase 5 INT-04:** graceful RAG degradation path (`embedder = None` or
`collection = None` → `generate_suggestions(chunks=[])` → canonical refusal).

**Phase 5 INT-05:** unified SQLite audit log merges `rag.ingest` + `rag.query`
events with STT + LLM events.

**Phase 6 FE-06:** React upload form → `POST /api/kb/upload`; document list
→ `GET /api/kb/documents`; KB health poll → `GET /api/kb/health`.
