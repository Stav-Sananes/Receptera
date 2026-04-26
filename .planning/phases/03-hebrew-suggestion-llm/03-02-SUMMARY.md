---
phase: 03-hebrew-suggestion-llm
plan: 03-02
subsystem: llm
tags: [llm, schema, pydantic, prompts, hebrew, chatml, few-shot, grounding, dos-bounds, discriminated-union, type-adapter]

# Dependency graph
requires:
  - phase: 02-hebrew-streaming-stt
    provides: SttEvent discriminated-union pattern (Plan 02-04) — mirrored byte-for-byte by SuggestionEvent
  - phase: 03-hebrew-suggestion-llm
    provides: Plan 03-01 — `ollama>=0.6.1` pinned, Settings extended with `llm_system_prompt_lang`, `tests/llm/conftest.py` live-test fixture
provides:
  - "`receptra.llm` package skeleton (`__init__.py`, `schema.py`, `prompts.py`)"
  - "`Suggestion`/`SuggestionResponse` pydantic v2 models (frozen, extra=forbid, min/max bounds)"
  - "`TokenEvent`/`CompleteEvent`/`LlmErrorEvent`/`SuggestionEvent` discriminated union (TypeAdapter pre-built)"
  - "`ChunkRef` frozen dataclass (Phase 4 RAG re-exports)"
  - "`SYSTEM_PROMPT_HE` (RESEARCH §5.2 verbatim, sha256 5726ca37a5ea082fee7b4b1b0dfe38c797d587a02f60ffea5324c9d62b341e0f)"
  - "`SYSTEM_PROMPT_EN` (placeholder English; refusal phrase stays Hebrew)"
  - "`FEW_SHOTS_HE` (4 alternating user/assistant turns; assistant entries are byte-exact valid SuggestionResponse JSON)"
  - "`build_user_message(transcript, chunks)` — DoS-bounded user-message renderer (≤2000 chars / ≤10 chunks / ≤12000 chars body)"
  - "`build_messages(transcript, chunks, lang)` — 6-message ChatML list for ollama.AsyncClient.chat"
affects:
  - 03-03 (client) — imports `Suggestion`, `SuggestionResponse` for parse target
  - 03-04 (engine) — calls `build_messages` and `model_validate_json`; yields `SuggestionEvent`
  - 03-05 (metrics) — reads `LlmErrorEvent.code` for Loki labels
  - 03-06 (CLI harness) — pretty-prints `CompleteEvent`
  - phase 4 (RAG) — re-exports `ChunkRef` under `receptra.rag.types`
  - phase 5 (hot-path muxer) — `SuggestionEventAdapter` validates events on `/ws/agent`
  - phase 6 (frontend) — codegen-derived TS types from these pydantic models

# Tech tracking
tech-stack:
  added:
    - "pydantic.TypeAdapter — pre-built `SuggestionEventAdapter` for discriminated-union validation"
    - "Annotated[Union[...], Field(discriminator='type')] — type-narrowing pattern (mirrors stt.events.SttEvent)"
  patterns:
    - "Locked-content modules: prompts.py is byte-exact RESEARCH §5.2/§5.4. Per-file ruff E501+RUF001 ignore documents the lock."
    - "DoS bounds enforced pre-LLM in pure-string builder (no I/O), so callers fail-fast with ValueError before any Ollama call."
    - "Hebrew refusal phrase ('אין לי מספיק מידע') hardcoded in BOTH SYSTEM_PROMPT_HE rule #2 AND FEW_SHOTS_HE example #2 — grep gate guarantees ≥3 hits in prompts.py (LLM-03 structural lock)."
    - "Few-shot assistant entries are themselves valid SuggestionResponse JSON — self-test via SuggestionResponse.model_validate_json in test_few_shot_assistants_are_valid_suggestion_response."

key-files:
  created:
    - backend/src/receptra/llm/__init__.py
    - backend/src/receptra/llm/schema.py
    - backend/src/receptra/llm/prompts.py
    - backend/tests/llm/test_schema.py
    - backend/tests/llm/test_prompts.py
  modified:
    - backend/pyproject.toml (per-file ruff ignores for Hebrew prompt files)

key-decisions:
  - "SuggestionEvent uses Annotated[Union[...], Field(discriminator='type')] — byte-exact mirror of `receptra.stt.events.SttEvent` so Phase 5 hot-path readers don't context-switch."
  - "DoS bounds (T-03-02-02) enforced in `build_user_message`, NOT in the engine. Pure-string + pure-data plan stays I/O-free; Plan 03-04 catches the ValueError and yields LlmErrorEvent(code='no_context'/'parse_error'). Engine never sends a giant prompt to Ollama."
  - "`SYSTEM_PROMPT_EN` keeps the refusal phrase in Hebrew (`'אין לי מספיק מידע'`) so the model's output language never drifts when the system prompt is in English. Phase 7 A/B owns real EN tuning."
  - "`FEW_SHOTS_HE` always Hebrew, regardless of `lang` parameter — the model needs Hebrew exemplars to learn the JSON-shape contract."
  - "`ChunkRef.source` is opaque to the LLM (regression-tested via `test_build_user_message_does_not_render_source_metadata`). Filename/offset metadata stays available for Phase 6 UI citation chips but never enters the prompt — prevents leaking host-filesystem details to Ollama."
  - "`LlmErrorEvent.code` Literal allowlist intentionally narrow (4 values: ollama_unreachable, parse_error, timeout, no_context). Adding a 5th requires plan amendment so consumer switches stay total."

patterns-established:
  - "Mirroring stt.events: same `Annotated + discriminator` shape, same `frozen=True, extra='forbid'` config, same `__all__` listing alphabetised. Future event-emitting subsystems should copy this skeleton."
  - "Locked-content per-file ruff ignores: When a module's strings are byte-exact research artefacts, document the lock via `tool.ruff.lint.per-file-ignores` in pyproject.toml with a comment naming the lock source. Avoids tempting future contributors to re-wrap Hebrew lines and corrupt UTF-8 codepoints."
  - "Few-shot self-validation: assistant entries in static prompt fixtures should themselves parse cleanly through the production schema — caught by `SuggestionResponse.model_validate_json(FEW_SHOTS_HE[i]['content'])` in tests. Prevents prompt drift from breaking parser without breaking tests."

requirements-completed: [LLM-03, LLM-04]

# Metrics
duration: 12min
completed: 2026-04-26
---

# Phase 3 Plan 03-02: Hebrew Suggestion Schema + Prompts Summary

**Pydantic v2 schema (Suggestion/SuggestionResponse + TokenEvent/CompleteEvent/LlmErrorEvent discriminated union + ChunkRef dataclass) plus Hebrew system prompt + 2 few-shot turns + DoS-bounded `build_user_message` + 6-element `build_messages` ChatML builder — the data and prompt contract every downstream Phase 3/4/5/6 plan consumes.**

## Performance

- **Duration:** ~12 min (TDD across 2 tasks: schema RED→GREEN, prompts RED→GREEN; resume executor implemented prompts.py off RED commit `669c8db`)
- **Started:** 2026-04-26 (resume) — original schema RED commit `dc4d7ec` landed earlier
- **Completed:** 2026-04-26
- **Tasks:** 2 (`type="auto" tdd="true"`)
- **Files modified:** 6 (3 source, 2 test, 1 config)

## Accomplishments

- **LLM-04 schema contract published** — `Suggestion` (text 1-280 chars, confidence 0-1, citation_ids), `SuggestionResponse` (1-3 suggestions), all `frozen=True, extra='forbid'`. Hebrew JSON round-trips byte-exactly through `model_validate_json` ↔ `model_dump_json`.
- **LLM-02 streaming event union published** — `SuggestionEvent` discriminated union with `SuggestionEventAdapter` pre-built. `TypeAdapter.validate_python({"type":"unknown"})` rejects cleanly. `LlmErrorEvent.code` Literal narrow to 4 values.
- **LLM-03 grounding contract locked at the prompt level** — Hebrew system prompt rule #2 + few-shot example #2 BOTH hardcode `'אין לי מספיק מידע'`. Grep gate `grep -F 'אין לי מספיק מידע' prompts.py` returns 3 hits (verification gate from plan).
- **DoS bounds enforced pre-LLM (T-03-02-02)** — transcript ≤2000 chars, ≤10 chunks, ≤12000 chars total body. ValueError raised in `build_user_message` BEFORE any I/O. `test_build_user_message_accepts_at_bounds` confirms boundary behaviour at exactly 2000/10/12000.
- **`ChunkRef.source` confirmed opaque to LLM** — `test_build_user_message_does_not_render_source_metadata` regression-guards the filesystem-leak surface (sets `source={"filename": "secret.md"}` and asserts the rendered prompt contains neither `secret.md` nor the keys `filename`/`offset`).
- **Package boundary works** — `from receptra.llm import Suggestion, ChunkRef, SuggestionEvent` succeeds; `from receptra.llm.prompts import build_messages` returns the 6-element ChatML list.

## Task Commits

TDD discipline (RED → GREEN per task):

1. **Task 1 RED — failing schema tests** — `dc4d7ec` (test)
2. **Task 1 GREEN — schema.py implementation** — `81157e3` (feat)
3. **Task 2 RED — failing prompts tests** — `669c8db` (test)
4. **Task 2 GREEN — prompts.py implementation + ruff per-file ignores** — `49083f7` (feat) ← this resume

**Plan metadata:** to be appended below as final docs commit.

## Files Created/Modified

- `backend/src/receptra/llm/__init__.py` — Package marker; re-exports `Suggestion`, `SuggestionResponse`, `TokenEvent`, `CompleteEvent`, `LlmErrorEvent`, `SuggestionEvent`, `SuggestionEventAdapter`, `ChunkRef`.
- `backend/src/receptra/llm/schema.py` — Pydantic v2 schema: 4 BaseModel classes + frozen ChunkRef dataclass + pre-built TypeAdapter. 132 LOC.
- `backend/src/receptra/llm/prompts.py` — Hebrew/English system prompts + 4-turn few-shot list + `build_user_message` + `build_messages`. 170 LOC. Locked-content per RESEARCH §5.2 + §5.4.
- `backend/tests/llm/test_schema.py` — 19 tests covering bounds, frozen, extra=forbid, Hebrew round-trip, discriminator, Literal allowlist, ChunkRef.
- `backend/tests/llm/test_prompts.py` — 28 tests covering grep gates, alternating roles, few-shot self-validation, refusal canonical shape, empty-context Hebrew marker, blank-line separator, DoS bounds, lang switch, source-metadata omission.
- `backend/pyproject.toml` — Added per-file ruff ignores: `src/receptra/llm/prompts.py = ["E501", "RUF001"]` (Hebrew lines cannot be wrapped without altering byte content; RUF001 ambiguous-glyph warnings are noise on a Hebrew prompt module). `tests/llm/test_prompts.py = ["S101", "RUF001"]`.

## Hebrew Byte-Exact Verification

The plan's `<output>` section asks for byte-exact regression watch numbers:

- **`SYSTEM_PROMPT_HE` SHA256:** `5726ca37a5ea082fee7b4b1b0dfe38c797d587a02f60ffea5324c9d62b341e0f`
- **Length:** 765 chars / 1225 UTF-8 bytes
- **Hebrew round-trip identical:** `True` (verified in-process via `json.dumps(...; ensure_ascii=False)` ↔ `json.loads`; also covered by `test_validate_json_round_trips_hebrew_byte_exact` through pydantic serialise/deserialise).
- **`SuggestionResponse.model_validate_json` Hebrew payload `'{"suggestions":[{"text":"שלום עולם","confidence":0.9,"citation_ids":["kb-1"]}]}'`** parses cleanly and round-trips with `שלום עולם` byte-preserved in `model_dump_json` output.
- **Few-shot example #2 parse:** `SuggestionResponse.model_validate_json(FEW_SHOTS_HE[3]["content"])` returns a SuggestionResponse with `suggestions[0].text == "אין לי מספיק מידע"`, `confidence == 0.0`, `citation_ids == []` — proves the canonical refusal shape is itself a valid SuggestionResponse, not just a string-match.

## Downstream Plan Inheritance Confirmation

The plan asks: confirm Plans 03-03 + 03-04 inherit the surface unchanged. Verified imports succeed at the package boundary:

- **Plan 03-03 (client) needs:** `Suggestion`, `SuggestionResponse`, `LlmErrorEvent` — all exported via `from receptra.llm import ...`.
- **Plan 03-04 (engine) needs:** `build_messages`, `Suggestion`, `SuggestionResponse`, `TokenEvent`, `CompleteEvent`, `LlmErrorEvent`, `ChunkRef` — all available; `build_messages(transcript, chunks, lang)` returns the exact `list[dict[str,str]]` shape ollama AsyncClient.chat consumes.
- **Plan 03-05 (metrics) needs:** `LlmErrorEvent.code` Literal allowlist (Loki label cardinality budget) — narrow to 4 values, validated by `test_error_event_code_literal_allowlist`.
- **Plan 03-06 (CLI harness) needs:** `CompleteEvent` — exported.
- **Phase 4 (RAG) needs:** `ChunkRef` re-export target — frozen dataclass shape settled.
- **Phase 5 (muxer) needs:** `SuggestionEventAdapter` for WebSocket frame validation — pre-built and exported.

## Decisions Made

All decisions were locked into the plan front-matter `<context>` section by the planner. Nothing was decided ad-hoc during execution. Key reaffirmations:

- **Mirrored `stt.events.SttEvent` exactly** — same Annotated+discriminator shape, same ConfigDict, same `__all__` ordering. A Phase 5 hot-path reviewer can context-switch zero times.
- **DoS bounds in builder, not engine** — keeps prompts.py I/O-free and unit-testable; Plan 03-04 wraps the ValueError into LlmErrorEvent (its concern, not ours).
- **Locked content stays byte-exact** — opted for per-file ruff ignores rather than wrapping/normalising Hebrew strings. The strings are quoted RESEARCH artefacts; modifying them silently is the failure mode we're guarding against.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added per-file ruff ignores for Hebrew locked-content files**

- **Found during:** Task 2 (prompts.py implementation)
- **Issue:** `ruff check` would fail with E501 (Hebrew prompt lines exceed 100 cols and cannot be wrapped without altering byte content) and RUF001 (ambiguous-glyph warnings between Hebrew letter forms and Latin lookalikes — entire point of a Hebrew prompt module). Required to satisfy the verification gate `cd backend && uv run ruff check src/receptra/llm tests/llm`.
- **Fix:** Added two `[tool.ruff.lint.per-file-ignores]` entries in `backend/pyproject.toml`:
  - `"src/receptra/llm/prompts.py" = ["E501", "RUF001"]`
  - `"tests/llm/test_prompts.py" = ["S101", "RUF001"]`
  Both with comments naming RESEARCH §5.2/§5.4 as the lock source.
- **Files modified:** `backend/pyproject.toml`
- **Verification:** `cd backend && uv run ruff check src/receptra/llm tests/llm` → "All checks passed!". `cd backend && uv run mypy src/receptra/llm tests/llm` → "Success: no issues found in 9 source files". Full backend suite: `112 passed, 3 skipped`.
- **Committed in:** `49083f7` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** Necessary to pass the plan's own verification gate without modifying locked Hebrew strings. No scope creep — the ignore list is narrowly scoped per-file and documented inline.

## Issues Encountered

None. The resume flow noticed `prompts.py` was already drafted on disk by the previous session but not yet committed; verified the file matched the plan's `<action>` byte-for-byte (cross-checked SYSTEM_PROMPT_HE against RESEARCH §5.2), confirmed all 28 tests passed, and committed as a single GREEN commit in TDD discipline.

## TDD Gate Compliance

Verified in `git log`:

- **RED schema:** `dc4d7ec` test(03-02): add failing tests for receptra.llm.schema
- **GREEN schema:** `81157e3` feat(03-02): publish receptra.llm.schema
- **RED prompts:** `669c8db` test(03-02): add failing tests for receptra.llm.prompts
- **GREEN prompts:** `49083f7` feat(03-02): implement receptra.llm.prompts

Both tasks followed RED → GREEN. No REFACTOR needed (locked content; tests covered the surface area exhaustively at first GREEN).

## User Setup Required

None. This plan is pure-data + pure-string — no environment variables, no model downloads, no service configuration. Plan 03-03 (Wave 2 next sibling) introduces Ollama AsyncClient probing; Plan 03-01 already shipped the `RECEPTRA_LLM_*` env keys.

## Next Phase Readiness

**Plan 03-03 (Wave 2 parallel sibling) — READY:**
- Imports `from receptra.llm.schema import Suggestion, SuggestionResponse, LlmErrorEvent` ✅
- All public surface frozen + extra='forbid' (no silent drift risk) ✅

**Plan 03-04 (Wave 3 — engine orchestration) — READY:**
- Calls `build_messages(transcript, chunks, lang)` → 6-element list passed straight to `client.chat(messages=...)` ✅
- Calls `SuggestionResponse.model_validate_json(stripped_completion)` for parse ✅
- Yields `TokenEvent`/`CompleteEvent`/`LlmErrorEvent` per `SuggestionEvent` union ✅
- Catches `build_user_message` ValueError → wraps as `LlmErrorEvent(code='no_context'|'parse_error')` ✅

**Plans 03-05 (metrics), 03-06 (CLI harness) — READY:**
- All needed types exported via `receptra.llm` package boundary ✅

**Phase 4 (RAG) — READY:**
- `ChunkRef` shape settled; Phase 4 RAG retriever returns `list[ChunkRef]` and `receptra.rag.types` re-exports ✅

**Phase 5 (hot path muxer) — READY:**
- `SuggestionEventAdapter` pre-built; muxer can `validate_python(payload)` on every WebSocket frame without rebuilding the TypeAdapter ✅

No blockers. Phase 3 has 4 plans remaining (03-03, 03-04, 03-05, 03-06).

## Self-Check: PASSED

Verified post-write:
- ✅ `backend/src/receptra/llm/__init__.py` exists
- ✅ `backend/src/receptra/llm/schema.py` exists
- ✅ `backend/src/receptra/llm/prompts.py` exists
- ✅ `backend/tests/llm/test_schema.py` exists
- ✅ `backend/tests/llm/test_prompts.py` exists
- ✅ Commit `dc4d7ec` (RED schema) in `git log`
- ✅ Commit `81157e3` (GREEN schema) in `git log`
- ✅ Commit `669c8db` (RED prompts) in `git log`
- ✅ Commit `49083f7` (GREEN prompts) in `git log`
- ✅ `cd backend && uv run pytest` → 112 passed, 3 skipped (live opt-in)
- ✅ `cd backend && uv run ruff check src/receptra/llm tests/llm` → All checks passed!
- ✅ `cd backend && uv run mypy src/receptra/llm tests/llm` → Success: no issues found in 9 source files
- ✅ `grep -F 'אין לי מספיק מידע' backend/src/receptra/llm/prompts.py | wc -l` → 3 (system_he + system_en + few-shot #2)

---
*Phase: 03-hebrew-suggestion-llm*
*Plan: 03-02*
*Completed: 2026-04-26*
