"""Upload validation and error mapping, exercised through HTTP without a database."""

from __future__ import annotations

from fastapi.testclient import TestClient

from claimtrace_api.core.errors import ErrorCode
from tests.conftest import StubSession, upload_pdf
from tests.pdf_factory import (
    build_encrypted_pdf,
    build_malformed_pdf,
    build_non_pdf_bytes,
    build_pdf_without_text,
    build_text_pdf,
)


def test_valid_pdf_is_accepted(upload_client: TestClient) -> None:
    response = upload_pdf(upload_client, build_text_pdf())

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["page_count"] == 2
    assert body["extracted_character_count"] > 0
    assert body["parser_name"] == "pymupdf-digital-text"
    assert body["parser_version"]
    assert len(body["sha256"]) == 64
    assert body["error_code"] is None


def test_response_never_exposes_the_storage_path(upload_client: TestClient) -> None:
    response = upload_pdf(upload_client, build_text_pdf())

    body = response.json()
    assert "storage_key" not in body
    assert "/data" not in response.text


def test_wrong_content_type_is_rejected(upload_client: TestClient) -> None:
    response = upload_pdf(upload_client, build_text_pdf(), content_type="text/plain")

    assert response.status_code == 415
    assert response.json()["error_code"] == ErrorCode.UNSUPPORTED_FILE_TYPE.value


def test_wrong_extension_is_rejected(upload_client: TestClient) -> None:
    response = upload_pdf(upload_client, build_text_pdf(), filename="patent.txt")

    assert response.status_code == 415
    assert response.json()["error_code"] == ErrorCode.UNSUPPORTED_FILE_TYPE.value


def test_non_pdf_content_renamed_as_pdf_is_rejected(upload_client: TestClient) -> None:
    """Extension and declared type both look right; only the bytes give it away."""
    response = upload_pdf(upload_client, build_non_pdf_bytes())

    assert response.status_code == 415
    assert response.json()["error_code"] == ErrorCode.UNSUPPORTED_FILE_TYPE.value


def test_empty_file_is_rejected(upload_client: TestClient) -> None:
    response = upload_pdf(upload_client, b"")

    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.EMPTY_FILE.value


def test_oversized_file_is_rejected(upload_client: TestClient) -> None:
    """The limit fixture is 1 MB, so this never buffers a real 20 MB body."""
    oversized = build_text_pdf() + b"%" + b"0" * (1024 * 1024)

    response = upload_pdf(upload_client, oversized)

    assert response.status_code == 413
    assert response.json()["error_code"] == ErrorCode.FILE_TOO_LARGE.value


def test_malformed_pdf_is_rejected_with_a_traceable_record(upload_client: TestClient) -> None:
    response = upload_pdf(upload_client, build_malformed_pdf())

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == ErrorCode.MALFORMED_PDF.value
    # The bytes were stored, so the failure is attached to a document record.
    assert body["document"]["status"] == "failed"
    assert body["document"]["error_code"] == ErrorCode.MALFORMED_PDF.value


def test_encrypted_pdf_is_rejected(upload_client: TestClient) -> None:
    response = upload_pdf(upload_client, build_encrypted_pdf())

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == ErrorCode.ENCRYPTED_PDF.value
    assert body["document"]["status"] == "failed"


def test_pdf_without_extractable_text_is_rejected(upload_client: TestClient) -> None:
    """No OCR: an image-only PDF fails with a specific, actionable code."""
    response = upload_pdf(upload_client, build_pdf_without_text())

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == ErrorCode.NO_EXTRACTABLE_TEXT.value
    assert "text layer" in body["detail"]
    assert body["document"]["status"] == "failed"
    assert body["document"]["page_count"] is None


def test_failed_upload_keeps_no_page_counts(
    upload_client: TestClient, stub_session: StubSession
) -> None:
    upload_pdf(upload_client, build_malformed_pdf())

    documents = [obj for obj in stub_session.added if hasattr(obj, "sha256")]
    assert len(documents) == 1
    assert documents[0].status.value == "failed"
    # No pages were added for a document that never parsed.
    assert not [obj for obj in stub_session.added if hasattr(obj, "page_number")]


def test_missing_file_field_is_a_validation_error(upload_client: TestClient) -> None:
    response = upload_client.post("/api/v1/documents", data={})

    assert response.status_code == 422
