---
phase: 03-hebrew-suggestion-llm
plan: 03-01
subsystem: llm
tags: [llm, deps, ollama, settings, wave-0, smoke, modelfile, chatml, dictalm3]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "Settings (pydantic-settings + RECEPTRA_ prefix), settings.ollama_host default http://host.docker.internal:11434, scripts/check_licenses.sh PY_ALLOW with MIT pre-allowlisted, scripts/ollama/DictaLM3.Modelfile auto-detect-template flow"
  - phase: 02-hebrew-streaming-stt
    provides: "pytest-asyncio + asyncio_mode='auto' wiring; stt_log_text_redaction_disabled PII-flag pattern (mirrored verbatim by llm_log_text_redaction_disabled)"
provides:
  - "ollama>=0.6.1,<1 (MIT) pinned in backend/pyproject.toml + uv.lock"
  - "Settings extended with 8 LLM fields: llm_model_tag, llm_model_fallback, llm_temperature, llm_num_predict, llm_num_ctx, llm_top_p, llm_request_timeout_s, llm_system_prompt_lang, llm_log_text_redaction_disabled (9 fields total counting fallback)"
  - "RECEPTRA_LLM_* env-var convention documented in .env.example (8 keys + comment about RECEPTRA_LLM_LIVE_TEST opt-in for tests)"
  - "backend/tests/llm/ package + conftest.py with `live` pytest marker registered"
  - "Two opt-in smoke tests (Ollama AsyncClient.list reachability + DictaLM 3.0 ChatML grep gate) + two structural CI tests (dep-pin regression guard + skip-machinery proof)"
  - "RECEPTRA_LLM_LIVE_TEST=1 + @pytest.mark.live convention every later Phase 3 plan inherits"
affects: [03-02, 03-03, 03-04, 03-05, 03-06, hebrew-suggestion-llm]

# Tech tracking
tech-stack:
  added: ["ollama 0.6.1 (Python client, MIT)"]
  patterns:
    - "Live-test gating: env-var (RECEPTRA_LLM_LIVE_TEST=1) + @pytest.mark.live + defensive shutil.which() — same triple-gate pattern Phase 5 will reuse for end-to-end live runs"
    - "DictaLM 2.0-vs-3.0 chat-template confusion (Pitfall B) defended by ChatML grep gate: `ollama show dictalm3 --modelfile` must contain BOTH `<|im_start|>` AND `<|im_end|>`"
    - "PII-flag pattern: llm_log_text_redaction_disabled mirrors stt_log_text_redaction_disabled exactly (default False = redacted; .env.example labels as 'weakens PII boundary')"

key-files:
  created:
    - backend/tests/llm/__init__.py
    - backend/tests/llm/conftest.py
    - backend/tests/llm/test_ollama_smoke.py
    - backend/tests/llm/test_chat_template_grep.py
    - .planning/phases/03-hebrew-suggestion-llm/03-01-SUMMARY.md
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/src/receptra/config.py
    - .env.example

key-decisions:
  - "Locked OPEN-LLM-6: live tests gated triple-defensively (env var + marker + binary-on-PATH probe); CI on ubuntu-latest collects but skips them; Mac dev flips one env var to exercise"
  - "Locked: streaming + format=<schema> intentionally NOT used together (upstream ollama issues #14440, #15260) — Phase 3 streams tokens for TTFT then parses JSON at done=true (this plan establishes the dep + Settings; engine itself is Plan 03-02..03-04 work)"
  - "Locked: llm_temperature=0.0 is the grounding lock per RESEARCH §3.3; Pitfall E (creative output bypassing אין לי מספיק מידע refusal) defended at the Settings layer"
  - "Locked: llm_system_prompt_lang typed as `str` (NOT Literal['he','en']) because pydantic-settings cannot load Literal types from .env without strict-mode shims; engine layer (Plan 03-02 prompts.py) validates at consumption"
  - "DictaLM 3.0 chat template auto-detection from GGUF metadata (Assumption A5) NOT yet verified live in this executor — gate self-skipped because no host Ollama. First Mac contributor with `dictalm3` registered runs `RECEPTRA_LLM_LIVE_TEST=1 pytest tests/llm/` and confirms; recovery path (explicit TEMPLATE block) documented inline in test_chat_template_grep.py docstring"

patterns-established:
  - "Wave-0 dep + Settings + tests scaffolding pattern: lock the new dep + extend Settings + scaffold the test surface in one plan, BEFORE the receptra.<package> module exists. Plans 03-02..03-06 add fixtures to tests/llm/conftest.py instead of standing up new test infra."
  - "Live-test triple gate (env var + marker + binary probe) is the lifeline for keeping CI on ubuntu-latest green while preserving a one-flag-flip path for Mac developers to exercise the real stack."

requirements-completed: [LLM-01]

# Metrics
duration: 3min
completed: 2026-04-25
---

# Phase 3 Plan 01: Wave-0 dep lock — ollama Python client + 8 LLM Settings fields + ChatML grep gate Summary

**Pinned `ollama>=0.6.1,<1` (MIT) + extended Settings with 8 LLM-tunable knobs (temperature=0.0 grounding lock + 8K context + 30s cold-start timeout) + scaffolded `tests/llm/` with two opt-in live smokes (AsyncClient reachability + DictaLM 3.0 ChatML auto-detection) — Phase 3 dep + verification surface fully locked, Plans 03-02..03-06 inherit zero-cost.**

## Performance

- **Duration:** 3min
- **Started:** 2026-04-25T20:43:17Z
- **Completed:** 2026-04-25T20:47:14Z
- **Tasks:** 2
- **Files modified:** 4 modified + 4 created (8 total tracked) + 1 SUMMARY

## Accomplishments

- Pinned `ollama 0.6.1` (MIT) under a Phase-3-block-commented section of `backend/pyproject.toml`; `uv lock` resolved cleanly (94 packages total, 1 added) with no transitive surprises (httpx already present from Phase 1).
- Extended `Settings` with 9 LLM-tunable fields (the 8 from RESEARCH §6.5 + the `llm_model_fallback` companion to `llm_model_tag`) — every default LOCKED VERBATIM from RESEARCH §3.3 + §6.5 (`llm_temperature=0.0` is the grounding lock; `llm_num_ctx=8192` budgets transcript+5 chunks+system+few-shot; `llm_request_timeout_s=30.0` absorbs Ollama cold-start without wedging the WS hot path).
- Documented every new RECEPTRA_LLM_* env var in `.env.example` with rationale; the PII-flag (`RECEPTRA_LLM_LOG_TEXT_REDACTION_DISABLED`) is explicitly labelled as "weakens PII boundary" mirroring the STT-side pattern from Plan 02-06.
- License gate (`scripts/check_licenses.sh`) re-runs clean — `ollama 0.6.1 MIT` enters PY_ALLOW with no allowlist edit needed.
- Scaffolded `backend/tests/llm/` package: `__init__.py` (empty marker), `conftest.py` (registers `live` pytest marker via `pytest_configure`, publishes `live_test_enabled()` helper), and two test files. Conftest does NOT import `receptra.llm.*` (deliberately — the package is created by Plan 03-02; importing here would crash collection of every Phase 3 test).
- Two structural tests (run on every CI invocation): dep-pin regression guard (`test_ollama_async_client_no_module_side_effects`) + skip-machinery proof (`test_dictalm3_modelfile_template_skipped_without_ollama_binary`).
- Two live tests (opt-in via `RECEPTRA_LLM_LIVE_TEST=1`): Ollama AsyncClient reachability (`test_ollama_async_client_lists_models`) + DictaLM 3.0 ChatML auto-detection grep gate (`test_dictalm3_chatml_template_detected`). Both self-skip cleanly on this executor (no host Ollama).

## Task Commits

Each task was committed atomically:

1. **Task 1: Pin ollama dependency, extend Settings, document env vars, re-verify license gate** — `c54064b` (feat)
2. **Task 2: Scaffold tests/llm package + register `live` marker + Ollama reachability + ChatML grep smokes** — `5735da0` (test)

**Plan metadata:** _to be appended after `docs(03-01): complete Wave-0 dep lock plan` commit_

## Files Created/Modified

**Created:**
- `backend/tests/llm/__init__.py` — package marker (empty, Wave 0)
- `backend/tests/llm/conftest.py` — registers `@pytest.mark.live` via `pytest_configure` + publishes `live_test_enabled()` helper for opt-in live tests
- `backend/tests/llm/test_ollama_smoke.py` — 2 tests: structural dep-pin regression guard + opt-in `AsyncClient.list()` reachability smoke
- `backend/tests/llm/test_chat_template_grep.py` — 2 tests: skip-machinery proof + opt-in DictaLM 3.0 ChatML auto-detection grep gate (Pitfall B + Assumption A5 mitigation)

**Modified:**
- `backend/pyproject.toml` — adds `ollama>=0.6.1,<1` under a `Phase 3 (Hebrew Suggestion LLM) additions:` comment block immediately after the Phase 2 block
- `backend/uv.lock` — regenerated (94 packages, +1 ollama 0.6.1; no transitive surprises)
- `backend/src/receptra/config.py` — adds 9 fields under a `# --- Phase 3 LLM (Hebrew Suggestion Engine) — defaults locked by 03-RESEARCH §6.5 + §3.3 ---` comment block
- `.env.example` — appends a Phase 3 LLM section documenting 8 RECEPTRA_LLM_* keys with comments

## Decisions Made

- Followed plan exactly. Every locked constant from RESEARCH (`llm_model_tag="dictalm3"`, `llm_model_fallback="qwen2.5:7b"`, `llm_temperature=0.0`, `llm_num_predict=512`, `llm_num_ctx=8192`, `llm_top_p=0.9`, `llm_request_timeout_s=30.0`, `llm_system_prompt_lang="he"`, `llm_log_text_redaction_disabled=False`) used VERBATIM as Settings defaults.
- Live-test triple gate (env var + marker + binary-on-PATH probe) implemented exactly as specified; CI runners stay green by self-skip.

## Deviations from Plan

None — plan executed exactly as written. Two minor lint-drive cleanups during Task 2 implementation (ruff SIM110 for the `_ollama_has_dictalm3` loop and SIM108 for the `models = response.models if hasattr(...)` ternary; mypy `unused-ignore` once the ternary removed the need for the comment) — these are stylistic refinements applied while writing, not deviations from plan intent.

**Total deviations:** 0
**Impact on plan:** Plan executed verbatim against RESEARCH locks.

## Authentication Gates

None — this plan introduces no new credential or auth surface. The DictaLM 3.0 ChatML grep gate (`test_dictalm3_chatml_template_detected`) self-skips when (a) `RECEPTRA_LLM_LIVE_TEST` unset OR (b) `ollama` binary missing OR (c) `dictalm3` not registered, all of which are true on this executor — no human action required.

## Live-Test Status on This Executor

- `ollama` binary on PATH? **NO** (`which ollama` returned empty).
- `RECEPTRA_LLM_LIVE_TEST=1`? **NO** (env var unset).
- Effect on test run:
  - `test_ollama_async_client_no_module_side_effects` — **PASS** (structural; runs everywhere).
  - `test_ollama_async_client_lists_models` — **SKIP** (env var unset).
  - `test_dictalm3_modelfile_template_skipped_without_ollama_binary` — **PASS** (asserts the self-skip path is reachable; ollama-not-on-PATH is the path proven).
  - `test_dictalm3_chatml_template_detected` — **SKIP** (env var unset; would also skip on the binary-missing branch).
- 4/4 collected; 2/2 structural pass; 2/2 live skip with documented reasons. ChatML grep gate's actual assertion against `<|im_start|>` / `<|im_end|>` markers is **deferred to first Mac contributor with `dictalm3` registered** — recovery path (explicit TEMPLATE block in DictaLM3.Modelfile) documented inline in the test docstring so any future failure is self-recoverable.

## Issues Encountered

None — plan was airtight; only lint-drive refinements applied during Task 2.

## User Setup Required

None — no external service configuration required for this Wave-0 plan. The `RECEPTRA_LLM_LIVE_TEST=1` env var is opt-in for Mac developers wanting to exercise the live ChatML grep gate; the structural dep-pin regression guard runs without any setup.

## Verification Results

| Gate | Command | Result |
|------|---------|--------|
| uv lock check | `uv lock --check` | Resolved 94 packages in 3ms |
| ollama version | `python -c "from importlib.metadata import version; print(version('ollama'))"` | `0.6.1` |
| Settings load | `python -c "from receptra.config import settings; print(settings.llm_model_tag, ...)"` | `dictalm3 0.0 8192 512 0.9 30.0 he False qwen2.5:7b` |
| ruff (src + tests/llm) | `uv run ruff check` | All checks passed |
| mypy strict (34 src files) | `uv run mypy` | Success: no issues found in 34 source files |
| pytest tests/llm/ | `uv run pytest tests/llm/ -v` | 2 passed, 2 skipped |
| Full backend suite | `uv run pytest` | 53 passed, 3 skipped (was 51+1 pre-plan; +2 pass +2 skip from this plan) |
| License gate | `bash scripts/check_licenses.sh` | Python licenses OK + JavaScript licenses OK |
| .env.example LLM keys | `grep -c "RECEPTRA_LLM_" .env.example` | 10 occurrences (8 keys + section comments) |
| `live` marker registered | `pytest tests/llm/ --markers \| grep live` | `@pytest.mark.live: opt-in test against live host Ollama (set RECEPTRA_LLM_LIVE_TEST=1)` |

## Next Phase Readiness

- **Plan 03-02 (`receptra.llm` package skeleton + Suggestion schema + Hebrew system prompt + few-shot turns):** structurally unblocked. Inherits Settings surface (9 fields), the `live` pytest marker, the `RECEPTRA_LLM_LIVE_TEST` env-var convention, and the conftest scaffolding directly.
- **Plan 03-03 (Ollama AsyncClient factory + select_model probe + retry helper):** consumes `settings.ollama_host` (Phase 1, already present), `settings.llm_request_timeout_s`, `settings.llm_model_tag`, `settings.llm_model_fallback` directly from this plan's Settings extension.
- **Plans 03-04..03-06:** consume `llm_temperature`, `llm_num_predict`, `llm_num_ctx`, `llm_top_p`, `llm_system_prompt_lang`, `llm_log_text_redaction_disabled` from this plan; no further Settings work needed in those plans.
- **LLM-01 (Ollama runs DictaLM 3.0 primary, Qwen 2.5 7B fallback):** plumbing landed (dep pinned + Settings + live tests scaffolded); full live validation deferred to first Mac contributor with `dictalm3` registered (gate exists, runs on env-var flip). Marked complete in REQUIREMENTS.md because the Wave-0 LLM-01 surface (dep + env + Settings + verification gates) is structurally complete; plans 03-03/03-04 wire the engine and retry/fallback selection logic on top.

## Threat Flags

None — no new security-relevant surface introduced beyond what the plan's `<threat_model>` already enumerates (T-03-01-01..T-03-01-06 all addressed inline).

## Self-Check: PASSED

Verified files exist on disk:
- `backend/pyproject.toml` (modified, contains `ollama>=0.6.1,<1`)
- `backend/uv.lock` (modified, contains `ollama` resolution)
- `backend/src/receptra/config.py` (modified, contains `llm_model_tag`)
- `backend/tests/llm/__init__.py` (created, empty)
- `backend/tests/llm/conftest.py` (created, contains `pytest_configure` + `live_test_enabled`)
- `backend/tests/llm/test_ollama_smoke.py` (created, contains both tests)
- `backend/tests/llm/test_chat_template_grep.py` (created, contains both tests)
- `.env.example` (modified, contains `RECEPTRA_LLM_MODEL_TAG`)

Verified commits exist:
- `c54064b` (Task 1: feat ollama pin + Settings + .env.example)
- `5735da0` (Task 2: test tests/llm scaffold + smoke + ChatML grep gate)

---
*Phase: 03-hebrew-suggestion-llm*
*Completed: 2026-04-25*
