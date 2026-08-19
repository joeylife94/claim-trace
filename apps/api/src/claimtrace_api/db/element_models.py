"""Persistence models for versioned claim-element decomposition.

Machine decomposition is stored separately from human review. The identity of one
run is ``(claim_id, parser_name, parser_version)`` so rerunning the same parser
version is idempotent while a future parser version can coexist without
rewriting older provenance.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from claimtrace_api.db.base import Base


class ElementDecompositionRun(Base):
    __tablename__ = "element_decomposition_runs"
    __table_args__ = (
        UniqueConstraint(
            "claim_id", "parser_name", "parser_version", name="uq_element_runs_claim_parser"
        ),
        CheckConstraint("element_count >= 0", name="ck_element_runs_element_count"),
        CheckConstraint("warning_count >= 0", name="ck_element_runs_warning_count"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parser_name: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    element_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sql_text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    elements: Mapped[list[ClaimElement]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ClaimElement.sequence_number",
    )


class ClaimElement(Base):
    __tablename__ = "claim_elements"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_number", name="uq_claim_elements_run_sequence"),
        CheckConstraint("sequence_number >= 0", name="ck_claim_elements_sequence_non_negative"),
        CheckConstraint("length(text) > 0", name="ck_claim_elements_text_non_empty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("element_decomposition_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped[ElementDecompositionRun] = relationship(back_populates="elements")
    spans: Mapped[list[ClaimElementSpan]] = relationship(
        back_populates="element",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ClaimElementSpan.sequence_number",
    )


class ClaimElementSpan(Base):
    __tablename__ = "claim_element_spans"
    __table_args__ = (
        UniqueConstraint("element_id", "sequence_number", name="uq_element_spans_element_sequence"),
        CheckConstraint("sequence_number >= 0", name="ck_element_spans_sequence_non_negative"),
        CheckConstraint("page_number >= 1", name="ck_element_spans_page_positive"),
        CheckConstraint("start_char >= 0", name="ck_element_spans_start_non_negative"),
        CheckConstraint("end_char > start_char", name="ck_element_spans_end_after_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    element_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("claim_elements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    element: Mapped[ClaimElement] = relationship(back_populates="spans")
