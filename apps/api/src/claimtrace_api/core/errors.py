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

    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    FILE_TOO_LARGE = "file_too_large"
    EMPTY_FILE = "empty_file"
    MALFORMED_PDF = "malformed_pdf"
    ENCRYPTED_PDF = "encrypted_pdf"
    NO_EXTRACTABLE_TEXT = "no_extractable_text"
    DOCUMENT_NOT_COMPLETED = "document_not_completed"
    DOCUMENT_RETRY_NOT_ALLOWED = "document_retry_not_allowed"
    CLAIM_PARSE_FAILED = "claim_parse_failed"
    CLAIM_PARSE_NOT_FOUND = "claim_parse_not_found"
    CLAIM_NOT_FOUND = "claim_not_found"
    CLAIM_PARSE_NOT_COMPLETED = "claim_parse_not_completed"
    CLAIM_INDEX_FAILED = "claim_index_failed"
    CLAIM_INDEX_NOT_FOUND = "claim_index_not_found"
    EMBEDDING_MODEL_UNAVAILABLE = "embedding_model_unavailable"
    EMBEDDING_DIMENSION_MISMATCH = "embedding_dimension_mismatch"
    LLM_CONFIGURATION_ERROR = "llm_configuration_error"
    LLM_PROVIDER_UNAVAILABLE = "llm_provider_unavailable"
    LLM_CONNECTION_ERROR = "llm_connection_error"
    LLM_REQUEST_TIMEOUT = "llm_request_timeout"
    LLM_MODEL_NOT_FOUND = "llm_model_not_found"
    LLM_AUTHENTICATION_ERROR = "llm_authentication_error"
    LLM_RATE_LIMITED = "llm_rate_limited"
    LLM_CONTEXT_LENGTH_EXCEEDED = "llm_context_length_exceeded"
    LLM_INVALID_REQUEST = "llm_invalid_request"
    LLM_INVALID_PROVIDER_RESPONSE = "llm_invalid_provider_response"
    LLM_MALFORMED_JSON = "llm_malformed_json"
    LLM_STRUCTURED_OUTPUT_VALIDATION_FAILED = "llm_structured_output_validation_failed"
    LLM_GENERATION_CANCELLED = "llm_generation_cancelled"
    LLM_UNSUPPORTED_CAPABILITY = "llm_unsupported_capability"
    LLM_INTERNAL_PROVIDER_ERROR = "llm_internal_provider_error"
    LLM_DIAGNOSTICS_DISABLED = "llm_diagnostics_disabled"
    GROUNDED_CONTEXT_TOO_LARGE = "grounded_context_too_large"
    GROUNDED_OUTPUT_INVALID = "grounded_output_invalid"
    GROUNDED_UNKNOWN_EVIDENCE_ID = "grounded_unknown_evidence_id"
    GROUNDED_CITATION_RESOLUTION_FAILED = "grounded_citation_resolution_failed"
    GROUNDED_GENERATION_UNAVAILABLE = "grounded_generation_unavailable"
    GROUNDED_REPAIR_FAILED = "grounded_repair_failed"
    COMPARISON_INVALID_REQUEST = "comparison_invalid_request"
    ELEMENT_DECOMPOSITION_RUN_NOT_FOUND = "element_decomposition_run_not_found"
    DOCUMENT_NOT_FOUND = "document_not_found"
    STORAGE_FAILURE = "storage_failure"
    INTERNAL_ERROR = "internal_error"


ERROR_STATUS: dict[ErrorCode, HTTPStatus] = {
    ErrorCode.UNSUPPORTED_FILE_TYPE: HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
    ErrorCode.FILE_TOO_LARGE: HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    ErrorCode.EMPTY_FILE: HTTPStatus.BAD_REQUEST,
    ErrorCode.MALFORMED_PDF: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.ENCRYPTED_PDF: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.NO_EXTRACTABLE_TEXT: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.DOCUMENT_NOT_COMPLETED: HTTPStatus.CONFLICT,
    ErrorCode.DOCUMENT_RETRY_NOT_ALLOWED: HTTPStatus.CONFLICT,
    ErrorCode.CLAIM_PARSE_FAILED: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.CLAIM_PARSE_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.CLAIM_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.CLAIM_PARSE_NOT_COMPLETED: HTTPStatus.CONFLICT,
    ErrorCode.CLAIM_INDEX_FAILED: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.CLAIM_INDEX_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.EMBEDDING_MODEL_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.EMBEDDING_DIMENSION_MISMATCH: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.LLM_CONFIGURATION_ERROR: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.LLM_PROVIDER_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.LLM_CONNECTION_ERROR: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.LLM_REQUEST_TIMEOUT: HTTPStatus.GATEWAY_TIMEOUT,
    ErrorCode.LLM_MODEL_NOT_FOUND: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.LLM_AUTHENTICATION_ERROR: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.LLM_RATE_LIMITED: HTTPStatus.TOO_MANY_REQUESTS,
    ErrorCode.LLM_CONTEXT_LENGTH_EXCEEDED: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.LLM_INVALID_REQUEST: HTTPStatus.BAD_REQUEST,
    ErrorCode.LLM_INVALID_PROVIDER_RESPONSE: HTTPStatus.BAD_GATEWAY,
    ErrorCode.LLM_MALFORMED_JSON: HTTPStatus.BAD_GATEWAY,
    ErrorCode.LLM_STRUCTURED_OUTPUT_VALIDATION_FAILED: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.LLM_GENERATION_CANCELLED: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.LLM_UNSUPPORTED_CAPABILITY: HTTPStatus.NOT_IMPLEMENTED,
    ErrorCode.LLM_INTERNAL_PROVIDER_ERROR: HTTPStatus.BAD_GATEWAY,
    ErrorCode.LLM_DIAGNOSTICS_DISABLED: HTTPStatus.NOT_FOUND,
    ErrorCode.GROUNDED_CONTEXT_TOO_LARGE: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.GROUNDED_OUTPUT_INVALID: HTTPStatus.BAD_GATEWAY,
    ErrorCode.GROUNDED_UNKNOWN_EVIDENCE_ID: HTTPStatus.BAD_GATEWAY,
    ErrorCode.GROUNDED_CITATION_RESOLUTION_FAILED: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.GROUNDED_GENERATION_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.GROUNDED_REPAIR_FAILED: HTTPStatus.BAD_GATEWAY,
    ErrorCode.COMPARISON_INVALID_REQUEST: HTTPStatus.BAD_REQUEST,
    ErrorCode.ELEMENT_DECOMPOSITION_RUN_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.DOCUMENT_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.STORAGE_FAILURE: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.INTERNAL_ERROR: HTTPStatus.INTERNAL_SERVER_ERROR,
}


class AppError(Exception):
    """A request that cannot be satisfied, carrying a client-safe explanation."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def status_code(self) -> HTTPStatus:
        return ERROR_STATUS[self.code]

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code.value!r})"
