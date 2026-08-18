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

    # Claim indexing and retrieval (Phase 3A).
    #: A claim parse result exists but did not complete, so there are no claims
    #: to index. Distinct from CLAIM_PARSE_NOT_FOUND, which means none was run.
    CLAIM_PARSE_NOT_COMPLETED = "claim_parse_not_completed"
    #: Indexing ran and could not finish. Persisted on the failed index run.
    CLAIM_INDEX_FAILED = "claim_index_failed"
    CLAIM_INDEX_NOT_FOUND = "claim_index_not_found"
    #: The embedding model could not be loaded - missing optional dependency,
    #: absent from the cache with no network, or out of memory. Retryable.
    EMBEDDING_MODEL_UNAVAILABLE = "embedding_model_unavailable"
    #: The provider returned vectors the migrated column cannot store. A
    #: configuration error, never something a caller can fix by retrying.
    EMBEDDING_DIMENSION_MISMATCH = "embedding_dimension_mismatch"

    # Local LLM provider (Phase 4A-1). One entry per member of
    # claimtrace_api.llm.errors.LLMErrorCode; a test asserts the two stay in
    # step, so a new provider failure cannot reach HTTP without a status.
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
    #: The diagnostics endpoints are turned off for this deployment.
    LLM_DIAGNOSTICS_DISABLED = "llm_diagnostics_disabled"

    # Evidence-grounded generation (Phase 4A-2).
    #
    # Note what is *not* here: insufficient evidence. A question the retrieved
    # claims do not answer is a correct, useful, 200 result - giving it an error
    # code would train a client to render the system's most honest answer as a
    # failure.
    #: The question, or the highest-ranked claim on its own, exceeds the
    #: configured context budget. Dropping lower-ranked evidence cannot help.
    GROUNDED_CONTEXT_TOO_LARGE = "grounded_context_too_large"
    #: The model returned a structurally valid answer that broke a grounding
    #: rule, and repair was not available.
    GROUNDED_OUTPUT_INVALID = "grounded_output_invalid"
    #: The model cited an identifier this request never issued. Kept distinct
    #: from the general invalid-output code because it is the single failure
    #: this phase exists to make impossible to serve, and an operator watching
    #: for it should not have to grep a message.
    GROUNDED_UNKNOWN_EVIDENCE_ID = "grounded_unknown_evidence_id"
    #: A validated citation could not be resolved against stored page text.
    #: A data-integrity failure, never something the caller did.
    GROUNDED_CITATION_RESOLUTION_FAILED = "grounded_citation_resolution_failed"
    #: Grounded answering is configured off, or its provider cannot serve it.
    GROUNDED_GENERATION_UNAVAILABLE = "grounded_generation_unavailable"
    #: The corrective attempt was spent and the answer still broke a rule.
    GROUNDED_REPAIR_FAILED = "grounded_repair_failed"

    # Claim comparison (v1.0 hardening).
    #: The requested comparison itself is contradictory, for example comparing
    #: a document to itself when the product contract requires a target and a
    #: distinct reference document.
    COMPARISON_INVALID_REQUEST = "comparison_invalid_request"

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
    ErrorCode.CLAIM_PARSE_NOT_COMPLETED: HTTPStatus.CONFLICT,
    ErrorCode.CLAIM_INDEX_FAILED: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.CLAIM_INDEX_NOT_FOUND: HTTPStatus.NOT_FOUND,
    # 503, not 500: the model is a dependency that can come back, and the caller
    # is being told to retry rather than that the request was wrong.
    ErrorCode.EMBEDDING_MODEL_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.EMBEDDING_DIMENSION_MISMATCH: HTTPStatus.INTERNAL_SERVER_ERROR,
    # LLM provider. The split that matters here is between "the operator must
    # change something" (5xx: the caller cannot fix a missing model or a wrong
    # base URL) and "the request was wrong" (4xx: too long, or a schema the model
    # cannot satisfy).
    ErrorCode.LLM_CONFIGURATION_ERROR: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.LLM_PROVIDER_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.LLM_CONNECTION_ERROR: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.LLM_REQUEST_TIMEOUT: HTTPStatus.GATEWAY_TIMEOUT,
    # 503 rather than 404: the *model* is missing, not the endpoint, and the
    # remedy is an `ollama pull` on the server rather than a different request.
    ErrorCode.LLM_MODEL_NOT_FOUND: HTTPStatus.SERVICE_UNAVAILABLE,
    # Our credential to the upstream server is wrong: an operator problem, and
    # never the calling client's own authentication.
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
    # Grounded generation. The split mirrors the LLM one: 422 for a request
    # that cannot be served as asked, 502 for a provider that answered with
    # something unusable, 500 for our own data disagreeing with itself.
    ErrorCode.GROUNDED_CONTEXT_TOO_LARGE: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.GROUNDED_OUTPUT_INVALID: HTTPStatus.BAD_GATEWAY,
    ErrorCode.GROUNDED_UNKNOWN_EVIDENCE_ID: HTTPStatus.BAD_GATEWAY,
    ErrorCode.GROUNDED_CITATION_RESOLUTION_FAILED: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.GROUNDED_GENERATION_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.GROUNDED_REPAIR_FAILED: HTTPStatus.BAD_GATEWAY,
    ErrorCode.COMPARISON_INVALID_REQUEST: HTTPStatus.BAD_REQUEST,
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
