"""Persistent analyst Case workspace service for D5-01.

Cases own only workspace metadata and references to existing documents. They do
not copy document text, page text, claims, description evidence, or locators.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CaseNotFoundError(LookupError):
    pass


class CaseDocumentNotFoundError(LookupError):
    pass


class CaseDocumentAssociationNotFoundError(LookupError):
    pass


class AnalystCaseService:
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def create(self, title: str) -> dict[str, Any]:
        case_id = uuid.uuid4()
        await self._session.execute(
            text(
                """
                INSERT INTO analyst_cases (id, title)
                VALUES (:id, :title)
                """
            ),
            {"id": case_id, "title": title},
        )
        await self._session.commit()
        return await self.get(case_id)

    async def list(self) -> list[dict[str, Any]]:
        rows = (
            await self._session.execute(
                text("SELECT id FROM analyst_cases ORDER BY created_at, id")
            )
        ).all()
        return [await self.get(row.id) for row in rows]

    async def get(self, case_id: uuid.UUID) -> dict[str, Any]:
        case_row = (
            await self._session.execute(
                text(
                    """
                    SELECT id, title, created_at, updated_at
                    FROM analyst_cases
                    WHERE id = :case_id
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings().first()
        if case_row is None:
            raise CaseNotFoundError(str(case_id))

        document_rows = (
            await self._session.execute(
                text(
                    """
                    SELECT d.id, d.original_filename, d.status, acd.associated_at
                    FROM analyst_case_documents AS acd
                    JOIN documents AS d ON d.id = acd.document_id
                    WHERE acd.case_id = :case_id
                    ORDER BY acd.associated_at, d.id
                    """
                ),
                {"case_id": case_id},
            )
        ).mappings().all()

        return {
            "id": case_row["id"],
            "title": case_row["title"],
            "created_at": _datetime(case_row["created_at"]),
            "updated_at": _datetime(case_row["updated_at"]),
            "documents": [
                {
                    "id": row["id"],
                    "original_filename": row["original_filename"],
                    "status": str(row["status"]),
                    "associated_at": _datetime(row["associated_at"]),
                }
                for row in document_rows
            ],
        }

    async def add_document(self, case_id: uuid.UUID, document_id: uuid.UUID) -> tuple[dict[str, Any], bool]:
        await self._assert_case(case_id)
        if not await self._document_exists(document_id):
            raise CaseDocumentNotFoundError(str(document_id))

        row = (
            await self._session.execute(
                text(
                    """
                    INSERT INTO analyst_case_documents (case_id, document_id)
                    VALUES (:case_id, :document_id)
                    ON CONFLICT (case_id, document_id) DO NOTHING
                    RETURNING document_id
                    """
                ),
                {"case_id": case_id, "document_id": document_id},
            )
        ).first()
        changed = row is not None
        await self._session.commit()
        return await self.get(case_id), changed

    async def remove_document(self, case_id: uuid.UUID, document_id: uuid.UUID) -> dict[str, Any]:
        await self._assert_case(case_id)
        row = (
            await self._session.execute(
                text(
                    """
                    DELETE FROM analyst_case_documents
                    WHERE case_id = :case_id AND document_id = :document_id
                    RETURNING document_id
                    """
                ),
                {"case_id": case_id, "document_id": document_id},
            )
        ).first()
        if row is None:
            await self._session.rollback()
            raise CaseDocumentAssociationNotFoundError(str(document_id))
        await self._session.commit()
        return await self.get(case_id)

    async def _assert_case(self, case_id: uuid.UUID) -> None:
        row = (
            await self._session.execute(
                text("SELECT 1 FROM analyst_cases WHERE id = :case_id"),
                {"case_id": case_id},
            )
        ).first()
        if row is None:
            raise CaseNotFoundError(str(case_id))

    async def _document_exists(self, document_id: uuid.UUID) -> bool:
        row = (
            await self._session.execute(
                text("SELECT 1 FROM documents WHERE id = :document_id"),
                {"document_id": document_id},
            )
        ).first()
        return row is not None


def _datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("database datetime column returned a non-datetime value")
    return value
