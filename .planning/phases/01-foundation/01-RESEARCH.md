# Phase 1: Foundation - Research

**Researched:** 2026-04-23
**Domain:** Monorepo scaffolding, Docker Compose on Apple Silicon (arm64), model download orchestration, CI + license compliance
**Confidence:** HIGH (stack decisions locked upstream; most claims verified against 2026 registry/docs)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FND-01 | Repo scaffolded with Python backend, React+Vite frontend, docs dir | Recommended File Layout §, backend pyproject.toml §, frontend package.json § |
| FND-02 | Docker Compose (arm64-compatible) starts stack with one command | Docker Compose on Apple Silicon §, Open Decisions §, healthcheck chain example |
| FND-03 | Model download step (separate from `docker compose up`) fetches Whisper + DictaLM + BGE-M3 to mounted volume with progress | Model Download Strategy §, Makefile spec |
| FND-04 | Backend `/healthz` returns 200, frontend empty sidebar reachable | Python Backend Scaffold §, Frontend Scaffold §, healthcheck example |
| FND-05 | Apache 2.0 LICENSE, bilingual (EN+HE) README, CONTRIBUTING.md at root | Licensing Docs §, Recommended File Layout § |
| FND-06 | CI runs lint + type-check + license allowlist check per commit | CI + Licensing §, pip-licenses / license-checker specs |
</phase_requirements>

## Summary

**TL;DR — 10 recommendations the planner should treat as default:**

1. **Monorepo layout** with `backend/` (Python + FastAPI), `frontend/` (React+Vite+TS), `docs/`, `knowledge/` (gitignored), root `docker-compose.yml`, `Makefile`, `.github/workflows/ci.yml`, and bilingual README at root.
2. **Ollama runs on the host, not in Compose** — Docker Desktop on Mac cannot pass through Metal/MPS; containerized Ollama falls back to CPU and blows the latency budget. Document `brew install ollama && ollama serve` as a prerequisite; the backend connects via `host.docker.internal:11434`.
3. **Backend image = `python:3.12-slim` multi-arch**, dependency-managed by **uv** (not pip) with `pyproject.toml` + `uv.lock`. uv correctly resolves arm64 wheels and is 10-100x faster than pip in CI.
4. **Frontend scaffold = `npm create vite@latest frontend -- --template react-ts`** + **Tailwind v4** via `@tailwindcss/vite` plugin (Tailwind v4 is the 2026 default; config lives in vite.config.ts).
5. **Models live in `~/.receptra/models/`** (user home), mounted read-only into the backend container. This survives `rm -rf receptra/` and container rebuilds; NEVER bake models into images.
6. **Model download via Makefile + `hf download` CLI** — separate step from `docker compose up`. Progress bars, ~11 GB total footprint (Whisper turbo-ct2 ~1.5GB + DictaLM 3.0 12B Q5_K_M ~8.8GB + BGE-M3 ~1.2GB).
7. **DictaLM 3.0 has NO official Ollama library entry** — a custom Modelfile is required, built from the HF GGUF (`dicta-il/DictaLM-3.0-Nemotron-12B-Instruct-GGUF`). This belongs in `scripts/` and is called from the Makefile. Qwen 2.5 7B (`ollama pull qwen2.5:7b`) is the one-line fallback.
8. **ChromaDB official image `chromadb/chroma:1.5.8`** is multi-arch. Healthcheck on `/api/v2/heartbeat`, volume at `/data`. Included in Compose (runs fine in a container; no GPU needed).
9. **CI on `ubuntu-latest` (x86_64)** for lint + type-check + license check — fast and free. Mac-specific integration tests (Metal, Compose up) are documented as manual for Phase 1 and can be wired to `macos-14` runners later if desired.
10. **License allowlist:** Python via `pip-licenses --allow-only`, frontend via `license-checker --onlyAllow`. Allowed: Apache-2.0, MIT, BSD-2/3, ISC, 0BSD, PSF, CC0. Blocked: GPL-*, AGPL-*, LGPL-*, SSPL, proprietary, research-only.

**Primary recommendation:** Lock the Ollama-on-host decision before planning. Everything else cascades cleanly from that choice.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Repo scaffolding & monorepo layout | Build / Meta | — | Structural; no runtime tier |
| FastAPI backend `/healthz` | API / Backend | — | Health signal lives on the process that owns the pipeline |
| Empty sidebar page | Frontend Server (Vite dev) | Browser | Vite dev server serves; browser renders |
| Docker Compose orchestration | Deployment / Infra | — | Coordinates runtimes, does not own business logic |
| Model storage (`~/.receptra/models/`) | Host filesystem | — | Must persist across container rebuilds; user-home avoids repo-clean data loss |
| Ollama runtime | Host (macOS, Metal) | — | Metal GPU is unreachable from Docker; running in-container collapses to CPU |
| ChromaDB runtime | Container | — | No GPU needed; runs fine in arm64 container |
| CI pipeline | GitHub Actions (x86_64 Ubuntu) | macos-14 (manual) | Speed + cost; Mac-specific checks manual for Phase 1 |
| License enforcement | CI | pre-commit (future) | Block bad-license merges at gate |

## Findings

### 1. Docker Compose on Apple Silicon

**1.1 Ollama image is multi-arch, but Metal does not work inside Docker on Mac.**
The `ollama/ollama` image has `linux/arm64` in its manifest [CITED: hub.docker.com/r/ollama/ollama], but Docker Desktop on macOS cannot pass through Apple Silicon GPU. Running Ollama in-container on Mac collapses to CPU and destroys the latency budget [CITED: chariotsolutions.com — "Apple Silicon GPUs, Docker and Ollama: Pick two."]. Community consensus 2026: **run Ollama natively on host**, point the backend at `host.docker.internal:11434`.

**Consequence:** "One command to bring up the stack" becomes `make up` (which calls `ollama serve` via launchd/brew services check + `docker compose up -d`). Document this as a Makefile wrapper — the UX is still one command.

**1.2 ChromaDB `chromadb/chroma:1.5.8` is multi-arch (linux/amd64 + linux/arm64).** [VERIFIED: hub.docker.com/r/chromadb/chroma, April 2026]
- Heartbeat endpoint: `GET /api/v2/heartbeat` (v1 endpoint deprecated) [CITED: docs.trychroma.com/guides/deploy/docker]
- Persistence volume mount path: `/data` on recent images [CITED: docs.trychroma.com; legacy path `/chroma/chroma` is pre-1.0]
- Port: `8000`
- Healthcheck: `curl -f http://localhost:8000/api/v2/heartbeat`

**1.3 Python backend base: `python:3.12-slim` is multi-arch** [VERIFIED: Docker Hub]. All critical wheels have linux/arm64 availability in early 2026:
- `pydantic` v2 — arm64 wheels [VERIFIED: PyPI]
- `tokenizers` — arm64 wheels [VERIFIED: PyPI]
- `ctranslate2` 4.7.1 — `manylinux_2_27_aarch64` and `manylinux_2_28_aarch64` wheels [VERIFIED: PyPI, Feb 4 2026]
- `faster-whisper` — pure Python over CTranslate2, inherits arm64 support [VERIFIED: SYSTRAN/faster-whisper]
- `fastapi`, `uvicorn`, `numpy` — arm64 wheels [ASSUMED stable, standard packages]

**1.4 Frontend base: `node:22-slim` is multi-arch** [VERIFIED: Docker Hub]. Use Node 22 LTS.

**1.5 Best-practice Compose healthcheck chain** [CITED: docs.docker.com]:
```yaml
services:
  chromadb:
    image: chromadb/chroma:1.5.8
    ports: ["8000:8000"]
    volumes:
      - ./data/chroma:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v2/heartbeat"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 15s

  backend:
    build: ./backend
    ports: ["8080:8080"]
    environment:
      OLLAMA_HOST: http://host.docker.internal:11434
      CHROMA_HOST: http://chromadb:8000
      MODEL_DIR: /models
    volumes:
      - ${HOME}/.receptra/models:/models:ro
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      chromadb:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 20s

  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    depends_on:
      backend:
        condition: service_healthy
```

Sources: [Docker Compose depends_on healthcheck docs](https://docs.docker.com), [ChromaDB Docker guide](https://docs.trychroma.com/guides/deploy/docker).

**1.6 `host.docker.internal` on Mac:** works automatically in Docker Desktop. On Linux, add `extra_hosts: ["host.docker.internal:host-gateway"]` [CITED: docker.com docs]. Include it in compose for cross-OS contributor support.

### 2. Model Download Strategy

**2.1 Use `hf` CLI (modern replacement for `huggingface-cli`).** [CITED: huggingface.co/docs/huggingface_hub]
```bash
hf download ivrit-ai/whisper-large-v3-turbo-ct2 \
  --local-dir ~/.receptra/models/whisper-turbo-ct2
```
Progress bars are enabled by default [CITED: huggingface docs]. The `--local-dir` flag replicates the repo structure into the target path. Silence with `--quiet` (don't — we want visible progress).

**2.2 DictaLM 3.0 Ollama strategy.** DictaLM 3.0 is **NOT** in the official Ollama library [VERIFIED: ollama.com/library search returns no `dicta-il` entry; only community `aminadaven/dictalm2.0-instruct` for the older 2.0]. Path of least resistance for v1:

**Option A (recommended):** Pull the HF GGUF and create a Modelfile.
```bash
# 1. Download GGUF (Q5_K_M = 8.76 GB, recommended for 32GB Macs; Q4_K_M = 7.49 GB for 16GB)
hf download dicta-il/DictaLM-3.0-Nemotron-12B-Instruct-GGUF \
  --include "*Q5_K_M.gguf" \
  --local-dir ~/.receptra/models/dictalm-3.0

# 2. Create a Modelfile (scripts/ollama/DictaLM3.Modelfile)
FROM ~/.receptra/models/dictalm-3.0/DictaLM-3.0-Nemotron-12B-Instruct-Q5_K_M.gguf
PARAMETER temperature 0.3
PARAMETER num_ctx 8192
# TEMPLATE is auto-detected from tokenizer.chat_template metadata in GGUF [CITED: huggingface.co/docs/hub/ollama]

# 3. Register with Ollama
ollama create dictalm3 -f scripts/ollama/DictaLM3.Modelfile
```
[CITED: huggingface.co/docs/hub/ollama — "Use Ollama with any GGUF Model"]. GGUF template is auto-detected from the built-in `tokenizer.chat_template` metadata.

**Option B (fallback):** `ollama pull qwen2.5:7b` — one-liner, no Modelfile needed. Keep this in the Makefile as `make models-fallback`.

**Model size table (verified from HF):**
| Model | Quant | Size | License |
|-------|-------|------|---------|
| `ivrit-ai/whisper-large-v3-turbo-ct2` | FP16 | ~1.5 GB [ASSUMED — confirm at download time] | Apache 2.0 [VERIFIED: HF model card] |
| `dicta-il/DictaLM-3.0-Nemotron-12B-Instruct-GGUF` | Q5_K_M | 8.76 GB [VERIFIED: HF model card] | Apache 2.0 [VERIFIED: dicta.org.il] |
| `dicta-il/DictaLM-3.0-Nemotron-12B-Instruct-GGUF` | Q4_K_M | 7.49 GB [VERIFIED: HF model card] | Apache 2.0 |
| `bge-m3` via Ollama | Q4 default | ~1.2 GB (568M params) [VERIFIED: morphllm.com, ollama.com/library/bge-m3] | MIT |

**Total footprint:** ~11 GB (Q5_K_M DictaLM) or ~10 GB (Q4_K_M). Document this in README with a "15 GB free disk required" note (buffer for future models).

**2.3 `ollama pull bge-m3` works directly.** [VERIFIED: ollama.com/library/bge-m3] Dimension 1024, 8192-token context, 100+ languages. No custom Modelfile needed.

**2.4 Progress UX:** `hf download` already prints MB/s + ETA + progress bars. For `ollama pull`, Ollama's default stdout includes a progress bar. The Makefile should just forward stdout — no extra tooling needed.

### 3. Python Backend Scaffold

**3.1 Use `uv`, not pip.** [CITED: docs.astral.sh/uv/guides/integration/fastapi]
- Rationale: 10-100x faster than pip, handles arm64 wheel selection correctly, unified pyproject.toml + uv.lock, works cleanly in Docker builds.
- uv 0.11.7+ provides arm64 wheel distributions (manylinux + musllinux + macOS) [CITED: pydevtools.com].
- Docker pattern: `COPY pyproject.toml uv.lock ./` → `RUN uv sync --frozen --no-dev`.

**3.2 Minimal FastAPI scaffold:**

`backend/pyproject.toml`:
```toml
[project]
name = "receptra"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "python-multipart>=0.0.20",  # for future file uploads
]

[dependency-groups]
dev = [
    "ruff>=0.7",
    "mypy>=1.13",
    "pip-licenses>=5.0",
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",  # for TestClient
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "C4", "SIM", "RUF"]

[tool.mypy]
strict = true
python_version = "3.12"
```

**3.3 Canonical `/healthz`:**
```python
# backend/src/receptra/main.py
from fastapi import FastAPI
from receptra.config import settings

app = FastAPI(title="Receptra", version="0.1.0")

@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

**3.4 pydantic-settings pattern:**
```python
# backend/src/receptra/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RECEPTRA_")

    model_dir: str = "/models"
    ollama_host: str = "http://host.docker.internal:11434"
    chroma_host: str = "http://chromadb:8000"
    log_level: str = "INFO"

settings = Settings()
```

**3.5 Pipecat: DEFER to Phase 5.** Phase 1 scaffold does NOT need Pipecat. Installing it early bloats the image and drags in heavy ML deps unnecessarily. Pin `pipecat-ai>=1.0.0` (released April 14, 2026 [VERIFIED: pypi.org/project/pipecat-ai]) in Phase 5's plan, not here. This keeps the Phase 1 image small and the CI fast.

### 4. Frontend Scaffold

**4.1 Scaffold command:**
```bash
npm create vite@latest frontend -- --template react-ts
```
[CITED: vite.dev/guide]. Scaffolds React + TypeScript + Vite with HMR.

**4.2 Tailwind v4 install (2026 default):** [CITED: tailwindcss.com/docs]
```bash
cd frontend
npm install tailwindcss @tailwindcss/vite
```
Edit `vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
      '/ws': { target: 'ws://localhost:8080', ws: true },
    },
  },
})
```
Edit `src/index.css`:
```css
@import "tailwindcss";
```
No `tailwind.config.js` needed for v4 baseline. [CITED: thelinuxcode.com 2026 guide, tailwindcss.com/docs].

**4.3 RTL + Hebrew defaults in `index.html`:**
```html
<html dir="rtl" lang="he">
```
Full `hebrew-tailwind-preset` wiring (fonts, RTL utilities, Hebrew webfonts) is a Phase 6 concern. For Phase 1, bare RTL on the root `<html>` + a placeholder sidebar page satisfies FND-04.

**4.4 Baseline sidebar page (`src/App.tsx`):**
```typescript
export default function App() {
  return (
    <main className="min-h-screen p-8" dir="rtl">
      <h1 className="text-2xl font-bold">Receptra</h1>
      <p className="mt-2 text-sm text-gray-600">Foundation skeleton — Phase 1</p>
    </main>
  )
}
```

**4.5 Dev server proxy** (above) forwards `/api/*` → backend :8080, `/ws/*` → backend WebSocket. Standard Vite pattern.

### 5. CI + Licensing

**5.1 Runners:** `ubuntu-latest` (x86_64) for Phase 1. Fast, free, sufficient for lint/type-check/license-check. Mac-specific integration tests (`docker compose up`, Metal benchmarks) are documented as manual for Phase 1; Phase 7 can add `macos-14` arm64 runners if a Compose smoke test is wanted.

**5.2 Python lint + type-check:**
```yaml
- name: Install uv
  uses: astral-sh/setup-uv@v4
- name: Install deps
  run: cd backend && uv sync --all-extras
- name: Ruff lint
  run: cd backend && uv run ruff check .
- name: Ruff format check
  run: cd backend && uv run ruff format --check .
- name: Mypy
  run: cd backend && uv run mypy src
```
Ruff replaces black + flake8 + isort + pyupgrade (800+ rules, 10-100x faster than flake8) [CITED: docs.astral.sh/ruff].

**5.3 Frontend lint + type-check:**
```yaml
- uses: actions/setup-node@v4
  with: { node-version: 22 }
- run: cd frontend && npm ci
- run: cd frontend && npm run lint       # eslint
- run: cd frontend && npm run typecheck   # tsc --noEmit
- run: cd frontend && npx prettier --check .
```
Vite's react-ts template ships with ESLint preconfigured. Add `"typecheck": "tsc --noEmit"` to `package.json` scripts.

**5.4 License allowlist — Python:**
```bash
uv run pip-licenses --format=json \
  --allow-only="Apache Software License;Apache 2.0;Apache-2.0;MIT License;MIT;BSD License;BSD-3-Clause;BSD-2-Clause;ISC License;ISC;Python Software Foundation License;PSF-2.0;The Unlicense;Mozilla Public License 2.0 (MPL 2.0)"
# exits 1 on any disallowed license
```
[CITED: pypi.org/project/pip-licenses]. The semicolon-separated allowlist intentionally includes both SPDX names (`Apache-2.0`) and long-form names (`Apache Software License`) since pip-licenses reports metadata as declared by each package.

**5.5 License allowlist — Frontend:**
```bash
npx license-checker --production \
  --onlyAllow "Apache-2.0;MIT;ISC;BSD-2-Clause;BSD-3-Clause;CC0-1.0;0BSD;Unlicense;BlueOak-1.0.0"
# exits 1 on disallowed license
```
[CITED: npmjs.com/package/license-checker]. As of v17, `--onlyAllow` uses semicolons.

**5.6 Allowed vs blocked license policy:**
- **Allowed (permissive):** Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD, CC0-1.0, Unlicense, PSF-2.0, MPL-2.0 (file-level copyleft, acceptable for libraries), BlueOak-1.0.0
- **Blocked (copyleft / restrictive):** GPL-2.0, GPL-3.0, AGPL-*, LGPL-* (ambiguous in dynamic-link JS), SSPL, BUSL, any "research-only" / non-commercial / proprietary
- **Warn (manual review):** custom licenses, UNKNOWN, multiple-license packages

**5.7 Negative test for the gate:** Add a CI sanity test that installs a known-GPL package in a scratch venv and confirms the license check exits non-zero. Without this, "we have a license check" is unverified. Suggested: a `test-license-gate` job that runs in a separate directory and installs `readline` or a similar known-GPL-tagged package, then asserts the allowlist script exits 1. This can also be gated behind a manual workflow dispatch to avoid slowing every commit.

**5.8 CI job order:**
```
install (cache) → lint → typecheck → license-check → (tests — Phase 2+)
```
All on `ubuntu-latest`, runs in parallel where possible using `needs:` DAG.

### 6. Licensing Docs

**6.1 Apache 2.0 LICENSE:** Use the canonical text from https://www.apache.org/licenses/LICENSE-2.0.txt verbatim. Do not modify. The copyright line at the bottom becomes `Copyright 2026 Receptra Contributors` (or GitHub org name once published).

**6.2 Bilingual README pattern — recommend SPLIT files:**
- `README.md` — English (GitHub renders this by default; default for non-Hebrew discoverability)
- `README.he.md` — Hebrew with `<div dir="rtl" lang="he">` wrapping [CITED: GitHub community discussion #65545 — single-file RTL rendering has bugs in GitHub's Markdown renderer]
- Add a language switcher at the top of each file: `[עברית](README.he.md) | [English](README.md)`

**Rationale:** GitHub's markdown renderer has known bugs with mixed-direction content in one file [CITED: github/markup#899]. Separate files render cleanly. This is also the pattern most Israeli OSS projects use.

**6.3 CONTRIBUTING.md scope for Phase 1 (minimum viable):**
- How to clone + bring up the stack (link to Makefile targets)
- How to run tests locally
- PR conventions: squash merges, conventional commits encouraged (not enforced in Phase 1)
- Dependency addition policy: licenses must be in the allowlist — link to the CI check
- Code of Conduct: placeholder line "We follow the Contributor Covenant" with link; full CoC file deferred to Phase 7

### 7. Repo Structure — see Recommended File Layout below

### 8. Pitfall Mitigations (must appear in the plan)

**8.1 arm64 wheel check (Pitfall #6):** Dockerfile for backend should use `python:3.12-slim` (multi-arch) and `RUN uv sync --frozen`. If any wheel is missing for arm64, uv fails loudly with the offending package name — good. Document manual fallback in CONTRIBUTING.md: `uv pip install <pkg> --no-binary=<pkg>` with build-essential available in the image.

**8.2 Model footprint (Pitfall #12):** `.dockerignore` MUST include:
```
# Model weights — mounted via volume, not baked into image
**/*.bin
**/*.safetensors
**/*.ct2
**/*.gguf
**/*.pt
**/*.pth
models/
.receptra/
data/
node_modules/
dist/
build/
__pycache__/
.venv/
.git/
```
Verify in CI: an image-size check step that fails if the built image exceeds 2 GB (sanity ceiling — backend image should be ~500MB, frontend ~300MB).

**8.3 License creep (Pitfall #15):** The allowlist check (§5.4, §5.5) IS the mitigation. The negative-test job (§5.7) proves the gate works. No silent dep upgrades — pin uv.lock and package-lock.json.

## Recommended File Layout

```
receptra/
├── .github/
│   └── workflows/
│       ├── ci.yml                       # lint, typecheck, license-check
│       └── license-gate-test.yml        # manual-dispatch negative test
├── .gitignore
├── .dockerignore
├── .env.example
├── LICENSE                              # Apache 2.0 verbatim
├── README.md                            # English, with link to README.he.md
├── README.he.md                         # Hebrew, <div dir="rtl" lang="he">
├── CONTRIBUTING.md
├── Makefile                             # setup, models, up, down, logs, test, lint
├── docker-compose.yml
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── .python-version                  # 3.12
│   └── src/
│       └── receptra/
│           ├── __init__.py
│           ├── main.py                  # FastAPI app, /healthz
│           ├── config.py                # pydantic-settings
│           └── __main__.py              # uvicorn entrypoint
│   └── tests/
│       ├── __init__.py
│       └── test_healthz.py              # Phase 1 smoke test
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html                       # <html dir="rtl" lang="he">
│   ├── eslint.config.js
│   └── src/
│       ├── main.tsx
│       ├── App.tsx                      # placeholder sidebar
│       └── index.css                    # @import "tailwindcss"
│
├── scripts/
│   ├── download_models.sh               # called by `make models`
│   ├── check_licenses.sh                # thin wrapper over pip-licenses + license-checker
│   └── ollama/
│       └── DictaLM3.Modelfile           # HF GGUF → Ollama registration
│
├── knowledge/
│   ├── .gitkeep
│   └── sample/                          # optional sample docs for RAG phase
│       └── README.md
│
└── docs/
    ├── architecture.md                  # placeholder — Phase 7 fills
    └── phases/                          # symlink-safe location for published phase notes (optional)
```

**Key decisions encoded in the layout:**
- `backend/src/receptra/` — src-layout (not flat) for clean imports and setuptools-friendly packaging.
- `knowledge/` at root — gitignored except `.gitkeep` and `sample/`; this is user data in deployment.
- `scripts/ollama/DictaLM3.Modelfile` — versioned; `ollama create` is idempotent so committing the Modelfile is safe.
- `~/.receptra/models/` (user home) — NOT in the repo. Survives `git clean`, survives `rm -rf receptra/`, shared across worktrees.

## Recommended Dependencies

### Backend (`backend/pyproject.toml`)

Core runtime:
| Package | Version | License | Why |
|---------|---------|---------|-----|
| fastapi | >=0.115 | MIT | Web framework + `/healthz` |
| uvicorn[standard] | >=0.32 | BSD-3-Clause | ASGI server |
| pydantic | >=2.9 | MIT | Models, validation |
| pydantic-settings | >=2.6 | MIT | Env var config (`RECEPTRA_*`) |
| python-multipart | >=0.0.20 | Apache-2.0 | Reserved for future file uploads |

Dev dependencies (dependency-group `dev`):
| Package | Version | License | Why |
|---------|---------|---------|-----|
| ruff | >=0.7 | MIT | Lint + format (replaces black/flake8/isort) |
| mypy | >=1.13 | MIT | Type check (strict) |
| pip-licenses | >=5.0 | MIT | License allowlist in CI |
| pytest | >=8.3 | MIT | Test runner |
| pytest-asyncio | >=0.24 | Apache-2.0 | Async test support |
| httpx | >=0.27 | BSD-3-Clause | Used by FastAPI TestClient |

**Intentionally deferred to later phases:**
- `faster-whisper`, `ctranslate2`, `tokenizers` → Phase 2 (STT)
- `pipecat-ai` 1.0.0+ → Phase 5 (integration)
- `chromadb` client → Phase 4 (RAG)
- `ollama` (Python client) → Phase 3 (LLM)

### Frontend (`frontend/package.json`)

Core runtime:
| Package | Version | License | Why |
|---------|---------|---------|-----|
| react | ^19 | MIT | UI |
| react-dom | ^19 | MIT | UI |
| tailwindcss | ^4 | MIT | Styling |
| @tailwindcss/vite | ^4 | MIT | Tailwind v4 Vite plugin |

Dev dependencies:
| Package | Version | License | Why |
|---------|---------|---------|-----|
| vite | ^6 | MIT | Bundler |
| @vitejs/plugin-react | latest | MIT | React plugin for Vite |
| typescript | ~5.6 | Apache-2.0 | Type checking |
| eslint | ^9 | MIT | Lint |
| typescript-eslint | latest | BSD-2-Clause / MIT | TS rules for ESLint |
| prettier | ^3 | MIT | Format |
| license-checker | ^25 | BSD-3-Clause | License allowlist in CI |

All dependencies above have verified arm64 availability (npm packages are OS-agnostic; only issue would be native addons — none in the above list) [ASSUMED for eslint + prettier standard packages, VERIFIED for react/vite/tailwind].

## Model Download Strategy

### `Makefile` (root) — proposed targets

```makefile
.PHONY: help setup models models-dictalm models-whisper models-bge models-fallback up down logs test lint clean

MODEL_DIR ?= $(HOME)/.receptra/models

help:
	@echo "Receptra Makefile targets:"
	@echo "  make setup            Install host prerequisites + fetch all models"
	@echo "  make models           Download Whisper + DictaLM + BGE-M3 (~11 GB)"
	@echo "  make models-fallback  Use Qwen 2.5 7B instead of DictaLM"
	@echo "  make up               Ensure ollama running, then docker compose up"
	@echo "  make down             docker compose down"
	@echo "  make logs             Tail all service logs"
	@echo "  make test             Run all tests (lint, typecheck, unit)"
	@echo "  make lint             Lint backend + frontend"

setup: check-prereqs models
	@echo "✓ Setup complete. Run 'make up' to start the stack."

check-prereqs:
	@command -v docker >/dev/null || (echo "ERROR: install Docker Desktop"; exit 1)
	@command -v ollama >/dev/null || (echo "ERROR: brew install ollama"; exit 1)
	@command -v hf >/dev/null || (echo "ERROR: pip install -U huggingface_hub[cli]"; exit 1)
	@command -v uv >/dev/null || (echo "ERROR: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1)

models: models-whisper models-dictalm models-bge
	@echo "✓ All models downloaded to $(MODEL_DIR)"

models-whisper:
	@mkdir -p $(MODEL_DIR)
	hf download ivrit-ai/whisper-large-v3-turbo-ct2 \
	    --local-dir $(MODEL_DIR)/whisper-turbo-ct2

models-dictalm:
	@mkdir -p $(MODEL_DIR)/dictalm-3.0
	@# Q5_K_M recommended for 32GB; planner/user picks via DICTALM_QUANT env var
	hf download dicta-il/DictaLM-3.0-Nemotron-12B-Instruct-GGUF \
	    --include "*$(DICTALM_QUANT).gguf" \
	    --local-dir $(MODEL_DIR)/dictalm-3.0
	ollama create dictalm3 -f scripts/ollama/DictaLM3.Modelfile

models-bge:
	ollama pull bge-m3

models-fallback:
	ollama pull qwen2.5:7b

DICTALM_QUANT ?= Q5_K_M  # Q4_K_M for 16GB Macs; override: make models DICTALM_QUANT=Q4_K_M

up: check-prereqs
	@pgrep -x ollama >/dev/null || (echo "Starting ollama server..."; ollama serve &)
	docker compose up -d
	@echo "✓ Stack up. Backend: http://localhost:8080/healthz  Frontend: http://localhost:5173"

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && uv run pytest
	cd frontend && npm test --if-present

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy src
	cd frontend && npm run lint && npm run typecheck && npx prettier --check .

clean:
	docker compose down -v
	cd backend && uv cache clean
	cd frontend && rm -rf node_modules dist
	@echo "NOTE: models in $(MODEL_DIR) preserved. Run 'rm -rf $(MODEL_DIR)' to reclaim disk."
```

### Disk footprint plan

| Model | Path | Approx Size | Source |
|-------|------|-------------|--------|
| Whisper turbo (CT2) | `~/.receptra/models/whisper-turbo-ct2/` | ~1.5 GB | HF: `ivrit-ai/whisper-large-v3-turbo-ct2` |
| DictaLM 3.0 12B Q5_K_M | `~/.receptra/models/dictalm-3.0/*.gguf` | 8.76 GB | HF: `dicta-il/DictaLM-3.0-Nemotron-12B-Instruct-GGUF` |
| DictaLM 3.0 12B Q4_K_M (16GB Macs) | same | 7.49 GB | same |
| BGE-M3 | Ollama internal (`~/.ollama/models/`) | ~1.2 GB | `ollama pull bge-m3` |
| Qwen 2.5 7B (fallback) | Ollama internal | ~4.7 GB | `ollama pull qwen2.5:7b` |
| **Total (Q5_K_M path)** | | **~11.5 GB** | |
| **Total (Q4_K_M path)** | | **~10 GB** | |

README must state: **"~15 GB free disk space required"** (headroom for future models).

### Why separate-from-`docker compose up`?

`docker compose up` must NOT trigger downloads — that would (a) make `docker compose up` minutes-long on first run and invisible from the compose logs, (b) retry downloads on every image rebuild, (c) risk partial downloads leaving models corrupt. Separating `make models` gives clean lifecycle, visible progress bars, and resumable failures.

## Open Decisions for Planner

Items the planner must resolve before Phase 1 executes. Flag these for discussion or user decision.

### OPEN-1: Ollama in-compose vs host — STRONGLY RECOMMEND HOST
**Recommendation:** host (`brew install ollama && ollama serve`), wrap in `make up`.
**Risk if ignored:** In-compose Ollama on Mac falls back to CPU — blows the <2s latency budget at Phase 5 acceptance.
**What planner should lock:** "Ollama runs natively on host on Mac. Compose handles chromadb + backend + frontend only. `make up` ensures ollama is running."
**User confirmation needed:** Ideally yes — but this is documented best practice, so planner can lock without asking if the mode is `yolo`.

### OPEN-2: DictaLM quant default — 16GB vs 32GB Macs
**Recommendation:** Q5_K_M (8.76 GB) as default; document Q4_K_M (7.49 GB) override via `DICTALM_QUANT=Q4_K_M make models` for 16GB Macs.
**Alternative:** Default to Q4_K_M for widest compatibility; 32GB users override up.
**What planner should ask user:** "What's the primary target — 16GB M2 (conservative) or 32GB+ M2 Pro (better quality)?" Roadmap DEMO-01 mentions both. Suggest: default Q4_K_M (works everywhere), README documents Q5_K_M upgrade for 32GB users.

### OPEN-3: Bilingual README — two files vs one
**Recommendation:** Two files (README.md + README.he.md) with language switcher. GitHub renders cleaner.
**Alternative:** One file with `<div dir="rtl">` blocks. Known to render inconsistently.
**Lock:** two files.

### OPEN-4: React version — 18 or 19
**Recommendation:** React 19 (latest stable as of 2026-04).
**Risk:** React 19 removed some legacy APIs; verify compatibility with any later-phase libraries (LiveKit client, react-wavesurfer, etc.).
**What planner should check:** Whether any Phase 6 libraries still pin react@18. If unclear, lock at 18.3.x until Phase 6 research.

### OPEN-5: `hebrew-tailwind-preset` install in Phase 1 vs Phase 6
**Recommendation:** Phase 6 (frontend polish phase). Phase 1 needs only bare Tailwind + `dir="rtl"` on the root element to satisfy FND-04 ("reachable empty sidebar page"). Installing the preset now adds dependency + config complexity without delivering Phase 1 value.
**Lock:** Phase 1 installs base Tailwind v4. The skill-based preset wiring is Phase 6's concern.

### OPEN-6: CI runner choice — ubuntu-latest only or add macos-14
**Recommendation:** `ubuntu-latest` only for Phase 1. Fast + free + covers lint/type-check/license-check.
**Risk:** Doesn't catch Mac-specific Docker build issues or arm64-only wheel issues (since ubuntu-latest is x86_64).
**Mitigation:** Document "manual smoke test on Mac" in CONTRIBUTING.md; add `macos-14` runners as a follow-up in Phase 7 polish.
**Lock:** ubuntu-latest. Phase 7 revisits.

### OPEN-7: Python version — 3.12 or 3.13
**Recommendation:** 3.12 (broader wheel coverage for ML libs). 3.13 is out but some ML deps still lag on arm64 wheels in early 2026.
**Lock:** 3.12.

### OPEN-8: Negative license-gate test — always on every commit or manual workflow
**Recommendation:** manual workflow dispatch (`.github/workflows/license-gate-test.yml`). Running it on every commit slows CI and installs a known-bad package which pollutes the cache. Manual-trigger + documented proves the gate works without slowing the loop.
**Lock:** manual.

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json` — section required.

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest 8.3+ |
| Backend config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Backend quick run | `cd backend && uv run pytest tests/ -x` |
| Backend full suite | `cd backend && uv run pytest tests/ --cov=receptra` |
| Frontend framework | (none in Phase 1 — Vitest added in Phase 6) |
| Frontend quick run | `cd frontend && npm run lint && npm run typecheck` |
| CI full suite | `ubuntu-latest`: lint → typecheck → pytest → license-check |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FND-01 | Backend + frontend + docs dirs exist with expected files | structural | `test -d backend/src/receptra && test -f frontend/package.json && test -d docs` (as CI script) | ❌ Wave 0 |
| FND-02 | `docker compose config` validates; `docker compose build` succeeds on arm64 | structural + build | `docker compose config -q && docker compose build` (manual on Mac, CI validates config only) | ❌ Wave 0 |
| FND-03 | `make models` downloads 3 model sets to `$(MODEL_DIR)` with visible progress; re-runs are idempotent | behavioral | Manual-only on Mac (downloads ~10GB); CI asserts Makefile target parses via `make -n models` | ❌ Wave 0 |
| FND-04a | Backend `/healthz` returns 200 with `{"status": "ok"}` | unit + contract | `cd backend && uv run pytest tests/test_healthz.py -x` | ❌ Wave 0 — file does not exist |
| FND-04b | Frontend dev server serves `/` with "Receptra" title | smoke | `cd frontend && npm run build && test -f dist/index.html && grep -q "Receptra" dist/index.html` | ❌ Wave 0 |
| FND-05a | LICENSE file is Apache 2.0 | structural | `grep -q "Apache License" LICENSE && grep -q "Version 2.0" LICENSE` | ❌ Wave 0 |
| FND-05b | README.md + README.he.md exist; README.he.md has RTL block | structural | `test -f README.md && test -f README.he.md && grep -q 'dir="rtl"' README.he.md` | ❌ Wave 0 |
| FND-05c | CONTRIBUTING.md exists with Makefile link | structural | `test -f CONTRIBUTING.md && grep -q "make setup" CONTRIBUTING.md` | ❌ Wave 0 |
| FND-06a | Ruff lint passes | lint | `cd backend && uv run ruff check .` | ❌ Wave 0 |
| FND-06b | Mypy strict passes | type-check | `cd backend && uv run mypy src` | ❌ Wave 0 |
| FND-06c | Frontend eslint + tsc pass | lint + type-check | `cd frontend && npm run lint && npm run typecheck` | ❌ Wave 0 |
| FND-06d | Python license allowlist blocks GPL | regression | `cd backend && uv run pip-licenses --allow-only="..."` (allowlist flag) | ❌ Wave 0 |
| FND-06e | Frontend license allowlist blocks GPL | regression | `cd frontend && npx license-checker --onlyAllow="..."` | ❌ Wave 0 |
| FND-06f | **Negative gate test** — intentionally installing GPL dep makes license check fail | regression | Manual workflow dispatch job; asserts exit code == 1 | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && uv run ruff check . && uv run mypy src && uv run pytest tests/ -x` + `cd frontend && npm run lint && npm run typecheck`
- **Per wave merge:** full CI suite (lint + typecheck + pytest + license-check on both sides)
- **Phase gate:** All CI green + manual Mac smoke test (`make up` brings stack healthy, `curl localhost:8080/healthz` returns 200, `curl localhost:5173` returns HTML) before `/gsd-verify-work`

### Nyquist Validation Dimensions

1. **Structural** (files exist): `test -f` / `test -d` checks for LICENSE, README.md, README.he.md, CONTRIBUTING.md, Makefile, docker-compose.yml, backend/pyproject.toml, frontend/package.json, .github/workflows/ci.yml
2. **Behavioral** (stack runs): `docker compose up -d && sleep 30 && curl -f http://localhost:8080/healthz` — manual on Mac, CI only validates `docker compose config -q` (static validation, arm64 build is Mac-local)
3. **Contract** (APIs match expected shape): `pytest test_healthz.py` asserts `{"status": "ok"}` exact match with status 200
4. **Chaos** (survives rebuilds): Manual check — `docker compose down && docker compose up -d && curl /healthz` still 200 (models persist via volume mount on `~/.receptra/models`); documented in CONTRIBUTING.md
5. **Regression** (license gate works): Negative test job installs a known-GPL package in scratch env and asserts allowlist check exits non-zero. Proves the gate is real, not theater.

### Wave 0 Gaps

Items that MUST be created in Wave 0 (scaffold wave) before other Phase 1 tasks can validate:

- [ ] `backend/pyproject.toml` — with `[tool.pytest.ini_options]` block
- [ ] `backend/tests/test_healthz.py` — FastAPI TestClient hits `/healthz`, asserts 200 + JSON shape
- [ ] `backend/tests/conftest.py` — shared fixtures (e.g., `app` fixture)
- [ ] `frontend/eslint.config.js` — ESLint 9 flat config (matches Vite 2026 template default)
- [ ] `frontend/package.json` `scripts.typecheck` — `"tsc --noEmit"`
- [ ] `scripts/check_licenses.sh` — wraps pip-licenses + license-checker, single exit code
- [ ] `.github/workflows/ci.yml` — lint → typecheck → pytest → license-check DAG
- [ ] `.github/workflows/license-gate-test.yml` — manual-dispatch negative regression test
- [ ] `Makefile` — targets per §7 above

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ivrit-ai/whisper-large-v3-turbo-ct2` is ~1.5 GB | Model Download Strategy | Download time estimate off by <5 min — low risk. Planner must re-verify at download time and update README. |
| A2 | React 19 is compatible with all Phase 6 libraries | Frontend Deps | If a later phase (LiveKit client, wavesurfer) pins react@18, frontend will need downgrade. Planner can defer decision to Phase 6 by pinning react@18.3 in Phase 1 to be safe. |
| A3 | Ollama auto-detects DictaLM chat template from GGUF metadata | Model Download Strategy | If template is NOT embedded, the Modelfile needs a custom `TEMPLATE` block. Phase 3 will hit this failure first — acceptable for Phase 1 since DictaLM is not exercised in Phase 1. |
| A4 | `ubuntu-latest` x86_64 is sufficient for lint/type-check/license-check | CI + Licensing | If a backend dep lacks x86_64 wheels (unlikely for 2026 libs), CI install fails. Negligible risk for current dep list. |
| A5 | Docker Desktop on macOS exposes `host.docker.internal` automatically | Docker Compose § | Would need manual host config on Linux contributors. Mitigation: `extra_hosts: ["host.docker.internal:host-gateway"]` documented in compose. |
| A6 | pip-licenses correctly reads metadata for packages using new PEP 639 license fields | CI + Licensing | Some 2026 packages may declare license under new PEP 639 SPDX format; allowlist string matching may miss. Mitigation: test the gate against actual installed deps before locking CI. |
| A7 | HF GGUF for DictaLM 3.0 Nemotron 12B has `tokenizer.chat_template` metadata embedded | Model Download Strategy | If missing, Ollama's auto-template selection fails and model produces garbage. Phase 3 surfaces this; Phase 1 only creates the Modelfile, so low risk to Phase 1 exit. |

**Conclusion on assumptions:** None block Phase 1 completion. A2 is the one the planner may want to lock conservatively (react 18.3) to avoid Phase 6 rework. All others are either verifiable at execution time or deferred to later phases.

## Environment Availability

| Dependency | Required By | Available on Dev Mac | Version | Fallback |
|------------|------------|----------------------|---------|----------|
| Docker Desktop | Compose stack | Assumed present | 4.x | None — required |
| Ollama (host) | LLM + embeddings | Assumed via `brew install ollama` | latest | None — required |
| Node 22 | Frontend dev + CI | Assumed via `brew install node@22` or CI image | 22 LTS | Node 20 acceptable |
| Python 3.12 | Backend dev + CI | Assumed via `uv python install 3.12` | 3.12.x | 3.11 acceptable |
| uv | Python dep mgmt | Install via `curl -LsSf https://astral.sh/uv/install.sh \| sh` | >=0.5 | pip (slower, but works) |
| `hf` CLI (huggingface_hub) | Model download | `pip install -U huggingface_hub[cli]` | >=0.28 | `wget` on raw HF URLs |
| GNU make | Makefile targets | Preinstalled on macOS | any | Shell scripts in `scripts/` |
| curl | Healthchecks inside container | Include in backend Dockerfile | any | wget |

**Missing dependencies with fallback:** All covered above.
**Missing dependencies with no fallback:** Docker Desktop (Mac), Ollama (for LLM phases). Document in README "Prerequisites" section.

## Sources

### Primary (HIGH confidence)
- [ollama/ollama Docker Hub](https://hub.docker.com/r/ollama/ollama) — multi-arch manifest
- [chromadb/chroma Docker Hub](https://hub.docker.com/r/chromadb/chroma) — 1.5.8 current stable, April 2026
- [ChromaDB Docker guide](https://docs.trychroma.com/guides/deploy/docker) — v2 heartbeat, /data volume
- [Hugging Face Ollama integration](https://huggingface.co/docs/hub/ollama) — GGUF auto-template
- [DictaLM 3.0 Nemotron 12B Instruct GGUF](https://huggingface.co/dicta-il/DictaLM-3.0-Nemotron-12B-Instruct-GGUF) — verified quant sizes
- [Ollama bge-m3 library](https://ollama.com/library/bge-m3) — dimension 1024, ~1.2 GB
- [Tailwind CSS v4 install guide](https://tailwindcss.com/docs) — Vite plugin pattern
- [Vite getting started](https://vite.dev/guide/) — react-ts template
- [uv + FastAPI integration](https://docs.astral.sh/uv/guides/integration/fastapi/) — canonical pyproject pattern
- [Ruff docs](https://docs.astral.sh/ruff/) — 2026 rule set, replaces black/flake8/isort
- [Pipecat AI 1.0.0 on PyPI](https://pypi.org/project/pipecat-ai/) — released April 14, 2026
- [CTranslate2 4.7.1 arm64 wheels](https://pypi.org/project/ctranslate2/) — Feb 4, 2026 release
- [pip-licenses on PyPI](https://pypi.org/project/pip-licenses/) — allowlist usage
- [license-checker on npm](https://www.npmjs.com/package/license-checker) — `--onlyAllow` flag

### Secondary (MEDIUM confidence)
- [Chariot Solutions — Apple Silicon GPUs, Docker and Ollama: Pick two](https://chariotsolutions.com/blog/post/apple-silicon-gpus-docker-and-ollama-pick-two/) — corroborates Ollama-on-host recommendation
- [Local AI Master — Ollama on Mac Apple Silicon M1-M4 Setup 2026](https://localaimaster.com/blog/mac-local-ai-setup) — Metal acceleration native only
- [GitHub community discussion #65545](https://github.com/orgs/community/discussions/65545) — RTL README rendering quirks
- [Dicta-LM 3.0 project page](https://dicta.org.il/dicta-lm-3) — model family overview, Apache 2.0

### Tertiary (LOW confidence — verify at execution time)
- Ivrit-ai whisper-large-v3-turbo-ct2 exact file size in GB (~1.5 GB assumed from analogous CT2 conversions; actual size shown by `hf download` at execution time)
- React 19 compatibility with Phase 6 libraries (verify in Phase 6 research)

## Metadata

**Confidence breakdown:**
- Docker Compose stack: HIGH — all images verified multi-arch via Docker Hub 2026
- Model download path: HIGH for Whisper + BGE-M3, MEDIUM for DictaLM (needs Modelfile + template verification at Phase 3)
- Backend scaffold: HIGH — uv + FastAPI + pyproject is the 2026 canonical pattern
- Frontend scaffold: HIGH — Vite + React + Tailwind v4 verified against official 2026 docs
- CI + licensing: HIGH — pip-licenses and license-checker are both mature, well-documented
- Ollama-on-host decision: HIGH — multiple independent 2026 sources corroborate

**Research date:** 2026-04-23
**Valid until:** 2026-05-23 (30 days — stack is stable; re-verify before Phase 1 execution if >30 days elapse)
