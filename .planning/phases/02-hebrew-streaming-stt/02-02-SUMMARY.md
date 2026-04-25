---
phase: "02-hebrew-streaming-stt"
plan: "02-02"
subsystem: stt
tags: [stt, whisper, lifespan, fastapi, apple-silicon, faster-whisper, silero-vad, loguru, asynccontextmanager]
requires:
  - "Plan 02-01: faster-whisper 1.2.1, silero-vad 6.2.1, loguru 0.7.3, numpy 2.0+ pinned in backend/pyproject.toml + uv.lock"
  - "Plan 02-01: 02-01-SPIKE-RESULTS.md → partial_interval_decision = 700 (provisional, UNMEASURED path)"
  - "Plan 02-01: locked WhisperModel kwargs contract (device=cpu, compute_type=int8, cpu_threads=4, num_workers=1)"
  - "Plan 01-02: backend FastAPI scaffold with pydantic-settings Settings + RECEPTRA_ env prefix + /healthz route"
  - "Plan 01-02: pytest + ruff + strict mypy gates wired into backend/pyproject.toml"
provides:
  - "backend/src/receptra/lifespan.py — asynccontextmanager FastAPI lifespan that loads WhisperModel + Silero VAD onto app.state, runs warmup transcribe, and emits structured loguru events"
  - "app.state.whisper: WhisperModel — single STT singleton consumed by Plan 02-04 WebSocket handler"
  - "app.state.vad_model — raw Silero VAD model; Plan 02-03 wraps this per-connection in VADIterator"
  - "app.state.warmup_complete: bool — True after warmup transcribe completes (Pitfall #7 mitigated)"
  - "backend/src/receptra/stt/engine.py — transcribe_hebrew(model, audio_f32) → (text, info_dict) wrapper with every RESEARCH §7 kwarg pinned in one place; consumed by Plan 02-04 (live) and Plan 02-05 (batch WER)"
  - "backend/src/receptra/stt/__init__.py — re-exports transcribe_hebrew"
  - "backend/src/receptra/config.py — Settings extended with 8 STT-related fields (whisper_model_subdir, whisper_compute_type=int8, whisper_cpu_threads=4, audit_db_path, stt_partial_interval_ms=700, vad_threshold=0.5, vad_min_silence_ms=300, vad_speech_pad_ms=200)"
  - ".env.example — documents 8 new RECEPTRA_* env vars with RESEARCH section refs"
  - "backend/tests/conftest.py — autouse _stub_heavy_loaders fixture so TestClient lifespan never tries to load real CT2 weights during offline CI"
  - "Loguru as the single backend logging sink (serialize=True JSON output) — replaces stdlib logging.basicConfig"
affects:
  - "Plan 02-03 (Silero VAD per-connection wrapper): consumes app.state.vad_model singleton, builds per-connection VADIterator (Pitfall #2)"
  - "Plan 02-04 (/ws/stt WebSocket endpoint): consumes app.state.whisper + transcribe_hebrew() in the asyncio.to_thread hot-path call"
  - "Plan 02-05 (Hebrew WER eval harness): imports transcribe_hebrew() for batch eval over Common Voice fixtures (single source of truth for Hebrew kwargs)"
  - "Plan 02-06 (latency instrumentation + audit log): consumes settings.audit_db_path + the loguru serialize=True JSON event shape established here"
  - "All future STT call sites: transcribe_hebrew() is the only sanctioned entry into model.transcribe(...) — drift caught by tests/stt/test_engine.py"
tech-stack:
  added:
    - "FastAPI asynccontextmanager lifespan pattern (replaces deprecated @app.on_event)"
    - "Loguru with serialize=True JSON sink (RESEARCH §11 audit-log contract)"
  patterns:
    - "Singleton-load-at-startup: heavy ML models are loaded once inside the lifespan contextmanager and attached to app.state, not in request handlers (FastAPI canonical)"
    - "Single-source-of-truth wrapper for vendor SDK calls: receptra.stt.engine.transcribe_hebrew is the only sanctioned entry into faster_whisper.WhisperModel.transcribe(...). All future call sites MUST go through it; drift caught by 5 unit tests asserting every kwarg"
    - "Defense-in-depth dtype gate: transcribe_hebrew raises TypeError on non-float32 input BEFORE invoking the model — prevents Pitfall #4 (int16 LE byte-order bug)"
    - "Warmup-before-yield: lifespan runs a 1s silence transcribe through the same wrapper the live hot path uses, so the first WS request lands inside the latency budget (Pitfall #7)"
    - "Test-time monkeypatch of heavy loaders: backend/tests/conftest.py autouse _stub_heavy_loaders fixture replaces WhisperModel + load_silero_vad with trivial stubs before any app import, keeping CI offline + fast"
    - "Structured loguru events with bound event=... discriminator: every lifespan log line carries a stable event tag for downstream audit-log consumers (Phase 5 INT-05)"
    - "mypy override for upstream untyped libs: ignore_missing_imports for faster_whisper + silero_vad (no py.typed markers); the public surface we use is narrow and Protocol-typed at our wrapper boundary"
key-files:
  created:
    - "backend/src/receptra/lifespan.py"
    - "backend/src/receptra/stt/engine.py"
    - "backend/src/receptra/stt/__init__.py"
    - "backend/tests/stt/__init__.py"
    - "backend/tests/stt/conftest.py"
    - "backend/tests/stt/test_engine.py"
    - "backend/tests/stt/test_lifespan.py"
    - ".planning/phases/02-hebrew-streaming-stt/02-02-SUMMARY.md"
  modified:
    - "backend/src/receptra/main.py"
    - "backend/src/receptra/config.py"
    - "backend/tests/conftest.py"
    - "backend/pyproject.toml"
    - ".env.example"
key-decisions:
  - "FastAPI(lifespan=lifespan) replaces @app.on_event — Pitfall #1 mitigated (the two MUST NOT coexist or the on_event hook is silently dropped). test_no_on_event_decorators_remain greps main.py to guard against regression."
  - "settings.stt_partial_interval_ms default = 700 ms (honors 02-01-SPIKE-RESULTS.md provisional lock; UNMEASURED path)."
  - "Silero VAD loaded with onnx=False (TorchScript path) per RESEARCH §8 — sidesteps onnxruntime arm64 oddities (Pitfall #8). Plan 02-06 may revisit if onnx beats torch on M2 measurements."
  - "Loguru is the single logging sink; stdlib logging.basicConfig removed from main.py. JSON serialize=True format is the audit-log contract for Phase 5 INT-05."
  - "Warmup transcribe uses the SAME transcribe_hebrew() wrapper as the hot path — guarantees the warmup primes the exact code path live requests will hit (no kwarg drift between warmup and serve)."
  - "Threat T-02-02-01 mitigation: every faster_whisper.WhisperModel.transcribe(...) call site in this repo MUST go through transcribe_hebrew(). 5 unit tests pin the kwarg contract; future contributors who fork the call site pay the CI failure tax."
patterns-established:
  - "Lifespan loads + warms ML singletons; request handlers read from app.state"
  - "Vendor-SDK call wrappers pin kwargs in one module; tests assert every locked kwarg by name+value"
  - "Test-time stub-before-import for heavy loaders via autouse conftest fixture"
  - "Loguru serialize=True with logger.bind(event=...) for downstream audit-log consumption"
requirements-completed: [STT-01]

# Metrics
duration: ~12min
completed: 2026-04-25
---

# Phase 2 Plan 02-02: FastAPI Lifespan + Whisper/VAD Singletons Summary

**FastAPI lifespan loads ivrit-ai/whisper-large-v3-turbo-ct2 + Silero VAD once at startup with a warmup transcribe; transcribe_hebrew() is the single source of truth for every RESEARCH §7 Hebrew kwarg.**

## Performance

- **Duration:** ~12 min (across two sessions; Task 1 RED+GREEN committed in prior session, Task 2 RED committed in prior session, Task 2 GREEN + bug fix + summary in resume session)
- **Started:** 2026-04-24T12:02:44Z (prior session, first RED commit)
- **Completed:** 2026-04-25T21:55:00Z (resume session, GREEN + summary)
- **Tasks:** 2 (each task split TDD RED+GREEN)
- **Files modified:** 13 (8 created + 5 modified)

## Accomplishments

- WhisperModel singleton loads once at startup via `asynccontextmanager` lifespan and is exposed at `app.state.whisper`. Subsequent requests read it; no per-request CT2 cold-start cost.
- Silero VAD model singleton (TorchScript path, `onnx=False`) loaded once at startup, exposed at `app.state.vad_model` for Plan 02-03 to wrap per-connection.
- Warmup transcribe (1s silence) runs inside lifespan BEFORE `yield`, going through the exact `transcribe_hebrew()` wrapper the hot path will use — Pitfall #7 mitigated; first user request never pays JIT compile cost.
- `transcribe_hebrew(model, audio_f32) → (text, info_dict)` extracted to `backend/src/receptra/stt/engine.py` as the single sanctioned entry into `WhisperModel.transcribe(...)`. Every RESEARCH §7 kwarg (`language="he"`, `task="transcribe"`, `beam_size=1`, `best_of=1`, `temperature=0.0`, `condition_on_previous_text=False`, `vad_filter=False`, `without_timestamps=True`, `initial_prompt=None`) pinned in one place.
- Defense-in-depth dtype gate: `transcribe_hebrew` raises `TypeError` on non-float32 input BEFORE invoking the model — prevents Pitfall #4 (int16 LE bytes sneaking past the WS boundary).
- 8 new `Settings` fields wired with research-locked defaults (`whisper_model_subdir`, `whisper_compute_type`, `whisper_cpu_threads`, `audit_db_path`, `stt_partial_interval_ms`, `vad_threshold`, `vad_min_silence_ms`, `vad_speech_pad_ms`) and documented in `.env.example`.
- Loguru installed as the single backend logging sink with `serialize=True` JSON output — replaces `logging.basicConfig`. Establishes the audit-log event shape Phase 5 INT-05 will consume.
- Pitfall #1 guard: deprecated `@app.on_event("startup")` removed entirely; `test_no_on_event_decorators_remain` greps `main.py` to prevent regression.
- 9 new tests added, all green: 5 engine + 4 lifespan. Existing 3 healthz tests remain green (regression protected).

## Task Commits

Each TDD cycle was committed atomically:

1. **Task 1 RED — failing tests for transcribe_hebrew + new Settings fields** — `9584947` (test) — added 5 engine tests + tests/stt/conftest.py mock_whisper_model fixture; tests fail because target module doesn't exist yet.
2. **Task 1 GREEN — transcribe_hebrew wrapper + STT Settings fields** — `d95f693` (feat) — created stt/engine.py with locked-kwargs wrapper + dtype gate; extended Settings with 8 STT fields; added .env.example documentation; all 5 engine tests pass.
3. **Task 2 RED — failing tests for lifespan Whisper+VAD singleton + warmup** — `c7f79c2` (test) — added 4 lifespan tests including @app.on_event grep guard, app.state populated, and warmup call count assertion; tests fail because lifespan.py doesn't exist.
4. **Task 2 GREEN — lifespan + Whisper/VAD singletons + warmup** — `2dde0a9` (feat) — created lifespan.py, refactored main.py to FastAPI(lifespan=lifespan), extended tests/conftest.py with autouse stub fixture, added mypy override for faster_whisper + silero_vad. All 12 tests pass; ruff + mypy strict clean.

**Plan metadata commit:** to follow as a separate `docs(02-02): complete plan` commit covering this SUMMARY + STATE.md + ROADMAP.md + REQUIREMENTS.md.

## Files Created/Modified

### Created

- `backend/src/receptra/lifespan.py` — asynccontextmanager that loads WhisperModel + Silero VAD onto app.state, runs warmup transcribe through `transcribe_hebrew()`, configures loguru, and yields. Logs startup phases via `logger.bind(event="stt.lifespan").info(...)`.
- `backend/src/receptra/stt/engine.py` — `transcribe_hebrew(model, audio_f32) → (text, info_dict)` with every RESEARCH §7 kwarg locked + float32 dtype gate. Uses `Protocol` for the `model` type so mypy strict passes without importing the heavy `WhisperModel` at test-collection time.
- `backend/src/receptra/stt/__init__.py` — re-exports `transcribe_hebrew`.
- `backend/tests/stt/__init__.py` — empty package marker.
- `backend/tests/stt/conftest.py` — `mock_whisper_model` fixture returning two segments (`"שלום"`, `"עולם"`) + an info stub (`duration=2.0`, `language_probability=0.98`).
- `backend/tests/stt/test_engine.py` — 5 tests pinning the RESEARCH §7 kwargs contract + the float32 dtype gate.
- `backend/tests/stt/test_lifespan.py` — 4 tests for lifespan wiring: no-on_event grep, app has lifespan, app.state populated, warmup transcribe called exactly once with `language='he'`.

### Modified

- `backend/src/receptra/main.py` — FastAPI now constructed with `lifespan=lifespan`; old `_log_config` `@app.on_event` handler removed (folded into lifespan structured loguru emits).
- `backend/src/receptra/config.py` — 8 new STT-related Settings fields with research-locked defaults.
- `backend/tests/conftest.py` — autouse `_stub_heavy_loaders` fixture monkeypatches `WhisperModel` + `load_silero_vad` BEFORE any app import, plus `_WhisperStub.transcribe(*args, **kwargs)` accepts the engine wrapper's keyword-style `audio=...` invocation.
- `backend/pyproject.toml` — mypy override `ignore_missing_imports = true` for `faster_whisper` + `silero_vad` modules (no py.typed markers upstream).
- `.env.example` — added 8 `RECEPTRA_*` env var lines with RESEARCH section refs and the 02-01 provisional comment for `STT_PARTIAL_INTERVAL_MS`.

## Decisions Made

- **`stt_partial_interval_ms = 700` default** — honors 02-01-SPIKE-RESULTS.md provisional lock (UNMEASURED path; matches RESEARCH §7 Option A). Plan 02-06 will replace this with a measured value on reference M2 hardware before Phase 2 exits.
- **Loguru is the single sink** — stdlib `logging.basicConfig` removed from main.py. RESEARCH §11 mandated `serialize=True` JSON; this is now the audit-log contract Phase 5 INT-05 will consume.
- **Silero VAD with `onnx=False`** — TorchScript path on Apple Silicon is fine and sidesteps onnxruntime arm64 oddities (Pitfall #8). Plan 02-06 may revisit if onnx beats torch on M2 measurements.
- **`Protocol` for the engine wrapper's `model` type** — avoids importing heavy `WhisperModel` at test-collection time, keeps the wrapper trivially testable with `unittest.mock`.
- **Warmup uses `transcribe_hebrew()` itself, not a raw `model.transcribe(...)`** — guarantees the warmup primes the exact code path live requests will hit (zero kwarg drift between warmup and serve).
- **mypy ignore_missing_imports for `faster_whisper`/`silero_vad`** — both ship without py.typed markers; our public surface is narrow and Protocol-typed at the wrapper boundary anyway.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Fixed `_WhisperStub.transcribe` signature in tests/conftest.py**

- **Found during:** Task 2 GREEN verification (`uv run pytest tests/`).
- **Issue:** The autouse `_stub_heavy_loaders` fixture's `_WhisperStub.transcribe(self, _audio: Any, **_kwargs: Any)` declared `_audio` as a positional-only parameter, but `transcribe_hebrew()` invokes it with `audio=audio_f32` as a keyword (per the locked kwargs contract). Result: `TypeError: _WhisperStub.transcribe() missing 1 required positional argument: '_audio'` raised inside lifespan during `tests/test_healthz.py` collection — breaking the regression suite.
- **Fix:** Changed signature to `def transcribe(self, *_args: Any, **_kwargs: Any) -> tuple[Any, _InfoStub]:` so the stub accepts `audio` as either positional or keyword. The actual return shape (`iter([]), _InfoStub()`) is unchanged.
- **Files modified:** `backend/tests/conftest.py`.
- **Verification:** `uv run pytest tests/` → 12 passed (5 engine + 4 lifespan + 3 healthz). `uv run mypy src tests` → clean.
- **Committed in:** `2dde0a9` (Task 2 GREEN commit; the conftest fix was bundled because the fix and the lifespan implementation are the same atomic change — without it, lifespan startup explodes on every TestClient construction).

---

**Total deviations:** 1 auto-fixed (1 Rule-1 bug)
**Impact on plan:** The bug only affected the conftest stub's parameter name, not any runtime code path. No scope creep; no architectural changes; no kwargs added or removed from the locked transcribe contract.

## Issues Encountered

- Plan-verification gate `grep -c 'language="he"' backend/src/receptra/stt/engine.py → 1` actually emits 2 in the current file: line 8 is a docstring listing the locked kwargs contract for human readers, and line 73 is the actual `model.transcribe(...)` call site. There is still exactly one call site; the docstring reference is intentional and harmless. Documenting here for the verifier.

## User Setup Required

None — no external service configuration changed. The new `RECEPTRA_*` env vars all carry research-locked defaults; contributors who want non-defaults copy `.env.example → .env` per the existing Phase 1 flow.

## Next Phase Readiness

- **Plan 02-03 ready:** `app.state.vad_model` singleton is published; Plan 02-03 will construct per-connection `VADIterator` instances wrapping it (Pitfall #2 — VADIterator carries per-stream state, must NOT be shared).
- **Plan 02-04 ready:** `app.state.whisper` + `transcribe_hebrew(model, audio_f32)` are published; Plan 02-04 wraps the call in `asyncio.to_thread(transcribe_hebrew, app.state.whisper, audio)` for the WebSocket hot path (Pitfall #5 — sync model call must not block the event loop).
- **Plan 02-05 ready:** `transcribe_hebrew()` is the sanctioned wrapper for batch WER eval too; Plan 02-05's harness imports it directly so Hebrew kwargs cannot drift between live and batch paths.
- **No blockers** for Plans 02-03..02-06.

## TDD Gate Compliance

This plan followed the TDD gate sequence cleanly across both tasks:

- **Task 1 RED gate:** `9584947` — `test(02-02): add failing tests for transcribe_hebrew + new Settings fields`.
- **Task 1 GREEN gate:** `d95f693` — `feat(02-02): add transcribe_hebrew wrapper + STT Settings fields (STT-01 prep)`.
- **Task 2 RED gate:** `c7f79c2` — `test(02-02): add failing tests for lifespan Whisper+VAD singleton + warmup`.
- **Task 2 GREEN gate:** `2dde0a9` — `feat(02-02): wire FastAPI lifespan + Whisper/VAD singletons + warmup`.

REFACTOR was not needed (ruff + mypy strict were already green at GREEN time on both tasks).

## Self-Check: PASSED

Verified after writing this SUMMARY:

- `backend/src/receptra/lifespan.py` exists ✓
- `backend/src/receptra/stt/engine.py` exists ✓
- `backend/src/receptra/main.py` contains `lifespan=lifespan` ✓ and zero `@app.on_event` ✓
- Commit `9584947` exists in `git log --all` ✓
- Commit `d95f693` exists in `git log --all` ✓
- Commit `c7f79c2` exists in `git log --all` ✓
- Commit `2dde0a9` exists in `git log --all` ✓
- `uv run pytest tests/` → 12 passed ✓
- `uv run ruff check src tests` → clean ✓
- `uv run mypy src tests` → clean (14 source files) ✓

---
*Phase: 02-hebrew-streaming-stt*
*Completed: 2026-04-25*
