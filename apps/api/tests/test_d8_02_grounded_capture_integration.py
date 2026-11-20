"""D8-02: the capture, driven through the real app and the real harness loop.

Real PostgreSQL, real ingestion, parsing, indexing and retrieval (fake embeddings),
the real grounded service and validator. Only the model server is scripted: an
Ollama-shaped ``MockTransport`` sits behind the recording client the harness installs.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from claimtrace_api.core.config import Settings
from claimtrace_api.grounding.draft import GroundedAnswerDraft
from claimtrace_api.grounding.validation import GroundedViolation, OutputLimits, validate_draft
from claimtrace_api.llm.ollama import OllamaProvider
from evals import grounded_run
from evals.grounded_capture import (
    DiagnosticsRecorder,
    RecordingProvider,
    capture_rejections,
    recording_ollama_provider,
)
from evals.grounded_dataset import load_grounded_cases, load_grounded_documents
from tests.grounded_fixtures import draft_json, make_catalog

pytestmark = pytest.mark.integration

GOOD = draft_json([("RAWSENTINEL-GOOD 수집부가 측정값을 수집한다.", ("EV-001",))])
CONTRADICTORY = draft_json(
    [("RAWSENTINEL-CONTRADICTORY", ("EV-001",))],
    insufficient_evidence=False,
    insufficient_reason="conflicting_evidence",
)
UNKNOWN_ID = draft_json([("RAWSENTINEL-UNKNOWN 없는 인용.", ("EV-099",))])


@pytest.fixture
def ollama_settings(integration_settings: Settings) -> Settings:
    return integration_settings.model_copy(
        update={
            "llm_provider": "ollama",
            "llm_ollama_base_url": "http://ollama:11434",
            "llm_ollama_model": "qwen2.5:1.5b",
        }
    )


@pytest.fixture
def served(indexing_client: TestClient) -> Iterator[TestClient]:
    grounded_run._PAGE_CACHE.clear()
    yield indexing_client
    grounded_run._PAGE_CACHE.clear()


def scripted_server(contents: list[str]) -> httpx.MockTransport:
    replies = iter(contents)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:1.5b",
                "message": {"role": "assistant", "content": next(replies)},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 700,
                "eval_count": 90,
                "total_duration": 3_000_000_000,
                "load_duration": 10_000_000,
                "prompt_eval_duration": 1_000_000_000,
                "eval_duration": 2_000_000_000,
            },
        )

    return httpx.MockTransport(handler)


def contradictory_message() -> str:
    """The product's own client-facing message for that violation."""
    from claimtrace_api.grounding.validation import GroundedOutputError

    with pytest.raises(GroundedOutputError) as caught:
        validate_draft(
            GroundedAnswerDraft.model_validate_json(CONTRADICTORY),
            catalog=make_catalog(),
            limits=OutputLimits(
                max_statements=6, max_statement_characters=1000, max_evidence_ids_per_statement=6
            ),
        )
    assert caught.value.violation is GroundedViolation.CONTRADICTORY_INSUFFICIENCY
    return caught.value.message


def test_three_scripted_cases_through_the_real_harness_loop(
    served: TestClient, ollama_settings: Settings
) -> None:
    corpus = grounded_run._index_corpus(served, load_grounded_documents())
    cases = load_grounded_cases()[:3]
    recorder = DiagnosticsRecorder()
    server = scripted_server([GOOD, CONTRADICTORY, CONTRADICTORY, UNKNOWN_ID, GOOD])

    original = served.app.state.llm_provider  # type: ignore[attr-defined]
    with (
        capture_rejections(recorder),
        recording_ollama_provider(served, ollama_settings, recorder, inner_transport=server),
    ):
        assert isinstance(served.app.state.llm_provider, RecordingProvider)  # type: ignore[attr-defined]
        outcomes = grounded_run._run_cases(served, cases, corpus, tier="ollama", recorder=recorder)
    # The application's own provider is back for its own shutdown.
    assert served.app.state.llm_provider is original  # type: ignore[attr-defined]

    assert [outcome.status for outcome in outcomes] == [200, 502, 200]
    blocks = recorder.case_blocks(corpus.corpus_ids)
    ok, failed, repaired = (blocks[case.id] for case in cases)

    assert [a["outcome"] for a in ok["attempts"]] == ["accepted"]
    assert ok["repair_used"] is False
    assert ok["generation"] is not None
    assert ok["generation"]["input_tokens"] == 700
    assert ok["generation"]["output_tokens"] == 90
    assert ok["attempts"][0]["done_reason"] == "stop"
    assert ok["attempts"][0]["prompt_eval_count"] == 700
    assert ok["attempts"][0]["eval_count"] == 90
    assert ok["attempts"][0]["total_ms"] == 3000.0
    assert ok["error_detail"] is None
    assert ok["catalog"], "the evidence catalog is read back from the prompt"
    known = set(corpus.corpus_ids.values())
    assert all(entry["document"] in known for entry in ok["catalog"])

    assert failed["generation"] is None
    assert failed["repair_used"] is True
    assert [a["outcome"] for a in failed["attempts"]] == ["rejected", "rejected"]
    assert [a["violation"] for a in failed["attempts"]] == ["contradictory_insufficiency"] * 2
    assert failed["error_detail"] == contradictory_message()
    assert failed["attempts"][0]["raw_output_sha256"] == failed["attempts"][1]["raw_output_sha256"]

    assert [a["outcome"] for a in repaired["attempts"]] == ["rejected", "accepted"]
    assert repaired["attempts"][0]["violation"] == "unknown_evidence_id"
    assert repaired["attempts"][1]["violation"] is None
    assert repaired["repair_used"] is True
    assert repaired["attempts"][0]["prompt_sha256"] != repaired["attempts"][1]["prompt_sha256"]
    # The repair adds only corrective text to the same prompt, so the catalog is the same.
    assert repaired["catalog"] == blocks[cases[2].id]["catalog"]

    # Every attempt carries a prompt hash, and every case a non-empty catalog.
    for block in blocks.values():
        assert block["catalog"]
        assert all(len(a["prompt_sha256"]) == 64 for a in block["attempts"])

    # Raw text: in the diagnostics document, nowhere in the results payload or report.
    summary = grounded_run.summarise(outcomes)
    provider = {"provider": "ollama", "model": "qwen2.5:1.5b"}
    payload = grounded_run._results_payload(
        "ollama", provider, corpus, summary, outcomes, [], diagnostics=blocks
    )
    report = grounded_run._markdown_report(payload, summary, outcomes, [])
    raw_document = recorder.raw_document("ollama")
    raw_text = json.dumps(raw_document, ensure_ascii=False)
    results_text = json.dumps(payload, ensure_ascii=False)
    for sentinel in ("RAWSENTINEL-GOOD", "RAWSENTINEL-CONTRADICTORY", "RAWSENTINEL-UNKNOWN"):
        assert sentinel in raw_text
        assert sentinel not in results_text
        assert sentinel not in report

    # The prompts are raw text too.
    first_prompt = raw_document["cases"][0]["calls"][0]["user_prompt"]
    assert first_prompt not in results_text
    assert raw_document["format_schema_sha256"]
    assert len(raw_document["system_prompts"]) == 1


def test_the_recording_provider_does_not_change_the_served_answer(
    served: TestClient, ollama_settings: Settings
) -> None:
    corpus = grounded_run._index_corpus(served, load_grounded_documents())
    case = load_grounded_cases()[0]
    request = {"query": case.question, "top_k": grounded_run.TOP_K}

    def run(recorded: bool) -> dict[str, Any]:
        server = scripted_server([GOOD])
        if recorded:
            recorder = DiagnosticsRecorder()
            with recording_ollama_provider(
                served, ollama_settings, recorder, inner_transport=server
            ):
                recorder.begin_case(case.id)
                response = served.post("/api/v1/grounded/answers", json=request)
        else:
            client = httpx.AsyncClient(
                base_url="http://ollama:11434", transport=server, trust_env=False
            )
            plain = OllamaProvider(
                base_url="http://ollama:11434", model="qwen2.5:1.5b", client=client
            )
            served.app.state.llm_provider = plain  # type: ignore[attr-defined]
            response = served.post("/api/v1/grounded/answers", json=request)
            served.portal.call(client.aclose)  # type: ignore[union-attr]
        assert response.status_code == 200, response.text
        body = response.json()
        body["generation"].pop("duration_seconds")
        return body

    assert corpus.claim_count
    assert run(recorded=True) == run(recorded=False)
