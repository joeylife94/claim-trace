"""Persistence for D5-02 Case-grounded analysis snapshots.

Only reviewer-visible analysis state and provenance references are persisted.
Source text remains owned by document_pages and is re-read from canonical
(document_id, page_number, start_char, end_char) locators when a result is reopened.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from claimtrace_api.schemas.grounded import GroundedAnswerRequest, GroundedAnswerResponse
from claimtrace_api.schemas.locators import SourceLocator


class CaseGroundedResultNotFoundError(LookupError):
    pass


class CaseGroundedScopeError(ValueError):
    pass


class CaseGroundedResultService:
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def request_fingerprint(request: GroundedAnswerRequest) -> str:
        payload = request.model_dump(mode="json")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def find_existing(
        self, case_id: uuid.UUID, request: GroundedAnswerRequest
    ) -> dict[str, Any] | None:
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT id
                    FROM analyst_case_grounded_results
                    WHERE case_id = :case_id AND request_fingerprint = :fingerprint
                    """
                ),
                {"case_id": case_id, "fingerprint": self.request_fingerprint(request)},
            )
        ).first()
        if row is None:
            return None
        return await self.get(case_id, row[0])

    async def persist(
        self,
        case_id: uuid.UUID,
        request: GroundedAnswerRequest,
        result: GroundedAnswerResponse,
    ) -> dict[str, Any]:
        await self._assert_case(case_id)
        associated_documents = await self._associated_document_ids(case_id)
        requested_documents = set(request.document_ids)
        if requested_documents and not requested_documents.issubset(associated_documents):
            raise CaseGroundedScopeError("grounded request references a document outside the Case")

        for evidence in result.evidence:
            if evidence.document_id not in associated_documents:
                raise CaseGroundedScopeError("grounded evidence references a document outside the Case")
            for span in evidence.source_spans:
                if span.locator.document_id != evidence.document_id:
                    raise CaseGroundedScopeError("evidence locator document does not match its evidence")

        existing = await self.find_existing(case_id, request)
        if existing is not None:
            return existing

        result_id = uuid.uuid4()
        request_snapshot = request.model_dump(mode="json")
        result_snapshot = result.model_dump(mode="json")
        evidence_snapshot = result_snapshot.pop("evidence")

        await self._session.execute(
            text(
                """
                INSERT INTO analyst_case_grounded_results
                    (id, case_id, request_fingerprint, query, request_snapshot, result_snapshot)
                VALUES
                    (:id, :case_id, :fingerprint, :query, CAST(:request_snapshot AS jsonb),
                     CAST(:result_snapshot AS jsonb))
                """
            ),
            {
                "id": result_id,
                "case_id": case_id,
                "fingerprint": self.request_fingerprint(request),
                "query": request.query,
                "request_snapshot": json.dumps(request_snapshot),
                "result_snapshot": json.dumps(result_snapshot),
            },
        )

        for evidence in evidence_snapshot:
            spans = evidence.pop("source_spans")
            locator_snapshot = [span["locator"] for span in spans]
            await self._session.execute(
                text(
                    """
                    INSERT INTO analyst_case_grounded_evidence
                        (result_id, evidence_id, document_id, evidence_snapshot, locator_snapshot)
                    VALUES
                        (:result_id, :evidence_id, :document_id, CAST(:evidence_snapshot AS jsonb),
                         CAST(:locator_snapshot AS jsonb))
                    """
                ),
                {
                    "result_id": result_id,
                    "evidence_id": evidence["evidence_id"],
                    "document_id": uuid.UUID(str(evidence["document_id"])),
                    "evidence_snapshot": json.dumps(evidence),
                    "locator_snapshot": json.dumps(locator_snapshot),
                },
            )

        await self._session.execute(
            text("UPDATE analyst_cases SET updated_at = now() WHERE id = :case_id"),
            {"case_id": case_id},
        )
        await self._session.commit()
        return await self.get(case_id, result_id)

    async def list(self, case_id: uuid.UUID) -> list[dict[str, Any]]:
        await self._assert_case(case_id)
        rows = (
            (
                await self._session.execute(
                    text(
                        """
                        SELECT id, case_id, query, created_at
                        FROM analyst_case_grounded_results
                        WHERE case_id = :case_id
                        ORDER BY created_at, id
                        """
                    ),
                    {"case_id": case_id},
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    async def get(self, case_id: uuid.UUID, result_id: uuid.UUID) -> dict[str, Any]:
        row = (
            (
                await self._session.execute(
                    text(
                        """
                        SELECT id, case_id, request_snapshot, result_snapshot, created_at
                        FROM analyst_case_grounded_results
                        WHERE id = :result_id AND case_id = :case_id
                        """
                    ),
                    {"result_id": result_id, "case_id": case_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise CaseGroundedResultNotFoundError(str(result_id))

        evidence_rows = (
            (
                await self._session.execute(
                    text(
                        """
                        SELECT evidence_id, document_id, evidence_snapshot, locator_snapshot
                        FROM analyst_case_grounded_evidence
                        WHERE result_id = :result_id
                        ORDER BY evidence_id
                        """
                    ),
                    {"result_id": result_id},
                )
            )
            .mappings()
            .all()
        )

        evidence: list[dict[str, Any]] = []
        for evidence_row in evidence_rows:
            snapshot = dict(evidence_row["evidence_snapshot"])
            source_spans = []
            for raw_locator in evidence_row["locator_snapshot"]:
                locator = SourceLocator.model_validate(raw_locator)
                if locator.document_id != evidence_row["document_id"]:
                    raise CaseGroundedScopeError("persisted locator document no longer matches evidence")
                quote = await self._resolve_quote(locator)
                source_spans.append({"locator": locator.model_dump(mode="json"), "quote": quote})
            snapshot["source_spans"] = source_spans
            evidence.append(snapshot)

        result_snapshot = dict(row["result_snapshot"])
        result_snapshot["evidence"] = evidence
        result = GroundedAnswerResponse.model_validate(result_snapshot)
        request = GroundedAnswerRequest.model_validate(row["request_snapshot"])
        return {
            "id": row["id"],
            "case_id": row["case_id"],
            "request": request,
            "result": result,
            "created_at": _datetime(row["created_at"]),
        }

    async def _resolve_quote(self, locator: SourceLocator) -> str:
        row = (
            await self._session.execute(
                text(
                    """
                    SELECT text, character_count
                    FROM document_pages
                    WHERE document_id = :document_id AND page_number = :page_number
                    """
                ),
                {"document_id": locator.document_id, "page_number": locator.page_number},
            )
        ).first()
        if row is None or locator.end_char > row.character_count:
            raise CaseGroundedScopeError("persisted source locator no longer resolves")
        return locator.resolve(row.text)

    async def _assert_case(self, case_id: uuid.UUID) -> None:
        row = (
            await self._session.execute(
                text("SELECT 1 FROM analyst_cases WHERE id = :case_id"),
                {"case_id": case_id},
            )
        ).first()
        if row is None:
            raise CaseGroundedResultNotFoundError(str(case_id))

    async def _associated_document_ids(self, case_id: uuid.UUID) -> set[uuid.UUID]:
        rows = (
            await self._session.execute(
                text("SELECT document_id FROM analyst_case_documents WHERE case_id = :case_id"),
                {"case_id": case_id},
            )
        ).all()
        return {row[0] for row in rows}


def _datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("database datetime column returned a non-datetime value")
    return value
