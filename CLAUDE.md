<!-- GSD:project-start source:PROJECT.md -->
## Project

**Receptra**

Receptra is an open-source, self-hosted Hebrew-first AI voice platform for small businesses — the "WordPress of voice AI." V1 ships as a **live agent co-pilot**: a browser-based sidebar that listens to a human agent's phone call, streams Hebrew transcription, and surfaces suggested replies plus RAG answers from the business knowledge base in real time. The full autonomous voice receptionist comes later on the same foundation.

**Core Value:** **A human agent taking a Hebrew call on a Mac gets useful, grounded suggestions in under two seconds — running entirely on their own machine with no cloud dependency.**

If everything else fails, this must work. Hebrew + local + live-latency is the moat.

### Constraints

- **Language:** Hebrew is the day-1 target. Every v1 choice must work in Hebrew before any English optimization.
- **Hardware floor:** Apple Silicon M2 or newer with 16GB+ unified memory. No CUDA requirement for v1. CPU-only is explicitly not supported (latency budget blown).
- **Licensing:** Full stack must be permissively licensed (Apache 2.0, MIT, BSD) or explicitly free-for-commercial (Edge-TTS). No GPL or research-only licenses in v1 dependencies.
- **Privacy:** Zero cloud dependency for the core loop — audio, transcripts, and LLM inference must run locally. A user can air-gap the machine and v1 still works.
- **Latency:** End-to-end speech → suggestion on screen target <2s (Cresta achieves <200ms; our bar is looser because we're local-first on consumer hardware).
- **Deployment:** One command (`docker compose up` or equivalent) must bring the whole stack online on a fresh Mac.
- **Distribution:** OSS self-host first. No hosted SaaS in Milestone 1.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack (V1: Hebrew Co-pilot on Apple Silicon)
| Layer | Primary Choice | Fallback | License | Confidence |
|---|---|---|---|---|
| **STT (Hebrew)** | `ivrit-ai/whisper-large-v3-turbo-ct2` via faster-whisper | `ivrit-ai/whisper-large-v3` | Apache 2.0 | High |
| **STT wrapper** | WhisperLive (streaming) + Silero VAD | Whisper-Streaming | MIT | High |
| **LLM (Hebrew)** | DictaLM 3.0 (12B preferred, 1.7B for dev) | Qwen 2.5 7B Instruct | Apache 2.0 / Apache 2.0 | High |
| **LLM runtime** | Ollama (Metal acceleration on Apple Silicon) | llama.cpp directly | MIT | High |
| **Embeddings** | BGE-M3 via Ollama | multilingual-e5-large | MIT | Medium (Hebrew benchmark thin) |
| **Vector DB** | ChromaDB (dev) → Qdrant (production) | pgvector | Apache 2.0 / Apache 2.0 | High |
| **Pipeline** | Pipecat (frame-based streaming) | LiveKit Agents | BSD-2-Clause | High |
| **Transport (v1)** | Browser WebRTC (bare or via LiveKit client) | — | Apache 2.0 | High |
| **Frontend** | React + Vite + TypeScript, TailwindCSS | SvelteKit | MIT | Medium (framework TBD) |
| **Backend shim** | FastAPI (Python) for STT+LLM+RAG orchestration | Node + Express | MIT | High |
| **Deployment** | Docker Compose targeting Apple Silicon (arm64) | Native install script | — | High |
## What NOT to use (and why)
- **OpenAI Whisper (original)** — 4x slower than faster-whisper, no streaming advantage.
- **Kokoro TTS** — English-only, Hebrew not supported. Also we defer TTS entirely in v1.
- **Edge-TTS in v1** — requires internet, unofficial API, and we're not doing TTS in v1.
- **HebTTS / Phonikud** — academic, not production-ready. Revisit in TTS milestone.
- **Vocode / Bolna** — momentum lost / going closed-source per research report.
- **ElevenLabs / commercial TTS** — cloud dependency violates privacy constraint.
- **GPT-4 / Claude / any cloud LLM** — violates "zero cloud dependency" constraint.
- **CUDA-only libraries** — Apple Silicon is the reference floor. Must run via Metal/MLX.
- **Heavy Kubernetes / Helm** — too much for SMB self-host. Docker Compose only.
- **GPL/AGPL deps in the core path** — permissive licensing is a hard constraint.
## Apple Silicon specifics
- Use `llama-cpp-python` or `ollama` with Metal support; verify `METAL=1` compile flag.
- faster-whisper runs via CTranslate2 — verify CPU/Metal path performance on M2. May need to benchmark `whisper.cpp` with Core ML as an alternative since it has Apple Silicon optimizations.
- Target: STT <500ms, LLM TTFT <400ms, total speech→suggestion <2s on M2 16GB.
- Memory budget: 16GB unified memory needs to hold STT model + 7B LLM + embeddings + OS + browser. Q4 quantization is mandatory. Consider DictaLM 1.7B for 16GB devices, 12B for 32GB+.
## Open questions to resolve in Phase 1 research spike
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
