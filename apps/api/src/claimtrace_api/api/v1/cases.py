"""Persistent analyst Case API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status

from claimtrace_api.api.deps import (
    GroundedGenerationServiceDep,
    SessionDep,
    SettingsDep,
)
from claimtrace_api.api.v1.grounded import _answer_response
from claimtrace_api.schemas.cases import (
    CaseCreateRequest,
    CaseDocumentMutationResponse,
    CaseGroundedResultListResponse,
    CaseGroundedResultResponse,
    CaseGroundedResultSummary,
    CaseListResponse,
    CaseResponse,
)
from claimtrace_api.schemas.grounded import GroundedAnswerRequest
from claimtrace_api.services.case_grounded_results import (
    CaseGroundedResultNotFoundError,
    CaseGroundedResultService,
    CaseGroundedScopeError,
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


@router.post(
    "/{case_id}/grounded-results",
    response_model=CaseGroundedResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_case_grounded_result(
    case_id: uuid.UUID,
    request: GroundedAnswerRequest,
    session: SessionDep,
    grounded: GroundedGenerationServiceDep,
    settings: SettingsDep,
) -> CaseGroundedResultResponse:
    persistence = CaseGroundedResultService(session=session)
    try:
        scoped_document_ids = await persistence.scope_document_ids(case_id, request.document_ids)
        scoped_request = request.model_copy(update={"document_ids": scoped_document_ids})
        existing = await persistence.find_existing(case_id, scoped_request)
        if existing is not None:
            return CaseGroundedResultResponse.model_validate(existing)
        answer = await grounded.answer(
            query=scoped_request.query,
            mode=scoped_request.mode,
            document_ids=scoped_request.document_ids,
            top_k=min(scoped_request.top_k, settings.search_top_k_max),
        )
        result = _answer_response(answer, rrf_k=settings.rrf_k)
        persisted = await persistence.persist(case_id, scoped_request, result)
    except CaseGroundedResultNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found.",
        ) from exc
    except CaseGroundedScopeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CaseGroundedResultResponse.model_validate(persisted)


@router.get(
    "/{case_id}/grounded-results",
    response_model=CaseGroundedResultListResponse,
)
async def list_case_grounded_results(
    case_id: uuid.UUID,
    session: SessionDep,
) -> CaseGroundedResultListResponse:
    try:
        items = await CaseGroundedResultService(session=session).list(case_id)
    except CaseGroundedResultNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found.",
        ) from exc
    return CaseGroundedResultListResponse(
        items=[CaseGroundedResultSummary.model_validate(item) for item in items]
    )


@router.get(
    "/{case_id}/grounded-results/{result_id}",
    response_model=CaseGroundedResultResponse,
)
async def get_case_grounded_result(
    case_id: uuid.UUID,
    result_id: uuid.UUID,
    session: SessionDep,
) -> CaseGroundedResultResponse:
    try:
        item = await CaseGroundedResultService(session=session).get(case_id, result_id)
    except CaseGroundedResultNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case grounded result not found.",
        ) from exc
    except CaseGroundedScopeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CaseGroundedResultResponse.model_validate(item)
