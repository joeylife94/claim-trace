"""Append-only human review records for machine claim decomposition."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from claimtrace_api.db.base import Base


class DecompositionReviewStatus(StrEnum):
    """Bounded reviewer judgements; never legal conclusions."""

    ACCEPTED = "accepted"
    NEEDS_CORRECTION = "needs_correction"


class ElementDecompositionReview(Base):
    """One immutable review action against one exact machine decomposition run."""

    __tablename__ = "element_decomposition_reviews"
    __table_args__ = (
        CheckConstraint(
            "status IN ('accepted', 'needs_correction')",
            name="ck_element_decomposition_reviews_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("element_decomposition_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped["ElementDecompositionRun"] = relationship()


from claimtrace_api.db.element_models import ElementDecompositionRun  # noqa: E402
