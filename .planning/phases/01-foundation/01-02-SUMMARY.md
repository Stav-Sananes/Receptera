---
phase: 01-foundation
plan: "01-02"
subsystem: backend
tags: [backend, python, fastapi, uv, pydantic-settings, pytest, ruff, mypy, healthz, src-layout]

# Dependency graph
requires: []
provides:
  - "backend/ src-layout Python 3.12 package (`receptra`) with pyproject.toml + uv.lock"
  - "FastAPI app `receptra.main:app` exposing GET /healthz returning {\"status\":\"ok\"} (FND-04 backend half)"
  - "pydantic-settings `Settings` class (RECEPTRA_ prefix) with model_dir / ollama_host / chroma_host / log_level"
  - "Module entrypoint `python -m receptra` launching uvicorn on 0.0.0.0:8080"
  - "Wave-0 pytest smoke tests (3/3 green): /healthz status, /healthz content-type, /openapi.json metadata"
  - "Strict mypy + ruff lint + ruff format config ready for Phase 1 Plan 06 CI"
affects: [01-04-docker-compose, 01-06-ci, 02-stt, 03-llm, 04-rag, 05-integration]

# Tech tracking
tech-stack:
  added:
    - "uv (0.11.7) — Python dependency manager (installed via Homebrew)"
    - "FastAPI >=0.115"
    - "uvicorn[standard] >=0.32"
    - "pydantic >=2.9 + pydantic-settings >=2.6"
    - "python-multipart >=0.0.20"
    - "ruff >=0.7 (dev)"
    - "mypy >=1.13 (dev, strict) + pydantic.mypy plugin"
    - "pip-licenses >=5.0 (dev, for Plan 01-06)"
    - "pytest >=8.3 + pytest-asyncio >=0.24 + httpx >=0.27 (dev)"
    - "hatchling — PEP-621 build backend for src-layout wheel"
  patterns:
    - "src-layout (`backend/src/receptra/`) with hatchling wheel packaging — avoids setuptools complexity, keeps tests outside the installed package"
    - "Tests import `receptra.*` via `[tool.pytest.ini_options] pythonpath = [\"src\"]` instead of requiring editable install on every iteration"
    - "All settings use RECEPTRA_ env prefix via pydantic-settings `SettingsConfigDict(env_prefix=..., extra=\"ignore\")`"
    - "from __future__ import annotations across all source + test modules — string-based annotations, strict-mypy friendly, faster import"
    - "FastAPI app metadata (title=Receptra, version=0.1.0) locked by OpenAPI test so downstream phases can't silently rename the service"
    - "Module entrypoint pattern: `__main__.py` runs uvicorn when `python -m receptra` is invoked"

key-files:
  created:
    - backend/pyproject.toml
    - backend/.python-version
    - backend/README.md
    - backend/uv.lock
    - backend/src/receptra/__init__.py
    - backend/src/receptra/config.py
    - backend/src/receptra/main.py
    - backend/src/receptra/__main__.py
    - backend/tests/__init__.py
    - backend/tests/conftest.py
    - backend/tests/test_healthz.py
  modified: []

key-decisions:
  - "uv 0.11.7 (Homebrew) chosen as the Python dependency manager per research §3.1 — 10-100x faster than pip, correct arm64 wheel resolution, single pyproject.toml + uv.lock source of truth"
  - "hatchling selected as build backend over setuptools — PEP-621 standard, minimal config for src-layout wheel packaging"
  - "`extra=\"ignore\"` on SettingsConfigDict (T-01-02-02 accept): a typo'd RECEPTRA_ var won't block service startup; mitigation is the explicit `_log_config` logging of resolved values"
  - "`on_event(\"startup\")` used (not lifespan events) to match plan text exactly — generates a DeprecationWarning captured by pytest; flagged as a potential cleanup in Plan 05 or later integration phase"
  - "S104 bandit noqa replaced with a plain inline comment because the `S` rule family is not enabled in `[tool.ruff.lint] select` — leaving the noqa triggers RUF100 (unused noqa). Intent is preserved as documentation."
  - "Three tests (not one) — status/content-type/openapi-metadata — so the Wave-0 gate isn't a single-point assertion; the OpenAPI metadata test locks the title+version contract for downstream phases"

patterns-established:
  - "Task commit convention: `{type}(01-02): {description}` matching the conventional-commits subject style"
  - "Strict mypy runs on both `src` and `tests` so fixture signatures stay typed — enforced in Plan 01-06 CI"
  - "Manual live-server smoke (`uvicorn receptra.main:app --port 8080` + `curl /healthz`) runs and returns `{\"status\":\"ok\"}` from the checked-in scaffold without any further configuration"

requirements-completed-partial:
  - "FND-01 (backend half): Python backend scaffolded with pyproject.toml, src-layout package, and tests. Frontend scaffold (Plan 01-03) still pending before FND-01 is fully satisfied."
  - "FND-04 (backend half): `/healthz` returns HTTP 200 with JSON `{\"status\":\"ok\"}`, proven by a passing pytest. Frontend sidebar (Plan 01-03) still pending before FND-04 is fully satisfied."

# Metrics
duration: ~9min
completed: 2026-04-23
---

# Phase 1 Plan 01-02: Backend Scaffold Summary

**Python 3.12 + FastAPI backend scaffolded via uv with src-layout, pydantic-settings-based config (RECEPTRA_ prefix), strict ruff+mypy configuration, and three Wave-0 pytest smoke tests proving `GET /healthz` returns `{"status":"ok"}` — the backend half of FND-01 and FND-04.**

## Performance

- **Duration:** ~9 min (includes one-time uv install via Homebrew)
- **Started:** 2026-04-23T22:06:27Z
- **Completed:** 2026-04-23
- **Tasks:** 3
- **Files created:** 11
- **Files modified:** 0
- **Tests:** 3 passing (100%)

## Accomplishments

- `backend/pyproject.toml` declares the `receptra` 0.1.0 project with Python >=3.12, FastAPI, pydantic-settings, and a full dev group (ruff, mypy, pytest+asyncio, httpx, pip-licenses) — single source of truth consumed by Plans 01-04 (Docker) and 01-06 (CI).
- `backend/uv.lock` committed (40 resolved packages) for reproducible installs across dev machines and CI.
- `backend/src/receptra/config.py` defines `Settings(BaseSettings)` with `model_dir`, `ollama_host`, `chroma_host`, `log_level` — all loadable via `RECEPTRA_*` env vars or optional `.env` file.
- `backend/src/receptra/main.py` wires a FastAPI app (title="Receptra", version=0.1.0) with a single `GET /healthz` route returning `{"status":"ok"}` and a startup hook that logs the resolved non-secret infra config (T-01-02-01 mitigation).
- `backend/src/receptra/__main__.py` enables `python -m receptra` (and `uv run python -m receptra`) as a one-liner uvicorn launcher on 0.0.0.0:8080 — Plan 01-04 Dockerfile will call this entrypoint.
- `backend/tests/test_healthz.py` with three passing tests: `/healthz` status, `/healthz` content-type, and `/openapi.json` app-metadata (locks title+version for downstream phases).
- `backend/tests/conftest.py` provides reusable `app` and `client` (FastAPI TestClient) fixtures for all future backend tests (Phase 2 STT, Phase 3 LLM, etc.).
- Strict mypy passes on 7 source files (src + tests); ruff check passes with zero violations; ruff format reports all files formatted.
- Live-server smoke verified: `uvicorn receptra.main:app --port 8080` + `curl http://localhost:8080/healthz` returns `{"status":"ok"}` from the committed scaffold.

## Task Commits

Each task committed atomically:

1. **Task 1: Create pyproject.toml + .python-version + backend README + uv.lock** — `530b3bc` (chore)
2. **Task 2: Create FastAPI app, config.py, __init__.py, __main__.py** — `8578d8e` (feat)
3. **Task 3: Write Wave-0 health tests + conftest fixtures** — `3bc6df2` (test)

**Plan metadata commit:** pending final commit after SUMMARY, STATE, ROADMAP, REQUIREMENTS updates.

## Files Created/Modified

- `backend/pyproject.toml` — Full project manifest: `[project]`, `[dependency-groups].dev`, `[build-system]` (hatchling), `[tool.ruff]`, `[tool.mypy]` (strict + pydantic plugin), `[tool.pytest.ini_options]` (pythonpath=["src"], asyncio_mode=auto).
- `backend/.python-version` — Single line `3.12` pinning the interpreter for uv-managed installs.
- `backend/README.md` — Quickstart (`uv sync`, `uv run uvicorn …`), tests+lint commands, RECEPTRA_ env var reference table.
- `backend/uv.lock` — uv-resolved lockfile (40 packages) for reproducible installs.
- `backend/src/receptra/__init__.py` — Package docstring + `__version__ = "0.1.0"`.
- `backend/src/receptra/config.py` — `Settings(BaseSettings)` with env_prefix="RECEPTRA_" and four typed fields.
- `backend/src/receptra/main.py` — FastAPI app + `GET /healthz` route + `_log_config` startup hook.
- `backend/src/receptra/__main__.py` — uvicorn entrypoint (0.0.0.0:8080) for `python -m receptra`.
- `backend/tests/__init__.py` — Empty marker so strict mypy can typecheck the tests package.
- `backend/tests/conftest.py` — `app` fixture (lazy import of `receptra.main.app`) and `client` fixture (FastAPI TestClient) shared across all backend tests.
- `backend/tests/test_healthz.py` — Three tests: `test_healthz_returns_200_ok`, `test_healthz_content_type_is_json`, `test_app_metadata_is_correct`.

## Decisions Made

- **uv over pip** (research §3.1) — 10-100x faster resolution, correct arm64 wheel selection, single pyproject.toml + uv.lock source of truth for Dockerfile and CI.
- **hatchling build backend** — PEP-621 default, minimal config for src-layout wheel packaging; avoids setuptools boilerplate.
- **`SettingsConfigDict(extra="ignore")`** — tradeoff logged in threat model (T-01-02-02, `accept` disposition). Typo-safe at runtime; mitigated by explicit startup logging so a misconfigured env var is visible in logs on every boot.
- **Three tests, not one** — the sampling gate is not a single-point assertion. The OpenAPI metadata test locks title+version so a downstream rename requires a conscious PR.
- **S104 noqa removed** (see Deviations) — the `S` bandit rule family is not in the ruff select list, so the noqa triggered `RUF100` (unused noqa). Intent is preserved as a plain inline comment.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking Issue] uv not installed on the host**
- **Found during:** Task 1 preparation — `uv --version` returned "not found"
- **Issue:** uv (the Python dependency manager the plan's verify commands assume) was absent from the Homebrew-managed toolchain; without it `uv lock` and subsequent `uv sync`/`uv run pytest` commands would fail immediately.
- **Fix:** `brew install uv` — pulled uv 0.11.7 (matches research §3.1 minimum). Installation took ~10 seconds.
- **Files modified:** None (system-level tool install).
- **Commit:** None (no repo state changed).

**2. [Rule 1 — Bug] `# noqa: S104` comment flagged by RUF100**
- **Found during:** Task 2 verification (`uv run ruff check .`)
- **Issue:** The plan's exact text for `__main__.py` included `# noqa: S104 — binding all interfaces is intended in container`. Ruff's `RUF100 Unused noqa directive` check (which IS enabled via the `RUF` family in `select`) flagged the noqa because `S` (bandit-style) rules are NOT enabled. Ruff check exited with error, blocking verification.
- **Fix:** Replaced the noqa with a plain inline comment that preserves the documented intent: `# Binding all interfaces is intended inside the Docker container.` Ruff check then passes with zero issues. Threat T-01-02-03 (0.0.0.0 bind) remains documented in-code per the threat model.
- **Files modified:** `backend/src/receptra/__main__.py`
- **Commit:** `8578d8e` (included in the Task 2 commit)

No architectural changes. No new dependencies beyond the plan spec.

## Issues Encountered

- **DeprecationWarning in pytest output:** FastAPI 1.0.0's `@app.on_event("startup")` is deprecated in favor of lifespan event handlers. The plan specified `on_event` verbatim so that pattern was kept for this plan; tests still pass. Recommend migrating to a lifespan context in Plan 05 (integration) or before the CI plan tightens warning-as-error rules.
- `mypy` runs against `src` and `tests` successfully — no issues in 7 source files. pydantic.mypy plugin resolves `Settings` typing correctly.

## Threat Model Compliance

All four dispositioned threats from the plan's STRIDE register are addressed:

| Threat ID | Disposition | Status | Evidence |
|-----------|-------------|--------|----------|
| T-01-02-01 (Settings leak on startup) | mitigate | mitigated | `_log_config` logs only `model_dir`, `ollama_host`, `chroma_host` — all non-secret infrastructure paths. `log_level` is also non-secret. No credentials live in `Settings` in Phase 1. |
| T-01-02-02 (`extra="ignore"` silent drop) | accept | accepted + mitigated | Tradeoff documented; startup log prints resolved config so a misconfigured var is visible at boot time. |
| T-01-02-03 (0.0.0.0 bind in `__main__.py`) | accept | accepted | Intent documented by inline comment. Constrained by docker-compose port mapping (Plan 01-04) and the project's local-only privacy constraint. |
| T-01-02-04 (transitive GPL dep risk) | mitigate | deferred to Plan 01-06 | This plan only pins versions via `pip-licenses>=5.0` in the dev group; enforcement lives in the CI plan. |

## User Setup Required

None — the scaffold runs end-to-end with just `cd backend && uv sync && uv run pytest`. Developers who don't already have uv installed need one `brew install uv` (documented in `backend/README.md` link to the uv docs).

## Next Plan Readiness

- **Unblocks Plan 01-04 (docker-compose)** — `backend/pyproject.toml` + `backend/src/receptra/main.py` + `backend/src/receptra/__main__.py` are the interface the Dockerfile will consume (`COPY pyproject.toml uv.lock ./`, `RUN uv sync --frozen --no-dev`, `CMD ["python", "-m", "receptra"]`).
- **Unblocks Plan 01-06 (CI)** — `uv run ruff check`, `uv run mypy src tests`, and `uv run pytest tests/` all pass and can be plumbed straight into GitHub Actions. `pip-licenses>=5.0` is already a dev-group dep ready for the license allowlist check.
- **Unblocks Phase 2 (Hebrew Streaming STT)** — Phase 2 plans can land STT code under `backend/src/receptra/` alongside `main.py` with full ruff/mypy/pytest scaffolding already in place.
- **FND-01 partially complete:** backend scaffold in. Frontend scaffold (Plan 01-03) needs to land before FND-01 is fully satisfied.
- **FND-04 partially complete:** backend `/healthz` in. Frontend sidebar (Plan 01-03) needs to land before FND-04 is fully satisfied.
- No blockers, no open questions.

## Self-Check

**Claimed files exist:**
- backend/pyproject.toml — FOUND
- backend/.python-version — FOUND
- backend/README.md — FOUND
- backend/uv.lock — FOUND
- backend/src/receptra/__init__.py — FOUND
- backend/src/receptra/config.py — FOUND
- backend/src/receptra/main.py — FOUND
- backend/src/receptra/__main__.py — FOUND
- backend/tests/__init__.py — FOUND
- backend/tests/conftest.py — FOUND
- backend/tests/test_healthz.py — FOUND

**Claimed commits exist:**
- 530b3bc — FOUND (Task 1: uv-managed project scaffold)
- 8578d8e — FOUND (Task 2: FastAPI app + config + entrypoint)
- 3bc6df2 — FOUND (Task 3: Wave-0 health tests + conftest)

**Claimed checks pass:**
- `uv lock` — OK (40 packages resolved)
- `uv sync --all-extras` — OK (all deps installed)
- `uv run ruff check .` — OK (zero violations)
- `uv run ruff format --check .` — OK (7 files already formatted)
- `uv run mypy src tests` — OK (no issues in 7 files)
- `uv run pytest tests/ -x -v` — OK (3 passed)
- Live server smoke (`curl http://localhost:8080/healthz`) — returned `{"status":"ok"}`

## Self-Check: PASSED

---
*Phase: 01-foundation*
*Completed: 2026-04-23*
