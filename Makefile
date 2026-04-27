# Receptra — Milestone 1 Foundation Makefile.
# One-liner targets for contributors. See docs/models.md and docs/docker.md.

SHELL := /usr/bin/env bash
.SHELLFLAGS := -euo pipefail -c

.PHONY: help setup check-prereqs models models-whisper models-dictalm models-bge \
        models-fallback up down logs test lint typecheck format licenses clean \
        eval-rag

MODEL_DIR      ?= $(HOME)/.receptra/models
DICTALM_QUANT  ?= Q4_K_M
COMPOSE        ?= docker compose

help:
	@echo "Receptra — Makefile targets"
	@echo ""
	@echo "  make setup             Install host prerequisites + fetch all models"
	@echo "  make check-prereqs     Verify docker, ollama, hf, uv, node, python are installed"
	@echo ""
	@echo "  make models            Download Whisper + DictaLM + BGE-M3 (~11 GB)"
	@echo "  make models-whisper    Download only ivrit-ai Whisper turbo CT2"
	@echo "  make models-dictalm    Download DictaLM 3.0 GGUF + register with Ollama"
	@echo "  make models-bge        ollama pull bge-m3"
	@echo "  make models-fallback   Use Qwen 2.5 7B instead of DictaLM"
	@echo ""
	@echo "  make up                Start Ollama (host) + docker compose up -d"
	@echo "  make down              docker compose down"
	@echo "  make logs              Tail all service logs"
	@echo ""
	@echo "  make test              Run backend pytest + frontend tests"
	@echo "  make lint              Ruff + ESLint + Prettier"
	@echo "  make typecheck         Mypy strict + tsc --noEmit"
	@echo "  make format            Ruff format + Prettier write"
	@echo "  make licenses          License allowlist check"
	@echo ""
	@echo "  make clean             Stop stack, remove build artifacts (keeps models)"
	@echo "  make eval-rag          Run RAG recall@5 eval against TestClient (Phase 4)"
	@echo ""
	@echo "Overrides:"
	@echo "  make models DICTALM_QUANT=Q5_K_M    # 32GB Macs — better quality"
	@echo "  make models MODEL_DIR=/opt/models   # custom model path"

check-prereqs:
	@missing=0; \
	for cmd in docker ollama hf uv node python3 make curl; do \
	  if ! command -v $$cmd >/dev/null 2>&1; then \
	    echo "MISSING: $$cmd"; missing=1; \
	  fi; \
	done; \
	if [ "$$missing" = "1" ]; then \
	  echo ""; \
	  echo "Install hints:"; \
	  echo "  docker   → Docker Desktop for Mac"; \
	  echo "  ollama   → brew install ollama"; \
	  echo "  hf       → pip install -U huggingface_hub[cli]"; \
	  echo "  uv       → curl -LsSf https://astral.sh/uv/install.sh | sh"; \
	  echo "  node     → brew install node@22"; \
	  echo "  python3  → brew install python@3.12"; \
	  exit 1; \
	fi; \
	echo "OK: all prereqs present"

setup: check-prereqs
	cd backend && uv sync --all-extras
	cd frontend && npm install
	$(MAKE) models
	@echo "✓ Setup complete. Run 'make up' to start the stack."

models: models-whisper models-dictalm models-bge
	@echo "✓ All models downloaded to $(MODEL_DIR)"

models-whisper:
	@mkdir -p $(MODEL_DIR)
	MODEL_DIR=$(MODEL_DIR) scripts/download_models.sh whisper

models-dictalm:
	@mkdir -p $(MODEL_DIR)/dictalm-3.0
	MODEL_DIR=$(MODEL_DIR) DICTALM_QUANT=$(DICTALM_QUANT) scripts/download_models.sh dictalm

models-bge:
	MODEL_DIR=$(MODEL_DIR) scripts/download_models.sh bge

models-fallback:
	MODEL_DIR=$(MODEL_DIR) scripts/download_models.sh qwen-fallback

up: check-prereqs
	@if ! pgrep -x ollama >/dev/null 2>&1; then \
	  echo "Starting ollama server in background..."; \
	  nohup ollama serve >/tmp/receptra-ollama.log 2>&1 & \
	  sleep 2; \
	fi
	MODEL_DIR=$(MODEL_DIR) $(COMPOSE) up -d
	@echo "✓ Stack up."
	@echo "  Backend:   http://localhost:8080/healthz"
	@echo "  Frontend:  http://localhost:5173"
	@echo "  Chroma:    http://localhost:8000/api/v2/heartbeat"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

test:
	cd backend && uv run pytest tests/ -x
	cd frontend && npm test --if-present

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint && npm run format:check

typecheck:
	cd backend && uv run mypy src tests
	cd frontend && npm run typecheck

format:
	cd backend && uv run ruff format .
	cd frontend && npm run format

licenses:
	scripts/check_licenses.sh

clean:
	-$(COMPOSE) down
	cd backend && rm -rf .venv .pytest_cache .ruff_cache .mypy_cache dist
	cd frontend && rm -rf node_modules dist .vite
	@echo "NOTE: models in $(MODEL_DIR) preserved. Run 'rm -rf $(MODEL_DIR)' to reclaim disk."

eval-rag:
	@cd backend && uv run python ../scripts/eval_rag.py --full --testclient
