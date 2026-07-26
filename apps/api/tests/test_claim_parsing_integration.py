"""Claim parsing against the real schema: persistence, transactions, and the API.

Runs the Alembic migrations on a throwaway database first, so revision 0003 is
verified against the ORM and the endpoints rather than assumed. Skipped when no
PostgreSQL is reachable.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from claimtrace_api.core.errors import ErrorCode
from tests.claim_fixtures import KOREAN_CLAIM_SET, NON_PATENT_TEXT, build_korean_claims_pdf
from tests.conftest import unknown_uuid, upload_pdf
from tests.pdf_factory import build_text_pdf

pytestmark = pytest.mark.integration

PARSE_URL = "/api/v1/documents/{document_id}/claims/parse"
CLAIMS_URL = "/api/v1/documents/{document_id}/claims"

#: Claim 3's body is split across the page break so the multi-span path is
#: exercised end to end rather than only in the parser's unit tests.
PAGE_ONE = """【청구범위】
【청구항 1】
하우징과, 상기 하우징의 내부에 배치되는 체결구를 포함하는 위젯 장치.
【청구항 2】
제1항에 있어서, 상기 체결구는 나사산을 갖는 샤프트를 포함하는 위젯 장치.
【청구항 3】
제1항 또는 제2항에 있어서, 상기 하우징은"""

PAGE_TWO = """금속 재질로 이루어지는 위젯 장치.
【청구항 4】
제1항 내지 제3항 중 어느 한 항에 있어서, 동작 온도가 100도인 위젯 장치."""


def ingest(client: TestClient, page_texts: tuple[str, ...], name: str = "patent.pdf") -> str:
    """Upload a synthetic Korean patent PDF and return its document id."""
    response = upload_pdf(client, build_korean_claims_pdf(page_texts), filename=name)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def parse(client: TestClient, document_id: str) -> Any:
    return client.post(PARSE_URL.format(document_id=document_id))


@pytest.fixture
def parsed_document(integration_client: TestClient) -> tuple[str, Any]:
    document_id = ingest(integration_client, (PAGE_ONE, PAGE_TWO))
    response = parse(integration_client, document_id)
    assert response.status_code == 201, response.text
    return document_id, response.json()


# -- persistence ------------------------------------------------------------


def test_parse_persists_result_claims_spans_and_dependencies(
    parsed_document: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    document_id, body = parsed_document

    assert body["result"]["status"] == "completed"
    assert body["result"]["parser_name"] == "korean-rule-based-claims"
    assert body["result"]["parser_version"] == "0.1.0"
    assert body["result"]["claim_count"] == 4

    with sync_engine.connect() as connection:
        result_row = connection.execute(
            sa.text(
                "SELECT status, claim_count, warning_count, started_at, completed_at "
                "FROM claim_parse_results WHERE document_id = :id"
            ),
            {"id": document_id},
        ).one()
        assert result_row.status == "completed"
        assert result_row.claim_count == 4
        assert result_row.started_at is not None
        assert result_row.completed_at is not None

        claims = connection.execute(
            sa.text(
                "SELECT c.claim_number, c.claim_type FROM claims c "
                "JOIN claim_parse_results r ON r.id = c.parse_result_id "
                "WHERE r.document_id = :id ORDER BY c.claim_number"
            ),
            {"id": document_id},
        ).all()
        assert [row.claim_number for row in claims] == [1, 2, 3, 4]
        assert [row.claim_type for row in claims] == [
            "independent",
            "dependent",
            "multiple_dependent",
            "multiple_dependent",
        ]

        spans = connection.scalar(
            sa.text(
                "SELECT count(*) FROM claim_spans s JOIN claims c ON c.id = s.claim_id "
                "JOIN claim_parse_results r ON r.id = c.parse_result_id WHERE r.document_id = :id"
            ),
            {"id": document_id},
        )
        assert spans >= 4


def test_dependency_edges_are_stored_as_a_graph(
    parsed_document: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    document_id, _ = parsed_document

    with sync_engine.connect() as connection:
        edges = connection.execute(
            sa.text(
                "SELECT dep.claim_number AS dependent, ref.claim_number AS referenced "
                "FROM claim_dependencies d "
                "JOIN claims dep ON dep.id = d.dependent_claim_id "
                "JOIN claims ref ON ref.id = d.referenced_claim_id "
                "JOIN claim_parse_results r ON r.id = d.parse_result_id "
                "WHERE r.document_id = :id ORDER BY dependent, referenced"
            ),
            {"id": document_id},
        ).all()

    assert [(row.dependent, row.referenced) for row in edges] == [
        (2, 1),
        (3, 1),
        (3, 2),
        (4, 1),
        (4, 2),
        (4, 3),
    ]


def test_page_crossing_claim_has_ordered_spans_on_both_pages(
    parsed_document: tuple[str, Any],
) -> None:
    _, body = parsed_document

    claim_three = next(claim for claim in body["claims"] if claim["claim_number"] == 3)
    assert claim_three["crosses_pages"] is True
    assert [span["sequence_number"] for span in claim_three["spans"]] == [0, 1]
    assert [span["page_number"] for span in claim_three["spans"]] == [1, 2]


def test_every_span_resolves_to_the_text_used_to_reconstruct_the_claim(
    integration_client: TestClient, parsed_document: tuple[str, Any]
) -> None:
    """The provenance guarantee: claim text is exactly its spans, nothing else."""
    document_id, body = parsed_document

    pages = integration_client.get(f"/api/v1/documents/{document_id}/pages").json()["items"]
    page_text = {page["page_number"]: page["text"] for page in pages}

    for claim in body["claims"]:
        resolved = [
            page_text[span["page_number"]][span["start_char"] : span["end_char"]]
            for span in sorted(claim["spans"], key=lambda span: span["sequence_number"])
        ]
        assert "\n".join(resolved) == claim["text"]
        assert all(part for part in resolved)


def test_span_locator_matches_the_page_endpoint_coordinates(
    integration_client: TestClient, parsed_document: tuple[str, Any]
) -> None:
    document_id, body = parsed_document

    span = body["claims"][0]["spans"][0]
    locator = span["locator"]

    assert locator["document_id"] == document_id
    assert locator["page_number"] == span["page_number"]
    assert locator["start_char"] == span["start_char"]
    assert locator["end_char"] == span["end_char"]

    page = integration_client.get(
        f"/api/v1/documents/{document_id}/pages",
        params={"page_number": locator["page_number"]},
    ).json()["items"][0]
    assert locator["end_char"] <= page["character_count"]


def test_claim_text_matches_the_stored_reconstruction(
    parsed_document: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    document_id, body = parsed_document

    with sync_engine.connect() as connection:
        stored = dict(
            connection.execute(
                sa.text(
                    "SELECT c.claim_number, c.text FROM claims c "
                    "JOIN claim_parse_results r ON r.id = c.parse_result_id "
                    "WHERE r.document_id = :id"
                ),
                {"id": document_id},
            ).all()
        )

    for claim in body["claims"]:
        assert stored[claim["claim_number"]] == claim["text"]


# -- lifecycle and idempotency ---------------------------------------------


def test_repeated_parse_is_idempotent(
    integration_client: TestClient, parsed_document: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    document_id, first = parsed_document

    second = parse(integration_client, document_id)

    assert second.status_code == 200
    assert second.json()["result"]["id"] == first["result"]["id"]

    with sync_engine.connect() as connection:
        results = connection.scalar(
            sa.text("SELECT count(*) FROM claim_parse_results WHERE document_id = :id"),
            {"id": document_id},
        )
        claims = connection.scalar(
            sa.text(
                "SELECT count(*) FROM claims c JOIN claim_parse_results r "
                "ON r.id = c.parse_result_id WHERE r.document_id = :id"
            ),
            {"id": document_id},
        )
    assert results == 1
    assert claims == 4


def test_no_claims_found_is_an_explicit_outcome(integration_client: TestClient) -> None:
    document_id = ingest(integration_client, (NON_PATENT_TEXT,), name="memo.pdf")

    response = parse(integration_client, document_id)

    assert response.status_code == 201
    body = response.json()
    assert body["result"]["status"] == "no_claims_found"
    assert body["result"]["claim_count"] == 0
    assert body["claims"] == []
    # Ingestion is untouched: the PDF was read perfectly well.
    assert (
        integration_client.get(f"/api/v1/documents/{document_id}").json()["status"] == "completed"
    )


def test_document_status_is_untouched_by_claim_parsing(
    integration_client: TestClient, parsed_document: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    document_id, _ = parsed_document

    with sync_engine.connect() as connection:
        status = connection.scalar(
            sa.text("SELECT status FROM documents WHERE id = :id"), {"id": document_id}
        )
    assert status == "completed"


def test_parsing_a_non_completed_document_is_rejected(
    integration_client: TestClient, sync_engine: sa.Engine
) -> None:
    """A failed ingestion has no page text, so there is nothing to parse."""
    from tests.pdf_factory import build_pdf_without_text

    failed = upload_pdf(integration_client, build_pdf_without_text(), filename="scan.pdf")
    assert failed.status_code == 422
    document_id = failed.json()["document"]["id"]

    response = parse(integration_client, document_id)

    assert response.status_code == 409
    assert response.json()["error_code"] == ErrorCode.DOCUMENT_NOT_COMPLETED.value


def test_parsing_a_missing_document_returns_404(integration_client: TestClient) -> None:
    response = parse(integration_client, str(unknown_uuid()))

    assert response.status_code == 404
    assert response.json()["error_code"] == ErrorCode.DOCUMENT_NOT_FOUND.value


def test_english_only_document_still_parses_via_the_fallback(
    integration_client: TestClient,
) -> None:
    """The isolated English fallback works on a plain ASCII PDF."""
    response = upload_pdf(
        integration_client,
        build_text_pdf(("Claim 1", "A widget comprising a housing and a fastener.")),
        filename="english.pdf",
    )
    document_id = response.json()["id"]

    parsed = parse(integration_client, document_id)

    assert parsed.status_code == 201
    assert parsed.json()["result"]["claim_count"] == 1


# -- read endpoints ---------------------------------------------------------


def test_claim_list_endpoint(
    integration_client: TestClient, parsed_document: tuple[str, Any]
) -> None:
    document_id, _ = parsed_document

    response = integration_client.get(CLAIMS_URL.format(document_id=document_id))

    assert response.status_code == 200
    body = response.json()
    assert [claim["claim_number"] for claim in body["claims"]] == [1, 2, 3, 4]
    assert body["claims"][1]["depends_on"] == [1]
    assert body["claims"][3]["depends_on"] == [1, 2, 3]
    assert body["result"]["warnings"] == []


def test_claim_detail_endpoint(
    integration_client: TestClient, parsed_document: tuple[str, Any]
) -> None:
    document_id, _ = parsed_document

    response = integration_client.get(f"{CLAIMS_URL.format(document_id=document_id)}/2")

    assert response.status_code == 200
    body = response.json()
    assert body["claim"]["claim_number"] == 2
    assert body["claim"]["claim_type"] == "dependent"
    assert body["claim"]["depends_on"] == [1]
    assert body["claim"]["spans"]
    assert body["result"]["parser_name"] == "korean-rule-based-claims"


def test_claim_detail_for_a_missing_claim_returns_404(
    integration_client: TestClient, parsed_document: tuple[str, Any]
) -> None:
    document_id, _ = parsed_document

    response = integration_client.get(f"{CLAIMS_URL.format(document_id=document_id)}/99")

    assert response.status_code == 404
    assert response.json()["error_code"] == ErrorCode.CLAIM_NOT_FOUND.value


def test_claim_list_before_parsing_returns_404(integration_client: TestClient) -> None:
    document_id = ingest(integration_client, (KOREAN_CLAIM_SET,), name="unparsed.pdf")

    response = integration_client.get(CLAIMS_URL.format(document_id=document_id))

    assert response.status_code == 404
    assert response.json()["error_code"] == ErrorCode.CLAIM_PARSE_NOT_FOUND.value


def test_claims_for_a_missing_document_return_404(integration_client: TestClient) -> None:
    response = integration_client.get(CLAIMS_URL.format(document_id=unknown_uuid()))

    assert response.status_code == 404


def test_warnings_are_surfaced_in_the_result(integration_client: TestClient) -> None:
    text = "【청구항 1】\n하우징을 포함하는 장치.\n【청구항 2】\n제9항에 있어서, 금속인 장치.\n"
    document_id = ingest(integration_client, (text,), name="warned.pdf")

    body = parse(integration_client, document_id).json()

    assert body["result"]["status"] == "completed"
    assert body["result"]["warning_count"] == 1
    warning = body["result"]["warnings"][0]
    assert warning["code"] == "unresolved_dependency_reference"
    assert warning["claim_number"] == 2
    assert next(c for c in body["claims"] if c["claim_number"] == 2)["claim_type"] == "unknown"


# -- constraints ------------------------------------------------------------


def test_deleting_a_document_cascades_to_the_whole_claim_graph(
    parsed_document: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    document_id, _ = parsed_document

    with sync_engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM documents WHERE id = :id"), {"id": document_id})

    with sync_engine.connect() as connection:
        for table in ("claim_parse_results", "claims", "claim_spans", "claim_dependencies"):
            remaining = connection.scalar(sa.text(f"SELECT count(*) FROM {table}"))
            assert remaining == 0, table


def test_duplicate_claim_number_within_a_result_is_rejected_by_the_database(
    parsed_document: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    document_id, body = parsed_document
    result_id = body["result"]["id"]

    with pytest.raises(sa.exc.IntegrityError), sync_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO claims (id, parse_result_id, claim_number, claim_type, text) "
                "VALUES (gen_random_uuid(), :result_id, 1, 'independent', 'duplicate')"
            ),
            {"result_id": result_id},
        )


def test_a_second_parser_version_may_coexist(
    parsed_document: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    """The uniqueness policy is per parser version, so upgrades stay possible."""
    document_id, _ = parsed_document

    with sync_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO claim_parse_results "
                "(id, document_id, status, parser_name, parser_version) VALUES "
                "(gen_random_uuid(), :id, 'completed', 'korean-rule-based-claims', '0.2.0')"
            ),
            {"id": document_id},
        )

    with sync_engine.connect() as connection:
        count = connection.scalar(
            sa.text("SELECT count(*) FROM claim_parse_results WHERE document_id = :id"),
            {"id": document_id},
        )
    assert count == 2


def test_the_same_parser_version_cannot_be_recorded_twice(
    parsed_document: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    document_id, _ = parsed_document

    with pytest.raises(sa.exc.IntegrityError), sync_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO claim_parse_results "
                "(id, document_id, status, parser_name, parser_version) VALUES "
                "(gen_random_uuid(), :id, 'completed', 'korean-rule-based-claims', '0.1.0')"
            ),
            {"id": document_id},
        )


def test_a_dependency_edge_cannot_cross_parse_results(
    parsed_document: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    """The composite foreign keys keep an edge inside one parse result."""
    document_id, body = parsed_document
    result_id = body["result"]["id"]

    with sync_engine.connect() as connection:
        claim_id = connection.scalar(
            sa.text("SELECT id FROM claims WHERE parse_result_id = :r LIMIT 1"),
            {"r": result_id},
        )

    with pytest.raises(sa.exc.IntegrityError), sync_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO claim_dependencies "
                "(id, parse_result_id, dependent_claim_id, referenced_claim_id) VALUES "
                "(gen_random_uuid(), :fake_result, :claim, :claim2)"
            ),
            {
                "fake_result": str(uuid.uuid4()),
                "claim": str(claim_id),
                "claim2": str(uuid.uuid4()),
            },
        )


def test_self_dependency_is_rejected_by_the_database(
    parsed_document: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    _, body = parsed_document
    result_id = body["result"]["id"]

    with sync_engine.connect() as connection:
        claim_id = connection.scalar(
            sa.text("SELECT id FROM claims WHERE parse_result_id = :r LIMIT 1"),
            {"r": result_id},
        )

    with pytest.raises(sa.exc.IntegrityError), sync_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO claim_dependencies "
                "(id, parse_result_id, dependent_claim_id, referenced_claim_id) VALUES "
                "(gen_random_uuid(), :r, :claim, :claim)"
            ),
            {"r": result_id, "claim": str(claim_id)},
        )
