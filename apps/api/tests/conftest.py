"""Shared pytest fixtures.

The suite is fully self-contained: it never opens a socket to PostgreSQL and never
calls an external model provider. Database behaviour is exercised by overriding the
readiness dependency.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from claimtrace_api.api.deps import get_postgres_ready
from claimtrace_api.core.config import Settings
from claimtrace_api.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Deterministic settings that ignore any developer ``.env`` on the machine."""
    return Settings(
        app_name="ClaimTrace API",
        app_version="0.1.0",
        environment="test",
        log_level="WARNING",
        cors_allow_origins=["http://localhost:3000"],
        database_url="postgresql+psycopg://unused:unused@localhost:5432/unused",
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Client whose PostgreSQL dependency reports healthy by default."""
    app.dependency_overrides[get_postgres_ready] = lambda: True
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
