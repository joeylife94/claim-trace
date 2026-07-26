"""Liveness endpoint behaviour."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from claimtrace_api.api.deps import get_postgres_ready


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_does_not_touch_postgres(app: FastAPI) -> None:
    """Liveness must stay green even when the database dependency would explode."""

    def exploding_dependency() -> bool:
        raise AssertionError("/health must not evaluate the PostgreSQL dependency")

    app.dependency_overrides[get_postgres_ready] = exploding_dependency

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
