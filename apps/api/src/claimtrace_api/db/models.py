"""ORM models.

Phase 2A adds the ingestion tables; Phase 2B adds claim structural parsing.
Sections, chunks, and embeddings are still out of scope; see ``docs/ROADMAP.md``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)

# Aliased: "text" is also a column name on Claim and DocumentPage, and a bare
# import would be shadowed inside those class bodies.
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
        server_onupdate=sql_text("now()"),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"AppMetadata(key={self.key!r})"


class DocumentStatus(StrEnum):
    """Ingestion lifecycle.

    ``uploaded`` is committed as soon as the bytes are safely stored, so a crash
    mid-parse still leaves a traceable record instead of an orphaned file.
    """

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


#: Stored as VARCHAR + CHECK rather than a native PostgreSQL enum: adding a state
#: later is then an ordinary migration instead of an ALTER TYPE dance.
_document_status = Enum(
    DocumentStatus,
    name="document_status",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    length=32,
)


class Document(Base):
    """An uploaded source document and the outcome of parsing it.

    The row is the citation anchor: every future claim, chunk, and piece of
    evidence resolves back to a ``document_id`` plus a page and offset range.
    """

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_documents_size_bytes_positive"),
        CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="ck_documents_page_count_non_negative",
        ),
        Index("ix_documents_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Content address of the original bytes. Unique: the same file is ingested once.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Opaque storage identifier. Never a client-supplied name, never returned by the API.
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)

    status: Mapped[DocumentStatus] = mapped_column(
        _document_status, nullable=False, default=DocumentStatus.UPLOADED, index=True
    )

    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_character_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    parser_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=sql_text("now()"),
        onupdate=func.now(),
    )

    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentPage.page_number",
    )

    def __repr__(self) -> str:
        return f"Document(id={self.id!r}, status={self.status.value!r})"


class DocumentPage(Base):
    """One page of extracted text.

    The page is the unit of provenance: ``(document_id, page_number, start_char,
    end_char)`` addresses a span of *this* stored text, so a citation stays valid
    for as long as the row does.
    """

    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_document_pages_document_page"),
        CheckConstraint("page_number >= 1", name="ck_document_pages_page_number_positive"),
        CheckConstraint("character_count >= 0", name="ck_document_pages_char_count_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # Pages are meaningless without their document, so they go with it.
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Lets a re-parse detect whether a page's text actually changed.
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="pages")

    def __repr__(self) -> str:
        return f"DocumentPage(document_id={self.document_id!r}, page_number={self.page_number!r})"


class ClaimParseStatus(StrEnum):
    """Claim parsing lifecycle.

    Deliberately separate from :class:`DocumentStatus`: a document that ingested
    cleanly stays ``completed`` no matter how claim parsing turns out. Failing to
    find claims says nothing about whether the PDF was read correctly.
    """

    PROCESSING = "processing"
    COMPLETED = "completed"
    #: Parsing ran to completion and found no claim headings. An outcome, not an
    #: error, and never reported as an empty success.
    NO_CLAIMS_FOUND = "no_claims_found"
    FAILED = "failed"


class ClaimType(StrEnum):
    """Structural classification, derived only from explicit references.

    This is a syntactic description of the claim text. It is not a legal
    characterisation and carries no conclusion about scope or validity.
    """

    INDEPENDENT = "independent"
    DEPENDENT = "dependent"
    MULTIPLE_DEPENDENT = "multiple_dependent"
    #: References were detected but none could be resolved safely.
    UNKNOWN = "unknown"


_claim_parse_status = Enum(
    ClaimParseStatus,
    name="claim_parse_status",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    length=32,
)

_claim_type = Enum(
    ClaimType,
    name="claim_type",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    length=24,
)


class ClaimParseResult(Base):
    """One run of one claim parser version against one document.

    Uniqueness is ``(document_id, parser_name, parser_version)``: a document has
    at most one current result per parser version. Re-running the same version is
    idempotent, and a future parser version produces a new row beside this one
    rather than overwriting a result that existing citations may point at.
    """

    __tablename__ = "claim_parse_results"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "parser_name",
            "parser_version",
            name="uq_claim_parse_results_document_parser",
        ),
        CheckConstraint("claim_count >= 0", name="ck_claim_parse_results_claim_count"),
        CheckConstraint("warning_count >= 0", name="ck_claim_parse_results_warning_count"),
        Index("ix_claim_parse_results_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[ClaimParseStatus] = mapped_column(
        _claim_parse_status, nullable=False, default=ClaimParseStatus.PROCESSING, index=True
    )

    parser_name: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)

    claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Structured parse warnings, always read together with the result and never
    #: queried on their own - a JSONB column rather than a fifth table.
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sql_text("'[]'::jsonb")
    )

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=sql_text("now()"),
        onupdate=func.now(),
    )

    document: Mapped[Document] = relationship()
    claims: Mapped[list[Claim]] = relationship(
        back_populates="parse_result",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Claim.claim_number",
    )

    def __repr__(self) -> str:
        return f"ClaimParseResult(id={self.id!r}, status={self.status.value!r})"


class Claim(Base):
    """One parsed claim.

    ``document_id`` is deliberately absent: it is reachable through
    ``parse_result``, and duplicating it would allow a claim to disagree with its
    own parse result about which document it came from.
    """

    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("parse_result_id", "claim_number", name="uq_claims_result_number"),
        # Redundant on its own, but it is the target of the composite foreign keys
        # in claim_dependencies, which is what keeps an edge inside one parse result.
        UniqueConstraint("id", "parse_result_id", name="uq_claims_id_result"),
        CheckConstraint("claim_number >= 1", name="ck_claims_number_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    parse_result_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("claim_parse_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    claim_number: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_type: Mapped[ClaimType] = mapped_column(_claim_type, nullable=False)

    #: Reconstructed deterministically by joining the ordered spans; stored so a
    #: reader does not have to re-resolve spans, and verified against them in tests.
    text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=sql_text("now()"),
        onupdate=func.now(),
    )

    parse_result: Mapped[ClaimParseResult] = relationship(back_populates="claims")
    spans: Mapped[list[ClaimSpan]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ClaimSpan.sequence_number",
    )
    dependencies: Mapped[list[ClaimDependency]] = relationship(
        back_populates="dependent_claim",
        foreign_keys="ClaimDependency.dependent_claim_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"Claim(number={self.claim_number!r}, type={self.claim_type.value!r})"


class ClaimSpan(Base):
    """One page-relative source span of a claim.

    A claim that crosses a page break has one span per page, ordered by
    ``sequence_number``. There is deliberately no flattened document offset: the
    canonical coordinate stays ``(document_id, page_number, start_char, end_char)``
    against ``document_pages.text``.
    """

    __tablename__ = "claim_spans"
    __table_args__ = (
        UniqueConstraint("claim_id", "sequence_number", name="uq_claim_spans_claim_sequence"),
        CheckConstraint("sequence_number >= 0", name="ck_claim_spans_sequence_non_negative"),
        CheckConstraint("page_number >= 1", name="ck_claim_spans_page_number_positive"),
        CheckConstraint("start_char >= 0", name="ck_claim_spans_start_non_negative"),
        # Half-open and non-empty: an empty span cites nothing.
        CheckConstraint("end_char > start_char", name="ck_claim_spans_end_after_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    claim_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True
    )

    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    claim: Mapped[Claim] = relationship(back_populates="spans")

    def __repr__(self) -> str:
        return f"ClaimSpan(page={self.page_number!r}, {self.start_char!r}:{self.end_char!r})"


class ClaimDependency(Base):
    """A resolved edge: ``dependent_claim`` explicitly references ``referenced_claim``.

    Stored as a graph rather than a tree, because a multiple-dependent claim has
    several parents and flattening that would lose the actual structure.

    ``parse_result_id`` is carried so both endpoints can be tied to the same parse
    result by composite foreign keys: without it, nothing at the database level
    would stop an edge from pointing into a different document's claims.
    """

    __tablename__ = "claim_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "dependent_claim_id",
            "referenced_claim_id",
            name="uq_claim_dependencies_pair",
        ),
        CheckConstraint(
            "dependent_claim_id <> referenced_claim_id",
            name="ck_claim_dependencies_no_self_reference",
        ),
        ForeignKeyConstraint(
            ["dependent_claim_id", "parse_result_id"],
            ["claims.id", "claims.parse_result_id"],
            name="fk_claim_dependencies_dependent_in_result",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["referenced_claim_id", "parse_result_id"],
            ["claims.id", "claims.parse_result_id"],
            name="fk_claim_dependencies_referenced_in_result",
            ondelete="CASCADE",
        ),
        Index("ix_claim_dependencies_referenced", "referenced_claim_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    parse_result_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    dependent_claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    referenced_claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    dependent_claim: Mapped[Claim] = relationship(
        back_populates="dependencies", foreign_keys=[dependent_claim_id, parse_result_id]
    )

    def __repr__(self) -> str:
        return f"ClaimDependency({self.dependent_claim_id!r} -> {self.referenced_claim_id!r})"
