---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-04-24T07:53:33.324Z"
progress:
  total_phases: 7
  completed_phases: 0
  total_plans: 6
  completed_plans: 5
  percent: 83
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

Phase: 01-foundation — EXECUTING
Plan: 01-05 complete; next is 01-06 (CI — last plan, depends on 01-04 + 01-05)

- **Phase:** 01-foundation
- **Plan:** 01-05 complete (Makefile with Phase 1 targets + scripts/download_models.sh with hf CLI dispatcher + scripts/ollama/DictaLM3.Modelfile template + scripts/check_licenses.sh allowlist gate + docs/models.md; FND-03 satisfied; OPEN-1 host-Ollama `make up` + OPEN-2 Q4_K_M default locked)
- **Status:** Executing Phase 01-foundation (Wave 1 complete; Plans 01-02, 01-03, 01-04, 01-05 complete; Plan 01-06 CI is the last plan)
- **Progress:** [████████░░] 83%

```
[████████░░] 83% — Phase 1 of 7 (5/6 plans)
```

## Performance Metrics

| Phase | Plan | Duration | Tasks | Files | Completed |
|-------|------|----------|-------|-------|-----------|
| 01-foundation | 01-01 | 3min | 3 | 10 | 2026-04-23 |
| 01-foundation | 01-02 | ~9min | 3 | 11 | 2026-04-23 |
| 01-foundation | 01-03 | ~20min | 2 | 16 | 2026-04-24 |
| 01-foundation | 01-04 | ~15min | 3 | 6 | 2026-04-24 |
| 01-foundation | 01-05 | ~8min | 2 | 5 | 2026-04-24 |

- Phases completed: 0/7
- Plans completed: 5
- v1 requirements delivered: 5/42 (FND-01, FND-02, FND-03, FND-04, FND-05 all complete; FND-06 lands in Plan 01-06)

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
- **Last action:** Completed Plan 01-05 (Makefile + model download orchestration). 5 files committed across 2 atomic commits (dc26343 Makefile; 50cefeb scripts/download_models.sh + scripts/ollama/DictaLM3.Modelfile + scripts/check_licenses.sh + docs/models.md). FND-03 now complete. All 12 `make -n <target>` dry-runs pass; `bash -n` syntax checks pass; download script dispatches to usage on bare invocation (Rule 1 bug-fix applied). Actual ~11 GB downloads deferred to Mac-local contributor smoke per autonomous-mode instruction.
- **Next action:** `/gsd-execute-phase 1` continues with Plan 01-06 (CI — last plan; depends on 01-04 + 01-05). Phase 1 closes after 01-06.
- **Last updated:** 2026-04-24

**Planned Phase:** 1 (Foundation) — 6 plans — 2026-04-23T19:12:18.810Z
**Plan 01-01 complete:** 2026-04-23T22:05:13Z — commits 1ba63fc, 3351d81, 7d45601
**Plan 01-02 complete:** 2026-04-23 — commits 530b3bc, 8578d8e, 3bc6df2
**Plan 01-03 complete:** 2026-04-24 — commits 64bcf99, 77b0d8f
**Plan 01-04 complete:** 2026-04-24 — commits 3ab2138, 3e5af29, 11c06bc
**Plan 01-05 complete:** 2026-04-24 — commits dc26343, 50cefeb
