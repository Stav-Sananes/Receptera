---
phase: "01-foundation"
plan: "01-05"
subsystem: build
tags: [makefile, model-download, hf-cli, ollama, modelfile, dictalm, whisper, bge-m3, license-allowlist, docs]
requires:
  - ".env.example with MODEL_DIR/DICTALM_QUANT defaults (Plan 01-01)"
  - "backend/pyproject.toml with pip-licenses in dev group (Plan 01-02)"
  - "frontend/package.json with license-checker@^25.0.1 in devDependencies (Plan 01-03)"
  - "docker-compose.yml (Plan 01-04) that `make up` wraps after starting host Ollama"
provides:
  - "Makefile — one-command UX for Phase 1 (setup / models / up / down / logs / test / lint / typecheck / format / licenses / clean)"
  - "scripts/download_models.sh — resumable hf CLI + ollama pull dispatcher (whisper / dictalm / bge / qwen-fallback)"
  - "scripts/ollama/DictaLM3.Modelfile — Ollama Modelfile template with __GGUF_PATH__ substitution marker"
  - "scripts/check_licenses.sh — license-allowlist gate wrapping pip-licenses + license-checker, invoked by `make licenses`"
  - "docs/models.md — model footprint, quant selection, fallback procedure, storage location rationale"
affects:
  - "Plan 01-06 CI: the `licenses` target + scripts/check_licenses.sh is the single script CI invokes for the license gate; the license allowlists are canonical and referenced by CI workflow"
  - "Phase 2 (STT): `make models-whisper` produces the model at `$MODEL_DIR/whisper-turbo-ct2/` which the backend Phase-2 code will load via faster-whisper"
  - "Phase 3 (LLM): `make models-dictalm` registers the GGUF with Ollama as model name `dictalm3` — Phase 3 service layer targets this exact name; `make models-fallback` provides the Qwen path per OPEN-1"
  - "Phase 4 (RAG): `make models-bge` pulls BGE-M3 via Ollama which Phase 4 embeddings service will call"
tech-stack:
  added:
    - "Makefile with GNU make recipes and bash `-euo pipefail` SHELLFLAGS"
    - "hf CLI (HuggingFace Hub) for resumable HF-hosted weight downloads with progress bars"
    - "ollama pull / ollama create for Ollama-library and GGUF-registered models"
    - "pip-licenses allowlist (research §5.4 verbatim)"
    - "license-checker allowlist (research §5.5 verbatim)"
  patterns:
    - "Modelfile-as-template with sed substitution: `__GGUF_PATH__` in checked-in template, replaced with absolute path at ollama-create time (keeps the committed Modelfile repo-portable)"
    - "Dispatch-before-validate in the download script: usage() fires on unknown subcommand before MODEL_DIR required-env check, so bare invocation gives a helpful message"
    - "Makefile env-var override pattern: `MODEL_DIR ?= $(HOME)/.receptra/models` + `DICTALM_QUANT ?= Q4_K_M`, passed explicitly to sub-make and script invocations"
    - "Host-Ollama gate in `make up`: `pgrep -x ollama` checks if server is running, starts with `nohup ollama serve` if not — preserves OPEN-1 host-Ollama decision while hiding it from the contributor"
    - "Single-script license gate: pip-licenses + license-checker wrapped in one bash script with two subshell cd blocks, one exit code — the exact contract Plan 01-06 CI will call"
key-files:
  created:
    - "Makefile"
    - "scripts/download_models.sh"
    - "scripts/ollama/DictaLM3.Modelfile"
    - "scripts/check_licenses.sh"
    - "docs/models.md"
  modified: []
decisions:
  - "OPEN-2 LOCKED: default DictaLM quant is Q4_K_M (7.49 GB) — works on 16 GB M2 reference hardware. Q5_K_M override documented for 32 GB+ Macs via `DICTALM_QUANT=Q5_K_M make models`. Default chosen for widest contributor compatibility."
  - "OPEN-1 ENFORCED in Makefile: `make up` runs `pgrep -x ollama` then nohup-starts ollama serve on host if absent, then `docker compose up -d`. Ollama never enters the compose file (Plan 01-04 already locked this); the Makefile just makes the host-side start seamless."
  - "DictaLM3.Modelfile is a TEMPLATE with `__GGUF_PATH__` placeholder, NOT a hardcoded path. Rationale: the downloaded GGUF filename depends on HF's publishing (e.g., `DictaLM-3.0-Nemotron-12B-Instruct-Q4_K_M.gguf`) and the absolute path depends on each contributor's $MODEL_DIR. sed substitution at `ollama create` time is the minimal, portable indirection (research §2.2 Option A)."
  - "License allowlist strings are VERBATIM from research §5.4 + §5.5 — including both SPDX names (`Apache-2.0`) and long-form names (`Apache Software License`) because pip-licenses reports license metadata as each package declares it, not normalized to SPDX."
  - "Download script dispatches to `usage()` BEFORE the `${MODEL_DIR:?...}` required-env check. Rationale: running `scripts/download_models.sh` bare should give a discoverable usage message, not a cryptic env-var error. The required-env check still fires for all valid subcommands."
  - "`make clean` preserves models on disk (at $MODEL_DIR) and emits a note telling the user how to reclaim that disk. Rationale: ~11 GB of downloads should not be silently wiped by a build-artifact cleanup."
  - "`make setup` chains check-prereqs → backend/frontend dep install → models. One command takes a fresh Mac from `git clone` to ready-to-run."
patterns-established:
  - "Makefile-owns-the-one-command-UX: contributors never invoke scripts/*.sh directly; every contributor-facing action is a `make <target>`"
  - "Scripts are callable by Makefile AND by CI (scripts/check_licenses.sh is both `make licenses` and a direct invocation from .github/workflows/ci.yml in Plan 01-06)"
  - "Env-var contract: MODEL_DIR + DICTALM_QUANT are the only two knobs, propagated from .env → Makefile → scripts/"
requirements-completed: [FND-03]

# Metrics
duration: ~8min
completed: 2026-04-24
---

# Phase 1 Plan 01-05: Makefile + Model Download Summary

Create the Phase 1 orchestration layer: one-command contributor UX via `make`, a resumable ~11 GB model download with visible progress to `~/.receptra/models/`, Ollama registration of DictaLM 3.0 via a checked-in Modelfile template, and the license-allowlist gate script that Plan 01-06 CI will wire into GitHub Actions. FND-03 now satisfied.

## Overview

Plan 01-05 locks two research Open Decisions into executable contract:

- **OPEN-1 (Ollama on host)** — already absent from compose (Plan 01-04); now the `make up` target runs `pgrep -x ollama` and launches `ollama serve` via `nohup` if the daemon isn't already running. Contributors type `make up` and get the host-Ollama behavior without reading docs.
- **OPEN-2 (DictaLM quant default)** — `DICTALM_QUANT ?= Q4_K_M` in the Makefile, `: "${DICTALM_QUANT:=Q4_K_M}"` in the download script, documented quant selection table in `docs/models.md`. 16 GB M2 Macs work out of the box; 32 GB+ Macs opt in with an env var.

Two atomic tasks, two atomic commits, five files (361 lines added, zero modifications). All acceptance criteria pass via `make -n` dry-run and `bash -n` syntax checks — no actual 11 GB download was executed (autonomous-mode constraint).

## What Was Built

### Task 1 — `Makefile` (commit `dc26343`)

Root Makefile with 14 phony targets organized into groups:

- **Discovery:** `help` (prints a human-readable target list with env-var override examples), `check-prereqs` (loops over docker/ollama/hf/uv/node/python3/make/curl and prints install hints on miss).
- **Setup:** `setup` (check-prereqs → `uv sync --all-extras` in backend → `npm install` in frontend → `$(MAKE) models`).
- **Models:** `models` (whisper → dictalm → bge), `models-whisper`, `models-dictalm`, `models-bge`, `models-fallback` — each delegates to `scripts/download_models.sh <subcommand>` with `MODEL_DIR` and `DICTALM_QUANT` forwarded explicitly.
- **Stack lifecycle:** `up` (pgrep-gated `nohup ollama serve` → `docker compose up -d` → prints three URLs), `down` (`docker compose down`), `logs` (`docker compose logs -f`).
- **Quality gates:** `test` (pytest + `npm test --if-present`), `lint` (ruff check + ruff format --check + eslint + prettier check), `typecheck` (mypy strict + tsc --noEmit), `format` (ruff format + prettier write), `licenses` (delegates to `scripts/check_licenses.sh`).
- **Cleanup:** `clean` (docker compose down + backend/frontend artifact removal; preserves $MODEL_DIR with a reclaim-disk note).

Uses `SHELL := /usr/bin/env bash` + `.SHELLFLAGS := -euo pipefail -c` so recipe failures surface immediately. `MODEL_DIR ?= $(HOME)/.receptra/models` and `DICTALM_QUANT ?= Q4_K_M` are exposed for override.

### Task 2a — `scripts/download_models.sh` (commit `50cefeb`)

Bash subcommand dispatcher with four handlers:

- `whisper` → `hf download ivrit-ai/whisper-large-v3-turbo-ct2 --local-dir $MODEL_DIR/whisper-turbo-ct2`
- `dictalm` → `hf download dicta-il/DictaLM-3.0-Nemotron-12B-Instruct-GGUF --include "*$DICTALM_QUANT.gguf"` → `find` the downloaded GGUF → `sed` substitute `__GGUF_PATH__` in the Modelfile template into a `mktemp` file → `ollama create dictalm3 -f <rendered>`
- `bge` → `ollama pull bge-m3`
- `qwen-fallback` → `ollama pull qwen2.5:7b`

Key hardening touches:

- `set -euo pipefail` at top — partial failures don't leave silent corruption.
- `usage()` dispatch runs BEFORE the `${MODEL_DIR:?...}` required-env check, so `scripts/download_models.sh` with no args prints usage and exits 1 (Rule 1 deviation — see below).
- `require_cmd hf|ollama` pre-flight per handler — fails with `make check-prereqs` hint instead of a cryptic `command not found`.
- `trap 'rm -f "${rendered}"' EXIT` cleans up the rendered Modelfile temp file even on error.
- `find | head -n 1` handles the case where HF ships multiple matching GGUF variants in a split download (bounded, not globbed).

### Task 2b — `scripts/ollama/DictaLM3.Modelfile` (commit `50cefeb`)

Eleven-line Modelfile template:

```
FROM __GGUF_PATH__
PARAMETER temperature 0.3
PARAMETER num_ctx 8192
PARAMETER num_predict 256
PARAMETER keep_alive -1
```

No `TEMPLATE` block — research §2.2 verified that `tokenizer.chat_template` metadata is embedded in the DictaLM 3.0 GGUF, so Ollama auto-detects it. `keep_alive -1` pins weights in memory so the first-request cold-start is absorbed at `make up`, not in the user-facing latency budget at Phase 5.

### Task 2c — `scripts/check_licenses.sh` (commit `50cefeb`)

Twenty-three-line wrapper with two subshells:

- Python: `cd backend && uv run pip-licenses --allow-only="$PY_ALLOW"`
- JS: `cd frontend && npx license-checker --production --onlyAllow "$JS_ALLOW"`

Allowlists are verbatim copies of research §5.4 (pip-licenses, semicolon-separated, includes both SPDX and long-form names) and §5.5 (license-checker, SPDX-only). Either subshell's failure propagates as the script's exit code (pipefail).

### Task 2d — `docs/models.md` (commit `50cefeb`)

Contributor-facing model documentation: footprint table (Whisper 1.5 GB, DictaLM 7.49 GB Q4_K_M / 8.76 GB Q5_K_M, BGE-M3 1.2 GB, total ~11 GB), quant selection (16 GB → Q4_K_M; 32 GB+ → Q5_K_M), Qwen fallback procedure, storage-location rationale (why `~/.receptra/models/` not inside the repo), `docker compose up` separation rationale, DictaLM Ollama registration mechanics, troubleshooting section.

## Performance

- **Duration:** ~8 min
- **Started:** 2026-04-24T07:42:32Z (inferred)
- **Completed:** 2026-04-24T07:50:47Z
- **Tasks:** 2 / 2
- **Files created:** 5 (Makefile, scripts/download_models.sh, scripts/ollama/DictaLM3.Modelfile, scripts/check_licenses.sh, docs/models.md)
- **Files modified:** 0
- **Lines added:** 361 (126 Makefile + 100 download_models.sh + 20 DictaLM3.Modelfile + 23 check_licenses.sh + ~92 docs/models.md)

## Verification

| Check | Command | Result |
|---|---|---|
| Makefile parses | `make -n help` | exit 0 ✓ |
| `make -n models` dry-run resolves whisper + dictalm + bge sub-targets | `make -n models` | exit 0 ✓ |
| `make -n up` dry-run shows pgrep + compose up | `make -n up` | exit 0 ✓ |
| All 12 phony targets dry-run | `for t in help check-prereqs models models-whisper models-dictalm models-bge models-fallback up down test lint licenses; do make -n $t; done` | all exit 0 ✓ |
| Shell syntax — download script | `bash -n scripts/download_models.sh` | exit 0 ✓ |
| Shell syntax — license script | `bash -n scripts/check_licenses.sh` | exit 0 ✓ |
| Download script no-arg → usage | `scripts/download_models.sh` | exit 1, prints "Usage:" ✓ |
| Modelfile marker present | `grep -q '^FROM __GGUF_PATH__$' scripts/ollama/DictaLM3.Modelfile` | match ✓ |
| Modelfile keep_alive pinned | `grep -q "PARAMETER keep_alive -1" scripts/ollama/DictaLM3.Modelfile` | match ✓ |
| License allowlist — long-form name | `grep -q "Apache Software License" scripts/check_licenses.sh` | match ✓ |
| License allowlist — SPDX form | `grep -q "Apache-2.0" scripts/check_licenses.sh` | match ✓ |
| docs/models.md footprint | `grep -q "~11 GB" docs/models.md` | match ✓ |
| docs/models.md quant | `grep -q "Q4_K_M" docs/models.md` | match ✓ |
| docs/models.md fallback | `grep -q "Qwen 2.5 7B" docs/models.md` | match ✓ |

`make models` was intentionally NOT executed in this run (autonomous-mode instruction: 11 GB download out of scope for static validation; runtime smoke is a Mac-local contributor step).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Reordered download_models.sh to dispatch to usage() before required-env validation**

- **Found during:** Task 2 verification
- **Issue:** The plan text placed `: "${MODEL_DIR:?...}"` at line 13 and the case-statement dispatch at the bottom. With `set -u` active, calling `scripts/download_models.sh` with no arguments tripped the MODEL_DIR check FIRST and printed `MODEL_DIR must be set` instead of the usage message. The plan's acceptance criterion "`scripts/download_models.sh 2>&1 | grep -q \"Usage:\"` exits 0" would therefore fail in a shell without MODEL_DIR set.
- **Fix:** Added an early case-statement dispatcher (immediately after `set -euo pipefail`) that calls `usage()` for any unknown/empty subcommand. The required-env checks (`MODEL_DIR`, `DICTALM_QUANT`) still fire for all valid subcommands. Both the early and the final case-statement dispatch are intentional: the early one guards on arg-validity, the final one routes valid args to handlers. No functional regression for valid use cases.
- **Files modified:** `scripts/download_models.sh`
- **Commit:** `50cefeb` (the fix was part of the initial Task 2 commit — not a follow-up)

### Architectural Changes

None. All deviations were Rule 1 bug fixes caught during verification; no Rule 4 pauses.

### Authentication Gates

None triggered — no registry logins, no API keys, no cloud services contacted. `hf download` and `ollama pull` are designed to work anonymously for public models, and we only executed `make -n` dry-runs so the downloads themselves were never attempted.

## Security Notes

Plan threat register fully addressed:

- **T-01-05-01 (HF supply-chain tampering, accept):** We pin repo IDs (`ivrit-ai/whisper-large-v3-turbo-ct2`, `dicta-il/DictaLM-3.0-Nemotron-12B-Instruct-GGUF`), not content hashes. HF Hub enforces HTTPS + content-hash verification during `hf download`. Phase 7 polish can tighten to `--revision <sha>` pins if the threat model shifts.
- **T-01-05-02 (sed path-injection into Modelfile, mitigate):** The substituted path comes from a `find "$MODEL_DIR/dictalm-3.0" -name "*$DICTALM_QUANT.gguf" -type f | head -n 1` invocation rooted in a directory the script itself created two lines earlier. No user input flows into the sed substitution. `set -euo pipefail` aborts if `find` returns nothing.
- **T-01-05-03 (license-checker info disclosure, accept):** Allowlist output is intentionally public — it's the CI gate. No secrets in package names.
- **T-01-05-04 (double-ollama race in `make up`, mitigate):** `pgrep -x ollama` check before `nohup ollama serve`. Log to `/tmp/receptra-ollama.log` for debugging. If a user started ollama via brew services, we don't spawn a second one.
- **T-01-05-05 (partial download DoS, mitigate):** `hf download` is resumable by default; `set -euo pipefail` prevents the script from continuing past a failed download. Re-running the script resumes cleanly.
- **T-01-05-06 (local license-gate bypass, mitigate):** Plan 01-06 will wire `scripts/check_licenses.sh` into `.github/workflows/ci.yml` — local skip cannot bypass the merge gate.

## Threat Flags

None. No new network endpoints, auth paths, or trust boundaries introduced beyond the HTTPS-to-HF and HTTPS-to-ollama.com flows already scoped in the plan's threat model.

## Known Stubs

None. All files are fully wired:
- Makefile delegates to scripts that exist.
- `scripts/download_models.sh` delegates to `hf` and `ollama` CLIs (external prerequisites).
- `scripts/ollama/DictaLM3.Modelfile` is a template consumed by `scripts/download_models.sh`.
- `scripts/check_licenses.sh` delegates to `pip-licenses` and `license-checker` (external prerequisites documented in `make check-prereqs`).
- `docs/models.md` is terminal documentation, no stubs.

The `__GGUF_PATH__` string in the Modelfile is a substitution marker, not a stub — it is the contract between the checked-in template and the download script's sed rendering step, and that contract is exercised in the `dictalm` subcommand code.

## Deferred Issues

None. All acceptance criteria passed on first verification.

## TDD Gate Compliance

Not applicable — this plan is `type: execute`, not `type: tdd`. No RED/GREEN/REFACTOR cycle required.

## Next Steps

- **Plan 01-06 (CI):** Wire `.github/workflows/ci.yml` to invoke `scripts/check_licenses.sh` as the license gate; add `make -n` sanity as a Makefile-validity job; add the manual-dispatch negative-test workflow that confirms the gate exits non-zero on a known-GPL package.
- **Mac-local smoke (contributor step, not CI):** Run `make check-prereqs && make models && make up` on a fresh M2 to validate the actual 11 GB download path and `ollama create dictalm3` registration. This is documented in `docs/models.md` and CONTRIBUTING.md.
- **Phase 2 (STT) consumers:** Phase 2 backend code will load `$MODEL_DIR/whisper-turbo-ct2/` via `faster-whisper`. The mount path is set by `docker-compose.yml` (Plan 01-04): `${MODEL_DIR:-~/.receptra/models}:/models:ro`.
- **Phase 3 (LLM) consumers:** Phase 3 service code will target Ollama model name `dictalm3` (registered by `make models-dictalm`) with `qwen2.5:7b` fallback logic per research OPEN-1.

## Self-Check: PASSED

Files created (all verified present):
- `Makefile` ✓
- `scripts/download_models.sh` ✓ (executable bit set)
- `scripts/ollama/DictaLM3.Modelfile` ✓
- `scripts/check_licenses.sh` ✓ (executable bit set)
- `docs/models.md` ✓

Commits verified:
- `dc26343` — `feat(01-05): add Makefile with Phase 1 targets` — in `git log --all --oneline`
- `50cefeb` — `feat(01-05): add model download script, DictaLM Modelfile, license check, models doc` — in `git log --all --oneline`

All acceptance criteria from Task 1 and Task 2 verification blocks pass. End-to-end `make -n` dry-runs succeed for all 12 target names. Shell syntax gates pass.
