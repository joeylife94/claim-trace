# ClaimTrace API

FastAPI backend for ClaimTrace. Phase 1 scope is the service skeleton only:
operational probes, system metadata, configuration, and the migration pipeline.

## Layout

| Path | Responsibility |
| --- | --- |
| `src/claimtrace_api/core/` | Settings (`pydantic-settings`) and logging setup |
| `src/claimtrace_api/api/` | Routers, dependencies, versioned endpoints under `v1/` |
| `src/claimtrace_api/db/` | Engine, session factory, ORM models, health probe |
| `src/claimtrace_api/schemas/` | Pydantic request/response models |
| `alembic/` | Migration environment and versions |
| `tests/` | pytest suite (no database or network required) |

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | Liveness. Never touches PostgreSQL. |
| GET | `/ready` | Readiness. `503` when PostgreSQL is unreachable. |
| GET | `/api/v1/system/info` | Name, version, environment. |
| GET | `/docs` | OpenAPI UI (disabled when `ENVIRONMENT=production`). |

## Local commands

```bash
uv sync --extra dev            # create .venv and install dependencies
uv run uvicorn claimtrace_api.main:app --reload --port 8000
uv run pytest                  # tests
uv run ruff check .            # lint
uv run ruff format --check .   # format check
uv run alembic upgrade head    # migrations (requires a reachable PostgreSQL)
```

Configuration is read from environment variables, falling back to the repository
root `.env`. See `.env.example` for the supported keys.
