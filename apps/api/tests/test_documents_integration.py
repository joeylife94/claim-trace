"""End-to-end ingestion against a real PostgreSQL schema.

These tests run the Alembic migrations on a throwaway database first, so the
migration, the ORM models, and the API are verified against each other. They are
skipped when no database is reachable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from claimtrace_api.core.errors import ErrorCode
from tests.conftest import unknown_uuid, upload_pdf
from tests.pdf_factory import build_malformed_pdf, build_pdf_without_text, build_text_pdf

pytestmark = pytest.mark.integration


def test_upload_persists_document_and_pages(
    integration_client: TestClient, sync_engine: sa.Engine
) -> None:
    pdf = build_text_pdf(("Page one text about a widget.", "Page two text about a fastener."))

    response = upload_pdf(integration_client, pdf, filename="synthetic-patent.pdf")

    assert response.status_code == 201
    document = response.json()
    assert document["status"] == "completed"
    assert document["page_count"] == 2
    assert document["sha256"] == hashlib.sha256(pdf).hexdigest()

    with sync_engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT status, page_count, extracted_character_count, storage_key, "
                "parser_name FROM documents WHERE id = :id"
            ),
            {"id": document["id"]},
        ).one()
        assert row.status == "completed"
        assert row.page_count == 2
        assert row.extracted_character_count > 0
        assert row.storage_key.endswith(".pdf")
        assert row.parser_name == "pymupdf-digital-text"

        pages = connection.execute(
            sa.text(
                "SELECT page_number, character_count, text_sha256 FROM document_pages "
                "WHERE document_id = :id ORDER BY page_number"
            ),
            {"id": document["id"]},
        ).all()
        assert [page.page_number for page in pages] == [1, 2]
        assert all(page.character_count > 0 for page in pages)


def test_original_is_written_to_storage_under_a_hashed_key(
    integration_client: TestClient, storage_root: Path
) -> None:
    pdf = build_text_pdf()
    digest = hashlib.sha256(pdf).hexdigest()

    response = upload_pdf(integration_client, pdf)

    assert response.status_code == 201
    stored = storage_root / digest[:2] / f"{digest}.pdf"
    assert stored.is_file()
    assert stored.read_bytes() == pdf
    # The client's filename appears nowhere on disk.
    assert not list(storage_root.rglob("*patent*"))


def test_duplicate_upload_returns_the_existing_document(
    integration_client: TestClient, sync_engine: sa.Engine
) -> None:
    pdf = build_text_pdf()

    first = upload_pdf(integration_client, pdf, filename="first.pdf")
    second = upload_pdf(integration_client, pdf, filename="second-name.pdf")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    # The record keeps the original upload's filename; nothing is overwritten.
    assert second.json()["original_filename"] == "first.pdf"

    with sync_engine.connect() as connection:
        count = connection.scalar(sa.text("SELECT count(*) FROM documents"))
        pages = connection.scalar(sa.text("SELECT count(*) FROM document_pages"))
    assert count == 1
    assert pages == 2


def test_distinct_files_are_distinct_documents(integration_client: TestClient) -> None:
    first = upload_pdf(
        integration_client, build_text_pdf(("Alpha content describing a first widget.",))
    )
    second = upload_pdf(
        integration_client, build_text_pdf(("Beta content describing a second widget.",))
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_failed_document_is_persisted_for_traceability(
    integration_client: TestClient, sync_engine: sa.Engine
) -> None:
    response = upload_pdf(integration_client, build_pdf_without_text())

    assert response.status_code == 422
    document_id = response.json()["document"]["id"]

    with sync_engine.connect() as connection:
        row = connection.execute(
            sa.text("SELECT status, error_code, page_count FROM documents WHERE id = :id"),
            {"id": document_id},
        ).one()
        pages = connection.scalar(
            sa.text("SELECT count(*) FROM document_pages WHERE document_id = :id"),
            {"id": document_id},
        )

    assert row.status == "failed"
    assert row.error_code == ErrorCode.NO_EXTRACTABLE_TEXT.value
    assert row.page_count is None
    # A failed parse must never leave a partial page set behind.
    assert pages == 0


def test_reuploading_a_failed_document_returns_the_failed_record(
    integration_client: TestClient,
) -> None:
    pdf = build_malformed_pdf()

    first = upload_pdf(integration_client, pdf)
    second = upload_pdf(integration_client, pdf)

    assert first.status_code == 422
    assert second.status_code == 200
    assert second.json()["status"] == "failed"
    assert second.json()["error_code"] == ErrorCode.MALFORMED_PDF.value


def test_document_list_is_newest_first_and_paginated(integration_client: TestClient) -> None:
    for index in range(3):
        upload_pdf(
            integration_client,
            build_text_pdf((f"Document number {index} with enough text to pass.",)),
            filename=f"doc-{index}.pdf",
        )

    listing = integration_client.get("/api/v1/documents").json()
    assert listing["total"] == 3
    assert [item["original_filename"] for item in listing["items"]] == [
        "doc-2.pdf",
        "doc-1.pdf",
        "doc-0.pdf",
    ]

    page = integration_client.get("/api/v1/documents", params={"limit": 1, "offset": 1}).json()
    assert page["limit"] == 1
    assert page["offset"] == 1
    assert page["total"] == 3
    assert [item["original_filename"] for item in page["items"]] == ["doc-1.pdf"]


def test_document_detail(integration_client: TestClient) -> None:
    created = upload_pdf(integration_client, build_text_pdf()).json()

    response = integration_client.get(f"/api/v1/documents/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert "storage_key" not in response.json()


def test_missing_document_returns_404(integration_client: TestClient) -> None:
    response = integration_client.get(f"/api/v1/documents/{unknown_uuid()}")

    assert response.status_code == 404
    assert response.json()["error_code"] == ErrorCode.DOCUMENT_NOT_FOUND.value


def test_pages_are_returned_in_order_with_locators(integration_client: TestClient) -> None:
    pdf = build_text_pdf(("First page body text.", "Second page body text."))
    created = upload_pdf(integration_client, pdf).json()

    response = integration_client.get(f"/api/v1/documents/{created['id']}/pages")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [page["page_number"] for page in body["items"]] == [1, 2]

    first = body["items"][0]
    assert "First page body text." in first["text"]
    # The locator spans exactly the persisted text of its own page.
    assert first["locator"]["document_id"] == created["id"]
    assert first["locator"]["page_number"] == 1
    assert first["locator"]["start_char"] == 0
    assert first["locator"]["end_char"] == len(first["text"])
    assert first["character_count"] == len(first["text"])


def test_locator_offsets_address_the_persisted_text(integration_client: TestClient) -> None:
    """A span taken from stored text resolves to the same characters on re-read."""
    created = upload_pdf(
        integration_client,
        build_text_pdf(("A widget comprising a housing and a fastener disposed therein.",)),
    ).json()

    page = integration_client.get(f"/api/v1/documents/{created['id']}/pages").json()["items"][0]
    start = page["text"].index("widget")
    quoted = page["text"][start : start + len("widget")]

    reread = integration_client.get(
        f"/api/v1/documents/{created['id']}/pages", params={"page_number": 1}
    ).json()["items"][0]

    assert reread["text"][start : start + len("widget")] == quoted
    assert reread["text_sha256"] == page["text_sha256"]


def test_page_filter_returns_a_single_page(integration_client: TestClient) -> None:
    created = upload_pdf(
        integration_client,
        build_text_pdf(("Page one body text for the filter test.", "Page two body text.")),
    ).json()

    response = integration_client.get(
        f"/api/v1/documents/{created['id']}/pages", params={"page_number": 2}
    )

    body = response.json()
    assert body["total"] == 1
    assert [page["page_number"] for page in body["items"]] == [2]


def test_pages_of_a_missing_document_return_404(integration_client: TestClient) -> None:
    response = integration_client.get(f"/api/v1/documents/{unknown_uuid()}/pages")

    assert response.status_code == 404


def test_deleting_a_document_cascades_to_pages(
    integration_client: TestClient, sync_engine: sa.Engine
) -> None:
    """The FK delete policy is intentional, so it is asserted rather than assumed."""
    created = upload_pdf(integration_client, build_text_pdf()).json()

    with sync_engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM documents WHERE id = :id"), {"id": created["id"]})

    with sync_engine.connect() as connection:
        remaining = connection.scalar(
            sa.text("SELECT count(*) FROM document_pages WHERE document_id = :id"),
            {"id": created["id"]},
        )
    assert remaining == 0


def test_duplicate_digest_is_rejected_by_the_database(
    integration_client: TestClient, sync_engine: sa.Engine
) -> None:
    """The duplicate policy rests on a constraint, not only on application code."""
    created = upload_pdf(integration_client, build_text_pdf()).json()

    with pytest.raises(sa.exc.IntegrityError), sync_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO documents (id, original_filename, content_type, size_bytes, "
                "sha256, storage_key, status) VALUES (gen_random_uuid(), 'copy.pdf', "
                "'application/pdf', 10, :sha, 'ab/copy.pdf', 'uploaded')"
            ),
            {"sha": created["sha256"]},
        )
