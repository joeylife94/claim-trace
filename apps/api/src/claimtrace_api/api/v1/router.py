"""Aggregates every ``/api/v1`` route module.

New v1 feature routers (ingestion, retrieval, analysis) are registered here; a
future ``v2`` package would expose its own router and be mounted alongside this one.
"""

from __future__ import annotations

from fastapi import APIRouter

from claimtrace_api.api.v1 import system

api_router = APIRouter()
api_router.include_router(system.router)
