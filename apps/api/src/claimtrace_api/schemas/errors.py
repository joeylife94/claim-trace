"""Error envelope returned for unhandled failures."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Client-safe error payload.

    Intentionally free of stack traces, SQL, and connection strings; the full
    context is written to the server log instead.
    """

    detail: str
