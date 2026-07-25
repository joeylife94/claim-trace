"""ORM models.

Only infrastructure-level tables live here for now. Patent, document, chunk,
embedding, and claim tables are deliberately out of scope until the ingestion and
indexing phases (see ``docs/ROADMAP.md``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from claimtrace_api.db.base import Base


class AppMetadata(Base):
    """Small key/value table used to validate migrations and record app-level facts.

    It gives the migration pipeline something real to create and lets the service
    answer "which schema am I talking to?" without inspecting domain tables.
    """

    __tablename__ = "app_metadata"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=text("now()"),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"AppMetadata(key={self.key!r})"
