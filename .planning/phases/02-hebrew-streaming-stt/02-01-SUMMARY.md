---
phase: "02-hebrew-streaming-stt"
plan: "02-01"
subsystem: stt
tags: [stt, spike, dependencies, apple-silicon, faster-whisper, silero-vad, license-allowlist, wave-0]
requires:
  - "backend/pyproject.toml with fastapi/uvicorn/pydantic stack (Plan 01-02)"
  - "scripts/check_licenses.sh single-source license gate (Plan 01-05)"
  - "Python 3.12 + uv 0.11.x toolchain (Plan 01-02)"
provides:
  - "backend/pyproject.toml — Phase 2 runtime deps pinned: faster-whisper>=1.2.1,<2; silero-vad>=6.2.1,<7; numpy>=2.0,<3; loguru>=0.7.3,<1"
  - "backend/pyproject.toml — Phase 2 dev deps pinned: jiwer>=4.0,<5; soundfile>=0.13"
  - "backend/uv.lock — full transitive resolution including ctranslate2 4.7.1, torch 2.11.0, onnxruntime 1.25.0, tokenizers 0.22.2, av 17.0.1"
  - "scripts/spike_stt_latency.py — reproducible Wave-0 latency tool with locked transcribe kwargs + embedded decision rule (700/1000/BLOCKED)"
  - "scripts/check_licenses.sh — PY_ALLOW extended with 5 pip-licenses 5+ verbatim strings; JS side excludes private self-reference"
  - ".planning/phases/02-hebrew-streaming-stt/02-01-SPIKE-RESULTS.md — Wave-0 spike results (UNMEASURED placeholder; partial_interval_decision=700 provisional) + durable contract for Plans 02-02..02-06"
affects:
  - "Plan 02-02 (lifespan refactor + WhisperModel load): consumes pinned MODEL_KWARGS contract (device=cpu, compute_type=int8, cpu_threads=4) from the spike tool"
  - "Plan 02-03 (Silero VAD wiring): consumes silero-vad 6.2.1 dep resolved here"
  - "Plan 02-04 (partial/final transcribe loop): consumes partial_interval_decision=700 (provisional) from 02-01-SPIKE-RESULTS.md"
  - "Plan 02-05 (WER eval harness): consumes jiwer 4.0.0 + soundfile 0.13.1 dev deps"
  - "Plan 02-06 (latency + observability): MUST re-run scripts/spike_stt_latency.py on reference M2 hardware and commit measured numbers back to 02-01-SPIKE-RESULTS.md before Phase 2 exits"
  - "Phase 1 CI license gate (.github/workflows/ci.yml): passes against the new lock without modification — the allowlist lives entirely in scripts/check_licenses.sh"
tech-stack:
  added:
    - "faster-whisper 1.2.1 (wraps CTranslate2 4.7.1 for CPU int8 STT inference on arm64)"
    - "silero-vad 6.2.1 (VAD endpointing; PyTorch 2.11 backend, ONNX fallback available)"
    - "torch 2.11.0 (silero-vad transitive, macOS arm64 wheel)"
    - "onnxruntime 1.25.0 (silero-vad optional ONNX path)"
    - "tokenizers 0.22.2 + av 17.0.1 (faster-whisper transitive)"
    - "loguru 0.7.3 (structured JSON logging; replaces stdlib logging.basicConfig in Plan 02-02)"
    - "numpy 2.0+ (PCM int16 -> float32 conversion; explicit pin even though transitive)"
    - "jiwer 4.0.0 (WER/CER computation for STT-05 — dev group)"
    - "soundfile 0.13.1 (read fixture WAV files in tests — dev group)"
  patterns:
    - "Hard-pinned Whisper kwargs (device=cpu, compute_type=int8, cpu_threads=4, num_workers=1) + transcribe kwargs (language=he, beam_size=1, condition_on_previous_text=False, without_timestamps=True) as the single-source contract surface — embedded in spike tool AND documented in RESEARCH §2/§7; downstream plans MUST reuse the same values"
    - "Warmup-then-measure spike shape: load model -> 1 s silence warmup transcribe -> N iters on synthetic 2 s 440 Hz sine -> p50/p95 via statistics.median + sorted[int(0.95*(N-1))]; monotonic clocks only"
    - "Decision-rule-embedded spike: the script encodes the three-way branch (p95<=700 -> 700 | p95<=1000 -> 1000 | else BLOCKED) so any future contributor re-running the spike produces the SAME output shape the downstream plans consume"
    - "UNMEASURED fallback branch in the spike tool: when model weights are absent, the script still writes a valid results doc with provisional partial_interval_decision=700 + explicit next-step (Plan 02-06 re-runs on reference M2). Downstream work is never blocked by a missing-model executor."
    - "License allowlist verbatim extension (not normalization): pip-licenses 5+ emits compound license strings literally (e.g. 'BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0', 'MPL-2.0 AND MIT', 'Apache-2.0 OR BSD-2-Clause', 'ISC License (ISCL)', '3-Clause BSD License'); allowlist is extended with each exact emitted string, never substituted with SPDX tags, preserving the gate's detection power."
key-files:
  created:
    - "scripts/spike_stt_latency.py"
    - ".planning/phases/02-hebrew-streaming-stt/02-01-SPIKE-RESULTS.md"
  modified:
    - "backend/pyproject.toml"
    - "backend/uv.lock"
    - "scripts/check_licenses.sh"
decisions:
  - "OPEN-2 locked at partial_interval_decision=700 ms (provisional). The spike tool embeds the decision rule so Plan 02-06 re-running on reference M2 hardware will auto-update or escalate. Downstream plans (02-02..02-06) consume 700 ms as the partial re-transcribe cadence until measured numbers replace it."
  - "OPEN-4 locked: new Phase 2 deps (torch 2.11.0 BSD-3-Clause, onnxruntime 1.25.0 MIT License, faster-whisper 1.2.1 MIT License, silero-vad 6.2.1 MIT License, ctranslate2 4.7.1 MIT) all pass the existing allowlist. Five allowlist additions were needed for PRE-EXISTING transitive deps whose license strings changed with pip-licenses 5+: packaging ('Apache-2.0 OR BSD-2-Clause'), protobuf ('3-Clause BSD License'), shellingham ('ISC License (ISCL)'), tqdm ('MPL-2.0 AND MIT'), numpy ('BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0'). All are permissive, all added VERBATIM per plan CRITICAL."
  - "License kwargs pinned in-script: the spike tool spells out WhisperModel + transcribe kwargs explicitly (not just via a dict) so the AST contract check in 02-01-PLAN.md <verify> passes AND downstream code review sees the contract at the call site. Kept the dict constants above as the documentation anchor."
  - "Faster-whisper 1.2.1 deliberately avoids device='mps' — faster-whisper has no Metal path (confirmed issue #911). CT2 runs via Apple Accelerate + oneDNN arm64 backend with int8 quantization, giving ~4x vs float32. This is a HARD ceiling the Wave-0 spike (when re-run on M2) will quantify."
  - "Spike runs from repo root's backend/ uv env (`cd backend && uv run python ../scripts/spike_stt_latency.py`), NOT from the Docker container, because the spike needs the HOST-filesystem model path (~/.receptra/models/whisper-turbo-ct2), not the container-mounted /models path. Settings.model_dir default ('/models') is container-side; the spike reads RECEPTRA_MODEL_DIR with ~/.receptra/models fallback."
  - "receptra-frontend self-reference excluded from license-checker --onlyAllow via --excludePackages. Rationale: license-checker treats any `private: true` package as UNLICENSED regardless of the `license` field. Excluding the root self-reference is the standard idiom; the exclusion is NARROW (one named package) and does NOT hide any third-party dep. Rule 3 fix for a pre-existing Plan 01-05 bug that would have blocked this plan's gate."
patterns-established:
  - "Pinned-contract-surface pattern: Phase 2's two most volatile values (WhisperModel constructor kwargs + transcribe kwargs) are encoded in a single script AND a decision doc, making the research -> implementation chain auditable. Downstream plans cite these values rather than re-deriving them."
  - "Spike-with-fallback pattern: measurement tools that MUST run on reference hardware but SHOULD produce a valid artifact on any hardware. The fallback path writes a clearly-labeled UNMEASURED placeholder with a provisional default and a concrete re-run task pinned to a specific future plan (02-06). Prevents measurement-blocked execution."
  - "Verbatim-license-allowlist pattern: pip-licenses compound strings are appended literally rather than decomposed. Keeps the allowlist a source of truth for what pip-licenses ACTUALLY emits (not what we wish it emitted)."
requirements-completed: []

# Metrics
duration: ~8min
completed: 2026-04-24
commits:
  - "3928bdd — chore(02-01): pin Phase 2 STT deps + patch license allowlist"
  - "6411ab5 — feat(02-01): add Wave-0 STT latency spike tool + UNMEASURED results"
---

# Phase 2 Plan 02-01: Phase 2 Dependency Lock + Wave-0 STT Latency Spike Summary

Lock Phase 2's dependency surface (faster-whisper + silero-vad + supporting deps) into `backend/pyproject.toml` / `backend/uv.lock`, verify the Phase 1 license allowlist accepts the new transitive deps (torch 2.11 + onnxruntime 1.25), and ship a reproducible Wave-0 latency spike tool that will lock the partial re-transcribe cadence (`stt_partial_interval_ms`) Plans 02-02..02-06 consume. This plan ships UNMEASURED placeholder spike results because the model weights are not on the executor filesystem; Plan 02-06 is the explicit re-run checkpoint.

## Overview

Plan 02-01 is the gatekeeper between RESEARCH and the WebSocket/VAD/Whisper wiring work that fills the rest of Phase 2. Three outputs, two atomic commits, five files touched.

- **Dep lock** — 4 runtime + 2 dev deps added; 10+ transitive deps resolved (notably torch 2.11.0, ctranslate2 4.7.1, onnxruntime 1.25.0). uv lock succeeds on Python 3.12 arm64 with no wheel-build fallback.
- **License gate** — `scripts/check_licenses.sh` passes (exit 0) against the new lock. Five verbatim allowlist additions required (all for pre-existing transitive deps whose license strings pip-licenses 5+ emits differently — details below). Zero GPL/AGPL creep; all new Phase 2 deps are MIT, Apache-2.0, or BSD-3-Clause. One Rule 3 fix to `check_licenses.sh`'s JS invocation (see Deviations).
- **Wave-0 spike tool** — `scripts/spike_stt_latency.py` is a ~340-line single-file reproducible baseline. It loads the model with the pinned CT2 int8 kwargs, warms up, runs N=10 steady-state transcribes on a synthetic 2s 440 Hz sine, computes p50/p95, and writes `02-01-SPIKE-RESULTS.md` with the decision (700/1000/BLOCKED). The model weights are not present on this executor, so the tool wrote the UNMEASURED placeholder with provisional `partial_interval_decision=700`, flagging Plan 02-06 as the re-run checkpoint.

The outputs form a durable contract: downstream plans read `02-01-SPIKE-RESULTS.md` for the partial cadence, and if they need the exact Whisper call shape they copy it from `scripts/spike_stt_latency.py` (which is the authoritative pinned version).

## What Was Built

### Task 1 — Dep lock + license allowlist patch (commit `3928bdd`)

**`backend/pyproject.toml` diff (lines 9–26):**

- Added under `[project].dependencies`:
  - `"faster-whisper>=1.2.1,<2"` — STT engine (MIT)
  - `"silero-vad>=6.2.1,<7"` — VAD endpointing (MIT)
  - `"numpy>=2.0,<3"` — PCM conversion (BSD-3-Clause compound)
  - `"loguru>=0.7.3,<1"` — structured logging (MIT)
- Added under `[dependency-groups].dev`:
  - `"jiwer>=4.0,<5"` — WER/CER (Apache-2.0)
  - `"soundfile>=0.13"` — fixture WAV I/O (BSD)

**`backend/uv.lock` — 982 lines added.** Key transitive resolutions:

| Package | Version | License (pip-licenses emission) |
|---------|---------|---------------------------------|
| ctranslate2 | 4.7.1 | MIT |
| torch | 2.11.0 | BSD-3-Clause |
| torchaudio | 2.11.0 | BSD License |
| onnxruntime | 1.25.0 | MIT License |
| tokenizers | 0.22.2 | Apache Software License |
| av | 17.0.1 | BSD-3-Clause |

All new Phase 2 deps match the existing allowlist verbatim — OPEN-4 is satisfied by the deps themselves.

**`scripts/check_licenses.sh` PY_ALLOW extensions (5 new verbatim strings):**

| String | Added because | Pre-existing dep |
|--------|---------------|------------------|
| `Apache-2.0 OR BSD-2-Clause` | packaging 26.1 emits this | packaging (transitive) |
| `3-Clause BSD License` | protobuf 7.34.1 emits this | protobuf (via onnxruntime) |
| `ISC License (ISCL)` | shellingham 1.5.4 emits this | shellingham (via typer -> huggingface_hub) |
| `MPL-2.0 AND MIT` | tqdm 4.67.3 emits this | tqdm (via huggingface_hub) |
| `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` | numpy 2.4.4 emits this | numpy (now explicit) |

Every added string is a permissive-licenses compound; no GPL/AGPL/research string was ever a candidate. Plan instruction "Do NOT substitute shorter SPDX tags for long-form names" was followed — pip-licenses' exact emission is what's in the allowlist.

### Task 2 — Wave-0 spike tool + UNMEASURED results (commit `6411ab5`)

**`scripts/spike_stt_latency.py`** (~340 LOC, executable):

Structure:
1. Pinned contract constants (`MODEL_KWARGS`, `TRANSCRIBE_KWARGS`) at module top as the documentation anchor.
2. `resolve_model_path()` honors `RECEPTRA_MODEL_DIR` env var (default `~/.receptra/models`), NOT the container-side `/models` default in `Settings`.
3. `run_spike()` — single function containing the full measurement protocol:
   - `time.monotonic()` around `WhisperModel(str(model_path), device="cpu", compute_type="int8", cpu_threads=4, num_workers=1)` → `model_load_ms`
   - Warmup transcribe on `np.zeros(16000, dtype=np.float32)` with the full pinned transcribe kwargs → `warmup_transcribe_ms`
   - Steady-state loop N=10 (argparse `--iters`) on a synthetic 2-second 440 Hz sine, amplitude 0.3; each iteration timed with `time.monotonic()`
   - p50 via `statistics.median`, p95 via `sorted(iter_ms)[int(0.95 * (N-1))]`
4. `decide_partial_interval(p95)` → 700 / 1000 / "BLOCKED" per plan's decision rule.
5. `write_measured_results()` / `write_unmeasured_results()` — branch on model-directory presence. Unmeasured path exits 1 (so contributors get a clear error) but writes a valid results doc with provisional `partial_interval_decision=700`.
6. JSON summary to stdout (measured path) via `json.dumps(..., indent=2)`.

Contract-visibility: `WhisperModel(...)` and both `model.transcribe(...)` calls spell out the kwargs inline (in addition to being defined as dict constants above). This satisfies the AST contract check in `02-01-PLAN.md <verify>` (which greps for literals like `cpu_threads=4`, `language=`, `condition_on_previous_text=False`) AND makes the pinned values visible at the call site.

Loguru is used for all progress logging (exercises the dep; logs include `{:.1f} ms` format patterns). No psutil. No `time.time()`. No audio files committed (the sine is generated in memory per run).

**`.planning/phases/02-hebrew-streaming-stt/02-01-SPIKE-RESULTS.md`** (UNMEASURED placeholder):

Content is the plan's fallback branch: all five numeric fields are labeled `UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks`. `partial_interval_decision = 700` is set as the provisional default. Host info is recorded (executor is macOS Darwin 26.4.1 arm64, cpu_count=10, Python 3.12.13 — close to but not identical to the reference M2 hardware). The reproduction command is embedded. The "Plan 02-06 will re-run this spike on reference M2 hardware" note is explicit.

## Decisions Made

All six decisions are in the frontmatter. Highlights:

1. **partial_interval_decision = 700 (provisional)** — locked as the contract Plans 02-02..02-06 consume until Plan 02-06 re-runs the spike on reference M2 hardware. The decision rule (700/1000/BLOCKED) is embedded in the tool so the re-run auto-produces the correct value.
2. **Five pip-licenses verbatim additions** — all are pre-existing transitive deps whose license strings changed with pip-licenses 5+. Zero new permissive categories introduced.
3. **Script runs from host `backend/` uv env**, not container — needs host-filesystem model path, not the container's `/models` mount.
4. **Faster-whisper runs CPU+int8 on Apple Silicon** — issue #911 confirms no Metal/MPS support. ~4x speedup vs float32 via Apple Accelerate + oneDNN arm64 backend.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pre-existing license-checker `UNLICENSED` failure on receptra-frontend self-reference**

- **Found during:** Task 1 (running `bash scripts/check_licenses.sh` after resolving all Python-side license strings)
- **Issue:** license-checker reports `receptra-frontend@0.1.0` as `UNLICENSED` because `package.json` has `"private": true`, even though `"license": "Apache-2.0"` is also declared. This is a license-checker behavior, not a bug in our package. The failure is pre-existing (from Plan 01-03's frontend scaffold + Plan 01-05's check_licenses.sh), not caused by Phase 2 deps. Verified by reverting all Phase 2 changes via `git stash` and re-running — the frontend failure reproduced before any of my changes, AND `packaging`'s license string also failed before my changes, confirming the Phase 1 gate was broken even before Phase 2 began (likely because Plan 01-05 used `make -n` dry-runs and never exercised the gate live).
- **Fix:** Added `--excludePackages "receptra-frontend@0.1.0"` to the license-checker invocation in `scripts/check_licenses.sh`. This exclusion is NARROW — it names the single workspace self-reference and does NOT hide any third-party package. The Apache-2.0 license on our own package is still declared in `package.json` and visible in the repo.
- **Files modified:** `scripts/check_licenses.sh`
- **Commit:** `3928bdd` (bundled with Task 1 dep lock)
- **Scope rationale:** Fixed because Task 1's explicit `<done>` requires `bash scripts/check_licenses.sh` to exit 0. Without this fix the plan could not complete. The fix is minimal and surgical.

**2. [Rule 2 - Critical Functionality] Pre-existing license allowlist missing entries for transitive deps**

- **Found during:** Task 1 (initial license gate run)
- **Issue:** Five transitive deps (`packaging`, `protobuf`, `shellingham`, `tqdm`, `numpy`) emit license strings under pip-licenses 5+ that the Plan 01-05 allowlist did not contain. These failures pre-date the Phase 2 dep additions (verified via `git stash`). Without fixing, the license gate would have been broken regardless of my plan work, which is why the plan explicitly calls out OPEN-4 as a task.
- **Fix:** Appended the 5 exact pip-licenses-emitted strings verbatim to `PY_ALLOW`. All five are compound permissive licenses (no single component is GPL/AGPL). Plan instruction "Do NOT substitute shorter SPDX tags for long-form names — match exactly what pip-licenses emits" was followed.
- **Files modified:** `scripts/check_licenses.sh`
- **Commit:** `3928bdd`
- **Scope rationale:** OPEN-4 mandates that the allowlist pass against the new lock. The plan's own action text is "If either is missing → append the exact license name(s)". This is exactly what was required.

### No Rule 4 (architectural) deviations

### Auth gates

None occurred — no network auth needed for this plan. Model download (`make models`, which would have given us a measured spike) was deliberately NOT run because the plan's autonomous-mode directive says: "If model not downloaded locally → cannot run live spike → write UNMEASURED placeholder with partial_interval_decision=700 (provisional), per plan's own fallback branch. Do not block; proceed." This is the documented flow, not a deviation.

## Spike Results Contract

The durable contract Plans 02-02..02-06 consume lives at `.planning/phases/02-hebrew-streaming-stt/02-01-SPIKE-RESULTS.md`. Current contract values:

```
status                      = UNMEASURED
partial_interval_decision   = 700     (provisional)
reproduction                = cd backend && uv run python ../scripts/spike_stt_latency.py --iters 10
re-run checkpoint           = Plan 02-06 (before Phase 2 exits, on reference M2 hardware)
```

Plan 02-04 should write against 700 ms partial cadence now. If Plan 02-06's re-run produces `p95 > 700`, the decision auto-promotes to 1000 and Plan 02-04's constants need a one-line update. If `p95 > 1000`, the BLOCKED outcome forces an escalation (OPEN-3: whisper.cpp + Core ML) before Phase 2 can exit.

## Self-Check: PASSED

All files claimed to be created/modified exist on disk; all commit hashes resolve in git log:

```
FOUND: backend/pyproject.toml
FOUND: backend/uv.lock
FOUND: scripts/check_licenses.sh
FOUND: scripts/spike_stt_latency.py
FOUND: .planning/phases/02-hebrew-streaming-stt/02-01-SPIKE-RESULTS.md
FOUND: 3928bdd (chore(02-01): pin Phase 2 STT deps + patch license allowlist)
FOUND: 6411ab5 (feat(02-01): add Wave-0 STT latency spike tool + UNMEASURED results)
```

Full plan verification (6 gates) re-run:

```
1: uv sync OK
2: imports OK (faster_whisper, silero_vad, jiwer, loguru, soundfile)
3: license gate OK (exit 0)
4: spike parses
5: results file exists
6: decision recorded (partial_interval_decision in 02-01-SPIKE-RESULTS.md)
```

## Known Stubs

**UNMEASURED spike results** — the only "stub" in this plan is the UNMEASURED placeholder in `02-01-SPIKE-RESULTS.md`. This is explicitly sanctioned by the plan's fallback branch and is tracked for re-run in Plan 02-06. Downstream plans (02-02..02-06) can and should proceed against the provisional `partial_interval_decision=700` — they are not blocked.

No other stubs, no hardcoded empty UI values, no "coming soon" placeholders.

## Pointer

- **Durable contract:** `.planning/phases/02-hebrew-streaming-stt/02-01-SPIKE-RESULTS.md`
- **Reproducible tool:** `scripts/spike_stt_latency.py`
- **Lock state:** `backend/uv.lock` (9 Phase-2-relevant packages resolved)
