---
feature: F3-post-call-summary
subsystem: backend-summary + frontend
tags: [hebrew, llm, summary, fastapi, react]
dependency_graph:
  requires: [receptra.llm.client, receptra.llm.engine._strip_markdown_fences]
  provides: [POST /api/summary, SummaryPanel, generateSummary]
  affects: [frontend/src/App.tsx, frontend/src/components/TranscriptPanel.tsx]
tech_stack:
  added: [receptra.summary package (schema + prompts + router)]
  patterns: [Hebrew few-shot prompting, Pydantic frozen schema, RTL React component]
key_files:
  created:
    - backend/src/receptra/summary/__init__.py
    - backend/src/receptra/summary/schema.py
    - backend/src/receptra/summary/prompts.py
    - backend/src/receptra/summary/router.py
    - frontend/src/api/summary.ts
    - frontend/src/components/SummaryPanel.tsx
    - backend/tests/summary/__init__.py
    - backend/tests/summary/test_summary_router.py
  modified:
    - backend/src/receptra/main.py
    - frontend/src/App.tsx
    - frontend/src/components/TranscriptPanel.tsx
    - backend/pyproject.toml
decisions:
  - "12000-char transcript budget for summary (separate from 2000-char per-utterance guard in llm/prompts.py)"
  - "select_model mock uses new=AsyncMock(return_value=...) not return_value=AsyncMock(...) — await semantics differ"
  - "SummaryPanel only rendered when summary/loading/error state is non-null (no empty div in DOM)"
metrics:
  duration: ~4min
  completed: "2026-04-27"
  tasks_completed: 2
  files_changed: 12
---

# Feature 3: Post-call Hebrew Summary

**One-liner:** Hebrew post-call summary via DictaLM with structured JSON output (topic/key_points/action_items) and RTL SummaryPanel frontend card.

## What Was Built

### Backend: `receptra.summary` package

**`schema.py`** — Two frozen Pydantic models:
- `CallSummaryRequest`: accepts `transcript_lines: list[str]` (min 1, max 500 items)
- `CallSummary`: returns `topic`, `key_points`, `action_items`, `raw_text`, `model`, `total_ms`

**`prompts.py`** — Hebrew system prompt + one few-shot example (order cancellation scenario). Uses a 12,000-char budget — intentionally separate from the 2,000-char per-utterance guard in `llm/prompts.py` so that full call transcripts are not rejected by the DoS guard designed for single utterances.

**`router.py`** — `POST /api/summary` endpoint:
1. Joins `transcript_lines` into a single transcript string
2. Calls `build_summary_messages()` for the prompt
3. Gets Ollama client via `get_async_client()` + `select_model()`
4. Calls `client.chat(stream=False, temperature=0.0)`
5. Strips markdown fences via `_strip_markdown_fences` (reused from `llm/engine`)
6. JSON-parses the LLM response into `CallSummary`
7. Raises HTTP 503 on Ollama errors, 422 on JSON parse failure

**`main.py`** — Router registered: `app.include_router(summary_router)`

### Frontend

**`api/summary.ts`** — `generateSummary(transcriptLines)` fetch helper with error propagation from `detail` field.

**`SummaryPanel.tsx`** — RTL card showing topic, key_points list, action_items list, latency/model footer. Has a "העתק" (copy) button. Returns `null` when no state to show.

**`App.tsx`** — Three new state variables (`summary`, `summaryLoading`, `summaryError`), `handleEndCall` async callback, `handleCopySummary` clipboard helper. `SummaryPanel` rendered conditionally below the two-column grid.

**`TranscriptPanel.tsx`** — Added optional `onEndCall?` prop. When `finals.length > 0` and `onEndCall` is provided, renders "סיים שיחה וצור סיכום" button at the bottom of the transcript panel.

## TDD Commit Pair

| Commit | Type | Description |
|--------|------|-------------|
| `7f33fe0` | RED | Failing tests for POST /api/summary — 4 tests, all failing (ModuleNotFoundError) |
| `f572d7e` | GREEN | Full implementation — 4/4 tests pass, full suite 351 pass / 11 skip |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed AsyncMock semantics in select_model patch**
- **Found during:** GREEN — test_summary_returns_structured_response failing
- **Issue:** `patch("...select_model", return_value=AsyncMock(return_value="dictalm3"))` makes `select_model` a `MagicMock` whose call returns an `AsyncMock` instance. `await select_model(client)` then awaits the `AsyncMock` instance directly (not calling it), which does not resolve to `"dictalm3"` — it resolves to the `AsyncMock` object itself, causing Pydantic to reject it as a non-string `model` field.
- **Fix:** Changed to `patch("...select_model", new=AsyncMock(return_value="dictalm3"))` — replaces `select_model` directly with an `AsyncMock` so `await select_model(client)` resolves to `"dictalm3"`.
- **Files modified:** `backend/tests/summary/test_summary_router.py`
- **Commit:** `f572d7e` (folded into GREEN)

**2. [Rule 2 - Ruff config] Added per-file ignores for summary Hebrew prompt files**
- **Found during:** GREEN — ruff flagged RUF001 (Hebrew geresh in few-shot) and E501 on the prompt string
- **Fix:** Added `"src/receptra/summary/prompts.py" = ["E501", "RUF001", "RUF002", "RUF003"]` and `"tests/summary/test_summary_router.py" = ["S101", "RUF001"]` to `pyproject.toml` per-file-ignores — same precedent as `llm/prompts.py` (Plan 03-02).
- **Files modified:** `backend/pyproject.toml`
- **Commit:** `f572d7e`

## Known Stubs

None — `generateSummary` calls the real `/api/summary` endpoint. `SummaryPanel` renders real data from the API response.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: dos | `backend/src/receptra/summary/router.py` | `transcript_lines` capped at 500 items by Pydantic `max_length` on the list field; individual line length is not bounded (a single 1MB line would pass validation). The 12,000-char truncation in `build_summary_messages` caps the actual LLM input, so the effective attack surface is limited. |

## TDD Gate Compliance

- RED gate: commit `7f33fe0` — `test(F3-summary):` prefix, 4 failing tests
- GREEN gate: commit `f572d7e` — `feat(F3-summary):` prefix, 4 passing tests

## Self-Check: PASSED
