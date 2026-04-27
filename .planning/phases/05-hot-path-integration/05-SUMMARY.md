# Phase 5 Summary — Hot-Path Integration

**Status:** Complete  
**Commit:** GREEN `5400d34`

## What shipped

### receptra.pipeline package (new)

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 1 | Package marker |
| `events.py` | 74 | WS event types for suggestion stream |
| `hot_path.py` | 213 | `make_suggest_fn` factory + `SuggestFn` type |
| `audit.py` | 80 | `pipeline_runs` SQLite table (INT-05) |

### Pipeline event types (`receptra.pipeline.events`)

| Type | `type` field | Purpose |
|------|-------------|---------|
| `SuggestionToken` | `suggestion_token` | One LLM token delta |
| `SuggestionComplete` | `suggestion_complete` | All suggestions + latency breakdown |
| `SuggestionError` | `suggestion_error` | RAG / LLM / pipeline error |

`SuggestionComplete` carries INT-03 latency fields:
- `rag_latency_ms`: embed + ChromaDB query time
- `e2e_latency_ms`: monotonic ms from `t_speech_end_ms` to event sent

### `make_suggest_fn` (INT-01 + INT-02)

- Per-connection closure; `SuggestFn = Callable[[str, int, str], Awaitable[None]]`
- Args: `(transcript, t_speech_end_ms, utterance_id)`
- Retrieves top-K chunks via `retrieve()`, streams `generate_suggestions()`, forwards events to WS

### INT-04 Graceful Degradation

| Condition | Behaviour |
|-----------|-----------|
| `embedder is None` | Skip RAG → `chunks=[]` → canonical refusal |
| `collection is None` | Same |
| `retrieve()` raises | `SuggestionError(code="rag_unavailable")` + `chunks=[]` → refusal |
| `generate_suggestions` LLM error | `SuggestionError(code=event.code)` |
| Client disconnects mid-stream | `send_json` swallowed with `contextlib.suppress` |
| Any crash in `_suggest` | Logged; `stt/pipeline.py` outer try/except prevents loop crash |

### INT-05 Unified Audit Log

`pipeline_runs` table in `data/audit.sqlite` (same file as `stt_utterances`):

```sql
CREATE TABLE IF NOT EXISTS pipeline_runs (
    utterance_id   TEXT PRIMARY KEY,
    ts_utc         TEXT NOT NULL,
    stt_latency_ms INTEGER NOT NULL,
    rag_latency_ms INTEGER,       -- NULL if RAG skipped
    llm_ttft_ms    INTEGER,       -- NULL if error before first token
    llm_total_ms   INTEGER,       -- NULL if LLM error
    n_chunks       INTEGER NOT NULL DEFAULT 0,
    n_suggestions  INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL,
    e2e_latency_ms INTEGER        -- NULL on error
);
```

Status values: `ok` | `rag_degraded` | `llm_error` | `no_context` | `pipeline_error`

### `stt/pipeline.py` changes

- `run_utterance_loop` gains `suggest: SuggestFn | None = None` keyword param
- `websocket_stt_endpoint` builds suggest callback from `app.state.embedder` + `app.state.chroma_collection`
- `suggest(text, t_speech_end_ms, utterance_id)` awaited inline after `FinalTranscript`

## Test coverage (22 new tests)

| File | Tests | Gates |
|------|-------|-------|
| `test_events.py` | 7 | discriminator, validation, TypeAdapter union |
| `test_hot_path.py` | 7 | happy path, null degradation, rag error, llm error, latency |
| `test_audit.py` | 5 | table creation, roundtrip, null fields, no-init guard |
| `test_ws_suggest.py` | 3 | WS end-to-end (real Silero + mock LLM), latency fields, null embedder |

Full suite: **332 pass / 10 skip**

## INT-03 Latency Baseline

**UNMEASURED** — requires real bge-m3 + Ollama + ChromaDB on Apple Silicon M2.

Target: `e2e_latency_ms < 2000` on M2 16GB (speech-end → suggestion-complete).

First live run: `make up && RECEPTRA_RAG_LIVE_TEST=1 python scripts/eval_rag.py --full --backend-url http://localhost:8080`; observe `e2e_latency_ms` in `suggestion_complete` events via browser DevTools or `wscat`.

## Cross-Phase Handoff

**Phase 6 FE-01..FE-04:** Browser sidebar consumes:
- `suggestion_token` → typewriter rendering
- `suggestion_complete` → structured suggestion cards with citation chips
- `suggestion_error` → warning badge / retry indicator
- `final` → transcript display

**Phase 6 FE-06:** `POST /api/kb/upload` + `GET /api/kb/documents` + `GET /api/kb/health` already mounted (Phase 4).

**Phase 7 DEMO-01:** `pipeline_runs` table feeds the latency dashboard; `e2e_latency_ms` p95 is the primary SLA metric.
