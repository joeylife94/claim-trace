"""Claim structural parsing.

``base`` defines the technology-neutral contract; each module beside it is one
deterministic implementation. Nothing here imports FastAPI, SQLAlchemy, or
storage types.
"""

from claimtrace_api.parsing.claims.base import (
    ClaimParser,
    ClaimParserError,
    ClaimTextSpan,
    ParsedClaim,
    ParsedClaimSet,
    ParseWarning,
    SourcePage,
    WarningCode,
)

__all__ = [
    "ClaimParser",
    "ClaimParserError",
    "ClaimTextSpan",
    "ParseWarning",
    "ParsedClaim",
    "ParsedClaimSet",
    "SourcePage",
    "WarningCode",
]
