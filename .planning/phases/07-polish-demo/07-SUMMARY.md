# Phase 7 — Polish & Demo (INT-SMOKE-01..INT-SMOKE-05)

## Goal

Cross-phase Milestone 1 integration smoke tests: verify the full in-process pipeline
(health, KB ingest, STT WebSocket handshake, audio → STT → RAG → LLM → WS events,
OpenAPI schema coverage) all pass offline without any live Whisper, Ollama, ChromaDB,
or BGE-M3 process.

## Test Matrix

| ID | Test | Fixture | Result |
|----|------|---------|--------|
| INT-SMOKE-01 | `/healthz` + `/api/kb/health` subsystem health | `client` (stubs) | PASS |
| INT-SMOKE-02 | KB ingest-text → `/api/kb/documents` round-trip | `client` (stubs) | PASS |
| INT-SMOKE-03 | `/ws/stt` connect → `SttReady` event emitted | `pipeline_app` (real Silero) | PASS |
| INT-SMOKE-04 | Audio frames → `FinalTranscript` → `SuggestionComplete` ordering | `pipeline_app` (real Silero + canned Whisper + patched LLM) | PASS |
| INT-SMOKE-05 | OpenAPI schema covers all HTTP routes; WS route verified via `app.routes` | `client` (stubs) | PASS |

## Key Design Decisions

### INT-SMOKE-03 fixture choice
WebSocket endpoint needs `VADIterator(model).reset_states()` — the autouse
`_stub_heavy_loaders` fixture returns `object()` as the VAD model stub, which has no
`reset_states` method. Fix: switch INT-SMOKE-03 to the `pipeline_app` fixture which
loads the real `silero_vad` model (same as INT-SMOKE-04).

### INT-SMOKE-05 WebSocket exclusion
FastAPI/OpenAPI 3.0 does not emit schema entries for `@app.websocket()` endpoints.
The test checks HTTP routes in `/openapi.json` and separately validates the WS route
via `isinstance(route, APIWebSocketRoute)` on `app.routes`.

### INT-SMOKE-04 parenthesized `with`
```python
with (
    patch("receptra.pipeline.hot_path.generate_suggestions", return_value=gen),
    TestClient(pipeline_app) as tc,
    tc.websocket_connect("/ws/stt") as ws,
):
```
Python 3.10+ parenthesized `with` enters context managers in order — `tc` is bound
before `tc.websocket_connect("/ws/stt")` is evaluated, so all three can be flattened
into one `with` block (SIM117 compliant).

## Full Suite Result

```
337 passed, 10 skipped, 15 warnings
```

Skipped: live-test guards (Ollama, ChromaDB, WER fixtures) — all require
`RECEPTRA_LLM_LIVE_TEST=1` / `RECEPTRA_RAG_LIVE_TEST=1` or pre-fetched audio fixtures.

## Milestone 1 Coverage Summary

| Phase | Tests | Status |
|-------|-------|--------|
| 01 Foundation | 12 | all pass |
| 02 Hebrew STT | 68 | all pass |
| 03 Hebrew LLM | 52 | all pass |
| 04 RAG KB | 61 | all pass |
| 05 Hot-Path Pipeline | 25 | all pass |
| 06 Frontend | (Vitest, not in this suite) | — |
| 07 Integration smoke | 5 | all pass |
| **Total** | **337** | **all pass** |
