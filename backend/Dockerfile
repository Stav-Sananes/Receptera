# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Receptra backend image — Python 3.12 + FastAPI + uv
# Multi-arch: linux/arm64 (Apple Silicon primary) + linux/amd64 (CI / Linux)
# ---------------------------------------------------------------------------

FROM python:3.12-slim AS builder

# Install uv from the official slim image (static binary, no apt deps needed here).
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# Copy dep files first — leverages Docker layer cache when source changes but deps don't.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install the package itself.
COPY src ./src
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------

FROM python:3.12-slim AS runtime

# Install curl (needed by compose healthcheck) + tini (PID 1 reaping).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — avoids running as root in container.
RUN groupadd --system --gid 1001 receptra \
    && useradd --system --uid 1001 --gid receptra --home-dir /app --shell /usr/sbin/nologin receptra

WORKDIR /app

# Pull the resolved venv from the builder stage.
COPY --from=builder --chown=receptra:receptra /opt/venv /opt/venv
COPY --from=builder --chown=receptra:receptra /app/src /app/src

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER receptra

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8080/healthz || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "receptra.main:app", "--host", "0.0.0.0", "--port", "8080"]
