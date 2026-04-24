# CI — Receptra

## Runner

All CI runs on `ubuntu-latest` (x86_64). Apple Silicon-specific smoke tests
(`docker compose up`, Metal benchmarks, arm64 wheel verification) are manual
for Phase 1 per research OPEN-6. Phase 7 polish may add `macos-14` runners.

## Main workflow — `.github/workflows/ci.yml`

Triggers: every `push` and `pull_request` to any branch. Old in-progress runs
are cancelled by the `concurrency` group.

Four parallel jobs:

| Job | Purpose | Must-pass commands |
|-----|---------|--------------------|
| `backend` | Python quality | `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src tests`, `uv run pytest tests/ -x` |
| `frontend` | JS quality | `npm run lint`, `npm run typecheck`, `npm run format:check`, `npm run build` |
| `compose` | Infra syntax | `docker compose config -q`, "no ollama service" regression guard (OPEN-1) |
| `licenses` | License allowlist | `bash scripts/check_licenses.sh` (both pip-licenses + license-checker) |

All four must pass for a PR to merge.

## Regression workflow — `.github/workflows/license-gate-test.yml`

**When to run:** manually (`workflow_dispatch`) before releases or when the
license allowlist in `scripts/check_licenses.sh` changes. Not wired to every
commit per OPEN-8 — running it every push slows CI and pollutes caches with
a known-bad package.

**What it proves:** the allowlist actually rejects a GPL package
(`gnureadline`, declared GPLv3). If someone accidentally adds
`GNU General Public License v3 (GPLv3)` to the allowlist, this workflow
catches it.

**How to trigger:**
1. GitHub UI → Actions tab → "License Gate Regression Test" → Run workflow.
2. Or via CLI: `gh workflow run license-gate-test.yml`.

**Expected outcome:** green check with logs showing
`✓ License gate correctly REJECTED the GPL package.`

## Caching

- Python: `astral-sh/setup-uv@v4` caches keyed on `backend/uv.lock`.
- Node: `actions/setup-node@v4` with `cache: npm` keyed on `frontend/package-lock.json`.

Cache miss on a first-time clone: expect ~2-3 min wall time for a full run;
~30-60s on warm cache.

## Troubleshooting

- Ruff fails on a new PR → `make format` locally, commit, re-push.
- Mypy fails → usually a missing type annotation; project is `strict = true`.
- License gate fails → new dep has a non-permissive license. Check the
  allowlist in `scripts/check_licenses.sh` — if the license is actually
  acceptable (e.g., a new SPDX name), add it; if not, find an alternative.
- `docker compose config -q` fails → env var referenced in compose file
  has no `.env.example` default. Add a `${VAR:-default}` fallback.
