"""D5-01 persistent analyst Case API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status

from claimtrace_api.api.deps import SessionDep
from claimtrace_api.schemas.cases import (
    CaseCreateRequest,
    CaseDocumentMutationResponse,
    CaseListResponse,
    CaseResponse,
)
from claimtrace_api.services.cases import (
    AnalystCaseService,
    CaseDocumentAssociationNotFoundError,
    CaseDocumentNotFoundError,
    CaseNotFoundError,
)

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(payload: CaseCreateRequest, session: SessionDep) -> CaseResponse:
    case = await AnalystCaseService(session=session).create(payload.title)
    return CaseResponse.model_validate(case)


@router.get("", response_model=CaseListResponse)
async def list_cases(session: SessionDep) -> CaseListResponse:
    items = await AnalystCaseService(session=session).list()
    return CaseListResponse(items=[CaseResponse.model_validate(item) for item in items])


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(case_id: uuid.UUID, session: SessionDep) -> CaseResponse:
    try:
        case = await AnalystCaseService(session=session).get(case_id)
    except CaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found.",
        ) from exc
    return CaseResponse.model_validate(case)


@router.put(
    "/{case_id}/documents/{document_id}",
    response_model=CaseDocumentMutationResponse,
)
async def associate_document(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    session: SessionDep,
) -> CaseDocumentMutationResponse:
    try:
        case, changed = await AnalystCaseService(session=session).add_document(
            case_id,
            document_id,
        )
    except CaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found.",
        ) from exc
    except CaseDocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from exc
    return CaseDocumentMutationResponse(
        case=CaseResponse.model_validate(case),
        changed=changed,
    )


@router.delete(
    "/{case_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def disassociate_document(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    session: SessionDep,
) -> Response:
    try:
        await AnalystCaseService(session=session).remove_document(case_id, document_id)
    except CaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found.",
        ) from exc
    except CaseDocumentAssociationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document is not associated with this Case.",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
