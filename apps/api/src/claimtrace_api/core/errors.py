"""Application error taxonomy.

Error codes are part of the API contract: clients (and the web UI) branch on
``error_code``, never on the human-readable message. Codes are also persisted on
failed documents and failed parse results, so a stored value must keep its
meaning across releases.
"""

from __future__ import annotations

from enum import StrEnum
from http import HTTPStatus


class ErrorCode(StrEnum):
    """Stable, client-facing reasons an upload can be rejected or fail to parse."""

    # Rejected before anything is stored.
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    FILE_TOO_LARGE = "file_too_large"
    EMPTY_FILE = "empty_file"

    # Stored, then found unusable. These are persisted on the document record.
    MALFORMED_PDF = "malformed_pdf"
    ENCRYPTED_PDF = "encrypted_pdf"
    NO_EXTRACTABLE_TEXT = "no_extractable_text"

    # Claim structural parsing.
    #: The document exists but its ingestion has not completed, so there is no
    #: page text to parse.
    DOCUMENT_NOT_COMPLETED = "document_not_completed"
    #: Parsing ran and could not produce a usable claim structure. Persisted on
    #: the failed parse result.
    CLAIM_PARSE_FAILED = "claim_parse_failed"
    CLAIM_PARSE_NOT_FOUND = "claim_parse_not_found"
    CLAIM_NOT_FOUND = "claim_not_found"

    # Lookup and internal failures.
    DOCUMENT_NOT_FOUND = "document_not_found"
    STORAGE_FAILURE = "storage_failure"
    INTERNAL_ERROR = "internal_error"


#: HTTP status for each code. 415/413 describe the request; 422 means the request
#: was well formed but the PDF itself cannot be ingested.
ERROR_STATUS: dict[ErrorCode, HTTPStatus] = {
    ErrorCode.UNSUPPORTED_FILE_TYPE: HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
    ErrorCode.FILE_TOO_LARGE: HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    ErrorCode.EMPTY_FILE: HTTPStatus.BAD_REQUEST,
    ErrorCode.MALFORMED_PDF: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.ENCRYPTED_PDF: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.NO_EXTRACTABLE_TEXT: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.DOCUMENT_NOT_COMPLETED: HTTPStatus.CONFLICT,
    ErrorCode.CLAIM_PARSE_FAILED: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.CLAIM_PARSE_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.CLAIM_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.DOCUMENT_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.STORAGE_FAILURE: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.INTERNAL_ERROR: HTTPStatus.INTERNAL_SERVER_ERROR,
}


class AppError(Exception):
    """A request that cannot be satisfied, carrying a client-safe explanation.

    ``message`` is shown to the user, so it must never contain a filesystem path,
    a connection string, or document or claim text.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def status_code(self) -> HTTPStatus:
        return ERROR_STATUS[self.code]

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code.value!r})"
