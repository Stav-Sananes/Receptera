# Receptra Backend

Python 3.12 + FastAPI service for Receptra. Dependency management via [uv](https://docs.astral.sh/uv/).

## Quickstart

```bash
cd backend
uv sync              # resolves + installs (respects uv.lock if present)
uv run uvicorn receptra.main:app --port 8080 --reload
# Healthcheck: curl http://localhost:8080/healthz  →  {"status":"ok"}
```

## Tests + lint

```bash
uv run pytest              # unit tests (Wave 0 smoke test: tests/test_healthz.py)
uv run ruff check .        # lint
uv run ruff format --check # format
uv run mypy src            # strict type check
```

## Configuration

Environment variables (prefixed `RECEPTRA_`, loaded by `receptra.config.Settings`):

| Var | Default | Purpose |
|-----|---------|---------|
| `RECEPTRA_MODEL_DIR` | `/models` | Path to model weights (mounted from host in Docker) |
| `RECEPTRA_OLLAMA_HOST` | `http://host.docker.internal:11434` | Ollama endpoint (host-native on Mac) |
| `RECEPTRA_CHROMA_HOST` | `http://chromadb:8000` | ChromaDB endpoint |
| `RECEPTRA_LOG_LEVEL` | `INFO` | Log level |

See repo-root `.env.example` for the full list and the Docker Compose defaults.
