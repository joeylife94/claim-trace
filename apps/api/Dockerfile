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
#
# The "embeddings" extra brings sentence-transformers and a CPU-only torch (the
# wheel index is pinned in pyproject.toml). It is installed here so the image can
# run the real local embedding model with no network access at runtime beyond the
# one-time model download. Model *weights* are never baked in: they live in the
# cache volume mounted at EMBEDDING_CACHE_DIR.
#
# The uv cache is a build cache mount rather than an image layer: torch's wheels
# alone are over a gigabyte, and copying them into the image would double their
# cost for no runtime benefit.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra dev --extra embeddings --no-install-project

# Application layer.
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY tests ./tests
COPY evals ./evals
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra dev --extra embeddings

# Keep every Hugging Face cache under one writable path, so a read-only or
# root-owned $HOME cannot send downloads somewhere the runtime user cannot write.
ENV HF_HOME=/models

# Run as an unprivileged user. Only the two writable paths are chowned: the
# runtime user reads /app and /opt/venv but never writes to them, and a recursive
# chown over the virtualenv would copy every torch file into a second layer.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/uploads /models \
    && chown -R appuser:appuser /data /models
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else sys.exit(1)"]

CMD ["uvicorn", "claimtrace_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
