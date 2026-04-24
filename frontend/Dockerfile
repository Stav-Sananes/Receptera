# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Receptra frontend image — Node 22 + Vite dev server
# Multi-arch: linux/arm64 + linux/amd64
# Phase 1 intentionally runs the Vite dev server (not a production nginx bundle).
# A production static-serve image lands in Phase 7 (Polish & Demo).
# ---------------------------------------------------------------------------

FROM node:22-slim AS runtime

# curl for compose healthcheck; tini for PID 1 reaping.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (node image ships with `node` uid 1000; we create our own for clarity).
RUN groupadd --system --gid 1001 receptra \
    && useradd --system --uid 1001 --gid receptra --home-dir /app --shell /usr/sbin/nologin receptra

WORKDIR /app

# Dep install layer — cached when source changes but deps don't.
COPY --chown=receptra:receptra package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Source
COPY --chown=receptra:receptra . .

USER receptra

EXPOSE 5173

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:5173 > /dev/null || exit 1

ENTRYPOINT ["tini", "--"]
# strictPort: true in vite.config.ts means this fails fast if 5173 is in use.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
