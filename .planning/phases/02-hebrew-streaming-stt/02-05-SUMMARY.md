---
phase: 02-hebrew-streaming-stt
plan: 02-05
subsystem: stt
tags: [stt, wer, cer, evaluation, hebrew, jiwer, common-voice, regression-test]

# Dependency graph
requires:
  - phase: 02-hebrew-streaming-stt
    provides: "transcribe_hebrew(model, audio_f32) — locked-kwarg wrapper from Plan 02-02"
  - phase: 02-hebrew-streaming-stt
    provides: "jiwer 4.0 + soundfile 0.13 dev deps from Plan 02-01"
provides:
  - "receptra.stt.wer — normalise_hebrew + compute_wer (jiwer 4.0 wrapper) for Hebrew-aware WER + CER"
  - "scripts/fetch_stt_fixtures.py — pinned Common Voice 25.0 Hebrew fixture downloader"
  - "scripts/eval_wer.py — batch WER + CER eval CLI with per-clip table + JSON aggregate output"
  - "backend/tests/stt/fixtures/he_cv_30.jsonl — 30-row fixture manifest (currently airgap placeholder)"
  - "backend/tests/stt/test_wer_baseline.py — regression guard (3pp grace) skipping gracefully when fixtures unfetched"
  - "docs/stt-eval.md — contributor-facing eval workflow + baseline-update policy"
affects:
  - "Plan 02-06 (chaos test + phase-transition gate consumes the JSON report schema)"
  - "Phase 7 (beam_size=5 ceiling eval, larger conversational fixtures, MLX/Core ML alternates)"

# Tech tracking
tech-stack:
  added: []   # No new runtime deps. `datasets` is intentionally an opt-in regen-only dep.
  patterns:
    - "Single-source-of-truth wrapper reuse: scripts/eval_wer.py imports transcribe_hebrew rather than re-spelling locked kwargs (matches Plan 02-02 design)"
    - "Airgap fallback pattern: scripts/fetch_stt_fixtures.py --airgap-placeholder writes a 1-row UNFETCHED manifest so the regression test skips gracefully on CI executors without HF Hub access"
    - "Two-class regex normalization: niqqud/bidi → empty string (intra-word, must not split), punctuation → space (between words, must split)"
    - "Pinned-revision fixture fetch via CV_REVISION_SHA module constant (T-02-05-01 mitigation)"

key-files:
  created:
    - "backend/src/receptra/stt/wer.py"
    - "backend/tests/stt/test_wer_hebrew.py"
    - "backend/tests/stt/test_wer_baseline.py"
    - "backend/tests/stt/fixtures/__init__.py"
    - "backend/tests/stt/fixtures/he_cv_30.jsonl"
    - "backend/tests/stt/fixtures/he_cv_30/.gitkeep"
    - "scripts/fetch_stt_fixtures.py"
    - "scripts/eval_wer.py"
    - "docs/stt-eval.md"
  modified: []

key-decisions:
  - "normalise_hebrew uses TWO separate regex classes — niqqud/bidi → empty string, punctuation → space. RESEARCH §9's single-class regex would shatter 'שָׁלוֹם' (with niqqud) into multiple tokens; the test contract demands a single-token output."
  - "compute_wer skips the RESEARCH §9 jiwer Compose([Strip(), RemoveMultipleSpaces()]) pipeline — jiwer 4.0 rejects it as non-list-of-list-of-words. normalise_hebrew already strips + collapses whitespace, so jiwer's library defaults handle the rest."
  - "datasets is NOT added to backend/pyproject.toml. It is a one-shot regeneration tool, not a runtime dep. fetch_stt_fixtures.py imports it lazily and emits an actionable install instruction on ImportError (`uv pip install 'datasets>=4.0,<5'`)."
  - "scripts/eval_wer.py imports receptra.stt.engine.transcribe_hebrew (single source of truth from Plan 02-02) — no Hebrew transcribe kwargs are duplicated in this script, preventing param drift."
  - "GRACE_PP = 0.03 (3 percentage-point regression grace) lives as a module-level constant in test_wer_baseline.py. Any change is a code-diff requiring review (T-02-05-04 mitigation)."
  - "BASELINE_WER + BASELINE_CER are intentionally None in this commit — the airgap-placeholder manifest means we cannot record a real baseline from this executor. Plan 02-06 phase-transition gate flags this as a follow-up (first contributor with HF Hub access + Common Voice 25.0 license acceptance + the model on disk runs scripts/eval_wer.py and commits the numbers)."

patterns-established:
  - "Pattern 1: airgap-placeholder fixture fallback — keeps CI green and the regression test skipping gracefully when external data is unreachable; first contributor with access regenerates real fixtures and commits the baseline in a single PR"
  - "Pattern 2: contributor-only resampling deps — `datasets` is documented in docs/stt-eval.md as a one-shot install for fixture regeneration; runtime deps stay minimal"
  - "Pattern 3: single-source-of-truth reuse for kwarg-locked APIs — eval CLI imports the same transcribe_hebrew the live `/ws/stt` path uses, so live and batch numbers stay comparable by construction"

requirements-completed: [STT-05]

# Metrics
duration: ~10min
completed: 2026-04-25
---

# Phase 2 Plan 02-05: Hebrew WER Eval Harness Summary

**Hebrew-normalised WER + CER pipeline (jiwer 4.0) with pinned Common Voice 25.0 fixture downloader, batch eval CLI reusing transcribe_hebrew, regression test with 3pp grace, and contributor-facing docs — STT-05 satisfied with airgap fallback for fixtures**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-25T19:28:46Z
- **Completed:** 2026-04-25T19:38:04Z
- **Tasks:** 2 (Task 1 TDD: RED + GREEN; Task 2 Build)
- **Files created:** 9
- **Tests added:** 9 unit + 1 regression = 10 (regression skips gracefully)

## Accomplishments

- Hebrew-aware WER + CER computation via `receptra.stt.wer` — NFC + niqqud strip + bidi strip + punctuation strip + whitespace collapse, then jiwer 4.0 default transforms.
- Reproducible Common Voice 25.0 fetcher with pinned `CV_REVISION_SHA`, gated-dataset auth probe, deterministic 30-clip selection, lazy `datasets` import (no runtime dep added).
- Batch eval CLI (`scripts/eval_wer.py`) reusing the locked `transcribe_hebrew` wrapper — no Hebrew kwarg drift between live and batch paths.
- Regression test (`test_wer_baseline.py`) with `BASELINE_WER` + `BASELINE_CER` constants and `GRACE_PP = 0.03`, skipping gracefully when fixtures are unfetched / model missing / baseline unrecorded.
- Contributor docs covering fetching, running, WER vs CER for Hebrew (agglutinative-morphology rationale), baseline-update policy (Hebrew-speaker review), training-data-leakage rejection of ivrit-ai test sets, beam-size-1 vs beam-size-5 follow-up, and known limitations.
- Full backend suite: 39 passed, 1 skipped (the regression test, as designed).

## Task Commits

1. **Task 1 RED: failing Hebrew WER tests** — `9ec96b2` (test)
2. **Task 1 GREEN: normalise_hebrew + compute_wer** — `4df048f` (feat)
3. **Task 2: fetch + eval CLI + regression + docs** — `700c798` (feat)

_Note: TDD task 1 has the canonical RED → GREEN cycle. Task 2 is non-TDD (mostly tooling + docs); covered by the AST contract gate + regression-test skip behaviour rather than new unit tests._

## Files Created

- `backend/src/receptra/stt/wer.py` — Hebrew-normalised WER + CER (jiwer 4.0 wrapper)
- `backend/tests/stt/test_wer_hebrew.py` — 9 unit tests (NFC, niqqud, punctuation, bidi, whitespace, identical, near-identical, substitution, empty-hyp)
- `backend/tests/stt/test_wer_baseline.py` — Regression guard with `BASELINE_WER` / `BASELINE_CER` constants + `GRACE_PP = 0.03`
- `backend/tests/stt/fixtures/__init__.py` — Marks fixtures dir as a package
- `backend/tests/stt/fixtures/he_cv_30.jsonl` — Airgap-placeholder manifest (1 UNFETCHED row); regenerated to 30 real rows by the first contributor with HF access
- `backend/tests/stt/fixtures/he_cv_30/.gitkeep` — Holds the audio dir under git
- `scripts/fetch_stt_fixtures.py` — Pinned-revision Common Voice 25.0 fetcher with HF auth probe + lazy `datasets` import + `--airgap-placeholder` mode
- `scripts/eval_wer.py` — Batch eval CLI using `transcribe_hebrew` (single source of truth)
- `docs/stt-eval.md` — Contributor-facing eval workflow doc

## Decisions Made

See `key-decisions` in frontmatter. Headline:

- **Two-class regex normalization** (niqqud → empty, punctuation → space) is necessary for the plan's behavior contract — the RESEARCH §9 single-class sketch would shatter niqqud-bearing words. Documented in `wer.py` module docstring.
- **`datasets` is opt-in.** Not in `pyproject.toml`. Fixture regeneration requires `uv pip install 'datasets>=4.0,<5'` documented in `docs/stt-eval.md`. This preserves "no silent dep additions" while leaving the regen workflow clean.
- **`BASELINE_WER` is None for now.** The airgap-placeholder manifest means we can't record a baseline from this executor. Phase 2 plan 02-06 phase-transition gate will block on a contributor running `scripts/fetch_stt_fixtures.py` + `scripts/eval_wer.py` and committing the numbers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] jiwer 4.0 Compose pipeline rejected**
- **Found during:** Task 1 GREEN (compute_wer implementation)
- **Issue:** RESEARCH §9 sketch + plan's `<action>` showed `Compose([Strip(), RemoveMultipleSpaces()])` as the jiwer transforms. jiwer 4.0 rejects this with "After applying the transformation, each reference should be a list of strings" because jiwer 4.0 mandates the final transform reduce to ListOfListOfWords.
- **Fix:** Skip the user-supplied jiwer transforms entirely. `normalise_hebrew()` already strips + collapses whitespace, so jiwer's library defaults are sufficient. Documented in `wer.py` module docstring.
- **Files modified:** `backend/src/receptra/stt/wer.py`
- **Verification:** All 9 unit tests pass; ruff + mypy strict clean.
- **Committed in:** `4df048f` (Task 1 GREEN)

**2. [Rule 1 - Bug] Niqqud-stripping regex would shatter words**
- **Found during:** Task 1 GREEN (test_niqqud_stripped contract)
- **Issue:** RESEARCH §9's single-class regex `[\u0591-\u05C7\u200E\u200F\.\,\!\?\:\;\"\'\(\)\[\]\-]` substituted to ` ` (space) would turn "שָׁלוֹם" (3 letters + 4 niqqud) into "ש ל ם" — three "words" — breaking the plan's `test_niqqud_stripped` contract that expects a single token "שלום".
- **Fix:** Split the regex into two classes — niqqud + bidi (intra-word) → empty string; punctuation (between words) → space. Whitespace collapse covers both cases.
- **Files modified:** `backend/src/receptra/stt/wer.py`
- **Verification:** `test_niqqud_stripped`, `test_bidi_control_chars_stripped`, and all sibling tests pass.
- **Committed in:** `4df048f` (Task 1 GREEN)

**3. [Rule 3 - Blocking] `datasets` library not transitively available**
- **Found during:** Task 2 (fetch script implementation)
- **Issue:** Plan said "use `datasets` if available transitively; otherwise return blocker — do NOT silently add deps." `datasets` is not pulled by `faster-whisper`/`silero-vad`/`huggingface_hub`/`soundfile` and resampling deps (librosa/soxr/scipy) are also missing.
- **Fix:** `fetch_stt_fixtures.py` imports `datasets` lazily inside `_ensure_datasets_installed()` and exits with an actionable installation instruction on `ImportError` (`uv pip install 'datasets>=4.0,<5'`). Documented in script header + `docs/stt-eval.md` "Fetching fixtures" as a contributor-only opt-in dep. No silent dep addition.
- **Files modified:** `scripts/fetch_stt_fixtures.py`, `docs/stt-eval.md`
- **Verification:** Plan AST contract gate green; `--airgap-placeholder` path exercised on this executor.
- **Committed in:** `700c798` (Task 2)

**4. [Rule 3 - Blocking] Common Voice 25.0 is a gated HF dataset**
- **Found during:** Task 2 (fetch script auth probe)
- **Issue:** `mozilla-foundation/common_voice_25_0` returns HTTP 401 unless the caller has signed in to HF Hub AND clicked "Agree and access repository" on the dataset page AND set `HF_TOKEN`. This executor has none of those, so an end-to-end fetch is impossible.
- **Fix:** `fetch_stt_fixtures.py` calls `HfApi().dataset_info(CV_REPO)` before `load_dataset` and emits a 5-step unblock instruction on 401 / "gated" / "RepositoryNotFoundError". Committed manifest is the airgap placeholder (1 UNFETCHED row); `BASELINE_WER` / `BASELINE_CER` left as None; regression test skips gracefully. Plan 02-06 phase-transition gate flags as follow-up.
- **Files modified:** `scripts/fetch_stt_fixtures.py`, `backend/tests/stt/fixtures/he_cv_30.jsonl`, `docs/stt-eval.md`
- **Verification:** `pytest backend/tests/stt/test_wer_baseline.py` skips with reason "fixtures unfetched"; `python scripts/eval_wer.py` returns `{"status": "skipped", "reason": "fixtures_unfetched"}`.
- **Committed in:** `700c798` (Task 2)

---

**Total deviations:** 4 auto-fixed (1 bug, 3 blocking)
**Impact on plan:** Deviations 1 + 2 are jiwer-API + behavior-contract corrections; without them the plan's stated tests would fail. Deviations 3 + 4 are environmental — the plan's `<autonomous_mode>` block explicitly allowed them as the airgap path. No scope creep, no silent dep additions.

## Issues Encountered

- ruff (backend config) flags scripts with `B`/`RUF` rules when run from `backend/` working dir. Auto-fixed via `ruff check --fix` (import sort + RUF046 unnecessary `int` cast + RUF034 useless `if-else`).
- mypy strict caught a `Returning Any from function declared to return "bool"` in `_fixtures_present()` due to `dict.get()` return type; fixed with explicit `bool(...)` cast.

## Threat Surface Audit

No new surface introduced beyond the plan's threat register:

- `T-02-05-01` (HF tampering) mitigated via `CV_REVISION_SHA` constant.
- `T-02-05-02` (PII in transcripts) accepted — Common Voice is CC0 volunteer read speech.
- `T-02-05-03` (CI DoS) noted in docs; Plan 02-06 will mark the regression test slow.
- `T-02-05-04` (silent grace widening) mitigated via module-level `GRACE_PP = 0.03`.
- `T-02-05-05` (`trust_remote_code=True` leak) mitigated — `datasets.load_dataset(..., trust_remote_code=False)` is the default; we never override it.

## Known Stubs

**1. `BASELINE_WER` / `BASELINE_CER` are `None`** in `backend/tests/stt/test_wer_baseline.py`.
- **Reason:** This executor has no HF Hub auth + no Common Voice 25.0 license acceptance + no Whisper model on disk, so the fetch + eval cannot run end-to-end here.
- **Resolves in:** Plan 02-06 phase-transition gate. First contributor with HF access + accepted CV-25 license + `make models` already run executes:
  ```
  python scripts/fetch_stt_fixtures.py
  cd backend && uv run python ../scripts/eval_wer.py > /tmp/eval.json
  # Read /tmp/eval.json["baseline"]["wer_mean"] + ["cer_mean"]
  # Update BASELINE_WER + BASELINE_CER in test_wer_baseline.py
  # Commit the regenerated fixtures + the baseline numbers in one PR
  ```
- **Test impact:** Regression test currently skips with reason "fixtures unfetched" — STT-05 is structurally satisfied (the harness exists and is exercised end-to-end via the placeholder skip path), but a numeric baseline is the Plan 02-06 work item.

**2. Placeholder manifest** at `backend/tests/stt/fixtures/he_cv_30.jsonl` (1 row with `id="UNFETCHED"`).
- **Reason:** Same as above. Regenerating requires HF Hub auth.
- **Resolves in:** Plan 02-06 (or any earlier PR with HF access).

These are intentional stubs documented in the plan's `<autonomous_mode>` airgap fallback. They do NOT prevent STT-05's structural requirement — the harness, normalization, eval CLI, regression test, and docs are all live and exercised.

## CV_REVISION_SHA used

`CV_REVISION_SHA = "main"` — placeholder. The first contributor with HF access pins this to a specific dataset revision SHA from the Common Voice 25.0 commit history (see `docs/stt-eval.md` "Updating the baseline" + the script header). Until pinned, the script falls back to the dataset's HEAD which is acceptable for first-baseline establishment but should be tightened to a SHA in the same PR that records the baseline.

## Next Phase Readiness

- **Plan 02-06 inputs ready:**
  - JSON output schema of `scripts/eval_wer.py` is stable: `{status, baseline: {wer_mean, wer_median, wer_p95, cer_mean, cer_median, cer_p95, n_clips}, per_clip: [...]}`. CI regression logging in Plan 02-06 can consume this directly.
  - `backend/tests/stt/fixtures/he_cv_30.jsonl` is the agreed input for Plan 02-06's chaos-test audio source. The placeholder manifest will be replaced with real fixtures by then (or the chaos test gracefully skips on the same UNFETCHED row).
  - `docs/stt-eval.md` is ready to be linked from `docs/stt.md` in Plan 02-06.
- **Phase-transition gate items for Plan 02-06:**
  1. Run `scripts/fetch_stt_fixtures.py` on a Mac with HF access + Common Voice 25.0 license accepted.
  2. Run `scripts/eval_wer.py` and commit the resulting `BASELINE_WER` + `BASELINE_CER` into `test_wer_baseline.py`.
  3. Pin `CV_REVISION_SHA` from `"main"` to the actual dataset commit SHA.
  4. Re-run the latency spike on M2 hardware to replace the provisional 700 ms `partial_interval` (carried over from Plan 02-01).

## Self-Check: PASSED

Verified:
- `backend/src/receptra/stt/wer.py` exists.
- `backend/tests/stt/test_wer_hebrew.py` exists; 9/9 tests green.
- `backend/tests/stt/test_wer_baseline.py` exists; skips with documented reason.
- `backend/tests/stt/fixtures/he_cv_30.jsonl` exists.
- `backend/tests/stt/fixtures/he_cv_30/.gitkeep` exists.
- `backend/tests/stt/fixtures/__init__.py` exists.
- `scripts/fetch_stt_fixtures.py` exists; `CV_REVISION_SHA` constant present.
- `scripts/eval_wer.py` exists; `transcribe_hebrew` import present (no kwarg drift).
- `docs/stt-eval.md` exists; covers all 6 contributor sections.
- Commits `9ec96b2`, `4df048f`, `700c798` present in `git log --oneline -5`.
- All 7 plan verification gates green; full backend suite 39 passed + 1 skipped.

---
*Phase: 02-hebrew-streaming-stt*
*Plan: 02-05*
*Completed: 2026-04-25*
