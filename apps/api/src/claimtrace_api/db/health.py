"""Database liveness probing used by the readiness endpoint."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def check_postgres(engine: AsyncEngine) -> bool:
    """Return ``True`` when a trivial query succeeds against PostgreSQL.

    Failures are logged with their cause but never surfaced to the client: the
    connection string may embed credentials.
    """
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        # One line per probe: readiness is polled continuously, so the traceback is
        # kept behind DEBUG rather than repeated in the log on every failure.
        logger.warning("postgres readiness check failed: %s", type(exc).__name__)
        logger.debug("postgres readiness failure detail", exc_info=True)
        return False
    return True
