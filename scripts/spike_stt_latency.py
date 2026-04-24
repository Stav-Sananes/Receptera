#!/usr/bin/env python3
"""Wave-0 STT latency spike (Phase 2, Plan 02-01).

Reproducible baseline that loads the ivrit-ai/whisper-large-v3-turbo-ct2 model
via faster-whisper, warms up, then transcribes a synthetic 2-second 440 Hz sine
buffer N times on CPU (int8) and reports p50/p95 wall-clock latency.

The measured p95 locks `stt_partial_interval_ms` — the cadence at which Plan
02-04 will re-transcribe the active VAD buffer. Decision rule (per RESEARCH
§7 partial-re-transcribe strategy + OPEN-2):

    p95 <=  700 ms  ->  partial_interval_decision = 700     (RESEARCH default)
    p95 <= 1000 ms  ->  partial_interval_decision = 1000    (fallback)
    p95  > 1000 ms  ->  partial_interval_decision = BLOCKED (escalate OPEN-3)

Model loading + transcribe kwargs are HARD-PINNED to the values RESEARCH §2
and §7 require; do NOT parametrize them here.

Usage:
    # From repo root (after `uv sync --all-groups` in backend/):
    cd backend && uv run python ../scripts/spike_stt_latency.py [--iters N]

Environment:
    RECEPTRA_MODEL_DIR  Host-side model root. Default: ~/.receptra/models
                        (MATCHES Plan 01-05 `scripts/download_models.sh`.)

Output:
    - JSON summary to stdout
    - Markdown results file:
      .planning/phases/02-hebrew-streaming-stt/02-01-SPIKE-RESULTS.md

If the model directory is missing, the script writes an UNMEASURED placeholder
results file (provisional partial_interval_decision=700) and exits 1 with an
actionable error pointing the contributor to `make models`.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from loguru import logger


# ---- Locked contract values (RESEARCH §2 + §7). Do NOT change without a new plan. ----
SAMPLE_RATE_HZ: int = 16_000
BUFFER_SECONDS: float = 2.0
SINE_FREQ_HZ: float = 440.0
SINE_AMPLITUDE: float = 0.3
WARMUP_BUFFER_SECONDS: float = 1.0  # RESEARCH §3 warmup note

# Transcribe kwargs, pinned per RESEARCH §7.
TRANSCRIBE_KWARGS: dict[str, object] = {
    "language": "he",
    "task": "transcribe",
    "beam_size": 1,
    "best_of": 1,
    "temperature": 0.0,
    "condition_on_previous_text": False,
    "vad_filter": False,
    "without_timestamps": True,
}

# WhisperModel constructor kwargs, pinned per RESEARCH §2.
MODEL_KWARGS: dict[str, object] = {
    "device": "cpu",
    "compute_type": "int8",
    "cpu_threads": 4,
    "num_workers": 1,
}

RESULTS_PATH = (
    Path(__file__).resolve().parent.parent
    / ".planning"
    / "phases"
    / "02-hebrew-streaming-stt"
    / "02-01-SPIKE-RESULTS.md"
)


def resolve_model_path() -> Path:
    root = Path(os.environ.get("RECEPTRA_MODEL_DIR", str(Path.home() / ".receptra" / "models")))
    return root / "whisper-turbo-ct2"


def make_sine_buffer(duration_seconds: float) -> np.ndarray:
    n = int(SAMPLE_RATE_HZ * duration_seconds)
    t = np.arange(n, dtype=np.float32) / float(SAMPLE_RATE_HZ)
    return (SINE_AMPLITUDE * np.sin(2.0 * np.pi * SINE_FREQ_HZ * t)).astype(np.float32)


def host_info() -> dict[str, object]:
    # platform-stdlib only; do NOT add psutil per plan CRITICAL list.
    return {
        "platform_machine": platform.machine(),
        "platform_processor": platform.processor(),
        "mac_ver": platform.mac_ver()[0],
        "os_cpu_count": os.cpu_count(),
        "python_version": platform.python_version(),
    }


def decide_partial_interval(p95_ms: float) -> int | str:
    if p95_ms <= 700.0:
        return 700
    if p95_ms <= 1000.0:
        return 1000
    return "BLOCKED"


@dataclass
class SpikeResult:
    model_load_ms: float
    warmup_transcribe_ms: float
    steady_state_p50_ms: float
    steady_state_p95_ms: float
    iters: int
    partial_interval_decision: int | str
    host: dict[str, object]
    iter_ms: list[float]


def run_spike(model_path: Path, iters: int) -> SpikeResult:
    # Import inside function so UNMEASURED path doesn't require faster-whisper + CT2.
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]

    logger.info("loading WhisperModel from {} (device=cpu, compute_type=int8)", model_path)
    t0 = time.monotonic()
    # Constructor kwargs match MODEL_KWARGS dict above; spelled out here so the
    # pinned contract (device, compute_type, cpu_threads=4, num_workers=1) is
    # visible to code review AND to the AST contract check in 02-01-PLAN.md.
    model = WhisperModel(
        str(model_path),
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
        num_workers=1,
    )
    model_load_ms = (time.monotonic() - t0) * 1000.0
    logger.info("model loaded in {:.1f} ms", model_load_ms)

    # Warmup: 1 s of silence (float32 zeros). RESEARCH Pitfall 7 warns the first
    # transcribe is 2-3x slower than steady state — this primes CTranslate2.
    warmup_audio = np.zeros(int(SAMPLE_RATE_HZ * WARMUP_BUFFER_SECONDS), dtype=np.float32)
    logger.info("running warmup transcribe (1s silence)")
    t0 = time.monotonic()
    # Kwargs match TRANSCRIBE_KWARGS dict above; spelled out here for contract
    # visibility (language="he" is MANDATORY per ivrit-ai model card).
    segments, _info = model.transcribe(
        warmup_audio,
        language="he",
        task="transcribe",
        beam_size=1,
        best_of=1,
        temperature=0.0,
        condition_on_previous_text=False,
        vad_filter=False,
        without_timestamps=True,
    )
    _ = [s.text for s in segments]  # drain generator
    warmup_ms = (time.monotonic() - t0) * 1000.0
    logger.info("warmup transcribe: {:.1f} ms", warmup_ms)

    # Steady-state loop: N transcribes of a synthetic 2s 440 Hz sine.
    sine = make_sine_buffer(BUFFER_SECONDS)
    iter_ms: list[float] = []
    logger.info("running steady-state loop N={}", iters)
    for i in range(iters):
        t0 = time.monotonic()
        segments, _info = model.transcribe(
            sine,
            language="he",
            task="transcribe",
            beam_size=1,
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=False,
            without_timestamps=True,
        )
        _ = [s.text for s in segments]
        dt_ms = (time.monotonic() - t0) * 1000.0
        iter_ms.append(dt_ms)
        logger.debug("  iter {}: {:.1f} ms", i, dt_ms)

    p50 = statistics.median(iter_ms)
    sorted_ms = sorted(iter_ms)
    # p95 index: floor(0.95 * (N-1)); for N=10 -> index 8.
    p95_idx = int(0.95 * (len(sorted_ms) - 1))
    p95 = sorted_ms[p95_idx]

    decision = decide_partial_interval(p95)
    logger.info("p50={:.1f} ms  p95={:.1f} ms  decision={}", p50, p95, decision)

    return SpikeResult(
        model_load_ms=model_load_ms,
        warmup_transcribe_ms=warmup_ms,
        steady_state_p50_ms=p50,
        steady_state_p95_ms=p95,
        iters=iters,
        partial_interval_decision=decision,
        host=host_info(),
        iter_ms=iter_ms,
    )


def write_measured_results(result: SpikeResult, repro_cmd: str) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    decision = result.partial_interval_decision
    decision_note: str
    if decision == 700:
        decision_note = "RESEARCH default (Option A confirmed): p95 fits the 700 ms partial cadence."
    elif decision == 1000:
        decision_note = "Fallback (RESEARCH §7): p95 exceeded 700 ms but remains under 1 s."
    else:
        decision_note = (
            "BLOCKER for Plan 02-04: steady-state p95 > 1000 ms. Escalate OPEN-3 "
            "(whisper.cpp + Core ML) OR accept partials >1s (violates STT-03)."
        )

    iter_line = ", ".join(f"{ms:.1f}" for ms in result.iter_ms)
    host_json = json.dumps(result.host, indent=2)
    content = f"""# Phase 2 Plan 02-01 — Wave-0 STT Latency Spike Results

**Status:** MEASURED
**Spike tool:** `scripts/spike_stt_latency.py`
**Model:** `ivrit-ai/whisper-large-v3-turbo-ct2`
**Iterations:** {result.iters}

## Measurements (wall-clock, monotonic)

| Metric | Value |
|--------|-------|
| `model_load_ms` | {result.model_load_ms:.1f} |
| `warmup_transcribe_ms` | {result.warmup_transcribe_ms:.1f} |
| `steady_state_p50_ms` | {result.steady_state_p50_ms:.1f} |
| `steady_state_p95_ms` | {result.steady_state_p95_ms:.1f} |
| `iters` | {result.iters} |
| `iter_ms` | {iter_line} |

## Decision (contract for Plans 02-02..02-06)

```
partial_interval_decision = {decision}
```

{decision_note}

## Host info

```json
{host_json}
```

## Reproduction

```
{repro_cmd}
```

## Interpretation

The steady-state p95 transcribe time on a synthetic 2-second buffer is what
drives the partial-re-transcribe cadence Plan 02-04 will consume. On
`cpu`/`int8`/`cpu_threads=4`, one transcribe must complete faster than the
partial interval or the server backs up. A p95 under 700 ms confirms the
RESEARCH default; a p95 between 700–1000 ms demands the loosened cadence;
anything above 1000 ms blocks Plan 02-04 and forces a runtime swap (OPEN-3
whisper.cpp + Core ML) or a relaxed partial contract.
"""
    RESULTS_PATH.write_text(content, encoding="utf-8")
    logger.info("wrote {}", RESULTS_PATH)


def write_unmeasured_results(model_path: Path, repro_cmd: str) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    host_json = json.dumps(host_info(), indent=2)
    content = f"""# Phase 2 Plan 02-01 — Wave-0 STT Latency Spike Results

**Status:** UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks
**Reason:** Model weights not present on the executor filesystem.
Expected location: `{model_path}` (not found).
Run `make models` from repo root (Phase 1 Plan 01-05) to fetch
`ivrit-ai/whisper-large-v3-turbo-ct2` (~1.5 GB) into `$MODEL_DIR`.

**Spike tool:** `scripts/spike_stt_latency.py`
**Model:** `ivrit-ai/whisper-large-v3-turbo-ct2`

## Measurements (UNMEASURED)

| Metric | Value |
|--------|-------|
| `model_load_ms` | UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks |
| `warmup_transcribe_ms` | UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks |
| `steady_state_p50_ms` | UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks |
| `steady_state_p95_ms` | UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks |
| `iters` | UNMEASURED — contributor must run on M2 hardware before Plan 02-04 locks |

## Decision (contract for Plans 02-02..02-06)

```
partial_interval_decision = 700
```

**Provisional default.** Plan 02-06 will re-run this spike on reference M2
hardware and bump to 1000 if the measured p95 > 700 ms (or escalate OPEN-3 if
p95 > 1000 ms). Until then, downstream plans may assume the RESEARCH default
(700 ms) because (a) it matches RESEARCH §7 Option A, and (b) RESEARCH §1
already verified the packages install cleanly on arm64, so the only unknown is
the steady-state wall-clock — which the fallback re-run in Plan 02-06 will
resolve before Phase 2 exits.

## Host info (executor, not reference hardware)

```json
{host_json}
```

## Reproduction (on reference M2 hardware, AFTER `make models`)

```
{repro_cmd}
```

## Interpretation

This plan could not run the spike because the model weights were not on disk
at the time of execution. The decision rule (700 / 1000 / BLOCKED) is embedded
in `scripts/spike_stt_latency.py` and will auto-fill correct numbers the next
time a contributor runs the script with the model present. Plan 02-04 should
consume `partial_interval_decision = 700` as a provisional default AND include
a follow-up task in Plan 02-06 that re-executes this spike and commits the
measured numbers back to this file before Phase 2 closes.
"""
    RESULTS_PATH.write_text(content, encoding="utf-8")
    logger.info("wrote UNMEASURED placeholder {}", RESULTS_PATH)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--iters",
        type=int,
        default=10,
        help="Number of steady-state transcribes after the warmup (default: 10).",
    )
    args = parser.parse_args()

    repro_cmd = f"cd backend && uv run python ../scripts/spike_stt_latency.py --iters {args.iters}"

    model_path = resolve_model_path()
    if not model_path.exists():
        logger.error("model directory not found at {}", model_path)
        logger.error(
            "run `make models` from repo root (Phase 1 Plan 01-05) to fetch "
            "ivrit-ai/whisper-large-v3-turbo-ct2 into $MODEL_DIR "
            "(default: ~/.receptra/models)."
        )
        write_unmeasured_results(model_path, repro_cmd)
        return 1

    result = run_spike(model_path, args.iters)
    write_measured_results(result, repro_cmd)

    # JSON summary to stdout for programmatic consumption.
    print(
        json.dumps(
            {
                "model_load_ms": result.model_load_ms,
                "warmup_transcribe_ms": result.warmup_transcribe_ms,
                "steady_state_p50_ms": result.steady_state_p50_ms,
                "steady_state_p95_ms": result.steady_state_p95_ms,
                "iters": result.iters,
                "partial_interval_decision": result.partial_interval_decision,
                "host": result.host,
            },
            indent=2,
        )
    )
    if result.partial_interval_decision == "BLOCKED":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
