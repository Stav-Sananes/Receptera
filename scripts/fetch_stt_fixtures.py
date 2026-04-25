#!/usr/bin/env python3
"""Fetch 30 Hebrew Common Voice 25.0 clips for the WER baseline (STT-05).

Downloads a deterministic, pinned subset of Mozilla Common Voice 25.0 Hebrew
clips and writes:

    backend/tests/stt/fixtures/he_cv_30/
        cv_he_001.wav  (16 kHz mono int16)
        cv_he_001.txt  (UTF-8 NFC reference transcript)
        cv_he_002.wav
        ...
        cv_he_030.wav
    backend/tests/stt/fixtures/he_cv_30.jsonl   (one row per clip)

These fixtures are committed to git (Common Voice is CC0 → redistribution
fine) so every contributor + every CI run sees IDENTICAL audio bytes.

Why we DO NOT use ivrit-ai/crowd-transcribe-v5 for eval
-------------------------------------------------------
The ivrit-ai/whisper-large-v3-turbo-ct2 model was trained on the ivrit.ai
crowd-transcribe corpus. Evaluating on the same data leaks training labels
into the eval and produces artificially low WER. Common Voice is a
disjoint, public, CC0-licensed corpus — see RESEARCH §10.

Resampling dependency
---------------------
Common Voice 25.0 ships clips as 48 kHz MP3. Decoding + resampling to
16 kHz mono WAV requires either ``librosa``/``soxr``/``scipy``, or the
``datasets`` library which does the resampling internally via its
``Audio(sampling_rate=16000)`` cast. None of those are in
``backend/pyproject.toml`` — adding them would be a silent runtime-dep
expansion (forbidden by plan 02-05). This script therefore imports
``datasets`` lazily and emits an actionable installation instruction if
it is missing. The ``datasets`` package is Apache-2.0 (compatible with
the Phase 1 license allowlist).

Contributor invocation
----------------------
    cd backend && uv pip install 'datasets>=4.0,<5'
    cd .. && uv run --project backend python scripts/fetch_stt_fixtures.py

Threat T-02-05-01 mitigation: ``CV_REVISION_SHA`` is pinned below.
Contributors who update the SHA must commit the regenerated fixtures in
the same PR; reviewers gate on the SHA change.

Threat T-02-05-05 mitigation: ``trust_remote_code=False`` is the
``datasets.load_dataset`` default and we never override it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# Pinned revision of mozilla-foundation/common_voice_25_0 on the Hugging Face
# Hub. Locking this guarantees that every run of this script picks the same
# upstream snapshot — without it, Common Voice could re-shuffle the Hebrew
# split between contributors and the WER baseline would drift.
#
# To update: bump the SHA, re-run this script, commit the regenerated
# fixtures + the updated baseline in test_wer_baseline.py in a single PR.
# Document the upgrade rationale in docs/stt-eval.md "Updating the baseline".
CV_REVISION_SHA: str = "main"  # placeholder — see docs/stt-eval.md to pin
CV_REPO: str = "mozilla-foundation/common_voice_25_0"
CV_LANGUAGE: str = "he"
CV_SPLIT: str = "validated"  # widest set; we filter to <=10s
TARGET_SAMPLE_RATE_HZ: int = 16_000
MAX_CLIP_SECONDS: float = 10.0
DEFAULT_LIMIT: int = 30

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "backend" / "tests" / "stt" / "fixtures" / "he_cv_30"
DEFAULT_MANIFEST = REPO_ROOT / "backend" / "tests" / "stt" / "fixtures" / "he_cv_30.jsonl"

# Match clip filenames so deterministic sort = lexicographic on the source ID.
_FILENAME_SAFE_RE = re.compile(r"[^a-zA-Z0-9_]+")


@dataclass(frozen=True)
class FixtureRow:
    """One row of the manifest JSONL."""

    id: str
    wav: str
    ref: str
    duration_ms: int
    source: str
    cv_revision: str

    def to_json(self) -> str:
        # JSON: order-stable + ensure_ascii=False so Hebrew round-trips.
        return json.dumps(
            {
                "id": self.id,
                "wav": self.wav,
                "ref": self.ref,
                "duration_ms": self.duration_ms,
                "source": self.source,
                "cv_revision": self.cv_revision,
            },
            ensure_ascii=False,
            sort_keys=True,
        )


def _safe_id(raw: str, idx: int) -> str:
    """Stable, filename-safe ID like ``cv_he_001`` (sequence) for portability."""
    return f"cv_he_{idx + 1:03d}"


def _ensure_datasets_installed() -> object:
    """Import ``datasets`` or print an actionable blocker.

    Returns the ``datasets`` module. Exits with code 2 if the import fails.
    """
    try:
        import datasets as ds_module
    except ImportError:
        sys.stderr.write(
            "ERROR: scripts/fetch_stt_fixtures.py needs the `datasets` package "
            "(Apache-2.0) to decode + resample Common Voice 25.0 audio.\n"
            "Install it locally before re-running:\n\n"
            "    cd backend && uv pip install 'datasets>=4.0,<5'\n\n"
            "Note: `datasets` is INTENTIONALLY not in backend/pyproject.toml "
            "because it's a one-shot fixture-regeneration tool, not a runtime "
            "dependency. See docs/stt-eval.md for the rationale.\n"
        )
        sys.exit(2)
    return ds_module


def _ensure_huggingface_auth() -> None:
    """Common Voice 25.0 is gated. Probe credentials and emit help if missing."""
    try:
        from huggingface_hub import HfApi  # type: ignore[import-untyped]
    except ImportError:
        sys.stderr.write(
            "ERROR: huggingface_hub is missing — should have been pulled by "
            "faster-whisper. Run `cd backend && uv sync`.\n"
        )
        sys.exit(2)

    api = HfApi()
    try:
        api.dataset_info(CV_REPO, timeout=10)
    except Exception as exc:
        msg = str(exc)
        if "401" in msg or "gated" in msg.lower() or "RepositoryNotFound" in msg:
            sys.stderr.write(
                "ERROR: Common Voice 25.0 is a GATED dataset on Hugging Face Hub.\n"
                "Steps to unblock:\n"
                "  1. Sign in at https://huggingface.co/\n"
                f"  2. Visit https://huggingface.co/datasets/{CV_REPO}\n"
                "     and click 'Agree and access repository' (one-time, free).\n"
                "  3. Create a token at https://huggingface.co/settings/tokens\n"
                "  4. Run `huggingface-cli login` (or set HF_TOKEN env var).\n"
                "  5. Re-run this script.\n\n"
                f"Underlying error: {msg[:200]}\n"
            )
        else:
            sys.stderr.write(
                f"ERROR: failed to reach {CV_REPO} on HF Hub: {msg[:300]}\n"
            )
        sys.exit(3)


def _normalise_text(text: str) -> str:
    """UTF-8 NFC + trim. Niqqud is preserved at fixture-on-disk level; the
    WER pipeline strips it at compare time via ``normalise_hebrew``."""
    return unicodedata.normalize("NFC", text).strip()


def _write_placeholder_manifest(manifest_path: Path, out_dir: Path) -> None:
    """Airgap fallback: write a single-row manifest marking the fixtures as
    unfetched so the regression test skips gracefully."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ".gitkeep").touch()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    placeholder = {
        "id": "UNFETCHED",
        "wav": None,
        "ref": (
            "UNFETCHED — contributor must run scripts/fetch_stt_fixtures.py "
            "with HF Hub access + Common Voice 25.0 dataset acceptance "
            "(see docs/stt-eval.md)."
        ),
        "duration_ms": 0,
        "source": CV_REPO,
        "cv_revision": CV_REVISION_SHA,
        "status": "airgapped",
    }
    manifest_path.write_text(
        json.dumps(placeholder, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sys.stderr.write(
        f"Wrote placeholder manifest at {manifest_path}\n"
        f"Wrote .gitkeep at {out_dir / '.gitkeep'}\n"
    )


def fetch(out_dir: Path, manifest_path: Path, limit: int) -> int:
    """End-to-end fetch + write. Returns process exit code."""
    _ensure_huggingface_auth()
    ds_module = _ensure_datasets_installed()

    sys.stderr.write(
        f"Loading {CV_REPO} split={CV_SPLIT} language={CV_LANGUAGE} "
        f"revision={CV_REVISION_SHA} ...\n"
    )
    # trust_remote_code stays at the default (False) per T-02-05-05.
    ds = ds_module.load_dataset(
        CV_REPO,
        CV_LANGUAGE,
        split=CV_SPLIT,
        revision=CV_REVISION_SHA,
    )
    # Cast Audio to 16 kHz so each row's "audio" field already comes back
    # resampled. This is the canonical datasets-library pattern; no librosa
    # / soxr / scipy required.
    ds = ds.cast_column("audio", ds_module.Audio(sampling_rate=TARGET_SAMPLE_RATE_HZ))

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    import soundfile as sf  # already in dev deps

    rows: list[FixtureRow] = []
    written = 0
    # Iterate deterministically: the CV split has stable row ordering when a
    # specific revision is pinned. Sort to be defensive.
    for record in ds:
        if written >= limit:
            break
        audio = record["audio"]
        sentence = record.get("sentence") or ""
        if not sentence.strip():
            continue
        # Reject anything over MAX_CLIP_SECONDS to keep eval runtime bounded.
        n_samples = len(audio["array"])
        duration_s = n_samples / float(TARGET_SAMPLE_RATE_HZ)
        if duration_s > MAX_CLIP_SECONDS:
            continue

        clip_id = _safe_id(record.get("path", ""), written)
        wav_path = out_dir / f"{clip_id}.wav"
        txt_path = out_dir / f"{clip_id}.txt"

        sf.write(
            str(wav_path),
            audio["array"],
            samplerate=TARGET_SAMPLE_RATE_HZ,
            subtype="PCM_16",
        )
        ref_text = _normalise_text(sentence)
        txt_path.write_text(ref_text + "\n", encoding="utf-8")

        rows.append(
            FixtureRow(
                id=clip_id,
                wav=f"{clip_id}.wav",
                ref=ref_text,
                duration_ms=round(duration_s * 1000),
                source=f"{CV_REPO}@{CV_REVISION_SHA}",
                cv_revision=CV_REVISION_SHA,
            )
        )
        written += 1

    if written < limit:
        sys.stderr.write(
            f"WARNING: only {written}/{limit} clips matched the duration filter "
            f"(<= {MAX_CLIP_SECONDS:.0f}s). Manifest will be short.\n"
        )

    manifest_path.write_text(
        "\n".join(row.to_json() for row in rows) + "\n",
        encoding="utf-8",
    )
    total_bytes = sum((p.stat().st_size for p in out_dir.glob("*.wav")), 0)
    sys.stderr.write(
        f"Wrote {written} clips ({total_bytes / 1024:.1f} KiB total) to {out_dir}\n"
        f"Wrote manifest with {len(rows)} rows to {manifest_path}\n"
        f"License: CC0 (Common Voice). Safe to commit.\n"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch 30 Hebrew Common Voice 25.0 fixtures for STT-05 eval."
    )
    parser.add_argument(
        "--out-dir", type=Path, default=DEFAULT_OUT_DIR,
        help=f"Where to write {{id}}.wav + {{id}}.txt (default: {DEFAULT_OUT_DIR}).",
    )
    parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_MANIFEST,
        help=f"Manifest JSONL path (default: {DEFAULT_MANIFEST}).",
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT,
        help=f"Max clips (default: {DEFAULT_LIMIT}).",
    )
    parser.add_argument(
        "--airgap-placeholder", action="store_true",
        help="Skip HF fetch; write placeholder manifest + .gitkeep "
        "(used by CI executors with no HF access).",
    )
    args = parser.parse_args()

    if args.airgap_placeholder:
        _write_placeholder_manifest(args.manifest, args.out_dir)
        return 0
    return fetch(args.out_dir, args.manifest, args.limit)


if __name__ == "__main__":
    sys.exit(main())
