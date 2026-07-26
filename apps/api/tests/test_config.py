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


# --------------------------------------------------------------------------
# Optional LLM settings
# --------------------------------------------------------------------------


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_optional_llm_variable_reads_as_unset(
    monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    """`.env.example` documents leaving these blank, so blank has to load.

    A variable written as ``LLM_DIAGNOSTICS_ENABLED=`` arrives as an empty
    string. Without the coercion this guards, pydantic rejects it as an invalid
    boolean and the application fails to start from its own documented
    configuration - which is exactly how it was found.
    """
    monkeypatch.setenv("LLM_DIAGNOSTICS_ENABLED", blank)
    monkeypatch.setenv("LLM_OPENAI_COMPATIBLE_API_KEY", blank)

    settings = _settings()

    assert settings.llm_diagnostics_enabled is None
    # Not SecretStr("") - an empty key would otherwise send a "Bearer " header.
    assert settings.llm_openai_compatible_api_key is None


def test_diagnostics_default_follows_the_environment() -> None:
    """Unset means on in development and off everywhere else."""
    assert _settings(environment="development").llm_diagnostics_active is True
    assert _settings(environment="staging").llm_diagnostics_active is False
    assert _settings(environment="production").llm_diagnostics_active is False


@pytest.mark.parametrize(("value", "expected"), [(True, True), (False, False)])
def test_an_explicit_diagnostics_flag_overrides_the_environment(
    value: bool, expected: bool
) -> None:
    settings = _settings(environment="production", llm_diagnostics_enabled=value)

    assert settings.llm_diagnostics_active is expected


def test_an_api_key_is_never_rendered_in_settings() -> None:
    settings = _settings(llm_openai_compatible_api_key="sk-local-secret")

    assert "sk-local-secret" not in repr(settings)
    assert "sk-local-secret" not in str(settings.model_dump())
    # Reachable only by asking for it explicitly.
    assert settings.llm_openai_compatible_api_key is not None
    assert settings.llm_openai_compatible_api_key.get_secret_value() == "sk-local-secret"


def test_an_unknown_provider_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="llm_provider"):
        _settings(llm_provider="gpt-9")
