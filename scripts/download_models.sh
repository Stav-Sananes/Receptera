#!/usr/bin/env bash
# Receptra — model download dispatcher.
# Usage: scripts/download_models.sh {whisper|dictalm|bge|qwen-fallback}
#
# Env:
#   MODEL_DIR        (required) — destination for HF-downloaded weights
#   DICTALM_QUANT    (optional) — Q4_K_M (default) or Q5_K_M
#
# Downloads are resumable via `hf download` (HuggingFace Hub retries partial fetches).

set -euo pipefail

usage() {
  echo "Usage: $0 {whisper|dictalm|bge|qwen-fallback}"
  echo ""
  echo "  whisper         ivrit-ai/whisper-large-v3-turbo-ct2 → \$MODEL_DIR/whisper-turbo-ct2"
  echo "  dictalm         DictaLM 3.0 GGUF (\$DICTALM_QUANT) → \$MODEL_DIR/dictalm-3.0 + ollama create dictalm3"
  echo "  bge             ollama pull bge-m3"
  echo "  qwen-fallback   ollama pull qwen2.5:7b"
  exit 1
}

# Dispatch first: no-arg or unknown subcommand prints usage BEFORE env-var validation,
# so that running the script bare (without MODEL_DIR set) yields a useful message.
case "${1:-}" in
  whisper|dictalm|bge|qwen-fallback) ;;
  *) usage ;;
esac

: "${MODEL_DIR:?MODEL_DIR must be set (e.g. export MODEL_DIR=$HOME/.receptra/models)}"
: "${DICTALM_QUANT:=Q4_K_M}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: required command '$1' not found. Run 'make check-prereqs' for install hints." >&2
    exit 1
  }
}

download_whisper() {
  require_cmd hf
  echo "==> Downloading ivrit-ai Whisper turbo CT2 (~1.5 GB) to ${MODEL_DIR}/whisper-turbo-ct2"
  mkdir -p "${MODEL_DIR}/whisper-turbo-ct2"
  hf download ivrit-ai/whisper-large-v3-turbo-ct2 \
    --local-dir "${MODEL_DIR}/whisper-turbo-ct2"
  echo "✓ Whisper download complete"
}

download_dictalm() {
  require_cmd hf
  require_cmd ollama
  echo "==> Downloading DictaLM 3.0 GGUF (${DICTALM_QUANT}) to ${MODEL_DIR}/dictalm-3.0"
  mkdir -p "${MODEL_DIR}/dictalm-3.0"
  hf download dicta-il/DictaLM-3.0-Nemotron-12B-Instruct-GGUF \
    --include "*${DICTALM_QUANT}.gguf" \
    --local-dir "${MODEL_DIR}/dictalm-3.0"

  # Locate the downloaded GGUF file (exact filename depends on what HF publishes).
  gguf_file="$(find "${MODEL_DIR}/dictalm-3.0" -name "*${DICTALM_QUANT}.gguf" -type f | head -n 1)"
  if [ -z "${gguf_file}" ]; then
    echo "ERROR: no *${DICTALM_QUANT}.gguf file found in ${MODEL_DIR}/dictalm-3.0" >&2
    exit 1
  fi
  echo "GGUF found: ${gguf_file}"

  # Render the Modelfile template with the absolute path, write to a temp file, register.
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local template="${script_dir}/ollama/DictaLM3.Modelfile"
  local rendered
  rendered="$(mktemp -t DictaLM3.Modelfile.XXXX)"
  trap 'rm -f "${rendered}"' EXIT
  sed "s|__GGUF_PATH__|${gguf_file}|g" "${template}" > "${rendered}"

  echo "==> Registering with Ollama as 'dictalm3'"
  ollama create dictalm3 -f "${rendered}"
  echo "✓ DictaLM 3.0 registered. Test: ollama run dictalm3 'שלום'"
}

download_bge() {
  require_cmd ollama
  echo "==> ollama pull bge-m3 (~1.2 GB)"
  ollama pull bge-m3
  echo "✓ BGE-M3 pulled"
}

download_qwen_fallback() {
  require_cmd ollama
  echo "==> ollama pull qwen2.5:7b (~4.7 GB) — DictaLM fallback"
  ollama pull qwen2.5:7b
  echo "✓ Qwen 2.5 7B pulled"
}

case "${1:-}" in
  whisper)       download_whisper ;;
  dictalm)       download_dictalm ;;
  bge)           download_bge ;;
  qwen-fallback) download_qwen_fallback ;;
  *)             usage ;;
esac
