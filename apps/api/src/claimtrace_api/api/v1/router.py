"""Aggregates every ``/api/v1`` route module."""

from __future__ import annotations

from fastapi import APIRouter

from claimtrace_api.api.v1 import (
    claim_element_reviews,
    claim_elements,
    claims,
    comparison,
    documents,
    grounded,
    llm,
    search,
    system,
)

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(documents.router)
api_router.include_router(claims.router)
api_router.include_router(claim_elements.router)
api_router.include_router(claim_element_reviews.router)
api_router.include_router(search.router)
api_router.include_router(comparison.router)
api_router.include_router(llm.router)
api_router.include_router(grounded.router)
