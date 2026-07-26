"""Readiness endpoint behaviour with the database dependency isolated."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from claimtrace_api.api.deps import get_postgres_ready
from claimtrace_api.db.health import check_postgres


def test_ready_reports_ready_when_postgres_is_reachable(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "dependencies": {"postgres": "ok"}}


def test_ready_returns_503_when_postgres_is_unreachable(app: FastAPI) -> None:
    app.dependency_overrides[get_postgres_ready] = lambda: False

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "dependencies": {"postgres": "unavailable"}}


@pytest.mark.asyncio
async def test_check_postgres_swallows_connection_errors() -> None:
    """A failed probe returns False rather than propagating driver internals."""

    class FailingEngine:
        def connect(self) -> object:
            raise OperationalError("SELECT 1", None, Exception("connection refused"))

    assert await check_postgres(FailingEngine()) is False  # type: ignore[arg-type]
