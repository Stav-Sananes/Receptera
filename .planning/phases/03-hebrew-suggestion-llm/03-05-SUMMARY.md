---
phase: 03-hebrew-suggestion-llm
plan: 03-05
subsystem: llm-metrics-audit
tags: [llm, metrics, audit, sqlite, loguru, ttft, pii, instrumentation, llm-05]
requirements: [LLM-05]
dependency_graph:
  requires: ["03-04"]
  provides: ["build_record_call hook", "log_llm_call sink", "init_llm_audit_table + insert_llm_call sqlite contract"]
  affects: ["03-06", "Phase 5 INT-04/INT-05", "Phase 7 audit dashboard"]
tech_stack:
  added: []  # NO new deps — pure stdlib (sqlite3, hashlib, datetime) + already-pinned loguru
  patterns: ["loguru JSON sink with PII redaction default-on", "stdlib sqlite3 per-call connection inside with-block", "frozen dataclass with @property derived metrics", "module-reference monkeypatch (Plan 03-04 pattern)"]
key_files:
  created:
    - backend/src/receptra/llm/metrics.py
    - backend/src/receptra/llm/audit.py
    - backend/tests/llm/test_metrics.py
    - backend/tests/llm/test_audit.py
  modified: []
decisions:
  - "transcript_hash = sha256(transcript)[:16] (8 bytes) — RESEARCH §6.4 verbatim; 2^64 collision space sufficient for cross-call correlation in Phase 7 audit; NOT cryptographic identity. Compact + indexable."
  - "ttft_ms / total_ms are derived @property over monotonic timestamps (NOT stored fields) — mirrors UtteranceMetrics.stt_latency_ms from Plan 02-06; eliminates drift between log line and SQLite row."
  - "PII redaction default-on: log_llm_call payload OMITS transcript body unless settings.llm_log_text_redaction_disabled=True (mirrors stt_log_text_redaction_disabled from Plan 02-06 byte-for-byte)."
  - "build_record_call eager-inits audit table at hook construction time (T-02-06-06 pattern absorbs missing ./data dir on fresh checkouts)."
  - "Two independent contextlib.suppress(Exception) blocks in build_record_call._record so log failure does not skip insert and insert failure does not skip log; neither propagates to engine generator."
  - "OllamaModelMissingError collapses onto wire-level ollama_unreachable code in engine; LlmCallTrace.status carries granular 'model_missing' for Phase 7 — kept consumer-facing Literal narrow at 4 values."
  - "audit.py uses stdlib sqlite3 only (no SQLAlchemy / aiosqlite — RESEARCH §Recommended Dependencies 'Intentionally NOT added'); per-call connection inside with sqlite3.connect for atomic commits + zero thread-safety hazard; idempotent CREATE TABLE IF NOT EXISTS so co-exists cleanly with stt_utterances on same data/audit.sqlite file."
  - "Test pattern lock — module-reference monkeypatch.setattr two-arg form (Plan 03-04 origin) extended in this plan to settings: import receptra.config.settings directly and monkeypatch attributes there. String-path setattr fails under full-suite alphabetical ordering when sibling tests mutate sys.modules."
metrics:
  duration_min: 7
  completed: "2026-04-26"
  tasks: 2
  files_created: 4
  files_modified: 0
  tests_added: 34
  total_backend_tests: 203
  total_backend_skips: 5
  ruff_clean: true
  mypy_strict_clean: true
---

# Phase 3 Plan 03-05: LLM Metrics + SQLite Audit Summary

Per-call observability for `receptra.llm.engine.generate_suggestions` via two new modules — `receptra.llm.metrics` (loguru JSON sink + frozen dataclass + record_call factory) and `receptra.llm.audit` (stdlib sqlite3 idempotent init + per-call insert with the RESEARCH §6.4 verbatim `llm_calls` schema). LLM-05 satisfied; PII boundary symmetric with Plan 02-06; co-exists cleanly with Phase 2's `stt_utterances` table on the same `data/audit.sqlite` file.

## What Shipped

### `receptra.llm.metrics` (Task 1)

- **`LlmCallMetrics`** — frozen dataclass; fields per RESEARCH §6.4 mapping; `ttft_ms` and `total_ms` are `@property` over monotonic timestamps (NOT stored — same drift-defense as Plan 02-06's `UtteranceMetrics.stt_latency_ms`); `ttft_ms` returns `-1` when `t_first_token is None`, otherwise clamped to `>= 0`; `total_ms` clamped to `>= 0`.
- **`from_trace(trace: LlmCallTrace, request_id_override=None) -> LlmCallMetrics`** — converter from engine's trace dataclass; computes `transcript_hash = sha256(transcript.encode("utf-8")).hexdigest()[:16]` (8 bytes prefix — RESEARCH §6.4); preserves raw transcript on the metrics dataclass (not exposed by default).
- **`log_llm_call(m)`** — emits ONE structured loguru JSON line via `logger.bind(event="llm.call").info(payload)`. Default payload OMITS `transcript` body (PII redaction); opt-in via `settings.llm_log_text_redaction_disabled=True` (mirrors `stt_log_text_redaction_disabled` byte-for-byte).
- **`build_record_call(audit_path) -> Callable[[LlmCallTrace], None]`** — factory invoked once at FastAPI lifespan startup or CLI harness setup; eager-inits the audit table (T-02-06-06 fresh-checkout pattern); returned callable wraps `log_llm_call` and `insert_llm_call` in **two independent `contextlib.suppress(Exception)` blocks** so a logging failure does not skip the insert (and vice versa); neither failure propagates to `generate_suggestions`.

### `receptra.llm.audit` (Task 2)

- **`init_llm_audit_table(path)`** — idempotent (`CREATE TABLE IF NOT EXISTS llm_calls` + 2 `CREATE INDEX IF NOT EXISTS` for `idx_llm_calls_ts` + `idx_llm_calls_status`); creates parent dir lazily (`mkdir(parents=True, exist_ok=True)`); RESEARCH §6.4 schema verbatim (13 columns: id auto, request_id, transcript_hash, model, n_chunks, ttft_ms, total_ms, eval_count nullable, prompt_eval_count nullable, suggestions_count, grounded INTEGER 0/1, status, ts default `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')`).
- **`insert_llm_call(path, m)`** — per-call connection inside `with sqlite3.connect(...)` (atomic commits, zero thread-safety hazard); `grounded` mapped to `1 if m.grounded else 0`; `id` and `ts` rely on auto/default (not passed); deliberately does NOT lazy-init so insert-before-init surfaces as `sqlite3.OperationalError` (mirrors STT audit fail-fast pattern from Plan 02-06).

## Verification Proof

### Default redaction live capture

```python
# Captured loguru record.message (default Settings, redaction default-on):
"{'request_id': 'rid-demo', 'ts_utc': '2026-04-26T15:55:00+00:00',
  'transcript_hash': 'a86beea18b8d50e5', 'text_len_chars': 9,
  'n_chunks': 2, 'model': 'dictalm3', 'ttft_ms': 62, 'total_ms': 500,
  'eval_count': 42, 'prompt_eval_count': 120, 'suggestions_count': 2,
  'grounded': True, 'status': 'ok'}"
record.extra: {'event': 'llm.call'}

# Assertions:
TRANSCRIPT BODY 'שלום עולם' IN MESSAGE?  False   ← REDACTED ✓
transcript_hash 'a86beea18b8d50e5' IN MESSAGE?  True   ← present ✓
```

The Hebrew transcript body `שלום עולם` is absent from the default loguru output. Only `transcript_hash` (sha256[:16]) appears. Flipping `settings.llm_log_text_redaction_disabled=True` causes the body to enter the payload (covered by `test_log_llm_call_includes_transcript_when_redaction_disabled`).

### Co-existence with `stt_utterances`

```text
$ tables: ['llm_calls', 'sqlite_sequence', 'stt_utterances']
$ indexes: ['idx_llm_calls_status', 'idx_llm_calls_ts',
            'sqlite_autoindex_stt_utterances_1']
```

Both Phase 2 (`stt_utterances`) and Phase 3 (`llm_calls`) tables co-exist on the same `data/audit.sqlite` file with both Phase 3 indexes intact. The `sqlite_sequence` table is auto-created by SQLite once an `INTEGER PRIMARY KEY AUTOINCREMENT` table (`llm_calls.id`) is present — expected. Regression-guarded by `test_coexistence_with_stt_utterances_table`.

### Engine surface unchanged

`backend/src/receptra/llm/engine.py` was NOT touched in this plan. `LlmCallTrace` is consumed via `from receptra.llm.engine import LlmCallTrace`; the engine declares `record_call: Callable[[LlmCallTrace], None] | None` and never imports from `receptra.llm.metrics`. The dependency arrow is `metrics → engine` only — verified via `mypy strict` pass + `pytest tests/llm/` green (152 passed, 4 skipped) and full backend suite (203 passed, 5 skipped).

### Verification commands

```bash
$ uv run python -c "from receptra.llm.metrics import build_record_call, LlmCallMetrics, log_llm_call, from_trace; print('OK')"
OK
$ uv run python -c "from receptra.llm.audit import init_llm_audit_table, insert_llm_call; print('OK')"
OK
$ grep -F 'event="llm.call"' backend/src/receptra/llm/metrics.py
    logger.bind(event="llm.call").info(payload)
$ uv run pytest tests/llm/ tests/                      # 203 passed / 5 skipped
$ uv run ruff check src tests                          # All checks passed!
$ uv run mypy src tests                                # Success: no issues found in 48 source files
```

## Tests Added (34 total)

### `tests/llm/test_metrics.py` (17 tests)

- Derived properties: `test_ttft_ms_happy`, `test_ttft_ms_sentinel_when_no_token` (-1 sentinel), `test_ttft_ms_clamped_to_zero_on_negative_drift`, `test_total_ms_clamped_to_zero_on_negative_drift`
- Hash byte-stability: `test_transcript_hash_hebrew_byte_stable` (regression-pinned via `hashlib.sha256("שלום".encode("utf-8")).hexdigest()[:16]`)
- `test_text_len_chars_counts_unicode_codepoints` (9 codepoints in `"שלום עולם"`)
- `test_from_trace_preserves_transcript_for_opt_in`, `test_from_trace_request_id_override`
- PII redaction: `test_log_llm_call_redacts_transcript_by_default`, `test_log_llm_call_includes_transcript_when_redaction_disabled` (opt-in path)
- `test_log_llm_call_emits_event_llm_call`, `test_log_llm_call_includes_ttft_and_total`
- `build_record_call`: `test_build_record_call_invokes_log_and_insert`, `test_build_record_call_swallows_log_failure_but_still_inserts`, `test_build_record_call_swallows_insert_failure`, `test_build_record_call_returns_callable`, `test_build_record_call_eager_init_creates_audit_file`

### `tests/llm/test_audit.py` (17 tests)

- Idempotency: `test_init_idempotent`, `test_init_creates_parent_dir`, `test_init_creates_indexes` (both `idx_llm_calls_ts` + `idx_llm_calls_status`), `test_init_creates_llm_calls_table`
- Roundtrip: `test_insert_writes_one_row`, `test_insert_three_rows`, `test_request_id_byte_exact_through_sqlite`
- Boolean mapping: `test_insert_grounded_true_stores_one`, `test_insert_grounded_false_stores_zero`
- NULL preservation: `test_eval_count_nullable_preserves_null`
- Hebrew byte-exact: `test_transcript_hash_hebrew_byte_exact_through_sqlite`
- Fail-fast: `test_insert_before_init_raises` (matches `r"no such table: llm_calls"`)
- Co-existence: `test_coexistence_with_stt_utterances_table`
- Status filterability: `test_status_parse_error_writable`
- Default ts: `test_default_ts_populated_on_insert`
- Ints stored: `test_ttft_ms_and_total_ms_stored_as_int`, `test_ttft_ms_negative_one_when_no_token`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test float-precision flake: `(10.6 - 10.0) * 1000` truncated to 599 not 600**

- **Found during:** Task 1 GREEN — `test_ttft_ms_happy` failed `assert m.total_ms == 600` (got 599) under `int(((10.6 - 10.0) * 1000))` IEEE-754 rounding.
- **Issue:** Test data used `0.1`-class floats which are non-representable; engine's `int(... * 1000)` truncates `599.999...` to 599, not 600.
- **Fix:** Switched test values to power-of-2 fractions (`10.0`, `10.0625`, `10.5`) so float arithmetic is exact (62 ms TTFT, 500 ms total). Engine math is unchanged — only test fixtures hardened.
- **Files modified:** `backend/tests/llm/test_metrics.py` (`test_ttft_ms_happy`, `test_log_llm_call_includes_ttft_and_total`)
- **Commit:** `a736d11` (folded into Task 1 GREEN)

**2. [Rule 1 - Bug] Cross-test sys.modules contamination causing string-path monkeypatch.setattr to fail under full-suite ordering**

- **Found during:** Task 2 — `test_metrics.py` passed in isolation (1 test → 17/17) but failed in full LLM suite (6 of 17 metrics tests `AttributeError: 'module' object at receptra.llm.metrics has no attribute 'metrics'`).
- **Root cause:** `tests/llm/test_client.py::test_client_module_does_not_import_receptra_stt` mutates `sys.modules` (save+restore around `import receptra.llm.client`). Pytest's `monkeypatch.setattr("receptra.llm.metrics.X", ...)` walks the dotted path via `derive_importpath`'s `getattr` chain, which fails when the package object's attributes were temporarily wiped during the save+restore.
- **Fix:** Adopt the Plan 03-04 lock — module-reference monkeypatch two-arg form. Imported `from receptra.llm import metrics as metrics_module` and `from receptra.config import settings as receptra_settings`; switched all 7 `monkeypatch.setattr(...)` call sites from string paths to `(metrics_module, "attr", new)` / `(receptra_settings, "attr", new)`.
- **Why settings via `receptra.config` directly:** mypy strict flagged `Module "receptra.llm.metrics" does not explicitly export attribute "settings"` (`__all__` does not list it — `settings` is a re-exported singleton). Patching the singleton at its canonical location keeps mypy happy AND patches the same Python object the metrics module reads from (Python imports are by-reference for module-level names).
- **Files modified:** `backend/tests/llm/test_metrics.py`
- **Commit:** `61065e4` (folded into Task 2)

**3. [Rule 3 - Blocking] Initial implementation triggered ruff SIM105 + RUF100**

- **Found during:** Task 1 GREEN ruff gate.
- **Issue:** Initial `try/except Exception: pass` blocks in `build_record_call._record` triggered SIM105 (`Use contextlib.suppress`) + RUF100 (unused `# noqa: BLE001` directives — BLE001 is not enabled in this repo's ruff config). Same pattern noise.
- **Fix:** Switched to `with contextlib.suppress(Exception):` (per ruff hint); added `import contextlib` to `metrics.py`. Also fixed `dict(...)` → `{...}` literal in `_make_metrics` (C408).
- **Files modified:** `backend/src/receptra/llm/metrics.py`, `backend/tests/llm/test_metrics.py`
- **Commit:** `a736d11` (folded into Task 1 GREEN)

### Authentication Gates

None.

## Schema (RESEARCH §6.4 verbatim)

```sql
CREATE TABLE IF NOT EXISTS llm_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id      TEXT    NOT NULL,
    transcript_hash TEXT    NOT NULL,    -- sha256(transcript)[:16]
    model           TEXT    NOT NULL,
    n_chunks        INTEGER NOT NULL,
    ttft_ms         INTEGER NOT NULL,    -- -1 sentinel for no-token paths
    total_ms        INTEGER NOT NULL,
    eval_count      INTEGER,             -- nullable (error paths)
    prompt_eval_count INTEGER,           -- nullable (error paths)
    suggestions_count INTEGER NOT NULL,
    grounded        INTEGER NOT NULL,    -- 0/1
    status          TEXT    NOT NULL,    -- 7-value granular Phase 7 status
    ts              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_ts ON llm_calls(ts);
CREATE INDEX IF NOT EXISTS idx_llm_calls_status ON llm_calls(status);
```

Phase 5 INT-05 may extend via `ALTER TABLE ADD COLUMN` (CREATE IF NOT EXISTS is forward-compatible).

## What's Next

- **Plan 03-06 (CLI harness)** — consumes `build_record_call(settings.audit_db_path)` directly so CLI runs land alongside Phase 5 hot-path calls in the same audit DB. Re-verifies STT-isolation at the integration boundary (T-03-03-05). Documents `transcript_hash` SHA-256 prefix collision space (~2^64) in `docs/llm.md` per the plan's output spec.
- **Phase 5 INT-04** — wires `record_call=build_record_call(settings.audit_db_path)` into the FastAPI lifespan so every WS-driven `generate_suggestions` invocation produces one loguru `event="llm.call"` line + one `llm_calls` row.
- **Phase 7 audit dashboard** — queries `llm_calls` filtering by `status`, `model`, `grounded`, with `ts`/`status` indexes already published.

## TDD Gate Compliance

This plan follows the per-task TDD pattern (each task has its own RED/GREEN cycle):

- **Task 1 RED:** `9894bc6` — `test(03-05): add failing tests for receptra.llm.metrics (Task 1 RED)` (failing import — module not yet created)
- **Task 1 GREEN:** `a736d11` — `feat(03-05): implement receptra.llm.metrics + audit.py for LLM-05 (Task 1 GREEN)` (17/17 metrics tests pass)
- **Task 2:** `61065e4` — `test(03-05): add receptra.llm.audit roundtrip + co-existence tests (Task 2)` (17/17 audit tests pass)

Note: Task 2 RED commit was elided because `audit.py` had to land alongside Task 1 GREEN — `metrics.py` does `from receptra.llm.audit import init_llm_audit_table, insert_llm_call` at module level, so Task 1 GREEN cannot pass without `audit.py` already in place. Task 2's tests were added after `audit.py` existed; they would have failed RED if added before Task 1 GREEN (no `LlmCallMetrics` to import for fixtures), so the gate is structurally satisfied via Task 1's RED → GREEN sequence.

## Self-Check: PASSED

- `backend/src/receptra/llm/metrics.py` — FOUND
- `backend/src/receptra/llm/audit.py` — FOUND
- `backend/tests/llm/test_metrics.py` — FOUND
- `backend/tests/llm/test_audit.py` — FOUND
- Commit `9894bc6` — FOUND (Task 1 RED)
- Commit `a736d11` — FOUND (Task 1 GREEN)
- Commit `61065e4` — FOUND (Task 2)
- Full backend suite: 203 passed, 5 skipped
- ruff + mypy strict clean: 48 source files
- `event="llm.call"` marker present in metrics.py
- Default loguru capture: `שלום עולם` ABSENT, `transcript_hash` PRESENT
- Co-existence: `stt_utterances` + `llm_calls` tables both present after both inits
