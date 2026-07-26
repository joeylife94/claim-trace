"""Shared pytest fixtures.

The suite has two tiers:

* Default tests need no database, no network, and no model provider. They cover
  validation, parsing, storage, and locators.
* Tests marked ``integration`` exercise the real schema on PostgreSQL. They are
  skipped automatically when no database is reachable, and they run the Alembic
  migrations from an empty database, so the migration itself is under test.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.api.deps import get_ingestion_service, get_postgres_ready
from claimtrace_api.core.config import Settings
from claimtrace_api.main import create_app
from claimtrace_api.parsing.pymupdf_parser import PyMuPDFDocumentParser
from claimtrace_api.services.ingestion import DocumentIngestionService
from claimtrace_api.storage.local import LocalFileStorage

API_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# Database-free fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    root = tmp_path / "uploads"
    root.mkdir()
    return root


@pytest.fixture
def settings(storage_root: Path) -> Settings:
    """Deterministic settings that ignore any developer ``.env`` on the machine."""
    return Settings(
        app_name="ClaimTrace API",
        app_version="0.1.0",
        environment="test",
        log_level="WARNING",
        cors_allow_origins=["http://localhost:3000"],
        database_url="postgresql+psycopg://unused:unused@localhost:5432/unused",
        storage_root=storage_root,
        upload_max_bytes=1024 * 1024,
        min_extracted_characters=32,
        # No test may download a model. The deterministic provider satisfies the
        # same protocol, so every path above it is exercised for real.
        embedding_provider="fake",
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


@pytest.fixture
def stub_session() -> StubSession:
    return StubSession()


@pytest.fixture
def upload_client(
    app: FastAPI, settings: Settings, stub_session: StubSession
) -> Iterator[TestClient]:
    """Client whose ingestion service runs against a stub session.

    Exercises the real validator, parser, storage, and HTTP error mapping without
    a database. Persistence itself is covered by the integration tier.
    """
    app.dependency_overrides[get_postgres_ready] = lambda: True
    app.dependency_overrides[get_ingestion_service] = lambda: DocumentIngestionService(
        session=cast(AsyncSession, stub_session),
        storage=LocalFileStorage(settings.storage_root),
        parser=PyMuPDFDocumentParser(),
        settings=settings,
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class StubResult:
    """Minimal stand-in for a SQLAlchemy ``Result``."""

    def __init__(self, value: Any = None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalars(self) -> list[Any]:
        return [] if self._value is None else [self._value]


class StubSession:
    """Async session stand-in for paths that must not reach a database.

    Any statement it is asked to run returns "nothing found", which is what the
    duplicate lookup expects on a fresh upload. Tests that need real persistence
    are marked ``integration`` instead of using this.
    """

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commits = 0

    @staticmethod
    def _apply_server_defaults(instance: Any) -> None:
        """Emulate the timestamp defaults PostgreSQL would fill in on insert."""
        now = datetime.now(tz=UTC)
        for column in ("created_at", "updated_at"):
            if hasattr(instance, column) and getattr(instance, column) is None:
                setattr(instance, column, now)

    async def execute(self, *_args: Any, **_kwargs: Any) -> StubResult:
        return StubResult()

    async def scalar(self, *_args: Any, **_kwargs: Any) -> Any:
        return 0

    async def get(self, *_args: Any, **_kwargs: Any) -> Any:
        return None

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    def add_all(self, instances: list[Any]) -> None:
        self.added.extend(instances)

    async def commit(self) -> None:
        self.commits += 1
        for instance in self.added:
            self._apply_server_defaults(instance)

    async def rollback(self) -> None:
        return None

    async def refresh(self, instance: Any) -> None:
        self._apply_server_defaults(instance)


# --------------------------------------------------------------------------
# PostgreSQL-backed fixtures
# --------------------------------------------------------------------------


def _base_settings() -> Settings:
    """Settings from the ambient environment, used to locate a test database."""
    return Settings()


def _admin_url(settings: Settings) -> str:
    """URL of the maintenance database used to create the test database."""
    admin = sa.engine.make_url(settings.sqlalchemy_database_uri).set(database="postgres")
    return admin.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def integration_database_url() -> str:
    """Create a dedicated test database and migrate it from empty.

    Skips the whole integration tier when PostgreSQL is not reachable, so the
    default suite still runs on a laptop with nothing else installed.
    """
    settings = _base_settings()
    base_url = sa.engine.make_url(settings.sqlalchemy_database_uri)
    test_database = f"{base_url.database}_test"
    test_url = base_url.set(database=test_database).render_as_string(hide_password=False)

    try:
        admin_engine = sa.create_engine(
            _admin_url(settings), isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3}
        )
        with admin_engine.connect() as connection:
            exists = connection.scalar(
                sa.text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": test_database},
            )
            if not exists:
                connection.execute(sa.text(f'CREATE DATABASE "{test_database}"'))
        admin_engine.dispose()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL is not reachable for integration tests: {type(exc).__name__}")

    _run_migrations(test_url)
    return test_url


def _run_migrations(url: str) -> None:
    """Apply every Alembic revision to ``url``."""
    from alembic import command
    from alembic.config import Config

    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    # Passed through attributes rather than a main option: no ConfigParser
    # interpolation, so a password containing '%' cannot corrupt the URL.
    config.attributes["sqlalchemy_url"] = url
    command.upgrade(config, "head")


@pytest.fixture
def integration_settings(integration_database_url: str, storage_root: Path) -> Settings:
    return Settings(
        app_name="ClaimTrace API",
        app_version="0.1.0",
        environment="test",
        log_level="WARNING",
        database_url=integration_database_url,
        storage_root=storage_root,
        # Larger than the unit-test limit: a PDF with an embedded CJK font is a
        # few megabytes, and the Korean claim fixtures need one to round-trip.
        # The size-limit rejection itself is covered in the database-free tier.
        upload_max_bytes=8 * 1024 * 1024,
        min_extracted_characters=32,
        embedding_provider="fake",
    )


@pytest.fixture
def clean_database(integration_database_url: str) -> Iterator[None]:
    """Empty the ingestion tables before each integration test.

    ``CASCADE`` reaches the claim and retrieval tables too: every one of them
    descends from ``documents`` by foreign key, which is exactly the property
    the schema is designed to have.
    """
    engine = sa.create_engine(integration_database_url)
    with engine.begin() as connection:
        connection.execute(sa.text("TRUNCATE TABLE document_pages, documents CASCADE"))
    engine.dispose()
    yield


@pytest.fixture
def integration_client(
    integration_settings: Settings, clean_database: None
) -> Iterator[TestClient]:
    """Client backed by the migrated test database and a temporary storage root."""
    application = create_app(integration_settings)
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def indexing_client(integration_settings: Settings, clean_database: None) -> Iterator[TestClient]:
    """Integration client whose embedding provider can be swapped mid-test.

    ``app.state.embedding_provider`` is the seam the failure-path tests use to
    inject a provider that raises, so those paths run through the real service,
    the real transaction handling, and the real HTTP mapping.
    """
    application = create_app(integration_settings)
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def sync_engine(integration_database_url: str) -> Iterator[sa.Engine]:
    """Synchronous engine for asserting directly against stored rows."""
    engine = sa.create_engine(integration_database_url)
    yield engine
    engine.dispose()


@contextmanager
def capture_logs(logger_name: str, level: int = logging.DEBUG) -> Iterator[list[logging.LogRecord]]:
    """Collect records from one logger, independent of global logging config.

    ``configure_logging`` replaces the root handlers when an app is built, which
    detaches pytest's ``caplog`` handler for the rest of the session. Attaching
    directly to the logger under test keeps these assertions reliable whatever
    order the suite runs in.
    """
    records: list[logging.LogRecord] = []

    class ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger(logger_name)
    handler = ListHandler(level=level)
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(level)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def upload_pdf(
    client: TestClient,
    data: bytes,
    *,
    filename: str = "patent.pdf",
    content_type: str = "application/pdf",
) -> Any:
    """POST one file to the upload endpoint."""
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, data, content_type)},
    )


def unknown_uuid() -> uuid.UUID:
    return uuid.UUID("00000000-0000-4000-8000-000000000000")
