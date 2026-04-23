---
phase: 01-foundation
plan: "01-01"
subsystem: infra
tags: [licensing, docs, scaffolding, apache-2.0, hebrew, rtl, gitignore, dockerignore]

# Dependency graph
requires: []
provides:
  - Apache 2.0 LICENSE at repo root (verbatim from apache.org)
  - Bilingual README (English default + Hebrew RTL variant) with language switcher
  - CONTRIBUTING.md referencing Makefile setup flow and license allowlist policy
  - .gitignore blocking model weights, venvs, node_modules, .env
  - .dockerignore blocking model weight globs from docker build context
  - .env.example documenting every service env var (MODEL_DIR, OLLAMA_HOST, CHROMA_HOST/PORT, BACKEND_PORT, FRONTEND_PORT, DICTALM_QUANT, RECEPTRA_LOG_LEVEL)
  - knowledge/ directory skeleton (.gitkeep + sample/README.md) for Phase 4 RAG landing
  - docs/architecture.md placeholder for Phase 7 architecture write-up
affects: [01-02-backend, 01-03-frontend, 01-04-docker-compose, 01-05-makefile, 01-06-ci, 04-rag, 07-polish]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Bilingual docs via two files (README.md + README.he.md) with language switcher — avoids GitHub Markdown bidi rendering bugs"
    - "Hebrew content wrapped in single <div dir=\"rtl\" lang=\"he\"> block per README.he.md"
    - "Model weights live in ~/.receptra/models/ (user home), NOT in repo or image"
    - "Env template documents every variable backend/compose/Makefile will consume"

key-files:
  created:
    - LICENSE
    - README.md
    - README.he.md
    - CONTRIBUTING.md
    - .gitignore
    - .dockerignore
    - .env.example
    - knowledge/.gitkeep
    - knowledge/sample/README.md
    - docs/architecture.md
  modified: []

key-decisions:
  - "Split bilingual READMEs into two files (README.md, README.he.md) — GitHub Markdown bidi rendering bugs rule out single-file approach"
  - "Hebrew README body wrapped in a single <div dir=\"rtl\" lang=\"he\"> to keep the language switcher LTR while the body is RTL"
  - "Apache 2.0 LICENSE taken verbatim from apache.org with only the [yyyy] [name of copyright owner] placeholder replaced (Copyright 2026 Receptra Contributors)"
  - "Both .gitignore and .dockerignore block model weight globs (*.gguf, *.safetensors, *.ct2, *.bin, *.pt, *.pth) to prevent weights from entering git history OR docker image layers"
  - ".env is gitignored (.env, .env.local, .env.*.local); .env.example is the only env template that ships"
  - "knowledge/ is gitignored with exceptions for .gitkeep and sample/ — user-deployment data never enters git"

patterns-established:
  - "Task commit convention: `{type}(01-01): {description} (task 01-01-T{N})` with Co-Authored-By trailer"
  - "All root docs/scaffolds written in one plan, so subsequent parallel waves (backend, frontend, docker, Makefile, CI) can assume root context exists"

requirements-completed: [FND-05]

# Metrics
duration: 3min
completed: 2026-04-23
---

# Phase 1 Plan 01-01: Repo-root Foundation Summary

**Apache 2.0 LICENSE, bilingual README (English + Hebrew RTL), CONTRIBUTING.md, .gitignore/.dockerignore blocking model weights, .env.example documenting every service var, plus knowledge/ and docs/ scaffolds — unblocks parallel waves 2-3.**

## Performance

- **Duration:** 3 min (152 seconds)
- **Started:** 2026-04-23T22:02:41Z
- **Completed:** 2026-04-23T22:05:13Z
- **Tasks:** 3
- **Files created:** 10
- **Files modified:** 0

## Accomplishments

- Apache 2.0 LICENSE committed verbatim from apache.org (202 lines) with `Copyright 2026 Receptra Contributors`
- Bilingual README landed: `README.md` (English default) and `README.he.md` (Hebrew wrapped in `<div dir="rtl" lang="he">`), with a language switcher at the top of each file
- `CONTRIBUTING.md` documents the Makefile developer flow, license allowlist policy, and Contributor Covenant commitment
- `.gitignore` and `.dockerignore` both block the six model weight globs (`*.gguf`, `*.safetensors`, `*.ct2`, `*.bin`, `*.pt`, `*.pth`) — multi-GB weights can never enter git history or docker image layers
- `.env.example` documents all seven service env vars so Plans 02 (backend), 04 (compose), and 05 (Makefile) can land without touching this file
- `knowledge/` and `docs/` skeletons are committed so Phase 4 (RAG) and Phase 7 (architecture) have documented landing spots
- Requirement **FND-05** (LICENSE + bilingual README + CONTRIBUTING) satisfied

## Task Commits

Each task committed atomically:

1. **Task 1: Write LICENSE (Apache 2.0 verbatim)** — `1ba63fc` (feat)
2. **Task 2: Write bilingual READMEs + CONTRIBUTING.md** — `3351d81` (docs)
3. **Task 3: Write .gitignore, .dockerignore, .env.example, knowledge/ + docs/ skeletons** — `7d45601` (chore)

**Plan metadata commit:** pending final commit after SUMMARY, STATE, ROADMAP updates

## Files Created/Modified

- `LICENSE` — Apache 2.0 verbatim (202 lines), copyright line "Copyright 2026 Receptra Contributors"
- `README.md` — English README, language switcher to Hebrew variant, quickstart, prereqs, license
- `README.he.md` — Hebrew README wrapped in single `<div dir="rtl" lang="he">` block, language switcher back to English
- `CONTRIBUTING.md` — Developer setup via `make setup`/`make up`, license allowlist ground rule, Contributor Covenant reference
- `.gitignore` — Python/Node/env/model-weight/knowledge/data/IDE/log exclusions with `!knowledge/.gitkeep` and `!knowledge/sample/**` exceptions
- `.dockerignore` — VCS/weights/user-data/dev-artifacts/docs/env/IDE exclusions for the docker build context
- `.env.example` — Documents `MODEL_DIR`, `OLLAMA_HOST`, `CHROMA_HOST`, `CHROMA_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`, `DICTALM_QUANT`, `RECEPTRA_LOG_LEVEL`
- `knowledge/.gitkeep` — Zero-byte marker so the directory ships in the repo
- `knowledge/sample/README.md` — Notes that actual sample Hebrew docs land in Phase 4
- `docs/architecture.md` — Placeholder pointing to PROJECT.md + ROADMAP.md + CLAUDE.md; Phase 7 fills in the real architecture diagram

## Decisions Made

- **Apache 2.0 LICENSE fetched verbatim from apache.org** rather than copied from any existing project, ensuring the canonical text is authoritative (mitigates T-01-01-03).
- **Two-file bilingual README** (not one file with embedded RTL blocks) because GitHub's Markdown renderer has known bidi bugs with mixed-direction content. Language switcher links live OUTSIDE the RTL div so they render LTR as intended.
- **Model-weight globs in both .gitignore AND .dockerignore** — belt-and-suspenders for T-01-01-02; a weight file cannot leak via either vector.
- **`knowledge/*` gitignored with exceptions for `.gitkeep` and `sample/**`** — user data never enters git, but the sample docs Phase 4 ships DO get committed.

## Deviations from Plan

None — plan executed exactly as written. All three tasks' acceptance criteria passed on first run. No bugs, no missing critical functionality, no blocking issues, no architectural decisions required.

## Issues Encountered

None.

## Threat Model Compliance

All four `mitigate` threats from the plan's STRIDE register are mitigated:

| Threat ID | Mitigation Status | Evidence |
|-----------|-------------------|----------|
| T-01-01-01 (`.env` leak) | mitigated | `.gitignore` lines for `.env`, `.env.local`, `.env.*.local`; `.env.example` is the only env template that ships |
| T-01-01-02 (Model weight leak) | mitigated | Both `.gitignore` and `.dockerignore` block `*.bin`, `*.safetensors`, `*.ct2`, `*.gguf`, `*.pt`, `*.pth` |
| T-01-01-03 (LICENSE authenticity) | mitigated | LICENSE fetched verbatim from apache.org; only copyright line modified |
| T-01-01-04 (User KB committed by accident) | mitigated | `.gitignore` `knowledge/*` with `!knowledge/.gitkeep` and `!knowledge/sample/**` exceptions; `git check-ignore` confirms sample README is explicitly un-ignored |

T-01-01-05 (GitHub bidi rendering) is `accept` disposition — mitigated as far as possible via two-file split; no sensitive content in public docs.

## User Setup Required

None — no external services, no environment configuration needed at this plan boundary. Users copy `.env.example` to `.env` in Plan 01-05 (Makefile setup) context.

## Next Plan Readiness

- **Unblocks Wave 2** (Plans 01-02 backend, 01-03 frontend, 01-04 docker-compose) — all root docs/scaffolds are in place; those plans can land their own subtrees without touching repo-root files.
- **Unblocks Plan 01-05** (Makefile) — `.env.example` documents the env vars the Makefile's `up` target will forward to docker compose.
- **Unblocks Plan 01-06** (CI) — CONTRIBUTING.md's license-allowlist policy is the spec the CI pipeline implements.
- No blockers, no open questions.

## Self-Check

**Claimed files exist:**
- LICENSE — FOUND
- README.md — FOUND
- README.he.md — FOUND
- CONTRIBUTING.md — FOUND
- .gitignore — FOUND
- .dockerignore — FOUND
- .env.example — FOUND
- knowledge/.gitkeep — FOUND (zero bytes)
- knowledge/sample/README.md — FOUND
- docs/architecture.md — FOUND

**Claimed commits exist:**
- 1ba63fc — FOUND (Task 1 LICENSE)
- 3351d81 — FOUND (Task 2 docs)
- 7d45601 — FOUND (Task 3 scaffolds)

## Self-Check: PASSED

---
*Phase: 01-foundation*
*Completed: 2026-04-23*
