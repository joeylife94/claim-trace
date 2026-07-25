"""Unversioned operational probes.

These live outside the ``/api/v1`` prefix on purpose: orchestrators and load
balancers should not have to track the application's API version.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter, Response

from claimtrace_api.api.deps import PostgresReadyDep
from claimtrace_api.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["operations"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns ok whenever the process is able to serve requests. "
    "Does not touch PostgreSQL or any other dependency.",
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Verifies that every hard dependency is reachable. "
    "Responds with 503 when the service must not receive traffic.",
    responses={HTTPStatus.SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def ready(response: Response, postgres_ready: PostgresReadyDep) -> ReadinessResponse:
    if not postgres_ready:
        # The probe itself logs the cause; here only the outcome matters.
        response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready", dependencies={"postgres": "unavailable"})
    return ReadinessResponse(status="ready", dependencies={"postgres": "ok"})
