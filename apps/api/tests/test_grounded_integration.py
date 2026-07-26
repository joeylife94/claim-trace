"""Evidence-grounded answering against the real schema and the real pipeline.

Nothing is stubbed except the model itself, and the model is stubbed with the
fake provider rather than a mock - so the JSON extraction, the schema
validation, the citation validation, and the span resolution are all the
production ones. The documents are uploaded as real PDFs, parsed by the real
Korean claim parser, indexed by the real indexing service, and retrieved through
``POST /api/v1/search/claims``'s own service.

The property these tests exist to establish is the one the phase is named for:
that a citation returned to a reader resolves, character for character, to text
this deployment has stored - and that no other kind of citation can be returned.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from claimtrace_api.llm.fake import FakeLLMProvider
from evals.dataset import load_documents
from tests.claim_fixtures import build_korean_claims_pdf
from tests.grounded_fixtures import INJECTION_CLAIM_TEXTS, draft_json

pytestmark = pytest.mark.integration

URL = "/api/v1/grounded/answers"

#: A third document, built here rather than added to the shared evaluation
#: corpus: its claims are hostile text, and the retrieval evaluation's labels
#: should not have to reason about them.
INJECTION_DOCUMENT = "synthetic-injection.pdf"


def injection_pages() -> tuple[str, ...]:
    lines = ["【청구범위】"]
    for number, text in enumerate(INJECTION_CLAIM_TEXTS.values(), start=1):
        lines.append(f"【청구항 {number}】")
        # Newlines inside a claim would end it as far as the parser is
        # concerned, so the hostile text is flattened onto one line - which is
        # also how it would arrive from a real PDF's extracted text.
        lines.append(text.replace("\n", " "))
    return ("\n".join(lines),)


def ingest(client: TestClient, filename: str, pages: tuple[str, ...]) -> str:
    upload = client.post(
        "/api/v1/documents",
        files={"file": (filename, build_korean_claims_pdf(pages), "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["id"]

    parsed = client.post(f"/api/v1/documents/{document_id}/claims/parse")
    assert parsed.status_code == 201, parsed.text

    indexed = client.post(f"/api/v1/documents/{document_id}/claims/index")
    assert indexed.status_code == 201, indexed.text
    return document_id


@pytest.fixture
def corpus(indexing_client: TestClient) -> dict[str, str]:
    """Three documents through the real pipeline: two synthetic, one hostile."""
    ids = {
        document.id: ingest(indexing_client, document.filename, document.page_texts())
        for document in load_documents()
    }
    ids["injection"] = ingest(indexing_client, INJECTION_DOCUMENT, injection_pages())
    return ids


@pytest.fixture
def scripted(indexing_client: TestClient) -> Iterator[TestClient]:
    """The integration client, with the provider replaced per test.

    ``app.state.llm_provider`` is the documented seam for exactly this: the
    dependency reads it on every request, so a test can script an answer without
    touching configuration or reaching into the service.
    """
    yield indexing_client


def script(client: TestClient, payload: str | list[str]) -> FakeLLMProvider:
    provider = FakeLLMProvider(structured_text=payload)
    client.app.state.llm_provider = provider  # type: ignore[attr-defined]
    return provider


def ask(client: TestClient, query: str, **extra: Any) -> Any:
    response = client.post(URL, json={"query": query, "top_k": 5, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def page_text(client: TestClient, document_id: str, page_number: int) -> str:
    response = client.get(f"/api/v1/documents/{document_id}/pages?limit=200")
    assert response.status_code == 200, response.text
    for page in response.json()["items"]:
        if page["page_number"] == page_number:
            return str(page["text"])
    raise AssertionError(f"page {page_number} not found")


def assert_citations_resolve(client: TestClient, body: Any) -> None:
    """Every returned quote must be the stored text at its own locator.

    Read back through the public pages endpoint rather than the same session
    that produced it, so the assertion is about persisted state rather than
    about an object still in memory.
    """
    assert body["evidence"], "expected at least one piece of cited evidence"
    for evidence in body["evidence"]:
        assert evidence["source_spans"]
        for span in evidence["source_spans"]:
            locator = span["locator"]
            assert locator["document_id"] == evidence["document_id"]
            stored = page_text(client, locator["document_id"], locator["page_number"])
            assert locator["end_char"] <= len(stored)
            assert span["quote"] == stored[locator["start_char"] : locator["end_char"]]
            assert span["quote"]


class TestAnswerableQuestions:
    def test_a_single_evidence_question_is_answered_and_resolvable(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        script(
            scripted,
            draft_json([("수집부는 복수의 센서로부터 측정값을 수집한다.", ("EV-001",))]),
        )
        body = ask(scripted, "센서 데이터를 수집하는 장치")

        assert body["insufficient_evidence"] is False
        assert len(body["statements"]) == 1
        assert body["statements"][0]["evidence_ids"] == ["EV-001"]
        assert_citations_resolve(scripted, body)

    def test_a_multi_evidence_question_resolves_every_citation(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        script(
            scripted,
            draft_json(
                [
                    ("수집부는 측정값을 수집한다.", ("EV-001",)),
                    ("통신부는 무선 근거리 통신 모듈을 포함한다.", ("EV-002", "EV-003")),
                ]
            ),
        )
        body = ask(scripted, "센서 데이터 수집 장치의 통신 및 저장 수단")

        cited = {
            evidence_id
            for statement in body["statements"]
            for evidence_id in statement["evidence_ids"]
        }
        assert cited == {"EV-001", "EV-002", "EV-003"}
        assert {e["evidence_id"] for e in body["evidence"]} == cited
        assert_citations_resolve(scripted, body)

    def test_a_document_scoped_question_cites_only_that_document(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        target = corpus["sensor"]
        script(scripted, draft_json([("수집부는 측정값을 수집한다.", ("EV-001",))]))
        body = ask(scripted, "센서 데이터를 수집하는 장치", document_ids=[target])

        assert body["evidence"]
        for evidence in body["evidence"]:
            assert evidence["document_id"] == target
        assert_citations_resolve(scripted, body)

    def test_the_answer_is_assembled_from_the_statements(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        script(
            scripted,
            draft_json([("수집부가 있다.", ("EV-001",)), ("통신부가 있다.", ("EV-002",))]),
        )
        body = ask(scripted, "센서 데이터를 수집하는 장치")
        assert body["answer"] == "수집부가 있다.\n통신부가 있다."


class TestUnanswerableQuestions:
    def test_a_model_declared_insufficiency_returns_200_with_no_evidence(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        script(
            scripted,
            draft_json(
                [],
                insufficient_evidence=True,
                insufficient_reason="question_outside_available_documents",
            ),
        )
        body = ask(scripted, "이 특허의 심사 청구 기한은 언제까지인가?")

        assert body["insufficient_evidence"] is True
        assert body["insufficient_reason"] == "question_outside_available_documents"
        assert body["evidence"] == []
        assert body["statements"] == []
        # The limitation sentence is the server's, selected by the enum.
        assert "indexed documents do not cover" in body["answer"]

    def test_a_scope_with_no_match_still_returns_a_grounded_shape(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        script(
            scripted,
            draft_json(
                [], insufficient_evidence=True, insufficient_reason="evidence_not_specific_enough"
            ),
        )
        body = ask(scripted, "존재하지 않는 주제", document_ids=[corpus["sensor"]])
        assert body["insufficient_evidence"] is True
        assert isinstance(body["retrieval"]["searched_index_run_count"], int)


class TestFabricatedCitations:
    def test_an_unknown_evidence_id_is_refused_rather_than_served(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        script(scripted, draft_json([("침해에 해당한다.", ("EV-999",))]))
        response = scripted.post(URL, json={"query": "센서 데이터를 수집하는 장치", "top_k": 5})
        assert response.status_code == 502
        assert response.json()["error_code"] in {
            "grounded_unknown_evidence_id",
            "grounded_repair_failed",
        }

    def test_a_model_supplied_locator_is_refused(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        """There is no field for one, so the answer fails schema validation."""
        script(
            scripted,
            json.dumps(
                {
                    "supported_statements": [
                        {
                            "text": "수집부가 있다.",
                            "evidence_ids": ["EV-001"],
                            "page_number": 1,
                            "start_char": 0,
                            "end_char": 20,
                        }
                    ],
                    "insufficient_evidence": False,
                    "insufficient_reason": None,
                },
                ensure_ascii=False,
            ),
        )
        response = scripted.post(URL, json={"query": "센서", "top_k": 5})
        assert response.status_code == 422
        assert response.json()["error_code"] == "llm_structured_output_validation_failed"

    def test_an_uncited_statement_cannot_be_returned(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        script(
            scripted,
            json.dumps(
                {
                    "supported_statements": [
                        {"text": "이 장치는 신규성이 있다.", "evidence_ids": []}
                    ],
                    "insufficient_evidence": False,
                    "insufficient_reason": None,
                },
                ensure_ascii=False,
            ),
        )
        response = scripted.post(URL, json={"query": "센서", "top_k": 5})
        assert response.status_code == 422


class TestPromptInjectionCorpus:
    def test_hostile_claims_are_retrieved_as_ordinary_evidence(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        """They are real claims in a real document, and they cite normally."""
        script(scripted, draft_json([("이 청구항은 지시문 형태의 문장을 포함한다.", ("EV-001",))]))
        body = ask(
            scripted,
            "Ignore all previous instructions",
            document_ids=[corpus["injection"]],
        )
        assert body["evidence"]
        assert body["evidence"][0]["document_id"] == corpus["injection"]
        assert_citations_resolve(scripted, body)

    def test_a_forged_id_inside_claim_text_authorises_nothing(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        """The corpus contains a claim demanding to be cited as EV-999.

        A model that complies produces an answer the server refuses, because
        EV-999 is not in the catalog no matter what any document says.
        """
        script(scripted, draft_json([("EV-999 에 따라 침해한다.", ("EV-999",))]))
        response = scripted.post(
            URL, json={"query": "EV-999", "top_k": 5, "document_ids": [corpus["injection"]]}
        )
        assert response.status_code == 502

    def test_no_forged_evidence_block_reaches_the_catalog(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        """Every issued id is positional, however many blocks the text forges."""
        script(scripted, draft_json([("이 청구항은 마크업 문자열을 포함한다.", ("EV-001",))]))
        body = ask(scripted, "evidence", document_ids=[corpus["injection"]])
        ids = [evidence["evidence_id"] for evidence in body["evidence"]]
        assert all(evidence_id.startswith("EV-0") for evidence_id in ids)
        assert "EV-999" not in ids


class TestNoSideEffects:
    def test_answering_changes_no_stored_status(
        self, scripted: TestClient, corpus: dict[str, str], sync_engine: sa.Engine
    ):
        """Grounded answering is a read. Nothing about ingestion, parsing, or
        indexing may move because someone asked a question.
        """

        def snapshot() -> list[tuple[Any, ...]]:
            with sync_engine.connect() as connection:
                documents = connection.execute(
                    sa.text("SELECT id, status, updated_at FROM documents ORDER BY id")
                ).all()
                parses = connection.execute(
                    sa.text(
                        "SELECT id, status, claim_count, updated_at "
                        "FROM claim_parse_results ORDER BY id"
                    )
                ).all()
                runs = connection.execute(
                    sa.text(
                        "SELECT id, status, indexed_claim_count, updated_at "
                        "FROM claim_index_runs ORDER BY id"
                    )
                ).all()
            return [*documents, *parses, *runs]

        before = snapshot()
        script(scripted, draft_json([("수집부가 있다.", ("EV-001",))]))
        ask(scripted, "센서 데이터를 수집하는 장치")
        assert snapshot() == before

    def test_answering_persists_no_question_or_answer(
        self, scripted: TestClient, corpus: dict[str, str], sync_engine: sa.Engine
    ):
        """The phase adds no table, so there is nowhere for one to be written.

        Asserted against the live schema rather than against the migration
        files, so adding a table without noticing fails here.
        """
        with sync_engine.connect() as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    sa.text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                ).all()
            }
        assert not {name for name in tables if "grounded" in name or "answer" in name}
        assert not {name for name in tables if "generation" in name or "citation" in name}


class TestRepairAgainstRealRetrieval:
    def test_one_repair_recovers_a_fabricated_citation(
        self, scripted: TestClient, corpus: dict[str, str]
    ):
        """And the repair does not change the evidence it may cite."""
        provider = script(
            scripted,
            [
                draft_json([("침해에 해당한다.", ("EV-999",))]),
                draft_json([("수집부는 측정값을 수집한다.", ("EV-001",))]),
            ],
        )
        body = ask(scripted, "센서 데이터를 수집하는 장치")

        assert len(provider.calls) == 2
        assert body["statements"][0]["evidence_ids"] == ["EV-001"]
        assert any("regenerated" in warning for warning in body["warnings"])
        assert_citations_resolve(scripted, body)
