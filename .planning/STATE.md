---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: completed
last_updated: "2026-04-25T19:08:58.238Z"
progress:
  total_phases: 7
  completed_phases: 1
  total_plans: 12
  completed_plans: 9
  percent: 75
---

# Receptra — STATE.md

*Project memory. Updated at phase transitions and plan boundaries.*

## Project Reference

- **Name:** Receptra
- **Core Value:** A human agent taking a Hebrew call on a Mac gets useful, grounded suggestions in under two seconds — running entirely on their own machine with no cloud dependency.
- **Milestone:** M1 — Hebrew Co-pilot MVP
- **Exit Criterion:** Live Hebrew demo end-to-end on reference Apple Silicon (M2 16GB or M2 Pro 32GB), fully offline.
- **Granularity:** standard
- **Mode:** yolo
- **Model Profile:** quality

## Current Position

Phase: 02-hebrew-streaming-stt — EXECUTING. Plans 02-01, 02-02, and 02-03 complete.

- **Phase:** 02-hebrew-streaming-stt (3/6 plans complete)
- **Plan:** 02-03 complete (per-connection StreamingVad wrapper around silero_vad.VADIterator; accepts an already-loaded model singleton via constructor + threshold/min_silence_ms/speech_pad_ms args; feed(1024-byte int16 LE frame) returns VadEvent {kind: 'start'|'end', t_ms: int} or None; reset_states() called in __init__ AND public reset() — Pitfall #2 belt-and-braces guard against cross-connection state leak, regression-tested by test_two_instances_have_independent_state; InvalidFrameError raised before numpy allocation when frame size != 1024 bytes — T-02-03-01 mitigation; little-endian explicitly pinned via dtype='<i2'; FRAME_BYTES=1024, FRAME_SAMPLES=512, SAMPLE_RATE_HZ=16000 module-level constants exported for Plan 02-04 wire-protocol reuse; 7 vad tests + 19/19 backend suite green; ruff + mypy strict clean; STT-02 satisfied)
- **Status:** Plans 02-01 + 02-02 + 02-03 COMPLETE. Next plan 02-04 (/ws/stt WebSocket endpoint that consumes app.state.whisper + app.state.vad_model + transcribe_hebrew() + StreamingVad). Phase 2 requires Plan 02-06 to re-run the latency spike on reference M2 hardware before phase exit.
- **Progress:** [████████░░] 75%

```
[████████░░] 75% — 9/12 plans (Phase 1: 6/6 complete; Phase 2: 3/6 complete)
```

## Performance Metrics

| Phase | Plan | Duration | Tasks | Files | Completed |
|-------|------|----------|-------|-------|-----------|
| 01-foundation | 01-01 | 3min | 3 | 10 | 2026-04-23 |
| 01-foundation | 01-02 | ~9min | 3 | 11 | 2026-04-23 |
| 01-foundation | 01-03 | ~20min | 2 | 16 | 2026-04-24 |
| 01-foundation | 01-04 | ~15min | 3 | 6 | 2026-04-24 |
| 01-foundation | 01-05 | ~8min | 2 | 5 | 2026-04-24 |
| 01-foundation | 01-06 | ~2min | 2 | 3 | 2026-04-24 |
| 02-hebrew-streaming-stt | 02-01 | ~8min | 2 | 5 | 2026-04-24 |
| 02-hebrew-streaming-stt | 02-02 | ~12min | 2 | 13 | 2026-04-25 |
| 02-hebrew-streaming-stt | 02-03 | ~4min | 1 | 3 | 2026-04-25 |

- Phases completed: 1/7 (Phase 1 Foundation complete; Phase 2 STT in progress)
- Plans completed: 9 (Phase 1: 6/6; Phase 2: 3/6)
- v1 requirements delivered: 8/42 (Phase 1 FND-* complete + STT-01 from Plan 02-02 + STT-02 from Plan 02-03; remaining Phase 2 requirements land at plan boundaries 02-04..02-06)

## Accumulated Context

### Decisions (locked)

- Co-pilot first (no TTS, no telephony in v1)
- Hebrew-first (ivrit.ai + DictaLM 3.0 primary, Qwen 2.5 7B fallback)
- Apple Silicon M2+ as reference floor
- OSS self-host (Apache 2.0), Docker Compose one-liner
- STT: faster-whisper + ivrit-ai/whisper-large-v3-turbo-ct2 + Silero VAD
- LLM runtime: Ollama with Metal
- Embeddings: BGE-M3 via Ollama; Vector DB: ChromaDB
- Frontend: React + Vite + TypeScript + Tailwind (RTL)
- Parallelizable: Phases 2, 3, 4 after Phase 1
- Backend dependency manager: uv (0.11.7+) with pyproject.toml + uv.lock (Plan 01-02)
- Backend build backend: hatchling (PEP-621) with src-layout wheel (Plan 01-02)
- Backend config pattern: pydantic-settings Settings with RECEPTRA_ env prefix, extra="ignore", .env-file support (Plan 01-02)
- Backend lint+type gates: strict mypy (src + tests) + ruff E/F/I/N/UP/B/C4/SIM/RUF; enforced in CI (Plan 01-02 → Plan 01-06)
- Frontend stack: React 19 + Vite 6 + TypeScript 5.6 + Tailwind v4 (`@tailwindcss/vite` plugin, no tailwind.config.js) — Plan 01-03
- Frontend RTL: `<html dir="rtl" lang="he">` on root + defense-in-depth attrs on `<main>` in App.tsx; Phase 6 layers on `hebrew-tailwind-preset` — Plan 01-03
- Frontend dev proxy: Vite forwards `/api/*` (HTTP) and `/ws/*` (WebSocket, `ws: true`) to `localhost:8080`; `host: '0.0.0.0'` + `strictPort: true` for Docker exposure — Plan 01-03
- Frontend lint+format gates: ESLint 9 flat config + Prettier 3 (singleQuote for JS/TS, double-quote CSS override); consumed by Plan 01-06 CI — Plan 01-03
- Frontend scripts contract pinned: dev / build / preview / lint / typecheck / format / format:check — Plan 01-06 CI calls these names (Plan 01-03)
- Ollama runs HOST-native, NOT in docker-compose — OPEN-1 locked. Backend reaches it via `host.docker.internal:11434` with `extra_hosts: host-gateway` for Linux parity (Plan 01-04)
- Docker Compose stack = chromadb + backend + frontend with healthcheck-gated chain (`depends_on.condition: service_healthy`); `docker compose config -q` is the CI static gate (Plan 01-04)
- Container images: non-root `receptra` user (uid 1001) in both backend (python:3.12-slim multi-stage + uv) and frontend (node:22-slim, Vite dev server in Phase 1; nginx static serve deferred to Phase 7) — Plan 01-04
- Model weights mounted read-only (`${MODEL_DIR:-~/.receptra/models}:/models:ro`) into backend container — never baked into images (Plan 01-04)
- `chromadb/chroma:1.5.8` image pinned; healthcheck on `/api/v2/heartbeat`, volume at `/data` (Plan 01-04)
- OPEN-2 LOCKED: default DictaLM quant is Q4_K_M (16GB M2 reference hardware); Q5_K_M override via `DICTALM_QUANT` env var for 32GB+ Macs (Plan 01-05)
- OPEN-1 ENFORCED in Makefile: `make up` pgrep-gates `ollama serve` on host (via `nohup` + /tmp log), then `docker compose up -d`. Ollama never enters compose (Plans 01-04 + 01-05)
- Model downloads are separate from `docker compose up`: `make models` delegates to `scripts/download_models.sh` using hf CLI + ollama pull, resumable, ~11 GB total (FND-03, Plan 01-05)
- DictaLM Ollama registration uses a Modelfile TEMPLATE with `__GGUF_PATH__` sed-substitution at ollama-create time — checked-in template is repo-portable, absolute paths resolved per contributor (Plan 01-05)
- License allowlists single-source-of-truth in `scripts/check_licenses.sh`: verbatim research §5.4 (pip-licenses, both SPDX + long-form names) + §5.5 (license-checker, SPDX). `make licenses` + Plan 01-06 CI both invoke this script (Plan 01-05)
- OPEN-6 LOCKED: CI runner = ubuntu-latest only in Phase 1. Mac-native `docker compose up` / Metal / arm64 wheel smoke deferred to Phase 7 (Plan 01-06)
- OPEN-8 LOCKED: license-gate negative test = manual workflow_dispatch only (`.github/workflows/license-gate-test.yml`). Installs GPLv3 `gnureadline` into scratch venv + asserts pip-licenses allowlist rejects it. Not on every push (slows CI, pollutes caches) (Plan 01-06)
- OPEN-1 ENFORCEMENT moved from docs + Makefile into CI: compose job grep-fails on `^\s*ollama:` in docker-compose.yml (Plan 01-06 — mitigates T-01-06-04 silent regression)
- CI topology locked: 4 parallel jobs on ubuntu-latest (backend, frontend, compose, licenses) gating every push + pull_request; concurrency.cancel-in-progress for superseded runs; actions pinned at @v4 (Plan 01-06)
- Plan 02-01: Phase 2 runtime deps pinned in backend/pyproject.toml — faster-whisper 1.2.1 (MIT), silero-vad 6.2.1 (MIT), numpy 2.0+ (compound permissive), loguru 0.7.3 (MIT). Dev deps: jiwer 4.0 (Apache-2.0), soundfile 0.13 (BSD). Transitive: ctranslate2 4.7.1, torch 2.11.0, onnxruntime 1.25.0, tokenizers 0.22.2, av 17.0.1. All permissive; license gate passes (Plan 02-01)
- Plan 02-01: STT contract partial_interval_decision=700 ms (provisional) — scripts/spike_stt_latency.py embeds decision rule; .planning/phases/02-hebrew-streaming-stt/02-01-SPIKE-RESULTS.md is the durable contract Plans 02-02..02-06 consume; Plan 02-06 re-runs on reference M2 hardware before Phase 2 exits to replace provisional value with measurement (Plan 02-01, OPEN-2 resolved for STT)
- Plan 02-01: scripts/check_licenses.sh PY_ALLOW extended with 5 pip-licenses 5+ verbatim strings (all pre-existing transitive deps): `Apache-2.0 OR BSD-2-Clause` (packaging), `3-Clause BSD License` (protobuf), `ISC License (ISCL)` (shellingham), `MPL-2.0 AND MIT` (tqdm), `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` (numpy). JS side: `--excludePackages receptra-frontend@0.1.0` excludes private workspace self-reference (Plan 02-01, OPEN-4 resolved)
- Plan 02-01: Whisper pinned kwargs are the single-source contract surface — WhisperModel(device=cpu, compute_type=int8, cpu_threads=4, num_workers=1) + transcribe(language=he, task=transcribe, beam_size=1, best_of=1, temperature=0.0, condition_on_previous_text=False, vad_filter=False, without_timestamps=True). Spelled out inline in scripts/spike_stt_latency.py; downstream plans reuse these values verbatim (Plan 02-01)
- Plan 02-01: Spike-with-fallback pattern — when model weights absent, spike script exits 1 AND writes UNMEASURED placeholder with provisional default; downstream plans never blocked by missing-model executor (Plan 02-01)
- Plan 02-02: FastAPI lifespan = asynccontextmanager that loads WhisperModel + Silero VAD singletons onto app.state and runs warmup transcribe BEFORE yield. `@app.on_event` fully removed from main.py (Pitfall #1 mitigated; greptest in test_lifespan.py guards against regression). Pitfall #7 mitigated via warmup transcribe through the same `transcribe_hebrew()` wrapper the hot path uses (Plan 02-02)
- Plan 02-02: `receptra.stt.engine.transcribe_hebrew(model, audio_f32) -> (text, info_dict)` is the single source of truth for RESEARCH §7 Hebrew transcribe kwargs. Threat T-02-02-01 (kwargs drift) mitigated via 5 unit tests pinning every locked kwarg by name+value. Float32-only dtype gate raises TypeError before model invocation (Pitfall #4 defense) (Plan 02-02)
- Plan 02-02: Loguru is now the single backend logging sink with serialize=True JSON output — replaces stdlib logging.basicConfig in main.py. Establishes the audit-log JSON event shape Phase 5 INT-05 will consume; structured events emitted via `logger.bind(event="stt.lifespan").info({...})` (Plan 02-02)
- Plan 02-02: Settings extended with 8 STT-related fields (whisper_model_subdir, whisper_compute_type=int8, whisper_cpu_threads=4, audit_db_path, stt_partial_interval_ms=700 honoring 02-01-SPIKE-RESULTS.md provisional lock, vad_threshold=0.5, vad_min_silence_ms=300, vad_speech_pad_ms=200) — all documented in .env.example (Plan 02-02)
- Plan 02-02: Test-time stub-before-import pattern — `backend/tests/conftest.py` autouse `_stub_heavy_loaders` monkeypatches WhisperModel + load_silero_vad before any app import; STT-specific tests opt into a richer stub fixture (`stubbed_app` in test_lifespan.py) when introspection is needed. Keeps CI offline + fast and works with TestClient lifespan startup (Plan 02-02)
- Plan 02-02: mypy strict override `ignore_missing_imports=true` for `faster_whisper` + `silero_vad` modules (no py.typed markers upstream); the wrapper boundary uses `Protocol` to keep our public surface narrowly typed (Plan 02-02)
- Plan 02-03: `receptra.stt.vad.StreamingVad(model, threshold, min_silence_ms, speech_pad_ms)` is the per-connection VAD wrapper. Each WebSocket handler in Plan 02-04 constructs its OWN StreamingVad wrapping the shared `app.state.vad_model` singleton; the underlying `silero_vad.VADIterator` carries per-session state and `reset_states()` is called in BOTH `__init__` AND the public `reset()` method (Pitfall #2 belt-and-braces; regression-tested by `test_two_instances_have_independent_state`) (Plan 02-03)
- Plan 02-03: Wire-format constants `FRAME_BYTES=1024`, `FRAME_SAMPLES=512`, `SAMPLE_RATE_HZ=16000` exported from `receptra.stt.vad` as module-level symbols. Plan 02-04 imports them so the WebSocket binary-frame size guard and the VAD wrapper share a single source of truth. Little-endian explicitly pinned via `dtype="<i2"` (NOT `np.int16`, which would honor native byte order) — Pitfall #4 partial defense; full byte-order validation is at the WebSocket protocol layer in Plan 02-04 (Plan 02-03)
- Plan 02-03: `InvalidFrameError(ValueError)` raised by `StreamingVad.feed()` BEFORE any numpy allocation when frame length != 1024 bytes. Plan 02-04 converts this to `{"type":"error","code":"protocol_error"}` envelope and closes the WebSocket. Threat T-02-03-01 (DoS via malformed frame size) mitigated; ASVS V5 input validation (Plan 02-03)
- Plan 02-03: `StreamingVad` accepts an already-loaded model + segmentation params via constructor — does NOT import `receptra.config` and does NOT call `load_silero_vad`. Decouples module from Plan 02-02 lifespan, makes unit tests self-contained, matches the FastAPI canonical app.state dependency-injection pattern. Plan 02-04 wires settings at the WebSocket entry point (Plan 02-03)
- Plan 02-03: `VadEvent` TypedDict normalizes `silero_vad.VADIterator`'s `{"start": seconds_float}` / `{"end": seconds_float}` raw output into `{"kind": "start"|"end", "t_ms": int}` for downstream consumers. Plan 02-06 uses `t_ms` timestamps as the headline latency metric (speech-start to first-partial-transcript) (Plan 02-03)
- Plan 02-03: Test signal upgraded from pure-tone to FM-modulated harmonic stack with 5 Hz AM envelope and 0.15-amplitude broadband noise — pure 1 kHz sinusoids register as silence to Silero v5 (peak prob ~0.2); the formant-FM synthesizer reliably crosses 0.9. Noise component seeded by phase (deterministic function of frame index, NOT a stateful module RNG) so test ordering is irrelevant (Plan 02-03)

### Open Todos

- Execute Phase 1 research spike questions (see `research/STACK.md` §"Open questions")

### Blockers

(none)

### Skills in play (`skills-il`)

- `hebrew-nlp-toolkit` → Phase 4 (RAG chunking)
- `hebrew-document-generator` → Phase 4 (seed KB)
- `hebrew-tailwind-preset`, `hebrew-rtl-best-practices`, `hebrew-i18n`, `israeli-accessibility-compliance` → Phase 6
- `hebrew-content-writer`, `israeli-accessibility-compliance` → Phase 7

## Session Continuity

- **Last agent:** executor
- **Last action:** Completed Plan 02-03 (Phase 2 Hebrew Streaming STT — per-connection Silero VAD streaming wrapper). 3 files created across 2 atomic TDD commits (b1633cf test RED / 801d658 feat GREEN). All 6 plan-verification gates passed: ruff clean, mypy strict clean (16 src files), 19/19 pytest green (5 engine + 4 lifespan + 7 vad + 3 healthz), `dtype="<i2"` little-endian pin present, `reset_states` called in 2 places (constructor + reset()), `FRAME_BYTES = 1024` constant exported. Two Rule-1 deviations in test helpers (both isolated to test_vad_streaming.py): (1) test signal synthesizer upgraded from plan-suggested 1 kHz pure tone to FM-modulated harmonic stack with AM envelope + broadband noise — pure tone gave Silero peak prob ~0.2 (silence-class); speechy synthesizer drives prob >0.9 reliably; (2) made noise generation stateless (seeded by phase, not by drained module RNG) so multi-test runs are deterministic. STT-02 satisfied. StreamingVad + InvalidFrameError + VadEvent + FRAME_BYTES/FRAME_SAMPLES/SAMPLE_RATE_HZ constants published as contracts for Plan 02-04.
- **Next action:** Proceed to Plan 02-04 (/ws/stt WebSocket endpoint that consumes app.state.whisper + app.state.vad_model via StreamingVad + transcribe_hebrew(); converts InvalidFrameError to protocol_error envelope; emits partial/final transcripts on speech-end events).
- **Last updated:** 2026-04-25

**Planned Phase:** 1 (Foundation) — 6 plans — 2026-04-23T19:12:18.810Z
**Plan 01-01 complete:** 2026-04-23T22:05:13Z — commits 1ba63fc, 3351d81, 7d45601
**Plan 01-02 complete:** 2026-04-23 — commits 530b3bc, 8578d8e, 3bc6df2
**Plan 01-03 complete:** 2026-04-24 — commits 64bcf99, 77b0d8f
**Plan 01-04 complete:** 2026-04-24 — commits 3ab2138, 3e5af29, 11c06bc
**Plan 01-05 complete:** 2026-04-24 — commits dc26343, 50cefeb
**Plan 01-06 complete:** 2026-04-24 — commits c44fc4d, 7a6b828
**Phase 1 Foundation COMPLETE:** 2026-04-24 — 6/6 plans, 6/6 FND-* requirements
**Plan 02-01 complete:** 2026-04-24 — commits 3928bdd, 6411ab5
**Plan 02-02 complete:** 2026-04-25 — commits 9584947, d95f693, c7f79c2, 2dde0a9 (TDD RED+GREEN x 2 tasks; STT-01 satisfied)
**Plan 02-03 complete:** 2026-04-25 — commits b1633cf, 801d658 (TDD RED+GREEN x 1 task; STT-02 satisfied — per-connection StreamingVad wrapper)
