# Contributing to Receptra

Thanks for your interest! Receptra is a Hebrew-first local-only voice AI project. Please read this before opening a PR.

## Ground rules

- **Licensing:** All dependencies MUST be permissively licensed (Apache-2.0, MIT, BSD-2/3, ISC, 0BSD, CC0, Unlicense, PSF). GPL / AGPL / LGPL / SSPL / proprietary deps are blocked by the CI license allowlist — see `.github/workflows/ci.yml`.
- **Privacy:** The core loop MUST run fully local. No cloud API calls in the hot path.
- **Platform:** Apple Silicon (M2+) is the reference floor for Milestone 1.

## Developer setup

```bash
# 1. Install host prerequisites
brew install ollama node@22 python@3.12
curl -LsSf https://astral.sh/uv/install.sh | sh
pip install -U huggingface_hub[cli]

# 2. Clone and configure
git clone <repo-url> receptra
cd receptra
cp .env.example .env

# 3. Install deps + download models (~11 GB)
make setup

# 4. Bring up the stack
make up

# 5. Tail logs
make logs
```

## Running tests locally

```bash
make lint        # ruff + mypy + eslint + tsc + prettier
make test        # pytest + frontend tests (when present)
```

Both `lint` and `test` are run in CI on every push. See `.github/workflows/ci.yml`.

## PR conventions

- Squash-merge is the default.
- Conventional commits encouraged (`feat:`, `fix:`, `docs:`, `chore:`) but not enforced in Milestone 1.
- Adding a new dependency? Verify its license is in the allowlist (see `scripts/check_licenses.sh`). PRs that introduce a disallowed license will fail CI.

## Code of Conduct

We follow the [Contributor Covenant](https://www.contributor-covenant.org/). A full `CODE_OF_CONDUCT.md` is planned for the public-launch phase.

## Questions

Open an issue in the repository or start a discussion.
