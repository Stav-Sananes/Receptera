# Docker Compose — Receptra Stack

## Why Ollama is NOT in the compose file

Docker Desktop on macOS cannot pass Apple Silicon GPU (Metal/MPS) through to
containers. Running Ollama in-container on a Mac collapses to CPU inference
and destroys the <2s end-to-end latency budget required by Milestone 1.

**Locked decision (Phase 1 research OPEN-1):** Ollama runs natively on the host. The backend connects to `host.docker.internal:11434`.

Install on macOS:

```bash
brew install ollama
ollama serve &     # or: brew services start ollama
```

On Linux, install per https://ollama.com/download and ensure `extra_hosts`
maps `host.docker.internal` to `host-gateway` (already configured in our
`docker-compose.yml`).

## Services

| Service | Image / Build | Port | Healthcheck | Persistence |
|---------|--------------|------|-------------|-------------|
| chromadb | `chromadb/chroma:1.5.8` | 8000 | `GET /api/v2/heartbeat` | `./data/chroma` → `/data` |
| backend | built from `backend/Dockerfile` (python:3.12-slim) | 8080 | `GET /healthz` | stateless; models mounted from `${MODEL_DIR}` |
| frontend | built from `frontend/Dockerfile` (node:22-slim) | 5173 | `GET /` | stateless |

## Startup chain

```
chromadb (service_healthy)
    ↓
backend  (service_healthy)
    ↓
frontend
```

`docker compose up -d` returns only after each service passes its healthcheck
(because `depends_on.condition: service_healthy` blocks the next service
from starting).

## Commands

```bash
docker compose up -d          # start
docker compose ps             # status
docker compose logs -f        # tail all logs
docker compose logs -f backend
docker compose down           # stop + remove
docker compose down -v        # + delete chromadb volume (rare)

# Validation (no containers started)
docker compose config -q      # validates docker-compose.yml
```

## Rebuilding after code changes

Dep file changed (pyproject.toml / package.json) → full rebuild:

```bash
docker compose build --no-cache backend
docker compose up -d
```

Source-only change → layer cache handles it:

```bash
docker compose up -d --build
```

## Volume layout

- `./data/chroma` — ChromaDB persistence. Survives `docker compose down`;
  deleted on `docker compose down -v`.
- `${MODEL_DIR}` (default `~/.receptra/models`) — mounted **read-only**
  into the backend container at `/models`. Populated by `make models`
  (Plan 05). Never baked into images.

## Troubleshooting

- `/healthz` never goes healthy → `docker compose logs backend` usually
  shows Python import errors or config parse failures.
- `host.docker.internal` unreachable on Linux → verify Docker version ≥
  20.10; the `extra_hosts: host-gateway` entry should handle it.
- Port 5173 / 8080 / 8000 already in use → override in `.env` with
  `FRONTEND_PORT=5174` etc.
