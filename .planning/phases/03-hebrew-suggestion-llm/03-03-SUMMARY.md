---
phase: 03-hebrew-suggestion-llm
plan: 03-03
subsystem: llm
tags: [llm, ollama, async-client, model-selection, fallback, retry, json-mode, hebrew, stt-isolation]

# Dependency graph
requires:
  - phase: 03-hebrew-suggestion-llm
    provides: Plan 03-01 — `ollama>=0.6.1,<1` pinned, Settings extended with `llm_model_tag`, `llm_model_fallback`, `llm_request_timeout_s`, `llm_temperature`, `llm_num_predict`, `llm_num_ctx`, `llm_top_p`; `tests/llm/conftest.py` live-test marker + `live_test_enabled()` helper
  - phase: 02-hebrew-streaming-stt
    provides: loguru as single backend logging sink (Plan 02-02) — Plan 03-03 emits structured `event="llm.model_selection"` and `event="llm.retry_failed"` on the same sink
provides:
  - "`receptra.llm.client` module — three-function surface + two custom exceptions"
  - "`get_async_client(host=None, timeout_s=None) -> ollama.AsyncClient` — bound to settings by default; httpx.Timeout-bounded (T-03-03-01)"
  - "`select_model(client) -> str` — probe primary → fallback → typed error; emits one structured loguru line with tags only (no transcript)"
  - "`retry_with_strict_json(client, model, base_messages) -> str | None` — ONE-shot bounded retry; stream=False + format='json' + Hebrew strict-JSON suffix on system message only"
  - "`OllamaModelMissingError` + `OllamaUnreachableError` plain Exception subclasses (engine maps onto LlmErrorEvent.code='ollama_unreachable')"
affects:
  - 03-04 (engine) — imports `get_async_client`, `select_model`, `retry_with_strict_json`, both custom exceptions; engine catches typed errors and yields `LlmErrorEvent`
  - 03-06 (CLI harness) — reuses `get_async_client` with `--ollama-host` pass-through; STT-isolation regression re-verified at harness boundary

# Tech tracking
tech-stack:
  added:
    - "ollama.AsyncClient — sole consumer surface (Plan 03-01 pinned the dep, Plan 03-03 wraps it)"
    - "httpx.ConnectError / httpx.ReadTimeout — caught at the AsyncClient call site to surface typed `OllamaUnreachableError`"
    - "httpx.Timeout — bounds every Ollama call (T-03-03-01 mitigation)"
  patterns:
    - "Cross-version response normalization: `_extract_models` accepts BOTH new ListResponse-with-.models-attr AND old dict {'models': [...]} shape; unknown shape returns [] (graceful degradation through typed-error path, never raises)."
    - "Tag-matching policy: exact match wins; otherwise repo-prefix match (split on `:`). `'dictalm3'` matches `'dictalm3:latest'`; `'qwen2.5:7b'` matches `'qwen2.5:14b'` (same repo)."
    - "Bounded one-retry contract: ONE attempt only, stream=False, format='json' (loose), broad except → None. Engine maps None to canonical refusal — closed loop, no retry storm (T-03-03-03)."
    - "Hebrew strict-JSON suffix appended to messages[0] (system) only; defensive `dict(m) for m in base_messages` copy keeps caller's list pristine and few-shots intact (T-03-03-06)."
    - "STT-isolation regression with sys.modules save/restore: the autouse conftest in `tests/conftest.py` pre-imports `receptra.lifespan` (which transitively imports `receptra.stt.*`), so the regression test compares the DELTA introduced by `import receptra.llm.client` rather than the absolute set. Save+restore prevents cross-test contamination of `test_package_reexports_public_surface` identity assertion."

key-files:
  created:
    - backend/src/receptra/llm/client.py
    - backend/tests/llm/test_client.py
  modified: []

key-decisions:
  - "Custom exceptions are plain `Exception` subclasses (NOT pydantic models). Engine maps onto `LlmErrorEvent.code='ollama_unreachable'`/`'parse_error'` at its boundary; client stays minimal."
  - "Tag matching is repo-prefix-tolerant by default. RESEARCH does not pin a specific Ollama tag suffix, and `dictalm3:latest` is the de-facto default after `make models dictalm`. Strict-exact match would force every contributor to align tag suffixes — repo-prefix match accepts any pulled variant."
  - "`retry_with_strict_json` returns `str | None`, NOT a parsed `SuggestionResponse`. Engine (Plan 03-04) owns the parse + validation so the retry helper has a single, narrow responsibility. Returns None on ANY failure (broad except by design — T-03-03-03)."
  - "Hebrew strict-JSON suffix `'\\n\\nהחזר אך ורק JSON תקין, ללא Markdown, ללא הסברים.'` is hardcoded in source so it forms part of the audited LLM-input surface. Modifying it requires plan amendment."
  - "STT-isolation test uses save+restore (not delete-and-reimport). Earlier draft permanently dropped `receptra.llm.*` from `sys.modules` and broke `test_schema.test_package_reexports_public_surface` (class-identity comparison across the package boundary). Save+restore around the regression's `import` keeps the assertion durable without re-running other tests under a `pytest_collection_modifyitems` hook."

patterns-established:
  - "Module-import regression at the smallest boundary: `tests/llm/test_client.py::test_client_module_does_not_import_receptra_stt` is the early canary on the `receptra.llm.* → receptra.stt.*` boundary. Plan 03-06 will re-verify the same property at the harness level for defense-in-depth (T-03-03-05)."
  - "Mocked AsyncClient pattern: `MagicMock(spec=['models'])` + `client.list = AsyncMock(return_value=fake_resp)` produces a deterministic, sub-millisecond test that mirrors the real ollama-python ListResponse shape. No live Ollama required; CI on ubuntu-latest stays green by self-skip on the live-only tests from Plan 03-01."

requirements-completed: [LLM-01]

# Metrics
duration: 5min
completed: 2026-04-26
---

# Phase 3 Plan 03-03: Ollama AsyncClient + Bounded Retry Helper Summary

**Three-function surface that decouples model-selection from the engine hot path: `get_async_client` (httpx.Timeout-bounded factory), `select_model` (primary → fallback → typed error with structured loguru observability), and `retry_with_strict_json` (one-shot bounded retry with Hebrew strict-JSON suffix on the system message and broad-except → None contract). Two custom exceptions (`OllamaUnreachableError`, `OllamaModelMissingError`) close the LLM-01 client layer.**

## Performance

- **Duration:** ~5 min (TDD across 1 task: client RED → GREEN with mid-cycle ruff cleanup + STT-isolation regression fix)
- **Started:** 2026-04-26T15:24:15Z
- **Completed:** 2026-04-26T15:29:28Z
- **Tasks:** 1 (`type="auto" tdd="true"`)
- **Files modified:** 2 (1 source, 1 test)

## Accomplishments

- **LLM-01 client surface published.** Plan 03-04 (engine) can `from receptra.llm.client import get_async_client, select_model, retry_with_strict_json, OllamaModelMissingError, OllamaUnreachableError` and wire the engine without any further plumbing.
- **`get_async_client(host=None, timeout_s=None)`** — defaults to `settings.ollama_host` + `settings.llm_request_timeout_s` (30 s); CLI harness in Plan 03-06 overrides via `--ollama-host`. Underlying httpx.AsyncClient is bound to `httpx.Timeout(timeout_s)` so a wedged Ollama process cannot hang the WS hot path (T-03-03-01).
- **`select_model(client)`** — primary `dictalm3` → fallback `qwen2.5:7b` → `OllamaModelMissingError`. Emits ONE structured loguru log line with `event="llm.model_selection"` + payload `{chosen, primary_missing, fallback_used, available}` (INFO on primary, WARN on fallback). Payload contains tags ONLY — no transcript text (T-03-03-04). Accepts BOTH the new `ollama-python 0.6.x` ListResponse-with-`.models`-attr shape AND older dict `{'models': [...]}` shape (test coverage for both paths).
- **`retry_with_strict_json(client, model, base_messages)`** — locked one-shot retry contract:
  - `stream=False` (we already streamed once and parse failed; trade latency for correctness)
  - `format='json'` (loose Ollama JSON mode, NOT `format=<schema>` mid-stream — RESEARCH §3.5 + §9 + upstream ollama-python issues #14440 + #15260)
  - Hebrew strict-JSON suffix `'\n\nהחזר אך ורק JSON תקין, ללא Markdown, ללא הסברים.'` appended to `messages[0]` (system) ONLY — few-shots intact, defensive copy of caller's list (T-03-03-06)
  - Returns raw completion string on success; `None` on httpx.ConnectError, httpx.ReadTimeout, broad Exception, empty body, or missing system message
  - Engine maps `None` → canonical Hebrew refusal — closed loop, no retry storm (T-03-03-03)
- **STT-isolation regression test green** — `import receptra.llm.client` introduces ZERO new `receptra.stt.*` modules. Test uses sys.modules save+restore so it does not break the schema's class-identity assertion in another file.

## Final ollama-python list-response shape detected

The plan's `<output>` section asks for the response shape. Both shapes are normalized by `_extract_models`:

- **New shape (ollama-python 0.6.x — current pin):** `ListResponse(models=[Model(model='dictalm3:latest', ...), Model(model='qwen2.5:7b', ...)])`. Each `Model` has a `.model` attribute carrying the tag.
- **Old shape (forward-compat):** plain dict `{'models': [{'model': 'qwen2.5:7b'}, {'name': 'bge-m3:latest'}]}`. Both `'model'` and `'name'` keys are accepted (older versions used `'name'`).

Tests cover BOTH shapes via `test_extract_models_handles_list_response_object` + `test_extract_models_handles_dict_old_api` + `test_select_model_handles_old_dict_api`.

## Confirmation: no `receptra.stt` modules entered `sys.modules` after `import receptra.llm.client`

Verified directly:

```
$ uv run python -c "import receptra.llm.client, sys; assert not any(k.startswith('receptra.stt') for k in sys.modules), [k for k in sys.modules if k.startswith('receptra.stt')]; print('STT-clean OK')"
STT-clean OK
```

In tests, the autouse conftest at `backend/tests/conftest.py` imports `receptra.lifespan` (which transitively imports `receptra.stt.*`) for Whisper/VAD stub patching. Therefore the regression test compares the DELTA introduced by `import receptra.llm.client` — not the absolute set — and asserts the delta is empty. Save+restore around the import keeps `receptra.llm.*` class identity stable across the rest of the test session.

## Whether the test runner caught any transitive import surprise

Yes — one cross-test ordering bug surfaced:

1. **Initial draft of the STT-isolation test** permanently deleted `receptra.llm.*` from `sys.modules` to force re-import. This re-execution created NEW class objects for `Suggestion`, `SuggestionResponse`, etc.
2. **Test ordering effect:** when `test_client.py` ran before `test_schema.py::test_package_reexports_public_surface`, the schema test's identity assertion `_Suggestion is Suggestion` failed because `Suggestion` (top-of-file import in test_schema.py) was the OLD pre-deletion class object, while `_Suggestion` (re-imported inside the test body) was the new post-deletion object.
3. **Fix (Rule 1 — bug in test fixture):** save the original `receptra.llm.*` entries before deletion, drop them, run the import-under-test, then restore the originals in a `finally` block. Net effect: the regression test sees a fresh import of `receptra.llm.client`, but the rest of the package's class objects remain identical across the test session.

Outcome: full backend suite went from `1 failed, 144 passed` → `145 passed, 3 skipped` after the fix.

## Task Commits

TDD discipline (RED → GREEN):

1. **Task 1 RED — failing tests for receptra.llm.client** — `fa9f8f6` (test) — 33 unit tests fail with `ModuleNotFoundError: No module named 'receptra.llm.client'`.
2. **Task 1 GREEN — implement receptra.llm.client** — `59f61d2` (feat) — 33 tests pass; ruff + mypy strict clean across 11 files; full backend suite 145 pass / 3 skip.

**Plan metadata:** appended below as final docs commit.

## Files Created/Modified

- `backend/src/receptra/llm/client.py` — Ollama AsyncClient factory + select_model probe + retry_with_strict_json helper + 2 custom Exception subclasses + 2 internal helpers (`_extract_models`, `_tag_present`). 297 LOC.
- `backend/tests/llm/test_client.py` — 33 unit tests across 5 sections: factory, helpers, select_model, retry_with_strict_json, STT-isolation regression. All offline; mocked AsyncClient via `MagicMock(spec=['models'])` + `AsyncMock`. 396 LOC.

## Decisions Made

All decisions were locked into the plan front-matter `<context>` section. The execution-time decisions:

- **Plain `Exception` subclasses, not pydantic models** — the engine boundary maps these onto `LlmErrorEvent` codes; client stays minimal and the exception classes carry only a string payload.
- **Repo-prefix tag matching is the default** — `'dictalm3'` matches both `'dictalm3'` AND `'dictalm3:latest'`; `'qwen2.5:7b'` matches both exact and `'qwen2.5:*'` (any tag of the same repo). Strict-exact match would make tag-suffix drift between contributors a tripwire; repo-prefix match accepts the de-facto `:latest` suffix `make models dictalm` produces.
- **`format='json'` (loose Ollama JSON mode), not `format=<schema>`** — RESEARCH §3.5 + §9 explicitly note that `format=<schema>` constraint does not strictly hold mid-stream (upstream ollama-python issues #14440, #15260). The retry path uses `stream=False`, but `format='json'` keeps the contract simple and reusable from a future engine path.
- **Broad `except Exception` in `retry_with_strict_json`** — by design per T-03-03-03. A malformed Ollama response or unexpected library error must NEVER propagate up the retry boundary; engine relies on the `None` return to deterministically fall back to the canonical Hebrew refusal. WARN log captures the error class + message for audit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test fixture used invalid HTTP port `99999`**

- **Found during:** Task 1 GREEN — first GREEN test run.
- **Issue:** `test_get_async_client_accepts_override` initially passed `host="http://localhost:99999"`. Ollama-python's `_parse_host` eagerly parses through `urllib.parse.urlsplit`, which calls `.port` and raises `ValueError: Port out of range 0-65535` on construction.
- **Fix:** Changed override host to the canonical `"http://localhost:11434"` (Ollama's default port).
- **Files modified:** `backend/tests/llm/test_client.py`
- **Verification:** Test passes; intent (override accepted) preserved.
- **Committed in:** `59f61d2` (Task 1 GREEN commit)

**2. [Rule 1 - Bug] STT-isolation test broke schema test's identity assertion**

- **Found during:** Task 1 GREEN — full backend suite re-run after isolated GREEN tests passed.
- **Issue:** Initial draft of `test_client_module_does_not_import_receptra_stt` permanently deleted `receptra.llm.*` from `sys.modules` before importing `receptra.llm.client`. Re-execution created NEW class objects, breaking the class-identity assertion in `test_schema.test_package_reexports_public_surface` when the schema test ran AFTER the client test.
- **Fix:** Save the original `receptra.llm.*` entries via `saved_llm: dict[str, Any] = {}; for k in list(sys.modules): if k.startswith('receptra.llm'): saved_llm[k] = sys.modules.pop(k)`, run the regression import, then restore in a `finally` block. Documented inline.
- **Files modified:** `backend/tests/llm/test_client.py`
- **Verification:** `uv run pytest tests/llm/test_client.py tests/llm/test_schema.py::test_package_reexports_public_surface -v` → 34 passed; full suite 145 pass / 3 skip.
- **Committed in:** `59f61d2` (Task 1 GREEN commit)

**3. [Rule 1 - Bug] Ruff cleanup on first GREEN — 7 ruff issues**

- **Found during:** Task 1 GREEN — first ruff run.
- **Issue:** Initial draft contained: SIM110 (`for` loop in `_tag_present` should be `any(...)`), RUF100 (unused `# noqa: BLE001` directive — BLE rule not enabled), 2× E702 (semicolon-multiple-statements in test fixture builders), 2× E501 (line-too-long in test docstring + JSON literal), N814 (`from pydantic import BaseModel as _BM` aliases CamelCase as constant).
- **Fix:** Replaced loop with `any(...)`; removed the unused noqa; split semicolon lines; shortened docstring + wrapped JSON literal; renamed import to `BaseModel` (top of test function). All inline.
- **Files modified:** `backend/src/receptra/llm/client.py`, `backend/tests/llm/test_client.py`
- **Verification:** `uv run ruff check src/receptra/llm tests/llm` → "All checks passed!"; `uv run mypy ...` → "Success: no issues found in 11 source files".
- **Committed in:** `59f61d2` (Task 1 GREEN commit)

---

**Total deviations:** 3 auto-fixed (3 bugs / lint cleanup, 0 architectural).
**Impact on plan:** All deviations were within the inline "Pure, mocked, no I/O — runs in milliseconds in CI" surface; no scope creep. The STT-isolation save/restore pattern is now an established pattern other Phase 3 tests can copy if they need similar regression coverage.

## Issues Encountered

None beyond the 3 deviations above. The mocked-AsyncClient pattern produced sub-millisecond tests (33 tests in ~0.65 s), and no live Ollama was required at any point in the GREEN phase.

## TDD Gate Compliance

Verified in `git log`:

- **RED:** `fa9f8f6` test(03-03): add failing tests for receptra.llm.client (Ollama AsyncClient + select_model + retry_with_strict_json)
- **GREEN:** `59f61d2` feat(03-03): implement receptra.llm.client (Ollama AsyncClient + select_model + retry_with_strict_json)

RED → GREEN sequence complete. No REFACTOR needed (initial GREEN was already minimal; ruff cleanup folded into the GREEN commit per the plan's verification gate requirement).

## User Setup Required

None. This plan is pure-mock + pure-Python — no environment variables, no model downloads, no service configuration. Ollama remains unstarted on this executor; live tests from Plan 03-01 still self-skip.

## Next Phase Readiness

**Plan 03-04 (Wave 3 — engine orchestration) — READY:**

- Imports `from receptra.llm.client import get_async_client, select_model, retry_with_strict_json, OllamaModelMissingError, OllamaUnreachableError` ✅
- Catches `OllamaUnreachableError` → yields `LlmErrorEvent(code='ollama_unreachable')` ✅
- Catches `OllamaModelMissingError` → yields `LlmErrorEvent(code='ollama_unreachable', detail='...')` ✅
- Calls `retry_with_strict_json(client, model, base_messages)` once on first parse failure; maps `None` → canonical Hebrew refusal ✅

**Plan 03-06 (Wave 4 — CLI harness) — READY:**

- Reuses `get_async_client(host=...)` with `--ollama-host` flag pass-through ✅
- STT-isolation regression already established at module boundary; harness re-verifies at integration boundary (T-03-03-05 defense-in-depth) ✅

**Phase 7 prompt eval — READY for correlation:**

- `event="llm.model_selection"` loguru line with `{chosen, primary_missing, fallback_used}` payload lets audit rows correlate prompt results against which model actually served ✅

No blockers. Phase 3 has 3 plans remaining (03-04, 03-05, 03-06).

## Self-Check: PASSED

Verified post-write:

- ✅ `backend/src/receptra/llm/client.py` exists
- ✅ `backend/tests/llm/test_client.py` exists
- ✅ Commit `fa9f8f6` (RED) in `git log`
- ✅ Commit `59f61d2` (GREEN) in `git log`
- ✅ `cd backend && uv run pytest tests/llm/test_client.py -x -v` → 33 passed
- ✅ `cd backend && uv run pytest` → 145 passed, 3 skipped (live opt-in)
- ✅ `cd backend && uv run ruff check src/receptra/llm tests/llm` → All checks passed!
- ✅ `cd backend && uv run mypy src/receptra/llm tests/llm` → Success: no issues found in 11 source files
- ✅ `python -c "from receptra.llm.client import get_async_client, select_model, retry_with_strict_json, OllamaModelMissingError, OllamaUnreachableError; print('OK')"` → OK
- ✅ `python -c "import receptra.llm.client, sys; assert not any(k.startswith('receptra.stt') for k in sys.modules); print('STT-clean OK')"` → STT-clean OK

---
*Phase: 03-hebrew-suggestion-llm*
*Plan: 03-03*
*Completed: 2026-04-26*
