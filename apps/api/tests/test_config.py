"""Settings behaviour that the rest of the application depends on."""

from __future__ import annotations

import pytest

from claimtrace_api.core.config import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "postgres_user": "user",
        "postgres_password": "secret",
        "postgres_host": "db",
        "postgres_port": 5432,
        "postgres_db": "claimtrace",
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def test_cors_origins_accept_a_comma_separated_string() -> None:
    """The env var is a plain list, not JSON, so it must survive a string source."""
    settings = _settings(
        cors_allow_origins="http://localhost:3000, https://claimtrace.internal ",
    )

    assert settings.cors_allow_origins == [
        "http://localhost:3000",
        "https://claimtrace.internal",
    ]


def test_cors_origins_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://a.example,http://b.example")

    assert Settings().cors_allow_origins == ["http://a.example", "http://b.example"]


def test_database_uri_is_assembled_from_discrete_settings() -> None:
    expected = "postgresql+psycopg://user:secret@db:5432/claimtrace"

    assert _settings().sqlalchemy_database_uri == expected


def test_explicit_database_url_wins() -> None:
    settings = _settings(database_url="postgresql+psycopg://other:pw@elsewhere:6543/other")

    assert settings.sqlalchemy_database_uri.endswith("@elsewhere:6543/other")
