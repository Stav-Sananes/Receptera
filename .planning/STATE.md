---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-04-24T07:58:31Z"
progress:
  total_phases: 7
  completed_phases: 1
  total_plans: 6
  completed_plans: 6
  percent: 100
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

Phase: 01-foundation — COMPLETE. Ready for Phase 2/3/4 (parallelizable).

- **Phase:** 01-foundation (complete — all 6 plans merged, all 6 FND-* requirements satisfied)
- **Plan:** 01-06 complete (.github/workflows/ci.yml with 4 parallel jobs + .github/workflows/license-gate-test.yml manual-dispatch regression canary + docs/ci.md; FND-06 satisfied; OPEN-6 ubuntu-latest + OPEN-8 manual-dispatch regression test locked; OPEN-1 Ollama-on-host enforced as grep guard in compose CI job)
- **Status:** Phase 01-foundation COMPLETE. Phase 1 exit criteria met: contributor can clone + `make setup` + `make models` + `make up` + see healthy stack; CI enforces lint + type + license gates on every push/PR; regression canary proves gate works.
- **Progress:** [██████████] 100% (Phase 1 / 7)

```
[██████████] 100% — Phase 1 of 7 (6/6 plans) — PHASE 1 COMPLETE
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

- Phases completed: 1/7 (Phase 1 Foundation complete)
- Plans completed: 6
- v1 requirements delivered: 6/42 (all Phase 1 FND-* complete: FND-01, FND-02, FND-03, FND-04, FND-05, FND-06)

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
- **Last action:** Completed Plan 01-06 (CI pipeline — closes Phase 1). 3 files committed across 2 atomic commits (c44fc4d .github/workflows/ci.yml with 4 parallel jobs + OPEN-1 regression guard; 7a6b828 .github/workflows/license-gate-test.yml manual-dispatch regression canary + docs/ci.md). FND-06 now complete. All 37 acceptance criteria passed on first verification; both workflow YAMLs parse via `yaml.safe_load`; no Rule 1/2/3 deviations needed. Phase 1 Foundation is now COMPLETE — all 6 FND-* requirements satisfied.
- **Next action:** Phase 1 done. Phases 2 (Hebrew Streaming STT), 3 (Hebrew Suggestion LLM), and 4 (Hebrew RAG KB) can now be planned + executed in parallel per the roadmap. Run `/gsd-transition 1 2` (or 3 or 4) to start the next phase.
- **Last updated:** 2026-04-24

**Planned Phase:** 1 (Foundation) — 6 plans — 2026-04-23T19:12:18.810Z
**Plan 01-01 complete:** 2026-04-23T22:05:13Z — commits 1ba63fc, 3351d81, 7d45601
**Plan 01-02 complete:** 2026-04-23 — commits 530b3bc, 8578d8e, 3bc6df2
**Plan 01-03 complete:** 2026-04-24 — commits 64bcf99, 77b0d8f
**Plan 01-04 complete:** 2026-04-24 — commits 3ab2138, 3e5af29, 11c06bc
**Plan 01-05 complete:** 2026-04-24 — commits dc26343, 50cefeb
**Plan 01-06 complete:** 2026-04-24 — commits c44fc4d, 7a6b828
**Phase 1 Foundation COMPLETE:** 2026-04-24 — 6/6 plans, 6/6 FND-* requirements
