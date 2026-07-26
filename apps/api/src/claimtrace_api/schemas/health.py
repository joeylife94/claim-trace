"""Response models for the liveness and readiness probes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DependencyStatus = Literal["ok", "unavailable"]


class HealthResponse(BaseModel):
    """Liveness probe payload. Has no external dependencies by design."""

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    """Readiness probe payload, including the state of every hard dependency."""

    status: Literal["ready", "not_ready"]
    dependencies: dict[str, DependencyStatus] = Field(
        description="Dependency name mapped to its observed status.",
        examples=[{"postgres": "ok"}],
    )
