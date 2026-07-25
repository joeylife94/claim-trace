"""System metadata endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from claimtrace_api.api.deps import SettingsDep
from claimtrace_api.schemas.system import SystemInfoResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get(
    "/info",
    response_model=SystemInfoResponse,
    summary="Application information",
    description="Non-sensitive identification of the running service.",
)
async def system_info(settings: SettingsDep) -> SystemInfoResponse:
    return SystemInfoResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
