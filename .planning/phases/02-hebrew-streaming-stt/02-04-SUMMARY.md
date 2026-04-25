---
phase: "02-hebrew-streaming-stt"
plan: "02-04"
subsystem: stt
tags: [stt, websocket, partial, final, pydantic, asyncio-to-thread, pipecat-deferred]
requires:
  - "Plan 02-02: app.state.whisper singleton + receptra.stt.engine.transcribe_hebrew(model, audio_f32) -> (text, info_dict) wrapper with research-locked Hebrew kwargs"
  - "Plan 02-02: app.state.vad_model singleton (raw Silero TorchScript model)"
  - "Plan 02-02: Settings fields stt_partial_interval_ms, vad_threshold, vad_min_silence_ms, vad_speech_pad_ms"
  - "Plan 02-03: receptra.stt.vad.StreamingVad per-connection wrapper + InvalidFrameError + FRAME_BYTES/FRAME_SAMPLES/SAMPLE_RATE_HZ wire-format constants"
provides:
  - "backend/src/receptra/stt/events.py — pydantic v2 BaseModel discriminated union (SttReady, PartialTranscript, FinalTranscript, SttError) with frozen=True; SttEvent TypeAdapter alias"
  - "backend/src/receptra/stt/pipeline.py — websocket_stt_endpoint(ws) FastAPI handler + run_utterance_loop(ws, vad, transcribe) testable inner loop"
  - "backend/src/receptra/main.py — @app.websocket('/ws/stt') route mounted, delegates to pipeline.websocket_stt_endpoint"
  - "Wire contract: 1024-byte int16 LE binary frames in / JSON text frames out per pydantic schema; pinned by 6 events_schema tests + 2 handshake tests + 3 roundtrip tests"
affects:
  - "Plan 02-05 (WER batch eval): can optionally drive /ws/stt to verify the live path produces the same Hebrew transcripts the offline path produces; SttEvent discriminator dispatches FinalTranscript for batch consumption"
  - "Plan 02-06 (latency instrumentation + audit log): wraps run_utterance_loop with metrics middleware — the function takes (ws, vad, transcribe) so an instrumented transcribe callable can record per-call latency + write audit-log rows without touching the FastAPI route decorator"
  - "Phase 6 frontend: consumes the JSON event stream — typed schema means TypeScript can mirror the discriminated union; partial vs final events drive different UI render paths"
tech-stack:
  added:
    - "pydantic v2 discriminated union (Annotated + Field(discriminator='type')) — single source of truth for outbound wire schema"
    - "asyncio.to_thread wrap around faster-whisper's synchronous C++ transcribe (Pitfall #5 fix); enables parallel transcribes across concurrent WS connections"
    - "FastAPI @app.websocket route with WebSocketDisconnect + Exception ladder for graceful protocol_error / model_error handling"
  patterns:
    - "Per-connection state isolation (Pitfall #2): a fresh StreamingVad is constructed inside websocket_stt_endpoint wrapping the SHARED app.state.vad_model singleton; vad.reset() is called in finally for defense-in-depth"
    - "Two-layer transcribe wrap: the outer transcribe closure handles asyncio.to_thread; the inner run_utterance_loop is wrap-agnostic (sync stub, real to_thread, or Plan 02-06 metrics decorator all work)"
    - "Audio-time partial cadence (Rule 1 deviation from RESEARCH §7 wall-clock pseudocode): partials gate on accumulated audio ms since last partial, not wall ms — equivalent in real-time streaming, deterministic in tests, semantically more correct"
    - "Pydantic-only outbound serialisation: every send_json goes through .model_dump() of a typed model; no ad-hoc dict json.dumps — regression-tested by test_discriminator_dispatches"
    - "WebSocket close code 1007 (RFC 6455 Invalid Frame Payload Data) for protocol_error path — semantically correct over generic 1000"
    - "Module-level TypeAdapter caching in tests (TypeAdapter is expensive to construct; lifting it to module scope cuts collection time + sidesteps mypy var-annotation noise)"
key-files:
  created:
    - "backend/src/receptra/stt/events.py"
    - "backend/src/receptra/stt/pipeline.py"
    - "backend/tests/stt/test_events_schema.py"
    - "backend/tests/stt/test_ws_handshake.py"
    - "backend/tests/stt/test_ws_pcm_roundtrip.py"
    - ".planning/phases/02-hebrew-streaming-stt/02-04-SUMMARY.md"
  modified:
    - "backend/src/receptra/main.py — added @app.websocket('/ws/stt') route + WebSocket import"
key-decisions:
  - "Audio-time partial cadence over wall-clock cadence (deviation from RESEARCH §7 pseudocode): the plan's elapsed_since_partial >= stt_partial_interval_ms gate fires correctly in real-time streaming but never in tests where TestClient bursts frames at processing speed. Audio-time gating is also semantically more correct (we want one partial per N ms of speech, not per N ms of wall clock); in real-time streaming the two are equivalent modulo tiny jitter. Documented inline in run_utterance_loop with a multi-line rationale comment."
  - "run_utterance_loop is split out from websocket_stt_endpoint as the wrappable unit. Plan 02-06's metrics middleware will pass an instrumented transcribe callable that records per-call latency + writes a SQLite audit row, without touching the FastAPI route decorator. The route stays a thin shim in main.py."
  - "vad.reset() is called in the finally block even though StreamingVad is local to the handler frame (per-connection construction makes reset technically redundant). The explicit call documents the per-connection isolation contract and protects against future refactors that hoist the wrapper to a longer-lived scope."
  - "WebSocket close code 1007 (Invalid Frame Payload Data, RFC 6455 §7.4.1) for the protocol_error path — semantically correct over a generic 1000 close. The frontend can switch on the code to distinguish 'bad client' from 'normal disconnect'."
  - "Frozen pydantic models (model_config = ConfigDict(frozen=True)) on every event type — defense against in-process .type mutation. test_frozen_type_discriminator pins the contract so a future contributor cannot relax it without a CI failure."
  - "SttError code is a 3-value Literal allowlist (model_error / vad_error / protocol_error) — RESEARCH §8 locks the codes. Adding a 4th requires a plan amendment so downstream consumer switch statements stay total."
  - "Test fixtures for handshake + roundtrip override the autouse conftest stubs to load the REAL Silero VAD (small TorchScript, ~30 MB) but keep WhisperModel stubbed with canned ' שלום' segments. The real-VAD path is necessary because StreamingVad constructs a VADIterator that calls model.reset_states() — the autouse object() sentinel does not satisfy that interface. Stubbed Whisper avoids loading 1.5 GB of weights into the test runner."
  - "test_no_event_loop_blocking is the Pitfall #5 regression guard: two concurrent WS connections with a 200 ms sleep-per-transcribe stub run in roughly parallel wall time. If a future contributor drops the asyncio.to_thread wrap, the second connection's accept() stalls behind the first's transcribe and total wall time doubles → test fails."
metrics:
  duration: "~10 min"
  tasks_completed: "2/2"
  files_created: 6
  files_modified: 1
  tests_added: 11
  completed: "2026-04-25"
threat_flags: []
---

# Phase 2 Plan 02-04: WebSocket /ws/stt with VAD-Gated Transcribe Loop Summary

The user-visible output of Phase 2: a FastAPI WebSocket at `/ws/stt` that accepts binary 1024-byte int16 LE PCM frames, runs them through the per-connection Silero VAD wrapper (Plan 02-03), drives the VAD-gated incremental re-transcribe loop (RESEARCH §7), and emits typed pydantic events (`ready`, `partial`, `final`, `error`) as JSON text frames. STT-03 + STT-04 satisfied; the published contract feeds Plan 02-05 (WER batch optionally hits the WS), Plan 02-06 (latency instrumentation wraps the inner loop), and Phase 6 frontend (the sidebar React component consumes the same JSON stream).

## STT-03 Satisfied

> **STT-03:** Backend exposes a WebSocket endpoint that accepts binary PCM frames and emits partial Hebrew transcripts within ~1s of speech onset.

How:
- `@app.websocket("/ws/stt")` mounted in `backend/src/receptra/main.py` delegates to `receptra.stt.pipeline.websocket_stt_endpoint`.
- Inbound: client sends 1024-byte binary frames (int16 LE, 16 kHz mono, 32 ms each — same wire contract Plan 02-03 pins via `FRAME_BYTES`).
- Outbound: server emits an `SttReady` event on accept, then `PartialTranscript` events on the `stt_partial_interval_ms` cadence (700 ms provisional from 02-01-SPIKE-RESULTS.md) once at least 500 ms of audio has accumulated since speech-start, then exactly one `FinalTranscript` on VAD end.
- `test_partial_emitted` drives a synthesized 3-second voiced burst followed by silence and asserts at least one partial arrives before the final.

## STT-04 Satisfied

> **STT-04:** Final-utterance transcript events are emitted when VAD detects end-of-speech.

How:
- The VAD-end branch of `run_utterance_loop` runs `transcribe_hebrew` on the complete utterance buffer (concatenated float32 frames captured between speech-start and speech-end), constructs a `FinalTranscript(text, t_speech_start_ms, t_speech_end_ms, stt_latency_ms, duration_ms)`, and emits it via `ws.send_json(model.model_dump())`.
- `test_final_emitted` asserts the final event has non-empty Hebrew text (the canned stub returns `" שלום"` which `transcribe_hebrew` strips to `"שלום"`), `t_speech_start_ms < t_speech_end_ms`, `stt_latency_ms >= 0`, `duration_ms > 0`.
- `stt_latency_ms` is computed as `t_final_ready_ms - t_speech_end_ms` — the headline metric Plan 02-06 will track for STT-06.

## Published Contract for Downstream Plans

### For Plan 02-05 (WER Batch Eval)

The discriminated-union event schema is the parsing contract:

```python
from pydantic import TypeAdapter
from receptra.stt.events import SttEvent, FinalTranscript

adapter = TypeAdapter(SttEvent)
for raw in ws_events:
    parsed = adapter.validate_python(raw)
    if isinstance(parsed, FinalTranscript):
        wer = compute_wer(parsed.text, ground_truth)
```

Plan 02-05 may choose to batch via `transcribe_hebrew` directly (no WS round-trip) for speed; the WS path stays available for end-to-end smoke testing.

### For Plan 02-06 (Latency Instrumentation + Audit Log)

`run_utterance_loop(ws, vad, transcribe)` is the wrappable unit. Metrics + audit instrumentation goes around the `transcribe` callable:

```python
async def instrumented_transcribe(audio):
    t0 = time.monotonic()
    text, info = await asyncio.to_thread(transcribe_hebrew, whisper, audio)
    audit_db.insert_utterance(text, info, latency_ms=int((time.monotonic()-t0)*1000))
    return text

await run_utterance_loop(ws, vad, instrumented_transcribe)
```

This is why the loop function takes `transcribe` as a callable parameter rather than calling `asyncio.to_thread(transcribe_hebrew, ...)` inline — the route decorator stays untouched while Plan 02-06 swaps in an instrumented variant.

### For Phase 6 Frontend

The TypeScript discriminated union mirrors the pydantic schema:

```ts
type SttEvent =
  | { type: 'ready'; model: string; sample_rate: 16000; frame_bytes: 1024 }
  | { type: 'partial'; text: string; t_speech_start_ms: number; t_emit_ms: number }
  | { type: 'final'; text: string; t_speech_start_ms: number; t_speech_end_ms: number; stt_latency_ms: number; duration_ms: number }
  | { type: 'error'; code: 'model_error' | 'vad_error' | 'protocol_error'; message: string };
```

Pydantic's `frozen=True` on every model means the wire format cannot drift mid-utterance.

## Architecture: Where the Loop Lives

```
main.py
  @app.websocket("/ws/stt")
  └── websocket_stt_endpoint(ws)
        ├── ws.accept()
        ├── ws.send_json(SttReady(model=...).model_dump())
        ├── construct StreamingVad(app.state.vad_model, threshold, ...)
        ├── define transcribe(audio):
        │     return await asyncio.to_thread(transcribe_hebrew, app.state.whisper, audio)
        └── try:
              run_utterance_loop(ws, vad, transcribe)   ◄── Plan 02-06 wrap point
            except WebSocketDisconnect: log clean disconnect
            except Exception: send SttError(model_error), log
            finally:
              vad.reset()
              ws.close()
```

`run_utterance_loop` is the testable + wrappable unit:

- Accepts a `vad: StreamingVad` (per-connection)
- Accepts a `transcribe: Callable[[NDArray[np.float32]], Awaitable[str]]` (the threadpool/instrumentation strategy is hidden behind this callable)
- Knows nothing about FastAPI app state, lifespan, or settings beyond `settings.stt_partial_interval_ms`

## Concurrency: asyncio.to_thread (Pitfall #5)

`faster_whisper.WhisperModel.transcribe` is synchronous C++ via CTranslate2. Calling it directly inside an `async def` route handler freezes the event loop for the entire transcribe duration → other clients starve, the same client's audio receive stalls → VAD drops events.

Mitigation:
- The per-connection `transcribe` closure inside `websocket_stt_endpoint` wraps `transcribe_hebrew` in `await asyncio.to_thread(...)`.
- `run_utterance_loop` only awaits the closure, never calls Whisper directly — so the threadpool strategy is a single-point-of-truth at the call site.

Regression guard: `test_no_event_loop_blocking` opens two concurrent WS connections (driven from two threads, since TestClient is sync), each with a 200 ms sleep-per-transcribe stub. With `asyncio.to_thread`, both transcribes run on separate threadpool workers in parallel — total wall time stays close to a single connection's. Without the wrap, the second connection would stall behind the first and total wall time would double.

## Per-Connection State Isolation (Pitfall #2)

A fresh `StreamingVad` is constructed inside `websocket_stt_endpoint` wrapping the SHARED `app.state.vad_model` singleton. The underlying `VADIterator` carries per-session segmentation state — sharing it across connections would corrupt boundary detection (one user's "end-of-speech" leaking into another user's stream).

Defense-in-depth: `vad.reset()` is called in the `finally` block on connection close, even though the wrapper goes out of scope at function exit. The explicit call documents the per-connection isolation contract and protects against future refactors that might hoist the wrapper to a longer-lived scope.

Plan 02-03's `test_two_instances_have_independent_state` already pins this — each StreamingVad owns its own VADIterator.

## Wire-Protocol Validation (T-02-04-01, T-02-04-04)

| Layer | Check | Failure path |
|-------|-------|--------------|
| Starlette | `websocket_max_size=65536` (default) | Frame >64KB → connection killed |
| `vad.feed()` | `len(frame_bytes) == FRAME_BYTES (1024)` | `InvalidFrameError` raised before numpy alloc |
| `pipeline.run_utterance_loop` | `except InvalidFrameError` | `SttError(code='protocol_error', message=...)` + `ws.close(code=1007)` |
| `pipeline.websocket_stt_endpoint` | `except WebSocketDisconnect` | Clean log line, no traceback |
| `pipeline.websocket_stt_endpoint` | `except Exception` (last resort) | `SttError(code='model_error', message=...)` + log w/ stack |

Pydantic schema validation acts as a second gate on outbound — every event leaves via `.model_dump()` of a frozen typed model; no ad-hoc dict serialisation. `test_discriminator_dispatches` regression-guards this.

## Tests Added (11 total — full backend suite now 30/30 green)

### `tests/stt/test_events_schema.py` (6 tests, Task 1)

| # | Test | What it pins |
|---|------|-------------|
| 1 | `test_ready_roundtrip` | `SttReady` JSON-dump emits `"type":"ready"`; parses back via `TypeAdapter(SttEvent)` to `SttReady` instance |
| 2 | `test_partial_roundtrip` | Hebrew UTF-8 text round-trips byte-exact through pydantic; no normalization |
| 3 | `test_final_roundtrip` | All 4 timing fields preserved (`t_speech_start_ms`, `t_speech_end_ms`, `stt_latency_ms`, `duration_ms`) |
| 4 | `test_error_roundtrip` | 3 allowed codes accepted; bogus code raises `ValidationError` at construction |
| 5 | `test_discriminator_dispatches` | `{"type":"final",...}` raw dict hydrates to `FinalTranscript`, not `PartialTranscript` or plain dict |
| 6 | `test_frozen_type_discriminator` | `frozen=True` forbids `.type` mutation post-construction |

### `tests/stt/test_ws_handshake.py` (2 tests, Task 2)

| # | Test | What it pins |
|---|------|-------------|
| 1 | `test_upgrade_succeeds_and_ready_sent` | `/ws/stt` WS upgrade emits `SttReady` with `sample_rate=16000`, `frame_bytes=1024`, non-empty model name |
| 2 | `test_invalid_frame_size_returns_protocol_error` | 100-byte frame → `SttError(code='protocol_error')` envelope before clean close (T-02-04-01) |

### `tests/stt/test_ws_pcm_roundtrip.py` (3 tests, Task 2)

| # | Test | What it pins |
|---|------|-------------|
| 1 | `test_partial_emitted` | ≥1 partial event arrives before final during sustained 3-second voiced burst (STT-03) |
| 2 | `test_final_emitted` | Exactly one final event with non-empty Hebrew text + valid timing fields (STT-04) |
| 3 | `test_no_event_loop_blocking` | Two concurrent WS with 200 ms sleep stub run in parallel wall time (Pitfall #5 regression guard) |

## Verification Gates (all PASS)

| Gate | Command | Result |
|------|---------|--------|
| 1 | `uv run ruff check src tests` | clean |
| 2 | `uv run mypy src tests` (strict) | 21 src files, 0 errors |
| 3 | `uv run pytest tests/ -v` | 30/30 green |
| 4 | `grep -q '@app.websocket("/ws/stt")' main.py` | PASS |
| 5 | `grep -q "asyncio.to_thread" pipeline.py` | PASS |
| 6 | `grep -q "time.time()" pipeline.py` | NOT present (monotonic only) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Replaced wall-clock partial cadence with audio-time cadence**

- **Found during:** Task 2, GREEN gate — `test_partial_emitted` failed with `partial_events == 0` despite a 3-second voiced burst producing a 3296 ms duration_ms in the final event.
- **Issue:** RESEARCH §7's pseudocode (and the plan's task description) gates partials on `(now_ms - t_last_partial_ms) >= stt_partial_interval_ms` — wall-clock time. TestClient drives all 95 voiced frames synchronously at processing speed (sub-ms per frame), so wall elapsed never crosses 700 ms during the burst. The test would also fail for any non-real-time client (e.g., a frontend buffering then bursting).
- **Fix:** Changed the gate to `(audio_ms - audio_ms_at_last_partial) >= stt_partial_interval_ms` — accumulated audio time since last partial. In real-time streaming, audio time and wall time are equivalent (1 s wall ≈ 1 s audio buffered), so production behaviour is unchanged. In tests + non-real-time clients, audio-time gating fires deterministically. Audio-time gating is also semantically more correct: the user-facing contract is "one partial per N ms of speech," not "one per N ms of wall clock."
- **Files modified:** `backend/src/receptra/stt/pipeline.py` (run_utterance_loop body + multi-line rationale comment)
- **Commit:** 591f0c3

**2. [Rule 3 - Blocking] Test fixtures override autouse conftest VAD stub with REAL Silero**

- **Found during:** Task 2, RED→GREEN transition — the autouse `_stub_heavy_loaders` from `tests/conftest.py` replaces `load_silero_vad` with a function returning `object()`. When `StreamingVad.__init__` constructs `VADIterator(model, ...)`, silero internally calls `model.reset_states()` → `AttributeError: 'object' object has no attribute 'reset_states'`.
- **Issue:** The autouse stub is correct for `test_healthz` (no VAD interaction) and `test_lifespan` (asserts loader was called, doesn't exercise VAD). But our handshake + roundtrip tests construct `StreamingVad` for real → need a usable model.
- **Fix:** Added a `real_vad_app` fixture (handshake) and `real_vad_canned_whisper_app` / `real_vad_slow_whisper_app` fixtures (roundtrip) that monkeypatch `lifespan_mod.load_silero_vad` back to the real loader BEFORE re-importing `receptra.main`. Keeps the autouse fast-path for unrelated tests; opts in to real VAD only where needed.
- **Files modified:** `backend/tests/stt/test_ws_handshake.py`, `backend/tests/stt/test_ws_pcm_roundtrip.py`
- **Commit:** 591f0c3

**3. [Rule 1 - Bug] mypy strict annotation cleanups in test_events_schema.py**

- **Found during:** Task 1, GREEN gate — initial test file used inline `TypeAdapter(SttEvent).validate_python(...)` and a `# type: ignore[misc]` for the frozen-mutation test. mypy strict reported 7 errors: var-annotated requirements on `parsed`, an "unused type-ignore" warning, and an assignment-to-Literal complaint.
- **Issue:** Pydantic v2's discriminated union has limited static-type inference; mypy needs help understanding the runtime narrowing.
- **Fix:** Lifted `_ADAPTER` to module scope with an explicit annotation (also avoids per-call TypeAdapter construction overhead). For the bogus-code test, routed through `Any = "bogus"` so the runtime ValidationError fires without fighting mypy. For the frozen-mutation test, `cast(Any, ready).type = "partial"` triggers pydantic's runtime guard while satisfying type checking.
- **Files modified:** `backend/tests/stt/test_events_schema.py`
- **Commit:** b99aa9b

### Authentication Gates

None — Plan 02-04 is local-loop only (no remote auth, no model registry pulls during execution; lifespan stub-loaders keep CI offline).

## Stub Watch (for Plan 02-05/02-06 Awareness)

The handshake + roundtrip tests use a stubbed `WhisperModel` returning `" שלום"` for all transcribes. This is fine for the wire-format and VAD-loop assertions but **does not** exercise the real ivrit-ai model. Plan 02-05 (WER batch) and Plan 02-06 (latency on reference hardware) are responsible for the real-model assertions; Plan 02-04 is intentionally model-agnostic above the `transcribe_hebrew` boundary.

## Why This Matters

Phase 2's exit criterion is a working live Hebrew co-pilot WS. After this plan:

- A WebSocket client (test, curl, frontend, anything) can connect to `/ws/stt`, send int16 LE PCM, and receive partial+final Hebrew transcripts.
- The contract is fully typed end-to-end (pydantic on backend, mirrors to TS in Phase 6).
- The hot path is non-blocking — multiple concurrent connections do not interfere.
- Plan 02-05 + 02-06 + Phase 6 all consume this published surface; their plans can proceed without further changes here.

## Self-Check: PASSED

- File `backend/src/receptra/stt/events.py` exists ✓
- File `backend/src/receptra/stt/pipeline.py` exists ✓
- File `backend/src/receptra/main.py` modified (route mounted) ✓
- File `backend/tests/stt/test_events_schema.py` exists ✓
- File `backend/tests/stt/test_ws_handshake.py` exists ✓
- File `backend/tests/stt/test_ws_pcm_roundtrip.py` exists ✓
- Commit bc968b1 (test RED) in git log ✓
- Commit b99aa9b (feat GREEN events) in git log ✓
- Commit 714703e (test RED ws) in git log ✓
- Commit 591f0c3 (feat GREEN pipeline + main route) in git log ✓
- Plan verification gates 1-6 all PASS ✓
- Backend test suite 30/30 green ✓
