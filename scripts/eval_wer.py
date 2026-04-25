#!/usr/bin/env python3
"""Batch WER + CER eval over the 30-sample Hebrew Common Voice fixture (STT-05).

The fixture set comes from ``mozilla-foundation/common_voice_25_0`` (CC0)
via ``scripts/fetch_stt_fixtures.py``. This script never touches HF Hub
itself — it only reads the already-committed WAV + JSONL fixtures from
disk and runs them through the locked ``transcribe_hebrew`` wrapper.

Pipeline
--------
1. Resolve model path (same logic as ``scripts/spike_stt_latency.py``).
2. Load ``WhisperModel`` with the LOCKED kwargs (device=cpu, compute_type=int8,
   cpu_threads=4, num_workers=1) and warm up on 1 s of silence.
3. Read ``backend/tests/stt/fixtures/he_cv_30.jsonl``. For each row:
   * read the WAV via ``soundfile.read`` (returns float64 → cast to float32
     mono 16 kHz),
   * call ``receptra.stt.engine.transcribe_hebrew`` (the SINGLE source of
     truth for Hebrew transcribe params — no kwarg duplication here),
   * compute WER + CER via ``receptra.stt.wer.compute_wer``.
4. Print a per-clip table to stderr; print aggregate JSON to stdout
   ``{baseline: {wer_mean, wer_median, cer_mean, cer_median}, per_clip: [...]}``.

Usage
-----
    cd backend && uv run python ../scripts/eval_wer.py
    cd backend && uv run python ../scripts/eval_wer.py --output-json /tmp/eval.json
    cd backend && uv run python ../scripts/eval_wer.py --limit 5

Skip behaviour
--------------
If the manifest contains a single ``UNFETCHED`` placeholder row (airgap
fallback from ``scripts/fetch_stt_fixtures.py``), this script exits 0 with
a clear stderr message — it does not synthesize fake numbers. The
regression test ``test_wer_baseline.py`` skips on the same condition.

Beam-size note
--------------
``transcribe_hebrew`` is locked to ``beam_size=1`` (matching live partials
in Plan 02-04). For a "ceiling" eval at ``beam_size=5`` see the follow-up
note in ``docs/stt-eval.md``; that is intentionally a separate Phase 7
exercise so the live + batch numbers stay comparable.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "backend" / "tests" / "stt" / "fixtures" / "he_cv_30.jsonl"
SAMPLE_RATE_HZ = 16_000
WARMUP_SECONDS = 1.0


def _resolve_model_path() -> Path:
    """Match scripts/spike_stt_latency.py.resolve_model_path so all entry
    points agree on $MODEL_DIR/whisper-turbo-ct2."""
    root = Path(
        os.environ.get(
            "RECEPTRA_MODEL_DIR", str(Path.home() / ".receptra" / "models")
        )
    )
    return root / "whisper-turbo-ct2"


def _read_manifest(manifest: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with manifest.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
    return rows


def _is_placeholder(rows: list[dict[str, Any]]) -> bool:
    return len(rows) == 1 and rows[0].get("id") == "UNFETCHED"


def _read_wav_f32(path: Path) -> NDArray[np.float32]:
    """Read a 16 kHz mono WAV and return float32 in [-1.0, 1.0]."""
    import soundfile as sf

    audio, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if sr != SAMPLE_RATE_HZ:
        raise RuntimeError(
            f"{path} has sample rate {sr} Hz; expected {SAMPLE_RATE_HZ} Hz. "
            "Re-run scripts/fetch_stt_fixtures.py to regenerate."
        )
    if audio.ndim != 1:
        # Mix to mono (defensive — fetch script writes mono int16).
        audio = audio.mean(axis=1)
    return np.ascontiguousarray(audio, dtype=np.float32)


def _percentile(values: list[float], p: float) -> float:
    """Linear-interpolation percentile matching numpy.percentile (default
    method)."""
    return float(np.percentile(values, p))  # type: ignore[no-any-return]


def run_eval(
    manifest: Path, fixtures_dir: Path, limit: int | None
) -> dict[str, Any]:
    rows = _read_manifest(manifest)
    if _is_placeholder(rows):
        sys.stderr.write(
            "Manifest is the airgap placeholder — fixtures unfetched. "
            "Run `python scripts/fetch_stt_fixtures.py` first.\n"
        )
        return {
            "status": "skipped",
            "reason": "fixtures_unfetched",
            "baseline": None,
            "per_clip": [],
        }

    if limit is not None:
        rows = rows[:limit]

    model_path = _resolve_model_path()
    if not model_path.exists():
        sys.stderr.write(
            f"ERROR: model not found at {model_path}. "
            "Run `make models` to fetch ivrit-ai/whisper-large-v3-turbo-ct2.\n"
        )
        return {
            "status": "skipped",
            "reason": "model_missing",
            "baseline": None,
            "per_clip": [],
        }

    # Lazy imports so this script can be syntax-checked + AST-imported in CI
    # without faster-whisper / CT2 backend present.
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]

    from receptra.stt.engine import transcribe_hebrew
    from receptra.stt.wer import compute_wer

    sys.stderr.write(f"Loading WhisperModel from {model_path} ...\n")
    t0 = time.monotonic()
    model = WhisperModel(
        str(model_path),
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
        num_workers=1,
    )
    load_ms = (time.monotonic() - t0) * 1000.0
    sys.stderr.write(f"loaded in {load_ms:.1f} ms\n")

    # Warmup: 1 s silence through transcribe_hebrew (Pitfall #7 — first
    # transcribe is 2-3x slower than steady state).
    warmup_audio = np.zeros(int(SAMPLE_RATE_HZ * WARMUP_SECONDS), dtype=np.float32)
    _ = transcribe_hebrew(model, warmup_audio)

    per_clip: list[dict[str, Any]] = []
    sys.stderr.write(f"\n{'id':<14} {'WER':>7} {'CER':>7} {'dur_ms':>8} {'ref…':<30}\n")
    sys.stderr.write("-" * 80 + "\n")

    for row in rows:
        wav_rel = row.get("wav")
        if not wav_rel:
            continue
        wav_path = fixtures_dir / wav_rel
        ref = row["ref"]
        audio = _read_wav_f32(wav_path)
        text, info = transcribe_hebrew(model, audio)
        metrics = compute_wer(ref, text)
        per_clip.append(
            {
                "id": row["id"],
                "wer": metrics["wer"],
                "cer": metrics["cer"],
                "duration_ms": row.get("duration_ms"),
                "ref": ref,
                "hyp": text,
                "language": info.get("language"),
            }
        )
        ref_preview = ref[:28] + "…" if len(ref) > 28 else ref
        sys.stderr.write(
            f"{row['id']:<14} "
            f"{metrics['wer']:>7.3f} "
            f"{metrics['cer']:>7.3f} "
            f"{row.get('duration_ms', 0):>8} "
            f"{ref_preview:<30}\n"
        )

    if not per_clip:
        sys.stderr.write("No clips evaluated.\n")
        return {
            "status": "skipped",
            "reason": "no_clips",
            "baseline": None,
            "per_clip": [],
        }

    wers = [c["wer"] for c in per_clip]
    cers = [c["cer"] for c in per_clip]
    baseline = {
        "wer_mean": statistics.fmean(wers),
        "wer_median": statistics.median(wers),
        "wer_p95": _percentile(wers, 95),
        "cer_mean": statistics.fmean(cers),
        "cer_median": statistics.median(cers),
        "cer_p95": _percentile(cers, 95),
        "n_clips": len(per_clip),
    }
    sys.stderr.write("-" * 80 + "\n")
    sys.stderr.write(
        f"AGGREGATE  wer_mean={baseline['wer_mean']:.3f}  "
        f"wer_median={baseline['wer_median']:.3f}  "
        f"cer_mean={baseline['cer_mean']:.3f}  "
        f"cer_median={baseline['cer_median']:.3f}  "
        f"n={baseline['n_clips']}\n"
    )
    return {
        "status": "ok",
        "baseline": baseline,
        "per_clip": per_clip,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch Hebrew WER + CER eval over the 30-sample fixture set."
    )
    parser.add_argument(
        "--fixtures", type=Path, default=DEFAULT_MANIFEST,
        help=f"Path to he_cv_30.jsonl (default: {DEFAULT_MANIFEST}).",
    )
    parser.add_argument(
        "--output-json", type=Path, default=None,
        help="Optional path to write the JSON report (default: stdout).",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap clips evaluated (default: all rows in manifest).",
    )
    args = parser.parse_args()

    manifest = args.fixtures
    if not manifest.exists():
        sys.stderr.write(
            f"ERROR: manifest {manifest} not found. "
            "Run `python scripts/fetch_stt_fixtures.py` first.\n"
        )
        return 1
    fixtures_dir = manifest.with_suffix("")  # he_cv_30.jsonl → he_cv_30/
    if not fixtures_dir.is_dir():
        # Fall back to a sibling directory named after the manifest stem.
        fixtures_dir = manifest.parent / manifest.stem

    report = run_eval(manifest, fixtures_dir, args.limit)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_json is not None:
        args.output_json.write_text(payload + "\n", encoding="utf-8")
        sys.stderr.write(f"wrote JSON report to {args.output_json}\n")
    else:
        print(payload)
    # Skip is not a failure: ok status + skipped status both return 0.
    return 0


if __name__ == "__main__":
    sys.exit(main())
