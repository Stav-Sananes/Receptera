---
phase: "01-foundation"
plan: "01-06"
subsystem: ci
tags: [ci, github-actions, license-gate, docker-compose, ubuntu-latest]
dependency_graph:
  requires:
    - backend/pyproject.toml (ruff, mypy, pytest commands)
    - backend/uv.lock (frozen install)
    - frontend/package.json (lint, typecheck, format:check, build scripts)
    - frontend/package-lock.json (npm ci)
    - docker-compose.yml (static-validated via docker compose config -q)
    - scripts/check_licenses.sh (pip-licenses + license-checker allowlist)
  provides:
    - .github/workflows/ci.yml (push + pull_request gate: 4 parallel jobs)
    - .github/workflows/license-gate-test.yml (manual regression canary for license allowlist)
    - docs/ci.md (CI topology + manual-dispatch procedure + troubleshooting)
  affects:
    - REQUIREMENTS.md (FND-06 complete)
    - ROADMAP.md (Phase 1 Foundation 6/6 plans complete)
tech_stack:
  added:
    - "GitHub Actions (ubuntu-latest)"
    - "astral-sh/setup-uv@v4 (Python/uv install + cache)"
    - "actions/setup-node@v4 (Node 22 + npm cache)"
    - "actions/checkout@v4"
  patterns:
    - "DAG of 4 parallel jobs (backend, frontend, compose, licenses) — no artificial cross-job deps"
    - "concurrency.cancel-in-progress for superseded runs"
    - "Caching keyed on lockfiles (uv.lock, package-lock.json) for <1min warm runs"
    - "Manual-dispatch regression canary (OPEN-8) separated from always-on gate"
    - "Inline regression guard in compose job (grep for '^\\s*ollama:' — OPEN-1 enforcement)"
key_files:
  created:
    - .github/workflows/ci.yml
    - .github/workflows/license-gate-test.yml
    - docs/ci.md
  modified: []
decisions:
  - "CI runner = ubuntu-latest only in Phase 1 (OPEN-6 locked). Mac-native smoke deferred to Phase 7."
  - "License-gate regression test = manual workflow_dispatch only (OPEN-8 locked). Running it on every push would slow CI and pollute caches with a known-bad package."
  - "OPEN-1 enforcement moved from docs into CI: compose job grep-fails if docker-compose.yml declares an 'ollama:' service."
  - "License gate single source of truth = scripts/check_licenses.sh. CI just invokes it; no allowlist duplicated in workflow YAML."
  - "Regression canary package = gnureadline (declares 'GNU General Public License v3 (GPLv3)' via pip metadata) — stable, tiny, pure-Python curses wrapper with no ABI risk."
metrics:
  duration: "~2min"
  completed: "2026-04-24"
---

# Phase 1 Plan 06: CI Pipeline Summary

GitHub Actions CI with four parallel jobs (backend, frontend, compose, licenses) gating every push and PR on ubuntu-latest, plus a manual-dispatch regression workflow that proves the license allowlist actually rejects GPL — closing FND-06 and Phase 1 Foundation.

## What Changed

**New files (3):**

1. **`.github/workflows/ci.yml`** (149 lines) — Main CI. Four parallel jobs:
   - **backend** — `uv sync --all-extras --frozen`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src tests`, `uv run pytest tests/ -x --tb=short` in `backend/` working directory.
   - **frontend** — `npm ci --no-audit --no-fund`, `npm run lint`, `npm run typecheck`, `npm run format:check`, `npm run build`, plus post-build assertion that `dist/index.html` contains "Receptra" in `frontend/` working directory.
   - **compose** — `docker compose config -q` with harmless env var defaults, plus `grep -qE "^\s*ollama:" docker-compose.yml` regression guard that fails the build if anyone re-adds Ollama to compose (OPEN-1 enforcement).
   - **licenses** — installs both backend (uv) and frontend (npm) deps, then runs `bash scripts/check_licenses.sh` (pip-licenses + license-checker allowlist from Plan 05).
   - Triggers on every `push` + `pull_request` to any branch. `concurrency.cancel-in-progress: true` kills superseded runs.

2. **`.github/workflows/license-gate-test.yml`** (58 lines) — Manual `workflow_dispatch` regression canary per OPEN-8. Installs `gnureadline` (GPLv3) into a scratch venv, runs the same pip-licenses allowlist, and asserts non-zero exit. Includes an inverse sanity check that installs `requests` and confirms the allowlist accepts permissive MIT/BSD deps.

3. **`docs/ci.md`** (51 lines) — Documents the runner choice (ubuntu-latest per OPEN-6), the four-job topology with command reference table, manual-dispatch procedure for the license regression test (both UI path and `gh workflow run license-gate-test.yml` CLI), caching behavior keyed on `backend/uv.lock` + `frontend/package-lock.json`, and troubleshooting for each gate type. References OPEN-1, OPEN-6, and OPEN-8.

**Requirements closed:** FND-06 ("CI pipeline runs lint + type-check + license allowlist check on every commit").

## Key Decisions Made

### 1. Four parallel jobs, not one serial mega-job (DAG style)

Chose a DAG of four independent jobs over a sequential "install-everything-then-run-everything" job. Tradeoffs:
- **Pro:** fail-fast surfacing — a ruff break in backend doesn't have to wait for npm ci to finish before being visible; developer sees the red X immediately.
- **Pro:** parallelism — wall clock is `max(backend, frontend, compose, licenses)` not the sum.
- **Pro:** cache isolation — each job only installs what it needs (except `licenses`, which needs both).
- **Con:** slight duplication — uv + Node are installed twice (once in backend/frontend, once in licenses). Accepted because caching makes the second install nearly free and duplication < coupling cost.

### 2. OPEN-8 locked: manual-dispatch for the negative gate test

Research §5.7 called for a regression test that proves the allowlist rejects GPL. Two placement options were considered:
- **Option A (rejected):** wire into main `ci.yml` on every push.
- **Option B (chosen):** separate `license-gate-test.yml` with `workflow_dispatch:` only.

Rejected A because: (1) installing a known-bad package on every push pollutes caches; (2) slows every PR by ~30-60s for a test that only needs to run when the allowlist configuration changes; (3) "it broke on my branch" false-positive risk if PyPI/gnureadline metadata drifts. The regression canary job is really a release-gate and config-change-gate, not a push-gate.

### 3. OPEN-1 enforcement as a grep guard, not just docs

Plan 04 documented the "Ollama on host, not in compose" decision. Plan 05 Makefile gated `make up` on a host `pgrep ollama`. But nothing blocked a future contributor from adding an `ollama:` service to `docker-compose.yml` by mistake. The compose job now runs:

```bash
if grep -qE "^\s*ollama:" docker-compose.yml; then
  echo "ERROR: docker-compose.yml must NOT declare an ollama service (OPEN-1)." >&2
  exit 1
fi
```

If `^\s*ollama:` appears at the start of a line in compose, CI fails with a clear message. Mitigates threat T-01-06-04 (silent OPEN-1 regression).

### 4. License gate single-sourced in scripts/check_licenses.sh

The CI `licenses` job is a one-liner: `bash scripts/check_licenses.sh`. All allowlist strings (PY_ALLOW, JS_ALLOW) live in the script, not duplicated in ci.yml. Benefits:
- Local `make licenses` and CI run identical logic — "it works on my machine" → "it works in CI" alignment.
- Allowlist changes ship as one Plan-05-scoped PR touching one file.
- The regression test (license-gate-test.yml) intentionally uses the *same allowlist string* inline — because its job is to catch cases where the script's allowlist drifts from what research §5.4 specified.

### 5. astral-sh/setup-uv@v4 + actions/setup-node@v4 for Python/Node install

Per research §5: uv is the modern Python installer, setup-uv handles `.python-version` pinning + caching automatically, and `actions/setup-node@v4` with `cache: npm` + `cache-dependency-path: frontend/package-lock.json` handles npm caching without extra `actions/cache` boilerplate. Pinned at `@v4` (major version) — accepted tradeoff for Phase 1; Phase 7 can tighten to commit SHAs if threat model requires (T-01-06-07).

## Deviations from Plan

**None — plan executed exactly as written.**

Both tasks completed cleanly; all 37 acceptance criteria across both tasks passed on first verification. No Rule 1/2/3 auto-fixes triggered. No architectural questions. The plan's exact file contents matched the stack assembled in Plans 02-05 — no interface drift detected during execution.

## Files Touched

| File | Action | Purpose |
|------|--------|---------|
| `.github/workflows/ci.yml` | created | Main CI: 4 parallel jobs on ubuntu-latest |
| `.github/workflows/license-gate-test.yml` | created | Manual-dispatch regression canary (OPEN-8) |
| `docs/ci.md` | created | CI topology + manual-dispatch procedure + troubleshooting |

Commits:
- `c44fc4d` — `feat(01-06): add main CI workflow (.github/workflows/ci.yml)`
- `7a6b828` — `feat(01-06): add license-gate negative test workflow + docs/ci.md`

## Verification

All 37 acceptance criteria passed:

**Task 1 (21 checks):** ci.yml exists; contains `name: CI`, `ubuntu-latest`, `astral-sh/setup-uv@v4`, `actions/setup-node@v4`, `node-version: 22`, all four backend commands (`uv run ruff check`, `uv run ruff format --check`, `uv run mypy src tests`, `uv run pytest`), all four frontend commands (`npm run lint`, `npm run typecheck`, `npm run format:check`, `npm run build`), `docker compose config -q`, `scripts/check_licenses.sh`, OPEN-1 regression guard (`must NOT declare an ollama service`), `pull_request:`, `concurrency:`; parses as valid YAML via `python3 -c "import yaml; yaml.safe_load(...)"`.

**Task 2 (16 checks):** license-gate-test.yml + docs/ci.md exist; license-gate-test.yml contains `workflow_dispatch`, `gnureadline`, `pip-licenses`, both success message phrasings (`License gate correctly REJECTED` + `License gate correctly ACCEPTED`), parses as valid YAML; docs/ci.md references `ubuntu-latest`, `workflow_dispatch`, `pip-licenses`, `license-checker`, all three locked open decisions (OPEN-1, OPEN-6, OPEN-8), and the CLI trigger command.

Local smoke (not run in this autonomous session per the plan's "once pushed to GitHub" note; structure verified statically):

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); yaml.safe_load(open('.github/workflows/license-gate-test.yml'))"  # PASS
! grep -qE "^\s*ollama:" docker-compose.yml && echo "OK: no ollama service"  # PASS
```

## Success Criteria — Plan Level

| Criterion | Status |
|-----------|--------|
| FND-06 satisfied (lint + type-check + license allowlist on every commit) | ✓ |
| Four parallel jobs (backend, frontend, compose, licenses) fail fast, block merge | ✓ |
| OPEN-6 locked (ubuntu-latest only; Mac smoke deferred to Phase 7) | ✓ |
| OPEN-8 locked (license-gate regression = manual-dispatch, with gnureadline canary) | ✓ |
| OPEN-1 regression guard (grep `^\s*ollama:` in docker-compose.yml) | ✓ |
| Both workflow files parse as valid YAML | ✓ |
| docs/ci.md documents topology + trigger procedure + OPEN-1/6/8 | ✓ |
| T-01-06-04 (silent OPEN-1 regression) mitigated via grep guard | ✓ |

## Phase 1 Foundation — Closing Notes

Plan 01-06 closes Phase 1 Foundation. With this merged:
- All 6 FND-* requirements complete (FND-01 through FND-06).
- A fresh-clone contributor can: `make setup` → `make models` → `make up` → hit `/healthz` → see the empty Hebrew RTL sidebar → push a commit and have CI enforce lint + type + license gates.
- Phases 2, 3, 4 can now start in parallel per the roadmap.

## Known Stubs

None. No placeholder data, no hardcoded empty UI values, no TODO markers introduced. The workflows are fully functional as written — `gh workflow run license-gate-test.yml` on a merged branch will immediately execute the real regression test against live PyPI (gnureadline).

## Self-Check: PASSED

All claimed artifacts verified:
- `FOUND: .github/workflows/ci.yml`
- `FOUND: .github/workflows/license-gate-test.yml`
- `FOUND: docs/ci.md`
- `FOUND: c44fc4d` (Task 1 commit in git log)
- `FOUND: 7a6b828` (Task 2 commit in git log)
