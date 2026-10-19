# Production image for the API (Render). Build context: repository root.
#   docker build -f deploy/backend.Dockerfile -t calibr-api .
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

FROM python:3.12-slim
RUN useradd --create-home --uid 1000 app && apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 APP_ENV=production \
    SEED_ARCHIVE_PATH=/app/seed/admin_archive.sql.gz PORT=8000
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app backend/ .
# Holds admin_archive.sql.gz only when it is present in the build context (it is not committed).
COPY --chown=app:app deploy/seed/ /app/seed/
RUN mkdir -p /uploads /data && chown -R app:app /uploads /data
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=8 CMD curl -fsS "http://localhost:${PORT}/health" || exit 1
# One worker: the per-user rate limiter and agent run locks are in-process (see docs/KNOWN_ISSUES.md).
CMD ["sh", "-c", "alembic upgrade head && python -m scripts.seed_archive && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
