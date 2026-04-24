# Models — Receptra

Receptra's core loop uses three Hebrew-capable models. They live in `~/.receptra/models/`
(or `$MODEL_DIR` if overridden) on the host and are mounted read-only into the backend
container at `/models`.

## Footprint

| Model | Purpose | Path | Size (default quant) | Size (high-quality quant) | License |
|-------|---------|------|----------------------|---------------------------|---------|
| `ivrit-ai/whisper-large-v3-turbo-ct2` | Hebrew STT (Phase 2) | `$MODEL_DIR/whisper-turbo-ct2/` | ~1.5 GB | — | Apache 2.0 |
| `dicta-il/DictaLM-3.0-Nemotron-12B-Instruct-GGUF` | Hebrew LLM (Phase 3) | `$MODEL_DIR/dictalm-3.0/` | Q4_K_M: 7.49 GB | Q5_K_M: 8.76 GB | Apache 2.0 |
| `bge-m3` (via Ollama) | Embeddings (Phase 4) | `~/.ollama/models/` | ~1.2 GB | — | MIT |

**Total:** ~10 GB default (Q4_K_M DictaLM), ~11.5 GB with Q5_K_M. Plan for **~15 GB free disk**. Total download is ~11 GB including buffer for overhead and intermediate files.

## Quant selection (DictaLM only)

| Target hardware | Recommended quant | Env var |
|-----------------|-------------------|---------|
| Apple Silicon M2 / M2 Pro / M2 Max with 16 GB unified memory | **Q4_K_M** (default) | `DICTALM_QUANT=Q4_K_M` |
| Apple Silicon M2 Pro / Max / M3+ with 32 GB+ unified memory | Q5_K_M (better quality) | `DICTALM_QUANT=Q5_K_M make models` |

Override by passing the env var to `make models` or exporting it before `make setup`.

## Download flow

```bash
# All models (recommended)
make models

# Individually
make models-whisper
make models-dictalm                                    # Q4_K_M default
DICTALM_QUANT=Q5_K_M make models-dictalm               # 32GB override
make models-bge
```

Every download uses `hf download` (for HF-hosted weights) or `ollama pull` (for
Ollama-library models). Both print MB/s + ETA + progress bars to stdout and are
resumable if interrupted.

## DictaLM fallback — Qwen 2.5 7B

If DictaLM 3.0 deployment is ever blocked (e.g., HF rate-limit, checksum mismatch,
broken Modelfile), fall back to Qwen 2.5 7B:

```bash
make models-fallback
```

Research Open Decision 1 locked DictaLM 3.0 as primary and Qwen 2.5 7B as the
documented fallback. Phase 3 (LLM) will wire the LLM service to prefer DictaLM
and log a fallback-to-Qwen path.

## Why downloads are separate from `docker compose up`

- `docker compose up` completes in seconds; model downloads take 5–30 minutes.
- Bundling them hides progress behind compose logs and retries on every image rebuild.
- Downloads must be resumable — a 7 GB partial download in a Docker build would
  need to start over from zero.

## Storage location — why `~/.receptra/models/`

- Survives `git clean` — never committed to the repo.
- Survives `docker compose down -v` — not a Docker volume.
- Shared across git worktrees of the same repo.
- User-writable without `sudo`.

To reclaim disk space: `rm -rf ~/.receptra/models/` (re-run `make models` later if
you want them back).

## DictaLM 3.0 Ollama registration

`scripts/ollama/DictaLM3.Modelfile` is a TEMPLATE. The download script substitutes
the absolute path to the downloaded GGUF and runs `ollama create dictalm3 -f ...`.
This registers the model under the name `dictalm3` (usable as `ollama run dictalm3`
or from Pipecat/ollama client as `model="dictalm3"`).

Research §2.2 verified that the GGUF includes `tokenizer.chat_template` metadata,
so no explicit `TEMPLATE` block is needed.

## Troubleshooting

- `hf: command not found` → `pip install -U huggingface_hub[cli]`
- `ollama: command not found` → `brew install ollama && ollama serve`
- DictaLM GGUF download hangs → `hf download` respects `HF_HUB_ENABLE_HF_TRANSFER=1` for faster transfer; set it in your shell to speed up large files.
- Disk full mid-download → free space, then re-run. `hf download` resumes.
