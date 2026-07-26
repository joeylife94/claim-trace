"""Async engine and session factory.

The engine is created once per process during application startup and disposed on
shutdown. Request handlers obtain sessions through the dependencies in
``claimtrace_api.api.deps``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from claimtrace_api.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the async engine for the configured PostgreSQL instance."""
    return create_async_engine(
        settings.sqlalchemy_database_uri,
        echo=False,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to ``engine``."""
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a session and guarantee it is closed."""
    async with session_factory() as session:
        yield session
