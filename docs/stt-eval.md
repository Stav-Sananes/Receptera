# Hebrew STT Evaluation (STT-05)

This doc describes how Receptra measures Hebrew Speech-to-Text accuracy and
how contributors keep the regression baseline honest.

The eval is **informational, not a pass/fail gate**. The goal is trend
detection — surface when a dependency upgrade or model swap silently
degrades Hebrew transcription so a human can review it.

---

## What gets measured

For every clip in the seeded 30-sample fixture set we report two numbers:

- **WER** (Word Error Rate) — the standard speech-recognition metric.
  Counts insertions + deletions + substitutions at the **word** level,
  divided by the reference word count.
- **CER** (Character Error Rate) — same arithmetic at the **character**
  level. We track CER alongside WER because Hebrew is morphologically
  agglutinative: a one-character prefix swap (ב/ל/מ etc.) registers as a
  full word error under WER but as `1/N` under CER. CER is often the more
  stable signal across small Hebrew vocab differences.

Both are computed by [`jiwer 4.0`](https://pypi.org/project/jiwer/) over
**Hebrew-normalised text** — see `backend/src/receptra/stt/wer.py` and
`research §9`. Normalization steps:

1. Unicode NFC.
2. Strip niqqud + cantillation marks (`U+0591..U+05C7`) to empty string —
   the model never outputs them; comparing un-stripped drives WER
   artificially high.
3. Strip bidi control chars (`U+200E`, `U+200F`) to empty string.
4. Replace common punctuation (`. , ! ? : ; " ' ( ) [ ] -`) with a single
   space so adjacent words remain distinct after stripping.
5. Collapse runs of whitespace to one space; trim.

---

## Fixture sourcing

We use **Mozilla Common Voice 25.0** Hebrew, CC0-licensed.

- Repo: `mozilla-foundation/common_voice_25_0` on the Hugging Face Hub.
- Pinned via `CV_REVISION_SHA` in `scripts/fetch_stt_fixtures.py` so every
  contributor + every CI run sees identical bytes.
- Filtered to clips ≤10 seconds with a non-empty validated transcript.
- Resampled to 16 kHz mono int16 WAV via the `datasets` library's
  `Audio(sampling_rate=16000)` cast (no `ffmpeg`, `librosa`, `soxr`, or
  `scipy` runtime dep needed).

All 30 WAVs + 30 TXTs (~1.5 MB total) are committed to the repo. No
git-LFS.

### Why we do NOT use ivrit-ai test sets

The `ivrit-ai/whisper-large-v3-turbo-ct2` model was trained on the
`ivrit-ai/crowd-transcribe-v5` corpus. Evaluating on the same data is
**training-data leakage**: training labels leak into the eval set and
produce artificially low WER. Common Voice is a disjoint, public, CC0
corpus — see `02-RESEARCH.md §10`.

---

## Fetching fixtures

The fixture-fetch tool is intentionally **not** part of the runtime
dependency set — it's a one-shot regeneration tool. To run it you need:

1. A Hugging Face account that has agreed to the Common Voice 25.0 dataset
   license (one-time click on the dataset page).
2. A Hugging Face token in your environment (`huggingface-cli login` or
   `HF_TOKEN=...`).
3. The `datasets` package (Apache-2.0):

```bash
cd backend && uv pip install 'datasets>=4.0,<5'
```

Then from repo root:

```bash
python scripts/fetch_stt_fixtures.py
```

This downloads, resamples, and writes 30 fixtures + a manifest JSONL.
Commit them all together (Common Voice is CC0 → redistribution is fine).

If you cannot reach HF Hub (airgapped CI), the fetch script supports
`--airgap-placeholder` which writes a one-row "UNFETCHED" manifest. The
regression test in `backend/tests/stt/test_wer_baseline.py` skips
gracefully on that placeholder.

---

## Running the eval

After fixtures are in place AND the Whisper model has been downloaded
(`make models`), run from repo root:

```bash
cd backend && uv run python ../scripts/eval_wer.py
```

Output:

- **stderr**: a per-clip table (`id`, WER, CER, duration, ref preview)
  followed by an `AGGREGATE` line.
- **stdout**: a JSON report with shape

```json
{
  "status": "ok",
  "baseline": {
    "wer_mean": 0.213,
    "wer_median": 0.200,
    "wer_p95": 0.500,
    "cer_mean": 0.085,
    "cer_median": 0.080,
    "cer_p95": 0.180,
    "n_clips": 30
  },
  "per_clip": [
    {"id": "cv_he_001", "wer": 0.166, "cer": 0.071, "ref": "...", "hyp": "...", "duration_ms": 3200, "language": "he"}
  ]
}
```

To save the JSON report to a file:

```bash
cd backend && uv run python ../scripts/eval_wer.py --output-json /tmp/eval.json
```

---

## Interpreting WER vs CER for Hebrew

Hebrew prefixes (`ב/ל/מ/ה/ש/ו` etc.) attach directly to the following word
without whitespace. A model emitting `שלום` instead of `הַשָּׁלוֹם` registers as a
**full word error** under WER (1.0 / 1 = 1.0) but **only ~25% under CER**
(1 char different out of 4-5). CER is therefore the more stable signal
when tracking small accuracy drift.

When reviewing a regression, look at both numbers:

- WER drift > CER drift → likely word-boundary/morphology issue (one or
  two prefix swaps).
- WER drift ≈ CER drift → systematic substitution.
- CER drift only → text-normalisation drift (niqqud / punctuation
  handling regressed).

---

## Updating the baseline

`backend/tests/stt/test_wer_baseline.py` carries two module-level
constants:

```python
BASELINE_WER: float | None = None  # set by first contributor with model access
BASELINE_CER: float | None = None
GRACE_PP: float = 0.03             # 3pp grace per RESEARCH §Validation
```

The regression test asserts `measured ≤ baseline + GRACE_PP`. Update the
baseline only when:

- A model upgrade is intentional and the new numbers are documented in
  the PR description.
- A dependency bump (jiwer / faster-whisper / Silero) shifts the
  measurement and the diff has been reviewed by a Hebrew speaker.
- A fixture refresh (new `CV_REVISION_SHA`) shifts the measurement.

**Policy**: any baseline change requires a Hebrew-speaker review of the
WER diff. T-02-05-04 (silent grace widening) is mitigated by keeping
`GRACE_PP = 0.03` as a module-level constant; reviewers gate on diffs to
that constant.

---

## Beam-size note (follow-up)

The eval uses the SAME `transcribe_hebrew(model, audio)` wrapper that
the live `/ws/stt` endpoint uses. Locked kwargs: `language="he"`,
`beam_size=1`, `temperature=0.0` etc. — see `backend/src/receptra/stt/engine.py`.

A "ceiling" eval at `beam_size=5` (typically reduces WER by 1-2pp on
short Hebrew clips per the model card) is intentionally **out of scope**
for Phase 2 — see Phase 7 backlog. Live partials need `beam_size=1` for
latency, and the batch eval is meant to track the live-path number, not
the theoretical ceiling.

---

## Known limitations

- **30 samples is small.** Statistically a confidence interval at this
  sample size is wide; we acknowledge this in `02-RESEARCH §Assumptions
  A9`. Sufficient for trend / regression detection, not for scientific
  claims about Hebrew WER.
- **Common Voice is read speech**, not conversational. Real Hebrew phone
  calls (Receptra's actual workload) have different prosody, more
  disfluencies, and noisier audio. A larger conversational eval lands in
  Phase 7.
- **CPU/int8 only.** The same model on Apple Silicon Metal (via MLX or
  whisper.cpp Core ML) may have different WER. Phase 2 reference
  hardware is `cpu`/`int8`/`cpu_threads=4` — Phase 7 spike covers
  alternates.

---

## License

The fixture audio is **Mozilla Common Voice CC0** — public-domain
crowd-sourced read speech from volunteers. No PII concerns. Safe to
commit, redistribute, and ship in OSS. See the dataset card for full
terms.
