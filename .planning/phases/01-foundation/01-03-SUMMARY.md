---
phase: 01-foundation
plan: "01-03"
subsystem: frontend
tags: [frontend, react-19, vite-6, typescript, tailwind-v4, eslint-9, prettier, rtl, hebrew]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "backend `/healthz` + port 8080 contract (Plan 01-02) — consumed by Vite dev proxy `/api` and `/ws` targets"
provides:
  - "frontend/ Vite 6 + React 19 + TypeScript 5.6 + Tailwind v4 (via @tailwindcss/vite) scaffold"
  - "RTL-ready root HTML: `<html dir=\"rtl\" lang=\"he\">` with `<title>Receptra</title>` (FND-04 frontend half)"
  - "Empty Receptra sidebar placeholder page served at http://localhost:5173 (FND-01 frontend half)"
  - "Vite dev proxy forwarding /api/* (HTTP) and /ws/* (WebSocket) to localhost:8080"
  - "ESLint 9 flat config (js + typescript-eslint + react-hooks + react-refresh), Prettier 3 with CSS override, strict TS composite (tsconfig.app.json + tsconfig.node.json)"
  - "npm scripts contract: dev, build, preview, lint, typecheck, format, format:check — consumed by Plan 01-06 CI"
  - "Production build outputs to frontend/dist/ with sourcemaps — consumed by Plan 01-04 frontend Dockerfile"
affects: [01-04-docker-compose, 01-06-ci, 06-frontend-sidebar]

# Tech tracking
tech-stack:
  added:
    - "react ^19.0.0 + react-dom ^19.0.0 (Open Decision 4 resolution per plan)"
    - "vite ^6.0.0 + @vitejs/plugin-react ^4.3.4"
    - "tailwindcss ^4.0.0 + @tailwindcss/vite ^4.0.0 (v4 single-import entry, no tailwind.config.js)"
    - "typescript ~5.6.0 (strict composite build)"
    - "eslint ^9.15.0 + typescript-eslint ^8.18.0 + @eslint/js ^9.15.0 + eslint-plugin-react-hooks ^5.1.0 + eslint-plugin-react-refresh ^0.4.14"
    - "prettier ^3.4.0 (singleQuote JS/TS, double-quote CSS override)"
    - "globals ^15.13.0"
    - "license-checker ^25.0.1 (staged for Plan 01-06 allowlist check)"
  patterns:
    - "Tailwind v4 wiring via Vite plugin — `@import \"tailwindcss\"` in a single CSS file, no tailwind.config.js, per research §4.2"
    - "RTL-first root: `dir=\"rtl\"` + `lang=\"he\"` on `<html>` and defensively on the `<main>` component — Phase 6 layers on `hebrew-tailwind-preset`"
    - "Composite tsconfig: `tsconfig.json` with file refs, `tsconfig.app.json` (src strict), `tsconfig.node.json` (Vite config)"
    - "ESLint 9 flat config (single `eslint.config.js`, no legacy .eslintrc chain)"
    - "Vite dev proxy declarative contract: `/api` → http://localhost:8080, `/ws` → ws://localhost:8080 with `ws: true`"
    - "`host: '0.0.0.0'` + `strictPort: true` — required for Plan 04 Docker container to expose 5173, fails fast instead of silent 5174 drift"
    - "Prettier CSS override (`overrides: [{ files: '*.css', options: { singleQuote: false } }]`) preserves `@import \"tailwindcss\"` double-quote invariant required by plan artifact checks"
    - "Production build emits `dist/assets/*` with sourcemaps (`sourcemap: true`) — dev aid; OSS repo so sources are already public"

key-files:
  created:
    - frontend/package.json
    - frontend/package-lock.json
    - frontend/tsconfig.json
    - frontend/tsconfig.app.json
    - frontend/tsconfig.node.json
    - frontend/eslint.config.js
    - frontend/.prettierrc.json
    - frontend/.prettierignore
    - frontend/README.md
    - frontend/vite.config.ts
    - frontend/index.html
    - frontend/src/main.tsx
    - frontend/src/App.tsx
    - frontend/src/index.css
    - frontend/src/vite-env.d.ts
  modified:
    - .gitignore  # added *.tsbuildinfo

key-decisions:
  - "React 19 locked (Open Decision 4 from research §4) — `^19.0.0` allows patch updates but caps at major 19. Phase 6 research may revisit if a downstream lib pins 18."
  - "Tailwind v4 via `@tailwindcss/vite` plugin, no tailwind.config.js — v4 is the 2026 default per research §4.2. Phase 6 adds `hebrew-tailwind-preset`."
  - "Composite tsconfig setup mirrors Vite 2026 `react-ts` template; `tsconfig.app.json` was created even though plan `files_modified` omits it (plan task action explicitly mandates it for the composite reference)."
  - "Prettier CSS override added (not in plan) to keep `@import \"tailwindcss\"` in double quotes — preserves the plan's literal `contains:` artifact check while still enforcing `singleQuote: true` for JS/TS."
  - "`erasableSyntaxOnly: false` removed from tsconfig.app.json — unknown compiler option under TS 5.6 (added in TS 5.8). Removing preserves default behavior; Phase 6 can re-add after a TS bump."
  - "`*.tsbuildinfo` added to root .gitignore — TypeScript incremental build metadata is generated output and should never be committed."
  - "Dev server binds 0.0.0.0 (accept T-01-03-01) — required for Plan 04 Docker container exposure. Dev-only; production serves static `dist/`, not the dev server."
  - "Source maps in build output (accept T-01-03-02) — dev aid; OSS repo so sources are public regardless."

patterns-established:
  - "Frontend scripts contract pinned: dev / build / preview / lint / typecheck / format / format:check — CI in Plan 01-06 calls these names."
  - "Verification order for frontend tasks: typecheck → lint → format:check → build → curl dev server for served HTML attrs."
  - "Defense-in-depth RTL: both `<html dir=\"rtl\" lang=\"he\">` AND `<main dir=\"rtl\" lang=\"he\">` in App.tsx, so if App is later mounted outside the shell, RTL still holds."

requirements-completed:
  - FND-01
  - FND-04

# Metrics
duration: ~20min
completed: 2026-04-24
---

# Phase 1 Plan 01-03: Frontend Scaffold Summary

**Vite 6 + React 19 + TypeScript 5.6 + Tailwind v4 frontend with RTL-first `<html dir="rtl" lang="he">` root, empty Receptra sidebar at :5173, and dev proxy forwarding /api + /ws to backend:8080 — completes the frontend halves of FND-01 and FND-04.**

## Performance

- **Duration:** ~20 min active (wall-clock 9h spans an overnight gap between Task 1 and Task 2 commits)
- **Started:** 2026-04-24T01:18:44+03:00 (Task 1 commit `64bcf99`)
- **Completed:** 2026-04-24T10:35:38+03:00 (Task 2 commit `77b0d8f`)
- **Tasks:** 2/2
- **Files created:** 15
- **Files modified:** 1 (.gitignore)

## Accomplishments

- Root HTML has `<html dir="rtl" lang="he">` and `<title>Receptra</title>` — Hebrew-ready without Phase 6 tooling.
- Empty Receptra sidebar renders at `http://localhost:5173` via `npm run dev`, matching the plan's deliverable. `dist/index.html` contains the string "Receptra" post-build.
- Tailwind v4 wired via `@tailwindcss/vite` plugin with single-import `@import "tailwindcss"` CSS entry — no `tailwind.config.js` needed.
- Dev proxy forwards both HTTP (`/api`) and WebSocket (`/ws` with `ws: true`) to `localhost:8080`, ready for Plan 02 STT streams and Plan 04 RAG HTTP calls.
- Static checks all green on the scaffold: `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm run build` all pass.
- `license-checker` devDep installed so Plan 01-06 can wire the allowlist gate without another npm install.

## Task Commits

1. **Task 1: Create package.json, tsconfig, ESLint, Prettier configs** — `64bcf99` (chore)
2. **Task 2: Create Vite config, index.html (RTL), and src/ app files** — `77b0d8f` (feat)

_Note: Task 1 was committed prior to this executor resuming; Task 2 was executed in this session. The Task 2 commit also bundles prettier auto-reformat of three files first-written in Task 1 (eslint.config.js, tsconfig.json, README.md) to keep `format:check` green, plus two auto-fixes (tsconfig.app.json `erasableSyntaxOnly` removal, .gitignore `*.tsbuildinfo`) and a .prettierrc.json CSS override._

**Plan metadata commit (this SUMMARY + STATE/ROADMAP/REQUIREMENTS updates):** will be recorded on the follow-up docs commit.

## Files Created/Modified

### Created
- `frontend/package.json` — receptra-frontend npm project, React 19 + Vite 6 + Tailwind v4 + TS 5.6 + ESLint 9 + Prettier 3, scripts contract for CI
- `frontend/package-lock.json` — npm lockfile (241 packages, 0 vulnerabilities reported at install)
- `frontend/tsconfig.json` — composite root referencing app + node configs
- `frontend/tsconfig.app.json` — strict TS config for `src/` (React JSX, ES2022, bundler resolution)
- `frontend/tsconfig.node.json` — strict TS config for `vite.config.ts`
- `frontend/eslint.config.js` — ESLint 9 flat config (js recommended + typescript-eslint + react-hooks + react-refresh)
- `frontend/.prettierrc.json` — no-semi, single-quote, trailing-comma-all, 100-width, with `*.css` double-quote override
- `frontend/.prettierignore` — dist, node_modules, coverage, lockfiles
- `frontend/README.md` — quickstart, scripts table, Phase 1 vs Phase 6 scope note
- `frontend/vite.config.ts` — React plugin, Tailwind v4 plugin, port 5173 strict, host 0.0.0.0, /api + /ws proxies, sourcemap build
- `frontend/index.html` — `<html dir="rtl" lang="he">`, `<title>Receptra</title>`, viewport meta, icon link, mounts `/src/main.tsx`
- `frontend/src/main.tsx` — StrictMode createRoot mount with root element guard
- `frontend/src/App.tsx` — Phase 1 placeholder sidebar (Receptra heading + status section), defensive `dir="rtl"` + `lang="he"`
- `frontend/src/index.css` — `@import "tailwindcss"` + baseline html/body reset
- `frontend/src/vite-env.d.ts` — `/// <reference types="vite/client" />`

### Modified
- `.gitignore` — added `*.tsbuildinfo` to prevent committing TS incremental build artifacts

## Decisions Made

- **React 19 locked.** Plan Open Decision 4 resolved in favor of `^19.0.0`. Phase 6 research may still downgrade to 18 if a downstream lib pins.
- **Tailwind v4 via Vite plugin, no tailwind.config.js.** Research §4.2 confirms this is the 2026 default. Phase 6 adds `hebrew-tailwind-preset`.
- **Composite tsconfig.** Mirrors Vite 2026 `react-ts` template. `tsconfig.app.json` was explicitly created despite being absent from the plan's `files_modified` list — the plan task action mandates it for the composite references to resolve.
- **Source maps in production build.** T-01-03-02 accepted: OSS repo, sources public anyway.
- **Dev server on 0.0.0.0 with strictPort.** T-01-03-01 accepted: required for Plan 04 Docker exposure; `strictPort: true` blocks silent 5174 drift.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed `erasableSyntaxOnly` compiler option from tsconfig.app.json**
- **Found during:** Task 2 verification (`npm run build`)
- **Issue:** `tsc -b` failed with `error TS5023: Unknown compiler option 'erasableSyntaxOnly'`. That option was introduced in TypeScript 5.8; the plan pins `typescript ~5.6.0`. Even with the option set to `false`, TS 5.6 rejects the unknown key.
- **Fix:** Removed the line `"erasableSyntaxOnly": false,` from `frontend/tsconfig.app.json`. Setting it to `false` is equivalent to the default behavior, so removal is semantically equivalent on TS 5.6.
- **Files modified:** `frontend/tsconfig.app.json`
- **Verification:** `cd frontend && npm run build` now passes and produces `dist/index.html` containing "Receptra".
- **Committed in:** `77b0d8f` (Task 2 commit)

**2. [Rule 2 - Missing Critical] Added `*.tsbuildinfo` to root .gitignore**
- **Found during:** Task 2 verification (`git status` after running `npm run build`)
- **Issue:** `tsc -b` generates `frontend/tsconfig.app.tsbuildinfo` and `frontend/tsconfig.node.tsbuildinfo` as untracked incremental build metadata. These are generated output, must never be committed.
- **Fix:** Added `*.tsbuildinfo` line under the Node block in root `.gitignore`.
- **Files modified:** `.gitignore`
- **Verification:** `git status --short` no longer lists the `*.tsbuildinfo` files as untracked.
- **Committed in:** `77b0d8f` (Task 2 commit)

**3. [Rule 1 - Bug] Added Prettier CSS override to preserve `@import "tailwindcss"` double quotes**
- **Found during:** Task 2 (`npm run format:check` round-trip)
- **Issue:** Global `singleQuote: true` in `.prettierrc.json` caused Prettier to rewrite `@import "tailwindcss"` → `@import 'tailwindcss'` in `src/index.css`. The plan's `artifacts` check and `<acceptance_criteria>` explicitly require `grep -q '@import "tailwindcss"'` — single quotes would break that invariant.
- **Fix:** Added Prettier `overrides: [{ files: "*.css", options: { singleQuote: false } }]` so CSS keeps double quotes while JS/TS still uses single quotes.
- **Files modified:** `frontend/.prettierrc.json`, `frontend/src/index.css` (restored to double quotes)
- **Verification:** `npm run format:check` passes AND `grep -q '@import "tailwindcss"' frontend/src/index.css` returns 0.
- **Committed in:** `77b0d8f` (Task 2 commit)

**4. [Rule 1 - Bug] Prettier auto-formatted three Task-1 files so format:check stays green**
- **Found during:** Task 2 (`npm run format:check`)
- **Issue:** Three files committed in Task 1 (`eslint.config.js`, `README.md`, `tsconfig.json`) had formatting drift from the `.prettierrc.json` rules (trailing commas, whitespace). `npm run format:check` failed until they were reformatted. The plan explicitly allows this: "or run `npm run format` first if prettier trips on generated files".
- **Fix:** Ran `npm run format` once; committed the reformatted files as part of the Task 2 commit.
- **Files modified:** `frontend/eslint.config.js`, `frontend/README.md`, `frontend/tsconfig.json`
- **Verification:** `npm run format:check` now passes.
- **Committed in:** `77b0d8f` (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (2 Rule 1 bugs + 1 Rule 1 invariant preservation + 1 Rule 2 missing critical gitignore)
**Impact on plan:** All four fixes were necessary to make the scaffold actually build/lint/format-check green on the pinned TypeScript 5.6. None expand scope; none touch runtime behavior.

## Issues Encountered

- None beyond the deviations above. Dev server curl test returned the expected `<html dir="rtl" lang="he">` and `<title>Receptra</title>` HTML on first try.

## User Setup Required

None — no external service configuration required. `cd frontend && npm install && npm run dev` is the complete quickstart.

## Next Phase Readiness

- **Plan 01-04 (Docker Compose):** can mount `frontend/` and run `npm run build` in a multi-stage Node 22 image. Port 5173 (dev) or static serve of `dist/` (prod) is documented and strict.
- **Plan 01-06 (CI):** all five script names the CI will call (`lint`, `typecheck`, `format:check`, `build`, and the license-check wrapper over `license-checker`) are present in `frontend/package.json`.
- **Phase 6 (Browser Sidebar Frontend):** scaffold is ready for `hebrew-tailwind-preset`, `hebrew-rtl-best-practices`, `hebrew-i18n` skill installs. The placeholder `App.tsx` is intentionally thin so Phase 6 rewrites it fully.
- **FND-01** and **FND-04** are now fully complete (both backend half from 01-02 and frontend half from 01-03 landed).

## Self-Check: PASSED

Verified post-commit:
- `test -f frontend/package.json` → exists
- `test -f frontend/vite.config.ts` → exists
- `test -f frontend/index.html` → exists
- `test -f frontend/src/App.tsx` → exists
- `test -f frontend/src/main.tsx` → exists
- `test -f frontend/src/index.css` → exists
- `test -f frontend/src/vite-env.d.ts` → exists
- `test -f frontend/tsconfig.app.json` → exists
- `git log --oneline | grep 64bcf99` → found (Task 1 commit)
- `git log --oneline | grep 77b0d8f` → found (Task 2 commit)
- `cd frontend && npm run typecheck && npm run lint && npm run format:check && npm run build` → all pass
- `grep 'dir="rtl"' frontend/index.html && grep 'lang="he"' frontend/index.html` → both found
- `grep "Receptra" frontend/dist/index.html` → found (post-build)
- `curl -fsS http://localhost:5173` → returned HTML with `<html dir="rtl" lang="he">` and `<title>Receptra</title>`

---
*Phase: 01-foundation*
*Completed: 2026-04-24*
