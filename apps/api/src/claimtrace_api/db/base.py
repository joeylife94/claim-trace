"""Declarative base shared by every ORM model.

Alembic imports this module (via ``claimtrace_api.db.models``) to discover the
target metadata for autogeneration.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ClaimTrace ORM models."""
