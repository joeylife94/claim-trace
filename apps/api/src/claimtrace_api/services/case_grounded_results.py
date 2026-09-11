"""Persistence and canonical-source rehydration for D5-02 Case grounded results."""

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
from claimtrace_api.schemas.retrieval import MAX_DOCUMENT_FILTER


class CaseGroundedResultNotFoundError(LookupError):
    pass


class CaseGroundedScopeError(ValueError):
    pass


class CaseGroundedResultService:
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def request_fingerprint(request: GroundedAnswerRequest) -> str:
        canonical = json.dumps(
            request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    async def scope_document_ids(
        self, case_id: uuid.UUID, requested: list[uuid.UUID]
    ) -> list[uuid.UUID]:
        await self._assert_case(case_id)
        associated = await self._associated_document_ids(case_id)
        requested_set = set(requested)
        if requested_set and not requested_set.issubset(associated):
            raise CaseGroundedScopeError("grounded request references a document outside the Case")
        selected = requested_set or associated
        if not selected:
            raise CaseGroundedScopeError("Case has no associated documents to search")
        if len(selected) > MAX_DOCUMENT_FILTER:
            raise CaseGroundedScopeError(
                f"Case scope exceeds the {MAX_DOCUMENT_FILTER}-document grounded request limit"
            )
        return sorted(selected, key=str)

    async def find_existing(
        self, case_id: uuid.UUID, request: GroundedAnswerRequest
    ) -> dict[str, Any] | None:
        row = (
            await self._session.execute(
                text(
                    "SELECT id FROM analyst_case_results "
                    "WHERE case_id = :case_id AND request_fingerprint = :fingerprint"
                ),
                {"case_id": case_id, "fingerprint": self.request_fingerprint(request)},
            )
        ).first()
        return None if row is None else await self.get(case_id, row[0])

    async def persist(
        self,
        case_id: uuid.UUID,
        request: GroundedAnswerRequest,
        result: GroundedAnswerResponse,
    ) -> dict[str, Any]:
        associated = await self._associated_document_ids(case_id)
        if not set(request.document_ids).issubset(associated):
            raise CaseGroundedScopeError("grounded request references a document outside the Case")
        for evidence in result.evidence:
            if evidence.document_id not in associated:
                raise CaseGroundedScopeError(
                    "grounded evidence references a document outside the Case"
                )
            locator_mismatches = (
                span.locator.document_id != evidence.document_id for span in evidence.source_spans
            )
            if any(locator_mismatches):
                raise CaseGroundedScopeError(
                    "evidence locator document does not match its evidence"
                )

        existing = await self.find_existing(case_id, request)
        if existing is not None:
            return existing

        result_id = uuid.uuid4()
        request_snapshot = request.model_dump(mode="json")
        result_snapshot = result.model_dump(mode="json")
        evidence_snapshots = result_snapshot.pop("evidence")
        inserted = await self._session.execute(
            text(
                """
                INSERT INTO analyst_case_results
                    (id, case_id, request_fingerprint, query, request_snapshot, result_snapshot)
                VALUES (:id, :case_id, :fingerprint, :query,
                        CAST(:request_snapshot AS jsonb), CAST(:result_snapshot AS jsonb))
                ON CONFLICT (case_id, request_fingerprint) DO NOTHING
                RETURNING id
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
        inserted_id = inserted.scalar_one_or_none()
        if inserted_id is None:
            existing = await self.find_existing(case_id, request)
            if existing is None:
                raise RuntimeError("conflicting Case grounded result could not be reopened")
            return existing

        for evidence in evidence_snapshots:
            spans = evidence.pop("source_spans")
            locators = [span["locator"] for span in spans]
            await self._session.execute(
                text(
                    """
                    INSERT INTO analyst_case_evidence
                        (result_id, evidence_id, document_id, evidence_snapshot, locator_snapshot)
                    VALUES (:result_id, :evidence_id, :document_id,
                            CAST(:evidence_snapshot AS jsonb), CAST(:locator_snapshot AS jsonb))
                    """
                ),
                {
                    "result_id": result_id,
                    "evidence_id": evidence["evidence_id"],
                    "document_id": uuid.UUID(str(evidence["document_id"])),
                    "evidence_snapshot": json.dumps(evidence),
                    "locator_snapshot": json.dumps(locators),
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
                        "SELECT id, case_id, query, created_at FROM analyst_case_results "
                        "WHERE case_id = :case_id ORDER BY created_at, id"
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
                        "SELECT id, case_id, request_snapshot, result_snapshot, created_at "
                        "FROM analyst_case_results "
                        "WHERE id = :result_id AND case_id = :case_id"
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
                        "SELECT document_id, evidence_snapshot, locator_snapshot "
                        "FROM analyst_case_evidence WHERE result_id = :result_id "
                        "ORDER BY evidence_id"
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
            spans: list[dict[str, Any]] = []
            for raw in evidence_row["locator_snapshot"]:
                locator = SourceLocator.model_validate(raw)
                if locator.document_id != evidence_row["document_id"]:
                    raise CaseGroundedScopeError(
                        "persisted locator document no longer matches evidence"
                    )
                spans.append(
                    {
                        "locator": locator.model_dump(mode="json"),
                        "quote": await self._resolve_quote(locator),
                    }
                )
            snapshot["source_spans"] = spans
            evidence.append(snapshot)

        result_snapshot = dict(row["result_snapshot"])
        result_snapshot["evidence"] = evidence
        return {
            "id": row["id"],
            "case_id": row["case_id"],
            "request": GroundedAnswerRequest.model_validate(row["request_snapshot"]),
            "result": GroundedAnswerResponse.model_validate(result_snapshot),
            "created_at": _datetime(row["created_at"]),
        }

    async def _resolve_quote(self, locator: SourceLocator) -> str:
        row = (
            await self._session.execute(
                text(
                    "SELECT text, character_count FROM document_pages "
                    "WHERE document_id = :document_id AND page_number = :page_number"
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
