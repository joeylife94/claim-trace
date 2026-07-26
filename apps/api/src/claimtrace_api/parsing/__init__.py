"""Document parsing boundary.

``base`` defines the technology-neutral contract; each module beside it is one
implementation. Nothing here imports FastAPI, SQLAlchemy, or storage types.
"""

from claimtrace_api.parsing.base import DocumentParser, ParsedDocument, ParsedPage, ParserError

__all__ = ["DocumentParser", "ParsedDocument", "ParsedPage", "ParserError"]
