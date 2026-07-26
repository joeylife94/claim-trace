"""Response models for system metadata endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class SystemInfoResponse(BaseModel):
    """Non-sensitive build/deployment information about the running service."""

    name: str
    version: str
    environment: str
