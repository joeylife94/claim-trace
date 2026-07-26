"""ORM models.

Phase 2A adds the ingestion tables. Sections, claims, chunks, and embeddings are
still out of scope; see ``docs/ROADMAP.md``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
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
        server_onupdate=text("now()"),
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
        server_onupdate=text("now()"),
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
