"""System information endpoint behaviour."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_system_info_returns_application_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/system/info")

    assert response.status_code == 200
    assert response.json() == {
        "name": "ClaimTrace API",
        "version": "0.1.0",
        "environment": "test",
    }


def test_system_info_is_served_under_the_versioned_prefix(client: TestClient) -> None:
    assert client.get("/system/info").status_code == 404
