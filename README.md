[עברית](README.he.md) | **English**

# Receptra

> Open-source, self-hosted Hebrew-first AI voice co-pilot for small businesses.

**Core Value:** A human agent taking a Hebrew call on a Mac gets useful, grounded suggestions in under two seconds — running entirely on their own machine with no cloud dependency.

## Status

Milestone 1 (Hebrew Co-pilot MVP) — under active development. Not yet ready for end users.

## Prerequisites

- Apple Silicon Mac (M2 or newer, 16GB+ unified memory)
- Docker Desktop for Mac
- [Ollama](https://ollama.com) installed natively on host (`brew install ollama`)
- Node.js 22 LTS
- Python 3.12
- [uv](https://docs.astral.sh/uv/) for Python dependency management
- [Hugging Face CLI](https://huggingface.co/docs/huggingface_hub/en/guides/cli) (`pip install -U huggingface_hub[cli]`)
- ~15 GB free disk space (for model weights in `~/.receptra/models/`)

## Quickstart

```bash
git clone <repo-url> receptra
cd receptra
cp .env.example .env          # adjust ports if needed
make setup                    # installs deps + downloads ~11 GB of models
make up                       # starts ollama (host) + docker compose stack
# Backend healthcheck:  http://localhost:8080/healthz
# Frontend sidebar:     http://localhost:5173
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full developer setup.

## License

Apache License 2.0. See [LICENSE](LICENSE).

## Roadmap

See `.planning/ROADMAP.md` for the Milestone 1 phase plan (STT, LLM, RAG, integration, frontend, demo).
