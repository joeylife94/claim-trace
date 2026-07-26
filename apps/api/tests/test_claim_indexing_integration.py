"""Claim indexing against the real schema: lifecycle, idempotency, and atomicity.

Runs the Alembic migrations on a throwaway database first, so revision 0004 is
verified against the ORM and the endpoints rather than assumed. Skipped when no
PostgreSQL is reachable.

Every test here uses the deterministic embedding provider. Nothing downloads a
model, and nothing needs one: the properties under test are transactional, not
semantic.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from claimtrace_api.core.errors import ErrorCode
from claimtrace_api.indexing.embeddings.base import EmbeddingError, EmbeddingModelUnavailable
from claimtrace_api.indexing.embeddings.fake import FakeEmbeddingProvider
from tests.claim_fixtures import KOREAN_CLAIM_SET, NON_PATENT_TEXT, build_korean_claims_pdf
from tests.conftest import unknown_uuid, upload_pdf

pytestmark = pytest.mark.integration

PARSE_URL = "/api/v1/documents/{document_id}/claims/parse"
INDEX_URL = "/api/v1/documents/{document_id}/claims/index"


def ingest(client: TestClient, page_texts: tuple[str, ...], name: str = "patent.pdf") -> str:
    response = upload_pdf(client, build_korean_claims_pdf(page_texts), filename=name)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def parsed_document_id(client: TestClient, name: str = "patent.pdf") -> str:
    document_id = ingest(client, (KOREAN_CLAIM_SET,), name=name)
    parsed = client.post(PARSE_URL.format(document_id=document_id))
    assert parsed.status_code == 201, parsed.text
    return document_id


@pytest.fixture
def indexed(indexing_client: TestClient) -> tuple[str, Any]:
    document_id = parsed_document_id(indexing_client)
    response = indexing_client.post(INDEX_URL.format(document_id=document_id))
    assert response.status_code == 201, response.text
    return document_id, response.json()


# -- successful indexing ----------------------------------------------------


def test_indexing_persists_a_completed_run_and_one_record_per_claim(
    indexed: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    document_id, run = indexed

    assert run["status"] == "completed"
    assert run["indexed_claim_count"] == 4

    with sync_engine.connect() as connection:
        records = connection.scalar(
            sa.text("SELECT count(*) FROM claim_search_records WHERE index_run_id = :id"),
            {"id": run["id"]},
        )
        claims = connection.scalar(
            sa.text(
                "SELECT count(*) FROM claims c JOIN claim_parse_results r "
                "ON r.id = c.parse_result_id WHERE r.document_id = :id"
            ),
            {"id": document_id},
        )

    # The count on the run must equal the rows actually written, or the status
    # reports an index that does not exist.
    assert records == claims == run["indexed_claim_count"]


def test_the_profile_is_persisted_on_the_run(indexed: tuple[str, Any]) -> None:
    """Without this an index cannot be told apart from one built by another model."""
    _, run = indexed

    assert run["embedding_provider"] == "fake"
    assert run["embedding_model"] == "deterministic-hash"
    assert run["embedding_model_version"] == "1"
    assert run["embedding_dimension"] == 384
    assert run["vectors_normalized"] is True
    assert run["normalization_version"] == "nfkc-v1"
    assert run["lexical_strategy"] == "postgres-simple-fts-trgm"
    assert run["lexical_strategy_version"] == "v1"
    assert run["started_at"] is not None
    assert run["completed_at"] is not None


def test_stored_embeddings_have_the_migrated_dimension(
    indexed: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    _, run = indexed

    with sync_engine.connect() as connection:
        dimensions = (
            connection.execute(
                sa.text(
                    "SELECT DISTINCT vector_dims(embedding) FROM claim_search_records "
                    "WHERE index_run_id = :id"
                ),
                {"id": run["id"]},
            )
            .scalars()
            .all()
        )

    assert dimensions == [384]


def test_stored_vectors_are_unit_length(indexed: tuple[str, Any], sync_engine: sa.Engine) -> None:
    """Cosine distance is only exact for normalised vectors, and the run says they are."""
    _, run = indexed

    with sync_engine.connect() as connection:
        norms = (
            connection.execute(
                sa.text(
                    "SELECT vector_norm(embedding) FROM claim_search_records "
                    "WHERE index_run_id = :id"
                ),
                {"id": run["id"]},
            )
            .scalars()
            .all()
        )

    assert all(norm == pytest.approx(1.0, abs=1e-5) for norm in norms)


def test_the_search_vector_is_populated_from_the_normalised_text(
    indexed: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    _, run = indexed

    with sync_engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT normalized_text, search_vector::text FROM claim_search_records "
                "WHERE index_run_id = :id ORDER BY claim_number LIMIT 1"
            ),
            {"id": run["id"]},
        ).one()

    assert "청구항 1" in row.normalized_text
    assert "독립항" in row.normalized_text
    assert row.search_vector != ""


# -- preconditions ----------------------------------------------------------


def test_indexing_a_missing_document_returns_404(indexing_client: TestClient) -> None:
    response = indexing_client.post(INDEX_URL.format(document_id=unknown_uuid()))

    assert response.status_code == 404
    assert response.json()["error_code"] == ErrorCode.DOCUMENT_NOT_FOUND.value


def test_indexing_a_document_whose_ingestion_failed_is_rejected(
    indexing_client: TestClient,
) -> None:
    from tests.pdf_factory import build_pdf_without_text

    failed = upload_pdf(indexing_client, build_pdf_without_text(), filename="scan.pdf")
    document_id = failed.json()["document"]["id"]

    response = indexing_client.post(INDEX_URL.format(document_id=document_id))

    assert response.status_code == 409
    assert response.json()["error_code"] == ErrorCode.DOCUMENT_NOT_COMPLETED.value


def test_indexing_an_unparsed_document_is_rejected(indexing_client: TestClient) -> None:
    document_id = ingest(indexing_client, (KOREAN_CLAIM_SET,), name="unparsed.pdf")

    response = indexing_client.post(INDEX_URL.format(document_id=document_id))

    assert response.status_code == 404
    assert response.json()["error_code"] == ErrorCode.CLAIM_PARSE_NOT_FOUND.value


def test_indexing_a_document_with_no_claims_is_rejected(indexing_client: TestClient) -> None:
    """'No claims found' is a successful parse, but there is nothing to index."""
    document_id = ingest(indexing_client, (NON_PATENT_TEXT,), name="memo.pdf")
    parsed = indexing_client.post(PARSE_URL.format(document_id=document_id))
    assert parsed.json()["result"]["status"] == "no_claims_found"

    response = indexing_client.post(INDEX_URL.format(document_id=document_id))

    assert response.status_code == 409
    assert response.json()["error_code"] == ErrorCode.CLAIM_PARSE_NOT_COMPLETED.value


def test_a_provider_of_the_wrong_dimension_is_rejected_before_anything_is_written(
    indexing_client: TestClient, sync_engine: sa.Engine
) -> None:
    """A width the column cannot hold is an operator error, not a failed run."""
    document_id = parsed_document_id(indexing_client, name="mismatch.pdf")
    indexing_client.app.state.embedding_provider = FakeEmbeddingProvider(dimension=128)

    response = indexing_client.post(INDEX_URL.format(document_id=document_id))

    assert response.status_code == 500
    assert response.json()["error_code"] == ErrorCode.EMBEDDING_DIMENSION_MISMATCH.value

    with sync_engine.connect() as connection:
        runs = connection.scalar(sa.text("SELECT count(*) FROM claim_index_runs"))
    assert runs == 0


# -- idempotency and retry --------------------------------------------------


def test_repeated_indexing_is_idempotent(
    indexing_client: TestClient, indexed: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    document_id, first = indexed

    second = indexing_client.post(INDEX_URL.format(document_id=document_id))

    assert second.status_code == 200
    assert second.json()["id"] == first["id"]

    with sync_engine.connect() as connection:
        runs = connection.scalar(sa.text("SELECT count(*) FROM claim_index_runs"))
        records = connection.scalar(sa.text("SELECT count(*) FROM claim_search_records"))
    assert runs == 1
    assert records == 4


def test_a_second_embedding_profile_creates_a_second_run(
    indexing_client: TestClient, indexed: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    """Future model versions must be able to coexist with existing citations."""
    document_id, first = indexed
    indexing_client.app.state.embedding_provider = FakeEmbeddingProvider(
        dimension=384, model_version="2"
    )

    second = indexing_client.post(INDEX_URL.format(document_id=document_id))

    assert second.status_code == 201
    assert second.json()["id"] != first["id"]

    with sync_engine.connect() as connection:
        runs = connection.scalar(sa.text("SELECT count(*) FROM claim_index_runs"))
        records = connection.scalar(sa.text("SELECT count(*) FROM claim_search_records"))
    assert runs == 2
    assert records == 8


def test_the_same_profile_cannot_be_recorded_twice_for_one_parse_result(
    indexed: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    """The idempotency policy is a database constraint, not just a pre-check."""
    _, run = indexed

    with pytest.raises(sa.exc.IntegrityError), sync_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO claim_index_runs (id, claim_parse_result_id, status, profile_key, "
                "embedding_provider, embedding_model, embedding_model_version, "
                "embedding_dimension, vectors_normalized, normalization_version, "
                "lexical_strategy, lexical_strategy_version) "
                "SELECT gen_random_uuid(), claim_parse_result_id, 'completed', profile_key, "
                "embedding_provider, embedding_model, embedding_model_version, "
                "embedding_dimension, vectors_normalized, normalization_version, "
                "lexical_strategy, lexical_strategy_version "
                "FROM claim_index_runs WHERE id = :id"
            ),
            {"id": run["id"]},
        )


def test_a_failed_run_is_traceable_and_retried_in_place(
    indexing_client: TestClient, sync_engine: sa.Engine
) -> None:
    document_id = parsed_document_id(indexing_client, name="retry.pdf")
    indexing_client.app.state.embedding_provider = FakeEmbeddingProvider(
        fail_with=EmbeddingModelUnavailable(
            ErrorCode.EMBEDDING_MODEL_UNAVAILABLE.value, "model missing"
        )
    )

    failure = indexing_client.post(INDEX_URL.format(document_id=document_id))
    assert failure.status_code == 503
    assert failure.json()["error_code"] == ErrorCode.EMBEDDING_MODEL_UNAVAILABLE.value

    # The attempt is recorded, not lost.
    status = indexing_client.get(INDEX_URL.format(document_id=document_id))
    assert status.status_code == 200
    failed_run = status.json()
    assert failed_run["status"] == "failed"
    assert failed_run["error_code"] == ErrorCode.EMBEDDING_MODEL_UNAVAILABLE.value
    assert failed_run["indexed_claim_count"] == 0

    with sync_engine.connect() as connection:
        records = connection.scalar(sa.text("SELECT count(*) FROM claim_search_records"))
    assert records == 0

    # Retrying reuses the same row rather than accumulating attempts.
    indexing_client.app.state.embedding_provider = FakeEmbeddingProvider()
    retried = indexing_client.post(INDEX_URL.format(document_id=document_id))

    assert retried.status_code == 201
    assert retried.json()["id"] == failed_run["id"]
    assert retried.json()["status"] == "completed"
    assert retried.json()["error_code"] is None

    with sync_engine.connect() as connection:
        runs = connection.scalar(sa.text("SELECT count(*) FROM claim_index_runs"))
    assert runs == 1


def test_a_stranded_processing_run_is_retried_in_place(
    indexing_client: TestClient, indexed: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    """A crash mid-index leaves 'processing'; the next request must recover it."""
    document_id, run = indexed
    with sync_engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE claim_index_runs SET status = 'processing', completed_at = NULL "
                "WHERE id = :id"
            ),
            {"id": run["id"]},
        )
        connection.execute(
            sa.text("DELETE FROM claim_search_records WHERE index_run_id = :id"), {"id": run["id"]}
        )

    recovered = indexing_client.post(INDEX_URL.format(document_id=document_id))

    assert recovered.status_code == 201
    assert recovered.json()["id"] == run["id"]
    assert recovered.json()["status"] == "completed"

    with sync_engine.connect() as connection:
        records = connection.scalar(sa.text("SELECT count(*) FROM claim_search_records"))
    assert records == 4


def test_an_unexpected_provider_error_leaves_no_partial_index(
    indexing_client: TestClient, sync_engine: sa.Engine
) -> None:
    document_id = parsed_document_id(indexing_client, name="broken.pdf")
    indexing_client.app.state.embedding_provider = FakeEmbeddingProvider(
        fail_with=EmbeddingError(ErrorCode.CLAIM_INDEX_FAILED.value, "encoder exploded")
    )

    response = indexing_client.post(INDEX_URL.format(document_id=document_id))

    assert response.status_code == 422
    assert response.json()["error_code"] == ErrorCode.CLAIM_INDEX_FAILED.value

    with sync_engine.connect() as connection:
        completed = connection.scalar(
            sa.text("SELECT count(*) FROM claim_index_runs WHERE status = 'completed'")
        )
        records = connection.scalar(sa.text("SELECT count(*) FROM claim_search_records"))
    assert completed == 0
    assert records == 0


# -- the other two lifecycles are untouched ---------------------------------


def test_indexing_does_not_change_document_or_parse_status(
    indexed: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    document_id, _ = indexed

    with sync_engine.connect() as connection:
        document_status = connection.scalar(
            sa.text("SELECT status FROM documents WHERE id = :id"), {"id": document_id}
        )
        parse_status = connection.scalar(
            sa.text("SELECT status FROM claim_parse_results WHERE document_id = :id"),
            {"id": document_id},
        )

    assert document_status == "completed"
    assert parse_status == "completed"


def test_a_failed_index_leaves_the_document_and_parse_result_alone(
    indexing_client: TestClient, sync_engine: sa.Engine
) -> None:
    document_id = parsed_document_id(indexing_client, name="untouched.pdf")
    indexing_client.app.state.embedding_provider = FakeEmbeddingProvider(
        fail_with=EmbeddingModelUnavailable(
            ErrorCode.EMBEDDING_MODEL_UNAVAILABLE.value, "model missing"
        )
    )

    indexing_client.post(INDEX_URL.format(document_id=document_id))

    with sync_engine.connect() as connection:
        document_status = connection.scalar(
            sa.text("SELECT status FROM documents WHERE id = :id"), {"id": document_id}
        )
        parse_status = connection.scalar(
            sa.text("SELECT status FROM claim_parse_results WHERE document_id = :id"),
            {"id": document_id},
        )

    assert document_status == "completed"
    assert parse_status == "completed"


# -- status endpoint --------------------------------------------------------


def test_index_status_before_indexing_returns_404(indexing_client: TestClient) -> None:
    document_id = parsed_document_id(indexing_client, name="nostatus.pdf")

    response = indexing_client.get(INDEX_URL.format(document_id=document_id))

    assert response.status_code == 404
    assert response.json()["error_code"] == ErrorCode.CLAIM_INDEX_NOT_FOUND.value


def test_index_status_reports_the_run(
    indexed: tuple[str, Any], indexing_client: TestClient
) -> None:
    document_id, run = indexed

    response = indexing_client.get(INDEX_URL.format(document_id=document_id))

    assert response.status_code == 200
    assert response.json()["id"] == run["id"]
    assert response.json()["status"] == "completed"
    assert response.json()["indexed_claim_count"] == 4


def test_index_status_for_a_missing_document_returns_404(indexing_client: TestClient) -> None:
    response = indexing_client.get(INDEX_URL.format(document_id=unknown_uuid()))

    assert response.status_code == 404
    assert response.json()["error_code"] == ErrorCode.DOCUMENT_NOT_FOUND.value


# -- cascade behaviour ------------------------------------------------------


def test_deleting_a_document_removes_its_index(
    indexed: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    """A search record must never outlive the claim it projects."""
    document_id, _ = indexed

    with sync_engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM documents WHERE id = :id"), {"id": document_id})

    with sync_engine.connect() as connection:
        for table in ("claim_index_runs", "claim_search_records"):
            assert connection.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0, table


def test_reparsing_does_not_orphan_search_records(
    indexing_client: TestClient, indexed: tuple[str, Any], sync_engine: sa.Engine
) -> None:
    """Deleting the parse result cascades to the index built from it."""
    document_id, run = indexed

    with sync_engine.begin() as connection:
        connection.execute(
            sa.text("DELETE FROM claim_parse_results WHERE document_id = :id"),
            {"id": document_id},
        )

    with sync_engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM claim_index_runs")) == 0
        assert connection.scalar(sa.text("SELECT count(*) FROM claim_search_records")) == 0
