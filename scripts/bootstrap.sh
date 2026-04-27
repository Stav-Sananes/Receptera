#!/usr/bin/env bash
#
# Receptra one-shot bootstrap — bring the stack up on a fresh Mac.
#
# Idempotent: safe to re-run. Skips steps that are already done.
#
# Usage:
#   ./scripts/bootstrap.sh           # full bring-up
#   ./scripts/bootstrap.sh --skip-models  # assume models already pulled
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

SKIP_MODELS=0
for arg in "$@"; do
    case "$arg" in
        --skip-models) SKIP_MODELS=1 ;;
        *) echo "unknown flag: $arg" >&2; exit 2 ;;
    esac
done

log()  { printf '\033[1;34m[bootstrap]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[bootstrap]\033[0m %s\n' "$*" >&2; exit 1; }

# --- Step 1: prerequisites -------------------------------------------------

log "checking prerequisites..."
missing=0
for cmd in docker ollama; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "  MISSING: $cmd"
        missing=1
    fi
done
[ "$missing" -eq 0 ] || fail "install missing prerequisites first; see README.md"

# --- Step 2: ensure Ollama is running --------------------------------------

if ! pgrep -x ollama >/dev/null 2>&1; then
    log "starting ollama serve in background..."
    nohup ollama serve >/tmp/receptra-ollama.log 2>&1 &
    # Wait up to 10s for Ollama to be reachable.
    for _ in $(seq 1 20); do
        if curl -sf http://localhost:11434/api/version >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
    curl -sf http://localhost:11434/api/version >/dev/null 2>&1 \
        || fail "ollama did not come up — see /tmp/receptra-ollama.log"
fi
log "ollama running"

# --- Step 3: pull required Ollama models -----------------------------------

if [ "$SKIP_MODELS" -eq 0 ]; then
    log "checking dictalm3 (Hebrew LLM)..."
    if ! ollama list | awk '{print $1}' | grep -qx "dictalm3:latest\|dictalm3"; then
        log "  → run 'make models-dictalm' first to register DictaLM 3.0 with Ollama"
    else
        log "  ✓ dictalm3 present"
    fi

    log "checking bge-m3 (Hebrew embeddings)..."
    if ! ollama list | awk '{print $1}' | grep -qx "bge-m3:latest\|bge-m3"; then
        log "  → pulling bge-m3..."
        ollama pull bge-m3 || fail "ollama pull bge-m3 failed"
    else
        log "  ✓ bge-m3 present"
    fi
else
    log "(skipping model pull — --skip-models)"
fi

# --- Step 4: bring up Docker stack -----------------------------------------

log "starting docker compose stack..."
MODEL_DIR="${MODEL_DIR:-$HOME/.receptra/models}" docker compose up -d

log "waiting for backend healthcheck..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8080/healthz >/dev/null 2>&1; then
        log "  ✓ backend healthy"
        break
    fi
    if [ "$i" -eq 60 ]; then
        fail "backend did not become healthy in 60s — run 'docker compose logs backend'"
    fi
    sleep 1
done

# --- Step 5: smoke-test KB endpoint ----------------------------------------

log "smoke-testing /api/kb/health..."
kb_health=$(curl -s http://localhost:8080/api/kb/health || true)
if echo "$kb_health" | grep -q '"chroma":"ok"'; then
    log "  ✓ KB reachable: $kb_health"
else
    log "  ⚠ KB partially degraded — backend up but chroma/embedder not ready"
    log "    response: $kb_health"
fi

# --- Done ------------------------------------------------------------------

cat <<EOF

╭───────────────────────────────────────────────╮
│  Receptra is up.                              │
│                                               │
│  Frontend:  http://localhost:5173             │
│  Backend:   http://localhost:8080/healthz     │
│  Chroma:    http://localhost:8000/api/v2/heartbeat │
│                                               │
│  Logs:      docker compose logs -f            │
│  Stop:      docker compose down               │
╰───────────────────────────────────────────────╯
EOF
