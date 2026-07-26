"""Error envelope returned for unhandled failures."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Client-safe error payload.

    Intentionally free of stack traces, SQL, and connection strings; the full
    context is written to the server log instead.
    """

    detail: str


class ApiErrorResponse(BaseModel):
    """Error payload carrying a stable code.

    Clients branch on ``error_code``; ``detail`` is for the reader and may be
    reworded at any time.
    """

    detail: str
    error_code: str
