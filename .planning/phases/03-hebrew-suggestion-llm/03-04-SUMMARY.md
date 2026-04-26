---
phase: 03-hebrew-suggestion-llm
plan: 03-04
subsystem: llm
tags: [llm, engine, async-generator, streaming, grounding, parse, retry, ttft, ollama, dictalm, hebrew]

# Dependency graph
requires:
  - phase: 03-hebrew-suggestion-llm/03-01
    provides: ollama dep pin + Settings llm_* fields + @pytest.mark.live registration
  - phase: 03-hebrew-suggestion-llm/03-02
    provides: receptra.llm.schema (Suggestion/SuggestionResponse/SuggestionEvent union/ChunkRef) + receptra.llm.prompts (build_messages/DoS bounds)
  - phase: 03-hebrew-suggestion-llm/03-03
    provides: receptra.llm.client (get_async_client/select_model/retry_with_strict_json + OllamaUnreachableError/OllamaModelMissingError)
provides:
  - receptra.llm.engine.generate_suggestions AsyncGenerator[SuggestionEvent, None] (LLM-02 internal interface)
  - LLM-03 grounding enforcement at engine layer (hard short-circuit + canonical refusal)
  - LLM-04 parsed Ollama output to SuggestionResponse (with markdown-fence tolerance + bounded retry)
  - LlmCallTrace frozen dataclass (consumed by Plan 03-05 metrics + audit)
  - _CANONICAL_REFUSAL Suggestion (RESEARCH §5.5 byte-exact)
  - _strip_markdown_fences pure helper (parametrized regression-tested)
  - record_call callback hook (default no-op; Plan 03-05 wires it)
  - 24 mocked-engine behavioral tests + 2 opt-in live tests (DictaLM 3.0 round-trip + grounding-refusal contract)
affects: [03-05-metrics-audit, 03-06-cli-harness, 04-rag, 05-integration-hot-path, 06-frontend]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "AsyncGenerator orchestration: short-circuit, stream, parse, retry, error-envelope, finally-callback — five-path single-function design"
    - "Pure-streaming engine with persistence concern decoupled via record_call(LlmCallTrace) hook — Plan 03-05 wraps without modifying engine.py"
    - "Bounded retry-on-parse-failure: ONE attempt only, no exponential backoff, no second retry — RESEARCH §6.2 step 7"
    - "Markdown fence stripping helper as a pure unit-testable function — applied BEFORE pydantic parse on both first stream + retry response"
    - "Hard short-circuit BEFORE any Ollama call when context_chunks is empty OR transcript.strip() is empty — saves ~2s of model time and is the strongest LLM-03 grounding defense"
    - "model_missing collapsed onto wire-level ollama_unreachable code — keeps LlmErrorEvent.code Literal narrow at 4 values; granular status retained on LlmCallTrace for audit"
    - "Defense-in-depth callback safety: contextlib.suppress(Exception) around record_call invocation in finally block — buggy callbacks must NEVER crash the engine generator"
    - "Module-reference monkeypatching pattern (engine_module, 'attr_name') instead of string path 'receptra.llm.engine.attr_name' — bypasses pytest derive_importpath getattr-walk vulnerability when sibling tests mutate sys.modules"

key-files:
  created:
    - "backend/src/receptra/llm/engine.py"
    - "backend/tests/llm/test_engine.py"
    - "backend/tests/llm/test_engine_live.py"
  modified: []

key-decisions:
  - "LlmCallTrace defined IN engine.py (not in schema.py) because it is a structural trace, not a wire schema — Plan 03-05 imports it and converts to its own LlmCallMetrics for loguru+SQLite persistence; the decoupling lets engine tests run without a writable audit DB"
  - "Streaming chat call deliberately omits format=<schema> kwarg; only retry_with_strict_json uses format='json' (loose) with stream=False — Pitfall A / RESEARCH §3.5 / upstream ollama-python issues #14440 + #15260; regression test asserts kwargs.get('format') is None during streaming"
  - "Empty context_chunks OR transcript.strip()=='' → short-circuit BEFORE any Ollama call, BEFORE build_messages, BEFORE select_model — saves ~2s of model time and is the strongest LLM-03 grounding defense (RESEARCH §5.5 layer 1)"
  - "On parse-error path, BOTH LlmErrorEvent AND CompleteEvent are yielded (in that order) — consumers always receive a terminal CompleteEvent; this differs from the ollama_unreachable / timeout paths which emit ONLY LlmErrorEvent (no terminal CompleteEvent) — those are explicit error modes for Phase 5 INT-04 graceful-degradation branch"
  - "Markdown fence stripping helper applied to BOTH the first streamed assembly AND the retry_with_strict_json response — because retry uses format='json' but the helper is idempotent on clean JSON so the double-apply is safe"
  - "TTFT measured with time.perf_counter() (monotonic) on first non-empty content delta — sentinel -1 when no token ever arrived (e.g. on parse-error path with empty stream)"
  - "Engine NEVER calls loguru/sqlite3 directly — all instrumentation goes through record_call callback (Plan 03-05 owns redaction + persistence). Engine.py logging surface: ZERO."
  - "OllamaModelMissingError mapped onto LlmErrorEvent(code='ollama_unreachable', detail='model_missing: ...') for wire — keeps the LlmErrorEvent.code Literal allowlist narrow at 4 values; LlmCallTrace.status carries the granular 'model_missing' for Phase 7 audit-level analysis"
  - "Engine catches build_user_message ValueError (DoS bounds from Plan 03-02) and yields LlmErrorEvent(code='no_context', detail=...) — DoS guard structurally prevents giant prompts from ever reaching Ollama"
  - "record_call invariant: invoked EXACTLY ONCE per generate_suggestions invocation regardless of which path; default no-op (lambda); failures swallowed via contextlib.suppress in finally block — defense in depth even though Plan 03-05's record_call also swallows internally"

patterns-established:
  - "Module-reference monkeypatching: when a sibling test file mutates sys.modules to test STT-isolation regressions, pass the module object directly to monkeypatch.setattr(module, 'attr', new) instead of a string path 'pkg.module.attr' — bypasses pytest derive_importpath's getattr-walk on the package object whose attributes may be wiped during the save+restore dance"
  - "Pure-streaming engine + callback hook for persistence: engine.py emits typed events and signals via record_call(LlmCallTrace); Plan 03-05 wraps with metrics + SQLite without modifying engine.py — keeps engine tests offline + writable-DB-free, and lets Phase 5 substitute its own audit behavior"
  - "Five-path single-function async generator: short-circuit / happy / parse-retry / unreachable / timeout — all observable from one entry point with deterministic event ordering and a single finally-block callback invocation"
  - "Wire-vs-audit error code split: LlmErrorEvent.code stays narrow (4-value Literal) while LlmCallTrace.status keeps granular per-path values (7) — consumer switches stay total without losing audit fidelity"

requirements-completed: [LLM-02, LLM-03, LLM-04]

# Metrics
duration: ~7min
completed: 2026-04-26
---

# Phase 3 Plan 04: Hebrew Suggestion Engine Summary

**`receptra.llm.engine.generate_suggestions` AsyncGenerator publishes the LLM-02 internal interface — five paths (short-circuit/happy/parse-retry/unreachable/timeout) from a single function with TTFT instrumentation, bounded JSON-retry, markdown fence tolerance, and decoupled record_call hook for Plan 03-05 metrics+audit.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-04-26T15:36:35Z
- **Completed:** 2026-04-26T15:42:57Z
- **Tasks:** 2 (TDD pair for engine.py + opt-in live test pair)
- **Files modified:** 0
- **Files created:** 3

## Accomplishments

- `receptra.llm.engine.generate_suggestions(transcript, context_chunks, *, request_id=None, model=None, record_call=None) -> AsyncGenerator[SuggestionEvent, None]` published — LLM-02 internal interface Phase 4 RAG and Phase 5 hot-path consume directly
- Five paths all observable from a single function with deterministic event ordering and exactly-once finally-callback
- Hard short-circuit on empty context or whitespace transcript → canonical refusal CompleteEvent BEFORE any Ollama call (LLM-03 strongest grounding defense, RESEARCH §5.5 layer 1)
- Bounded ONE-shot parse retry via `retry_with_strict_json` (Plan 03-03) on pydantic.ValidationError or json.JSONDecodeError — recovery yields CompleteEvent with status='parse_retry_ok'; exhaustion yields LlmErrorEvent + canonical refusal CompleteEvent
- Markdown-fence-wrapped JSON parses successfully via `_strip_markdown_fences` helper (parametrized 6-case unit tests + integration regression)
- LlmCallTrace frozen dataclass exposes per-call structural data for Plan 03-05 metrics + audit via record_call callback hook (default no-op)
- Two opt-in live DictaLM 3.0 tests gated behind RECEPTRA_LLM_LIVE_TEST=1: structural smoke (token+complete+TTFT) + grounding-refusal contract (irrelevant context → 'אין לי מספיק מידע')
- Pitfall A regression: streaming chat call deliberately omits `format=<schema>` kwarg; regression test captures kwargs and asserts `format` is absent (RESEARCH §3.5 + upstream issues #14440/#15260)
- Pitfall C regression: two concurrent `generate_suggestions` calls against a slow mock complete in <250 ms (would be ~300 ms if serialized) — proves AsyncClient is non-blocking
- Full backend suite goes 145 pass / 3 skip → 169 pass / 5 skip; ruff + mypy strict clean across 44 source files

## Task Commits

Each task was committed atomically following TDD discipline:

1. **Task 1 RED: Failing tests for engine.py** — `ba3ec72` (test)
2. **Task 1 GREEN: engine.py implementation + cross-test pollution fix** — `6ba0af1` (feat)
3. **Task 2: Opt-in live DictaLM 3.0 round-trip + grounding-refusal contract** — `26fd622` (test)

_TDD pair: RED `ba3ec72` → GREEN `6ba0af1`. Live test `26fd622` is structurally self-skipping on this executor (no host Ollama)._

## Files Created

- `backend/src/receptra/llm/engine.py` (286 LOC) — generate_suggestions AsyncGenerator + LlmCallTrace frozen dataclass + _CANONICAL_REFUSAL constant + _strip_markdown_fences helper + _extract_chunk_fields chunk-shape normalizer
- `backend/tests/llm/test_engine.py` (24 tests) — full mocked-AsyncClient behavioral coverage: 6-case parametrized fence-strip + 2 short-circuit + 2 happy-path (one with kwargs assertion) + 1 markdown-fence integration + 3 parse-retry (recovers/exhausted/garbage) + 4 error-path (unreachable/missing/timeout/connect-error) + 1 DoS-bound + 1 TTFT-bounded + 1 concurrency regression + 3 callback invariants
- `backend/tests/llm/test_engine_live.py` (2 tests) — opt-in `@pytest.mark.live` against real DictaLM 3.0: structural smoke + grounding-refusal contract (irrelevant context must return canonical refusal)

## Decisions Made

See `key-decisions` frontmatter above for the 10 locked decisions. Highlights:

- **LlmCallTrace defined IN engine.py** (not schema.py) — structural trace, not wire schema; lets Plan 03-05 import it and convert to its own LlmCallMetrics
- **format=<schema> NEVER passed while streaming** (only on retry with format='json' loose) — Pitfall A regression-tested
- **Hard short-circuit BEFORE Ollama** on empty context OR whitespace transcript — saves ~2s and is the strongest grounding defense
- **Wire-vs-audit error code split** — LlmErrorEvent.code stays narrow (4-value Literal) while LlmCallTrace.status keeps granular 7-value status for audit; OllamaModelMissingError collapses onto wire-level `ollama_unreachable` with `model_missing:` prefix in detail
- **record_call defense in depth** — `contextlib.suppress(Exception)` in finally block; buggy callback must NEVER crash the engine generator (Plan 03-05's record_call also swallows internally)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Cross-test sys.modules pollution from test_client's STT-isolation regression**

- **Found during:** Task 1 GREEN — full-suite run after engine tests passed in isolation
- **Issue:** `tests/llm/test_engine.py` used string-path `monkeypatch.setattr("receptra.llm.engine.X", ...)` form. When `tests/llm/test_client.py::test_client_module_does_not_import_receptra_stt` ran first (alphabetical order), its sys.modules save+restore dance restored a stale `receptra.llm` package object whose `engine` attribute had been wiped during the test. Pytest's `derive_importpath` walks the dotted path via `getattr` on the package, and `getattr(receptra.llm, 'engine')` raised AttributeError. 18 of 24 engine tests failed in the full suite while passing in isolation.
- **Root cause:** test_client.py's save+restore captures `receptra.llm` from BEFORE test_engine collection. Re-importing only `receptra.llm.client` inside the test re-creates the package object without an `engine` attribute. After restoration, the package object reference in `sys.modules['receptra.llm']` is the stale one with no `engine` attribute even though `sys.modules['receptra.llm.engine']` is back. (Pre-existing test_client.py code is correct for its purpose; the fragility lives at the consumer.)
- **Fix:** Added `from receptra.llm import engine as engine_module` import at top of test_engine.py, then replaced all `monkeypatch.setattr("receptra.llm.engine.attr", new)` with `monkeypatch.setattr(engine_module, "attr", new)`. The two-arg module-reference form bypasses derive_importpath's getattr walk on the package object — pytest goes directly to the live engine module.
- **Files modified:** `backend/tests/llm/test_engine.py`
- **Verification:** Full backend suite 169 pass / 5 skip cleanly across all collection orders; both isolated and full-suite runs green.
- **Committed in:** `6ba0af1` (folded into Task 1 GREEN per TDD discipline)

**2. [Rule 3 - Blocking] ruff RUF022 + I001 import-sort cleanup**

- **Found during:** Task 1 GREEN — `uv run ruff check` flagged 2 issues
- **Issue:** `__all__` list in engine.py was not isort-sorted; test_engine.py imports were grouped without future-annotations import block separator
- **Fix:** `uv run ruff check --fix` applied auto-sort
- **Files modified:** `backend/src/receptra/llm/engine.py`, `backend/tests/llm/test_engine.py`
- **Verification:** `uv run ruff check src/receptra/llm tests/llm` returns "All checks passed!"
- **Committed in:** `6ba0af1` (folded into Task 1 GREEN — pre-commit cleanup, not behavior change)

---

**Total deviations:** 2 auto-fixed (1 Rule-1 bug — cross-test isolation; 1 Rule-3 blocking — lint cleanup)
**Impact on plan:** Both auto-fixes mandatory. The Rule-1 fix establishes a new project-level pattern (module-reference monkeypatching when sibling tests touch sys.modules) documented in patterns-established. No scope creep — engine.py LOC and test count match plan.

## Issues Encountered

- **Cross-test sys.modules pollution** (covered above as Deviation #1) — only material issue. Discovered via the standard "isolated tests pass + full suite fails" diagnostic; root-caused by tracing pytest's `derive_importpath` against test_client.py's save+restore code. The fix is local (test_engine.py only) and establishes a reusable pattern.

## Authentication Gates

None — engine layer is pure orchestration; no auth surface. Live tests self-skip on this executor (no host Ollama + no RECEPTRA_LLM_LIVE_TEST env var); first Mac contributor with `dictalm3` registered runs the live grounding-contract test on env-var flip.

## Next Phase Readiness

- **Plan 03-05 (metrics + audit):** Imports `LlmCallTrace` from `receptra.llm.engine`; wires `record_call=` to its `log_llm_call` (loguru) + `insert_llm_call` (SQLite). Engine surface unchanged.
- **Plan 03-06 (CLI harness):** Imports `generate_suggestions` and iterates the AsyncGenerator. Surface unchanged.
- **Phase 4 (RAG):** Re-exports `ChunkRef` under `receptra.rag.types` once retriever is built; otherwise consumes `generate_suggestions` directly.
- **Phase 5 (hot path):** `SuggestionEvent` discriminated union flows through the WebSocket muxer; engine's `record_call` may be substituted with a Phase-5-specific audit sink.

No blockers. Independent follow-ups still tracked at the project level: numeric WER + latency baseline on M2 reference hardware (Phase 2 deferred work) and live ChatML grep gate run on the first Mac contributor with `dictalm3` registered (Plan 03-01 follow-up).

## Self-Check: PASSED

**Files verified:**
- FOUND: `backend/src/receptra/llm/engine.py`
- FOUND: `backend/tests/llm/test_engine.py`
- FOUND: `backend/tests/llm/test_engine_live.py`

**Commits verified:**
- FOUND: `ba3ec72` (Task 1 RED)
- FOUND: `6ba0af1` (Task 1 GREEN)
- FOUND: `26fd622` (Task 2 live)

---
*Phase: 03-hebrew-suggestion-llm*
*Plan: 03-04*
*Completed: 2026-04-26*
