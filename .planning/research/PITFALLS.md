# PITFALLS — Receptra V1

*Derived from the user's research report and known failure modes of voice AI systems.*

## Critical — will kill the project if ignored

### 1. Hebrew STT accuracy gap
- **Warning signs:** WER >15% on real SMB audio (accents, noise, jargon).
- **Prevention:** Test ivrit.ai turbo on realistic Hebrew audio early in Phase 1 (research spike). Have a fallback plan to use large-v3 (slower) if turbo accuracy is insufficient.
- **Phase:** Foundation / STT phase.

### 2. DictaLM deployment complexity
- **Warning signs:** DictaLM 3.0 not packaged as GGUF for Ollama; custom conversion required; chat template mismatches; Hebrew prompts produce English responses.
- **Prevention:** Verify day 1 whether DictaLM is in Ollama's library. If not, check Hugging Face for GGUF-converted versions. Test chat template and tool-calling format before committing to it as primary LLM. Keep Qwen 2.5 7B as a working fallback that definitely runs in Ollama.
- **Phase:** LLM integration phase.

### 3. Apple Silicon memory pressure
- **Warning signs:** OOM when running STT + LLM + browser + OS on 16GB. Swap thrashing. Slow first token.
- **Prevention:** Publish a memory budget table. Default to DictaLM 1.7B on 16GB and 12B only on 32GB+. Use aggressive quantization (Q4_K_M). Verify model eviction works when switching between STT and LLM if memory is tight.
- **Phase:** Foundation / LLM phase.

### 4. Streaming latency cascade
- **Warning signs:** Total latency >3s. Agent ignores suggestions because they arrive after the call moves on.
- **Prevention:** Instrument every stage. Log time-to-first-partial, time-to-final, time-to-retrieval, time-to-first-LLM-token, time-to-suggestion-render. Set budgets per stage and fail CI if exceeded. Don't buffer — stream end-to-end.
- **Phase:** Integration / polish phase.

### 5. Ungrounded LLM suggestions (hallucinations on business facts)
- **Warning signs:** LLM suggests wrong hours, wrong prices, fabricated policies. Citations don't actually support the suggestion.
- **Prevention:** Strict prompt: "Only use facts from the provided context. If context does not contain the answer, say so." Evaluate on a seeded KB with adversarial questions. Show citation in UI so agent can verify before using.
- **Phase:** LLM integration + polish.

## High — will slow the project significantly

### 6. Pipecat or LiveKit not cleanly supporting Apple Silicon
- **Warning signs:** pip install fails; native deps missing arm64 wheels; Docker image built for amd64 only.
- **Prevention:** Build and test the Docker image on M-series from day 1. Use multi-arch bases (`python:3.11-slim` has arm64). Verify all wheels have arm64 versions; build from source where needed.
- **Phase:** Foundation phase.

### 7. RTL and bidi text rendering bugs
- **Warning signs:** Hebrew appears reversed, punctuation on wrong side, mixed Hebrew/English garbled, copy-paste mangles.
- **Prevention:** Set `dir="rtl"` on relevant containers, test with real Hebrew + English code-mixed strings. Use `unicode-bidi: plaintext` where appropriate. Hebrew speakers review the UI early.
- **Phase:** Frontend phase.

### 8. Chunking loses meaning in Hebrew
- **Warning signs:** RAG retrieves irrelevant chunks because chunker splits mid-word or mid-sentence.
- **Prevention:** Use sentence-aware chunking, not character count. Test with Hebrew docs. BGE-M3 handles Hebrew but the chunker is a separate concern.
- **Phase:** RAG phase.

### 9. Ollama chat template not set correctly for DictaLM
- **Warning signs:** Model outputs garbage or refuses. System prompt ignored. Tool calls malformed.
- **Prevention:** Read DictaLM's model card carefully for the correct chat template. Test with `ollama run` before wiring into the backend.
- **Phase:** LLM integration phase.

### 10. Browser mic permissions + HTTPS requirement
- **Warning signs:** `getUserMedia` only works on HTTPS or localhost. User tries to use the app on a LAN IP and mic is blocked.
- **Prevention:** Document localhost-only for v1. For LAN access, bundle an mkcert-based self-signed cert generator in the Docker Compose setup. Or provide clear instructions.
- **Phase:** Frontend + deployment phase.

## Medium — watch for these

### 11. Users expect TTS (autonomous mode) and are disappointed
- **Warning signs:** Early users ask "when can it answer the phone itself?" and leave when the answer is "later."
- **Prevention:** README + landing copy is crystal clear: v1 is a co-pilot for human agents. Autonomous mode is on the roadmap but not in v1. Show a roadmap publicly.

### 12. Docker Compose footprint is too big for a "one-liner" install
- **Warning signs:** 20GB+ model downloads, 10GB+ images, slow first-run.
- **Prevention:** Separate model download step from `docker compose up`. Use a `make setup` or `receptra init` that pulls models to a mounted volume with a progress bar. Don't bake models into images.

### 13. Knowledge base ingest is flaky on PDFs
- **Warning signs:** Scanned PDFs produce empty text; Hebrew PDFs with embedded fonts extract gibberish.
- **Prevention:** Start with .md and .txt only in v1. Document that PDF support is best-effort. Use `pdfplumber` + fallback to OCR via `rapidocr` only when text extraction fails.

### 14. No telemetry means no learning
- **Warning signs:** We have no idea if suggestions are being accepted or ignored.
- **Prevention:** Add opt-in local telemetry (accept/reject clicks, latency histograms) stored locally in SQLite. Do NOT phone home. Surface via a local dashboard.

### 15. License creep in dependencies
- **Warning signs:** A dep pulls in GPL or research-only licensed code.
- **Prevention:** Run a license check in CI. Maintain an explicit allowlist. Be especially careful with model weights (check each model's license).

## Low — be aware

- Lock files diverge on macOS vs Linux arm64.
- Hebrew keyboard input in the KB upload UI.
- Font availability for Hebrew in the frontend.
- The word "receptionist" translates awkwardly to Hebrew (פקיד/ה קבלה).
