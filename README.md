[עברית](README.he.md) | **English**

<div align="center">

# 🎙️ Receptra

### Open-source, self-hosted Hebrew AI voice co-pilot for small businesses

**A human agent taking a Hebrew phone call gets grounded reply suggestions in under 2 seconds — running entirely on their Mac, no cloud, no API key.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-337%20passing-brightgreen.svg)](backend/tests/)
[![Platform](https://img.shields.io/badge/platform-Apple%20Silicon-black.svg)](https://www.apple.com/mac/)

</div>

---

## What is this?

Receptra is the **"WordPress of Hebrew voice AI"** — a self-hosted sidebar that sits next to a human agent during a phone call and does three things in real time:

1. **Transcribes** the Hebrew conversation (Whisper ivrit-ai, <500ms)
2. **Retrieves** relevant answers from the business's knowledge base (ChromaDB + BGE-M3)
3. **Suggests** grounded replies (DictaLM 3.0 12B via Ollama, <1.5s TTFT)

Everything runs locally on an Apple Silicon Mac. No audio leaves the device. No API keys. No monthly bill.

> **Target user:** A receptionist at an Israeli clinic, law office, or repair shop who takes Hebrew calls and needs real-time help without switching screens.

---

## Demo

<!-- TODO: add demo GIF here — `make demo-gif` generates it from a sample call recording -->

```
Agent hears: "שלום, אני רוצה לדעת מה שעות הפתיחה שלכם ביום שישי"

Receptra surfaces (< 1.8s):
┌─────────────────────────────────────────────────────┐
│ 💡 הצעה 1  ████████████████████░░░  92%             │
│ ביום שישי אנחנו פתוחים בין 08:00 ל-13:00.          │
│ ⬗ hours.md                                          │
└─────────────────────────────────────────────────────┘
```

---

## Why Receptra vs. alternatives?

| | Receptra | WhisperLive | LiveKit Agents | Bolna | Cloud (Cresta) |
|---|---|---|---|---|---|
| Hebrew STT | ✅ ivrit-ai fine-tuned | ⚠️ vanilla Whisper | ❌ | ❌ | ✅ expensive |
| Hebrew LLM | ✅ DictaLM 3.0 | ❌ | ❌ | ❌ | ✅ expensive |
| Human-in-the-loop co-pilot | ✅ | ❌ | ❌ | ❌ | ✅ |
| RAG from business KB | ✅ | ❌ | ❌ | ❌ | ✅ |
| Apple Silicon (Metal) | ✅ | ⚠️ community | ⚠️ | ❌ | N/A |
| Zero cloud dependency | ✅ | ✅ | ❌ | ❌ | ❌ |
| One-command install | ✅ | ❌ | ❌ | ❌ | N/A |
| **Cost** | **Free** | Free | Free | Free | $$$$ |

---

## Architecture

```
Browser Sidebar (React + Vite)
        │  WebSocket /ws/stt  │  REST /api/kb
        ▼                     ▼
  ┌─────────────────────────────────────┐
  │         FastAPI Backend             │
  │                                     │
  │  PCM audio ──► Silero VAD           │
  │                    │                │
  │              ► Whisper ivrit-ai     │ ◄── ~/.receptra/models/
  │                    │ transcript     │
  │              ► BGE-M3 embed         │
  │                    │               │
  │              ► ChromaDB retrieve   │ ◄── ./data/chroma/
  │                    │ chunks         │
  │              ► DictaLM 3.0         │ ◄── Ollama (host Metal)
  │                    │ suggestions    │
  │  WebSocket ◄───────┘               │
  └─────────────────────────────────────┘
```

**Stack:**

| Layer | Technology |
|-------|-----------|
| STT | [`ivrit-ai/whisper-large-v3-turbo-ct2`](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ct2) via faster-whisper |
| VAD | Silero VAD |
| Embeddings | BGE-M3 via Ollama |
| Vector DB | ChromaDB |
| LLM | DictaLM 3.0 12B Q4_K_M via Ollama (Metal) |
| Backend | FastAPI + Python 3.12 |
| Frontend | React 19 + Vite 6 + Tailwind v4 (RTL/Hebrew) |
| Deployment | Docker Compose + native Ollama |

---

## Requirements

- **Hardware:** Apple Silicon M2 or newer, **16GB+ unified memory** (M2 16GB → DictaLM 1.7B; M2 32GB → 12B)
- **OS:** macOS 13+
- **Disk:** ~12 GB free for model weights
- **Software:** Docker Desktop, Homebrew

> CPU-only (Intel Mac, Linux without Metal) is not supported in v1 — latency budget requires Metal acceleration.

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/receptra.git
cd receptra

# 2. Install prerequisites + download all models (~11 GB, one-time)
make setup

# 3. Start the stack
make up

# → Frontend sidebar:  http://localhost:5173
# → Backend API:       http://localhost:8080/healthz
```

**That's it.** Open `http://localhost:5173`, click **התחל**, allow microphone access, and start talking.

### Manual steps (if `make setup` fails)

```bash
# Install tools
brew install ollama
pip install -U "huggingface_hub[cli]"

# Download models
make models-whisper   # ivrit-ai Whisper turbo CT2 (~1.5 GB)
make models-dictalm   # DictaLM 3.0 Q4_K_M GGUF (~7.5 GB)
make models-bge       # BGE-M3 embeddings (~1.2 GB)

# Start
make up
```

---

## Knowledge Base

Upload `.md` or `.txt` files directly from the sidebar — or via the API:

```bash
# Ingest a business FAQ
curl -X POST http://localhost:8080/api/kb/ingest-text \
  -H "Content-Type: application/json" \
  -d '{"filename": "hours.md", "content": "שעות פתיחה: ראשון-חמישי 9:00-18:00, שישי 9:00-13:00"}'

# List documents
curl http://localhost:8080/api/kb/documents
```

Supported formats: `.md`, `.txt`. Chunked automatically, embedded with BGE-M3, stored in ChromaDB.

---

## Roadmap

### ✅ Milestone 1 — Hebrew Co-pilot MVP (current)
- [x] Streaming Hebrew STT with Silero VAD (Phase 2)
- [x] DictaLM 3.0 suggestion engine with Hebrew system prompt (Phase 3)
- [x] RAG pipeline — ChromaDB + BGE-M3 embeddings (Phase 4)
- [x] Hot-path: STT → RAG → LLM → WebSocket events <2s (Phase 5)
- [x] React sidebar — transcript + suggestions + KB management (Phase 6)
- [x] Full integration smoke tests (Phase 7)

### 🔜 Milestone 2 — v1.1 (next)
- [ ] **Confidence-gated suggestions** — only show RAG answers above threshold (reduces noise)
- [ ] **PDF / DOCX ingestion** — clinic price lists, legal templates, manuals
- [ ] **Post-call summary** — auto-generate Hebrew summary with action items, one-click copy
- [ ] **Intent detection badges** — booking / complaint / billing / legal classification in real time
- [ ] **DictaLM 1.7B mode** — auto-detect 16GB devices, use fast small model

### 🔭 Milestone 3 — v2
- [ ] **Multi-turn context memory** — suggestions improve as call progresses
- [ ] **Vertical packs** — starter KB templates for clinics, lawyers, repair shops
- [ ] **Supervisor dashboard** — suggestion acceptance rates, KB hit/miss analytics
- [ ] **Multi-language** — Hebrew/English/Russian mid-call detection
- [ ] **Autonomous receptionist mode** — full bot answers (no human-in-the-loop)

---

## Development

```bash
# Run tests (337 passing, 10 live-only skipped)
make test

# Lint + typecheck
make lint
make typecheck

# Backend only (with hot reload)
cd backend && uv run uvicorn receptra.main:app --port 8080 --reload

# Frontend only
cd frontend && npm run dev
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full contributor guide.

---

## Privacy

All audio, transcripts, and LLM inference happen **on your machine**. No data is sent to any external server. The `./data/` directory contains:
- `audit.sqlite` — transcript audit log (Hebrew text is PII — keep this dir private)
- `chroma/` — vector index of your knowledge base

Both are `.gitignore`d. Never commit them.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

---

<div align="center">

Built with ❤️ for Israeli small businesses · המוצר בנוי עם אהבה לעסקים קטנים בישראל

</div>
