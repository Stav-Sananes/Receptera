---
phase: 03-hebrew-suggestion-llm
plan: 03-06
subsystem: llm-cli-harness
tags: [llm, cli, harness, eval, fixtures, stt-isolation, docs, phase-3-close, llm-06]
requirements: [LLM-06]
dependency_graph:
  requires: ["03-04", "03-05"]
  provides: ["scripts/eval_llm.py CLI harness", "fixtures/llm/ JSON contract", "test_harness_isolation subprocess regression", "docs/llm.md user/contributor surface"]
  affects: ["Phase 5 INT-04 (mirrors composition pattern)", "Phase 7 prompt-tuning (eval_set.jsonl seed)", "Phase 4 RAG (fixture JSON shape contract)"]
tech_stack:
  added: []  # NO new deps — pure stdlib (argparse, asyncio, json, statistics, contextlib, pathlib, subprocess) + already-pinned receptra.llm + receptra.config
  patterns: ["argparse + asyncio.run + AsyncGenerator drain", "subprocess STT-isolation regression (sys.modules leak detection)", "settings.__dict__ patching for CLI overrides (skips pydantic re-validation)", "ExitStack for optional file context manager (SIM115 lock)", "Top-level JSON-array fixture format (Phase 4 RAG contract seed)"]
key_files:
  created:
    - scripts/eval_llm.py
    - fixtures/llm/policy_returns.json
    - fixtures/llm/policy_hours.json
    - fixtures/llm/empty_context.json
    - fixtures/llm/eval_set.jsonl
    - backend/tests/llm/test_harness_isolation.py
    - docs/llm.md
  modified: []
decisions:
  - "scripts/eval_llm.py imports ONLY stdlib + receptra.config + receptra.llm.* — LLM-06 structural lock enforced via subprocess regression test that enumerates 7 forbidden module prefixes (receptra.stt, faster_whisper, silero_vad, torch, onnxruntime, ctranslate2, av). First contributor to add a leaky import sees a named-module failure with the exact leaked module list."
  - "Subprocess execution for the STT-isolation regression is intentional (NOT in-process import + assertion). Module-state pollution from sibling tests in this session (e.g. tests/llm/test_client.py STT-isolation save+restore that mutates sys.modules) cannot mask a real regression when the test runs in a fresh interpreter. Belt-and-braces companion test asserts the same on `import receptra.llm.engine` alone so an engine-layer regression surfaces even if the harness imports something else."
  - "CLI overrides applied via `settings.__dict__[key] = value` (NOT pydantic re-validation) because Settings is loaded once at process start and we trust the developer-supplied URL/lang. Documented inline; threat T-03-06-05 (--ollama-host pointing at arbitrary URL) accepted because RECEPTRA_OLLAMA_HOST is operationally equivalent."
  - "Single-shot stdout = pretty-printed CompleteEvent JSON; stderr = TokenEvent feed (suppressed under --no-stream) + final TTFT/TOTAL/MODEL/GROUNDED summary line. Eval-set stdout = aggregate JSON (count, mean_ttft_ms, p95_ttft_ms, refusal_rate, grounded_rate, parse_retry_rate, parse_error_rate, pass_rate); stderr = per-row {id, passed, status} progress; --out-jsonl writes full per-row dump (id, ttft_ms, total_ms, status, is_refusal, is_grounded, passed, suggestions, error_code) to OUT. Transcript NEVER round-trips to stdout/stderr (T-03-06-03 mitigation — only suggestion text and timings flow out)."
  - "Exit code semantics LOCKED: 0 success / 1 ollama unreachable or timeout (single-shot only) / 2 parse_error_rate > 5% (eval-set only). The 5% threshold is the Phase 7 prompt-tuner attention bar — 1-in-20 calls failing to parse despite the bounded retry indicates degraded prompt or model. Single-shot ignores the parse_error gate because one bad call is too small a sample."
  - "Fixture JSON shape `[{id,text,source?},...]` is a top-level ARRAY (NOT object) — published as the Phase 4 RAG retrieval output contract. `source` is opaque metadata for Phase 6 UI citation chips and is NEVER rendered into the prompt (Plan 03-02 grep regression). Empty array `[]` is valid and exercises the Plan 03-04 short-circuit; this is the cheapest end-to-end CI smoke."
  - "_load_chunks performs explicit row-shape validation (must be dict with 'id' + 'text'; source must be dict if present) and raises ValueError with the file path on wrong shape — T-03-06-02 mitigation. Developer sees a clean error message instead of a Python stacktrace from inside Pydantic."
  - "eval-set _run_one_eval row-level errors are recorded into per-row results, not bubbled. One bad row never blocks the whole eval — T-03-06-04 DoS mitigation. The aggregate distinguishes parse_retry_ok (recovery) from parse_error (exhaustion) so the 5% gate measures real pathology, not transient parse-and-retry-OK."
  - "docs/llm.md (531 lines) parallels docs/stt.md (Plan 02-06) byte-for-byte in structure: Overview, Internal Interface Contract, CLI Usage, Audit Log + PII Warning (with the 'NOT for bug reports' WARNING block byte-equivalent to Phase 2's), Grounding Contract (LLM-03 three layers), Live Tests, Known Limitations, Troubleshooting (6 named scenarios), Cross-references. Reading docs/stt.md and docs/llm.md side-by-side gives the cross-domain audit + PII story without context-switching."
  - "PHASE 3 COMPLETE: 6/6 LLM-* requirements delivered across plans 03-01..03-06. Milestone progress 18/18 plans (100%). Independent follow-ups (Plan 02-05 numeric WER baseline + Plan 03-01 live ChatML grep gate + Plan 03-04 grounding-refusal live test) are contributor-with-Mac work, NOT structural blockers."
metrics:
  duration_min: 6
  completed: "2026-04-26"
  tasks: 4
  files_created: 7
  files_modified: 0
  tests_added: 2
  total_backend_tests: 205
  total_backend_skips: 5
  ruff_clean: true
  mypy_strict_clean: true
---

# Phase 3 Plan 03-06: LLM CLI Harness + STT-Isolation Regression + docs/llm.md Summary

`scripts/eval_llm.py` is the user-facing entry point closing Phase 3 — a 434-line argparse CLI that drives `receptra.llm.engine.generate_suggestions` end-to-end with two modes (single-shot + eval-set), eight flags, and three exit codes. Its STT-independence is regression-tested in a subprocess against seven forbidden module prefixes. Four fixtures (3 single-shot JSON + 1 five-line JSONL eval set) ship in `fixtures/llm/`. `docs/llm.md` (531 lines) is the parallel Phase 3 user/contributor doc to `docs/stt.md`. After this plan: 6/6 LLM-* requirements delivered, milestone 18/18 plans complete.

## What Shipped

### `scripts/eval_llm.py` (Task 2 — 434 LOC)

- **Argparse surface (8 flags):** `--transcript T` / `--eval-set FILE` (mutex), `--context-file FILE`, `--out-jsonl OUT`, `--model TAG`, `--ollama-host URL`, `--system-prompt-lang {he,en}`, `--no-stream`, `--no-audit`.
- **Single-shot mode:** consumes `--transcript T --context-file FILE`; streams TokenEvent deltas to stderr (suppressible via `--no-stream`); pretty-prints CompleteEvent JSON `{type, suggestions:[{text,confidence,citation_ids}], ttft_ms, total_ms, model}` to stdout; emits `TTFT: N ms  TOTAL: N ms  MODEL: M  GROUNDED: true|false` summary to stderr.
- **Eval-set mode:** iterates JSONL rows `{id, transcript, context, expected:{grounded, refusal}}`; per-row stderr `{id, passed, status}` progress; `--out-jsonl OUT` writes full per-row dump (id, ttft_ms, total_ms, status, is_refusal, is_grounded, passed, suggestions, error_code); aggregate stdout JSON `{count, mean_ttft_ms, p95_ttft_ms, refusal_rate, grounded_rate, parse_retry_rate, parse_error_rate, pass_rate}`.
- **Exit codes:** `0` success / `1` ollama_unreachable or timeout (single-shot only) / `2` parse_error_rate > 5% (eval-set only). Single-shot ignores the parse_error gate because one bad call is too small a sample; the 5% threshold is the Phase 7 prompt-tuner attention bar.
- **Settings overrides** via `settings.__dict__[k] = v` to skip pydantic re-validation (developer-supplied URL/lang trusted; T-03-06-05 accepted).
- **Audit wiring:** `--no-audit` skips `build_record_call(settings.audit_db_path)`; otherwise every call emits ONE loguru `event="llm.call"` line + ONE `llm_calls` SQLite row (Plan 03-05 surface).
- **Threat model coverage:** T-03-06-02 (malformed JSON → friendly ValueError with file path) + T-03-06-03 (transcript NEVER on stdout/stderr — only suggestion deltas + timings) + T-03-06-04 (one bad eval row does not block the rest).

### Fixtures (Task 1 — 4 files)

| File                                | Shape                                                | Use                                              |
|-------------------------------------|------------------------------------------------------|--------------------------------------------------|
| `fixtures/llm/policy_returns.json`  | `[{id, text, source}]` (1 chunk)                     | Single-shot grounded reply                       |
| `fixtures/llm/policy_hours.json`    | `[{id, text, source}]` (same chunk)                  | Pairs with hours question → refusal              |
| `fixtures/llm/empty_context.json`   | `[]`                                                 | Short-circuit smoke (zero Ollama call)           |
| `fixtures/llm/eval_set.jsonl`       | 5 lines `{id, transcript, context, expected}`        | Phase 7 grows to 20                              |

The eval set covers 5 categories: grounded reply, irrelevant-context refusal, empty-context refusal, multi-chunk grounded reply, very-short-transcript edge case.

### `backend/tests/llm/test_harness_isolation.py` (Task 3 — 2 tests, subprocess-based)

- **`test_harness_module_is_stt_clean`** — imports `scripts/eval_llm.py` via `importlib.util` in a SUBPROCESS spawned from the test's `sys.executable`; enumerates 7 forbidden module prefixes (`receptra.stt`, `faster_whisper`, `silero_vad`, `torch`, `onnxruntime`, `ctranslate2`, `av`) and asserts NONE of them appear in the subprocess's `sys.modules` after import. Subprocess execution is intentional — module-state pollution from sibling tests cannot mask a real regression.
- **`test_engine_module_is_stt_clean`** — belt-and-braces companion: `import receptra.llm.engine` alone in a fresh subprocess and run the same forbidden-prefix check. Surfaces an engine-layer regression (Plan 03-04 boundary) even if the harness imports something else.
- **Failure mode** — leaked module list is named in the assertion message so triage is one click away.

### `docs/llm.md` (Task 4 — 531 lines)

10 sections mirroring `docs/stt.md` (Plan 02-06):

1. Overview — Phase 3 surface (DictaLM 3.0 via Ollama, internal interface only, no public route)
2. Internal Interface Contract — `generate_suggestions(...)` signature + 5 paths + LlmErrorEvent code Literal allowlist + canonical refusal byte-exact
3. CLI Usage — both modes with examples; flag table; exit code table; output shapes; fixture format
4. Audit Log + PII Warning — `event="llm.call"` schema; `transcript_hash` sha256[:16] PII boundary; `RECEPTRA_LLM_LOG_TEXT_REDACTION_DISABLED` opt-in; "DO NOT attach to bug reports" WARNING block (byte-equivalent to docs/stt.md)
5. Grounding Contract (LLM-03) — three layered defenses (short-circuit + system prompt + few-shot) + grep gate count
6. Live Tests — `RECEPTRA_LLM_LIVE_TEST=1 pytest -m live` workflow + ChatML grep gate (Pitfall B / Assumption A5)
7. Known Limitations — DictaLM non-determinism + format-vs-streaming Pitfall A + Hebrew system prompt default + prompt injection accepted-risk + self-reported confidence + ~5s cold start + no public route
8. Troubleshooting — 6 named scenarios (ollama_unreachable / model_missing / parse_error spike / TTFT > 1s / ChatML grep failure / audit DB not writing) with recovery recipes
9. Cross-references — RESEARCH §5.2/§5.5/§6.4 + Plan 03-01..03-06 SUMMARYs + parallel docs/stt.md

## Verification Proof

### Empty-context short-circuit smoke

```text
$ cd backend && uv run --project . python ../scripts/eval_llm.py \
    --transcript "שלום" \
    --context-file ../fixtures/llm/empty_context.json \
    --no-audit --no-stream
{
  "type": "complete",
  "suggestions": [
    {
      "text": "אין לי מספיק מידע",
      "confidence": 0.0,
      "citation_ids": []
    }
  ],
  "ttft_ms": 0,
  "total_ms": 0,
  "model": "dictalm3"
}
TTFT: 0 ms  TOTAL: 0 ms  MODEL: dictalm3  GROUNDED: false
EXIT=0
```

### Subprocess STT-isolation regression

```text
$ cd backend && uv run pytest tests/llm/test_harness_isolation.py -x -v
tests/llm/test_harness_isolation.py::test_harness_module_is_stt_clean PASSED [ 50%]
tests/llm/test_harness_isolation.py::test_engine_module_is_stt_clean PASSED [100%]
============================== 2 passed in 0.93s ===============================
```

### Direct STT-clean check

```text
$ cd backend && uv run python -c "
import sys, importlib.util
spec = importlib.util.spec_from_file_location('h', '../scripts/eval_llm.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
forbidden = ['receptra.stt', 'faster_whisper', 'silero_vad', 'torch', 'onnxruntime', 'ctranslate2', 'av']
leaked = sorted(k for k in sys.modules if any(k == p or k.startswith(p + '.') for p in forbidden))
assert leaked == [], f'leaked: {leaked}'
print('STT-clean')
"
STT-clean
```

### Eval-set mode end-to-end (no Ollama, empty-context row)

```text
$ echo '{"id":"e003","transcript":"היי","context":[],"expected":{"grounded":false,"refusal":true}}' > /tmp/eval_one.jsonl
$ cd backend && uv run --project . python ../scripts/eval_llm.py --eval-set /tmp/eval_one.jsonl --no-audit --no-stream
{"id": "e003", "passed": true, "status": "ok"}     # stderr per-row progress
{
  "count": 1,
  "mean_ttft_ms": 0,
  "p95_ttft_ms": 0.0,
  "refusal_rate": 1.0,
  "grounded_rate": 0.0,
  "parse_retry_rate": 0.0,
  "parse_error_rate": 0.0,
  "pass_rate": 1.0
}
EXIT=0
```

### Full suite

```text
$ cd backend && uv run pytest tests/llm/ -x        # 154 passed / 4 skipped (live opt-in)
$ cd backend && uv run pytest tests/ -x            # 205 passed / 5 skipped
$ cd backend && uv run ruff check src tests        # All checks passed!
$ cd backend && uv run mypy src tests              # Success: no issues found in 49 source files
$ bash scripts/check_licenses.sh                   # exit 0 (no new deps; allowlist unchanged)
$ wc -l docs/llm.md                                # 531 lines (≥150 required)
```

### Live eval-set run

Not exercised on this executor (no host Ollama / no `dictalm3` registered). First Mac contributor with `dictalm3` registered runs:

```bash
RECEPTRA_LLM_LIVE_TEST=1 uv run --project backend python scripts/eval_llm.py \
    --eval-set fixtures/llm/eval_set.jsonl --no-audit --no-stream
```

The plan's verification §6 requires `pass_rate >= 0.6` (3/5 — empty-context refusal + irrelevant-context refusal + at least one grounded reply). Recorded as a Mac-contributor follow-up.

## Tests Added (2 total)

`backend/tests/llm/test_harness_isolation.py`:
- `test_harness_module_is_stt_clean` — subprocess-imports scripts/eval_llm.py and asserts no STT-domain modules in sys.modules.
- `test_engine_module_is_stt_clean` — subprocess-imports receptra.llm.engine alone for the same check (engine-boundary canary).

Full backend suite advances 203+5 → 205+5 (skips unchanged; the live opt-in count was already 4 in tests/llm + 1 STT WER fixture skip).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ruff I001/RUF046/SIM115 cleanup on scripts/eval_llm.py**

- **Found during:** Task 2 lint gate.
- **Issue:** Initial harness shipped with three ruff violations: (1) I001 import-block formatting because the `from receptra.*` block was preceded by a multi-line comment that disrupted the isort grouping; (2) RUF046 — `int(round(0.95 * (len(xs_sorted) - 1)))` calling `int(...)` on the already-int return of Python 3 `round`; (3) SIM115 — `out_handle = open(out_jsonl, ...) if out_jsonl else None` opens a file outside a context manager.
- **Fix:** (1) `ruff check --fix` applied to flatten the import grouping (single-line `from receptra.llm.schema import ...` resolved I001 + the comment block now sits between import groups cleanly); (2) dropped the redundant `int(...)` cast — `round(...)` already returns int in Python 3; (3) refactored `run_eval_set` to use `contextlib.ExitStack` so the optional `--out-jsonl` file handle is managed by a context manager regardless of whether the flag was supplied. Behavior unchanged.
- **Files modified:** `scripts/eval_llm.py` (import block, `_aggregate._p95`, `run_eval_set`)
- **Commit:** folded into Task 2 commit `42f6d08`.

**2. [Rule 3 - Blocking] ruff I001 cleanup on test_harness_isolation.py**

- **Found during:** Task 3 lint gate.
- **Issue:** Single I001 — extra blank line between module docstring and import block.
- **Fix:** `ruff check --fix` applied; ruff removed the extraneous blank line.
- **Files modified:** `backend/tests/llm/test_harness_isolation.py`
- **Commit:** folded into Task 3 commit `84e5728`.

### Authentication Gates

None.

### Architectural Decisions

None — plan executed exactly as written.

## Threat Model Coverage

All 7 STRIDE entries covered:

| Threat ID    | Disposition | Verified By                                                                                                                                                  |
|--------------|-------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| T-03-06-01 (E) | mitigate    | `test_harness_module_is_stt_clean` + `test_engine_module_is_stt_clean` enumerate 7 forbidden module prefixes in subprocess `sys.modules`.                  |
| T-03-06-02 (T) | mitigate    | `_load_chunks` raises ValueError with file path on wrong shape (manual: malformed JSON exits cleanly, no Python stacktrace).                                  |
| T-03-06-03 (I) | mitigate    | Single-shot stdout = CompleteEvent (suggestions + timings, no transcript echo); stderr = TokenEvent deltas (model OUTPUT, not input); audit goes through `build_record_call` → metrics.py PII redaction. |
| T-03-06-04 (D) | mitigate    | `_run_one_eval` per-row error wrap; one bad row records error_code into per-row dict and continues to next row (verified via plan-internal flow).             |
| T-03-06-05 (T) | accept      | `--ollama-host` flag is operationally equivalent to `RECEPTRA_OLLAMA_HOST`; documented in CLI Usage section of docs/llm.md.                                  |
| T-03-06-06 (I) | accept      | `--out-jsonl` location is developer-supplied; same trust as `data/audit.sqlite`. Documented in docs/llm.md audit section.                                    |
| T-03-06-07 (T) | mitigate    | Subprocess regression test runs in CI on every push; first regression fails the build with the leaked module list named in the assertion.                    |

## Phase 3 Closure

**6/6 LLM-* requirements delivered:**

| Requirement | Plans                  | Surface                                                                                                                                              |
|-------------|------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| LLM-01      | 03-01 + 03-03          | `ollama>=0.6.1` dep + Settings + `receptra.llm.client` (AsyncClient factory + select_model + retry_with_strict_json + typed errors)                 |
| LLM-02      | 03-04                  | `receptra.llm.engine.generate_suggestions(...) -> AsyncGenerator[SuggestionEvent, None]` 5-path orchestration                                        |
| LLM-03      | 03-02 + 03-04          | Schema/prompt-level lock + engine hard short-circuit + canonical refusal byte-exact + 3-layer defense                                                |
| LLM-04      | 03-02 + 03-04          | `Suggestion`/`SuggestionResponse` Pydantic v2 schema + bounded retry + markdown-fence tolerance                                                       |
| LLM-05      | 03-05                  | `receptra.llm.metrics` (loguru `event="llm.call"` PII-redacted by default) + `receptra.llm.audit` (idempotent `llm_calls` SQLite, RESEARCH §6.4)    |
| LLM-06      | 03-06 (this plan)      | `scripts/eval_llm.py` CLI harness + 4 fixtures + subprocess STT-isolation regression + `docs/llm.md`                                                 |

**Milestone progress:** 18/18 plans complete (Phase 1: 6/6; Phase 2: 6/6; Phase 3: 6/6). Phases 4–7 remain on the roadmap; Phases 2 + 3 are the hard parts of the v1 moat (Hebrew + local + live-latency) and are now structurally complete.

## What's Next

- **Phase 5 INT-04** — wires `record_call=build_record_call(settings.audit_db_path)` into the FastAPI lifespan so every WS-driven `generate_suggestions` invocation produces one loguru `event="llm.call"` line + one `llm_calls` row alongside CLI-driven calls.
- **Phase 7 prompt-tuning** — extends `fixtures/llm/eval_set.jsonl` from 5 to 20 lines + adds qualitative review by a Hebrew speaker; runs `scripts/eval_llm.py --eval-set` thousands of times against varying prompts. The CLI's exit-code-2 gate (5% parse_error rate) is the operational quality bar.
- **Independent follow-ups** still tracked:
  1. Plan 02-05 numeric WER + 02-06 latency baseline on reference M2 hardware (HF auth + CV 25.0 license + Apple Silicon — separate from Phase 3).
  2. Plan 03-01 live ChatML grep gate run on the first Mac with `dictalm3` registered.
  3. Plan 03-04 grounding-refusal contract live test (`test_grounding_refusal_on_irrelevant_context_live`) as the v1 Phase 3 quality bar — first Mac contributor flips `RECEPTRA_LLM_LIVE_TEST=1`.
  4. Plan 03-06 live eval-set run with `pass_rate >= 0.6` confirmation.

## TDD Gate Compliance

Plan 03-06 frontmatter does NOT mark `type: tdd`; instead Task 2 has `tdd="true"` per-task. Task 2's "behavior" section is the harness functional spec; verification is via the smoke command (`--transcript "שלום" --context-file empty_context.json --no-audit --no-stream` → exit 0 + canonical refusal in stdout). Task 3 IS the structural test that asserts the LLM-06 contract — committed AFTER Task 2's GREEN harness (so the test could fail meaningfully against a regressed harness).

Per-commit gate:
- `db148c8` (`feat(03-06): add LLM CLI harness fixtures...`) — Task 1 GREEN (no TDD; pure data files).
- `42f6d08` (`feat(03-06): add scripts/eval_llm.py CLI harness (LLM-06)`) — Task 2 GREEN, smoke-verified inline.
- `84e5728` (`test(03-06): add LLM-06 STT-isolation regression (subprocess-based)`) — Task 3 structural regression test landing as TEST commit (not a separate RED→GREEN since the harness it tests already exists in commit 42f6d08; the test would have FAILED in 42f6d08 only if the harness leaked an STT import — it doesn't, so the test passes on first run).
- `510ad8d` (`docs(03-06): add docs/llm.md user/contributor doc (LLM-06 close)`) — Task 4 docs commit.

Phase 3 plan-level TDD gate (per references/tdd.md): 03-02 / 03-03 / 03-04 / 03-05 each have RED + GREEN commits; 03-01 (Wave 0 dep lock) and 03-06 (CLI + docs) are tooling/docs plans where the structural regression IS the test surface (not a behavioral RED→GREEN).

## Self-Check: PASSED

- `scripts/eval_llm.py` — FOUND (executable, 434 LOC including docstring)
- `fixtures/llm/policy_returns.json` — FOUND (1 chunk, returns policy)
- `fixtures/llm/policy_hours.json` — FOUND (same chunk, paired with hours question for refusal)
- `fixtures/llm/empty_context.json` — FOUND (`[]`)
- `fixtures/llm/eval_set.jsonl` — FOUND (5 valid JSON lines)
- `backend/tests/llm/test_harness_isolation.py` — FOUND (2 tests, both passing)
- `docs/llm.md` — FOUND (531 lines, all 10 sections, 5 grep gates passing)
- Commit `db148c8` — FOUND (Task 1 fixtures)
- Commit `42f6d08` — FOUND (Task 2 CLI harness)
- Commit `84e5728` — FOUND (Task 3 STT-isolation regression)
- Commit `510ad8d` — FOUND (Task 4 docs/llm.md)
- Full backend suite: 205 passed / 5 skipped (live opt-in only)
- ruff + mypy strict clean: 49 source files
- License gate: exit 0 (no new deps; allowlist unchanged)
- Smoke: `--transcript "שלום" --context-file empty_context.json --no-audit --no-stream` → exit 0, stdout contains `אין לי מספיק מידע`
- Subprocess STT-isolation regression: `test_harness_module_is_stt_clean` + `test_engine_module_is_stt_clean` both PASSED in 0.93s
