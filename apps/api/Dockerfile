# syntax=docker/dockerfile:1
# ClaimTrace API image. Pinned to Python 3.12; dependencies are installed with uv
# from the committed lockfile so builds are reproducible.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app

# Dependency layer: only invalidated when the manifest or lockfile changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --extra dev --no-install-project

# Application layer.
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY tests ./tests
RUN uv sync --frozen --extra dev

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app /opt/venv
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else sys.exit(1)"]

CMD ["uvicorn", "claimtrace_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
