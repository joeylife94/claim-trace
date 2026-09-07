"""D3-01 bounded acceptance over locally acquired real public Korean patent PDFs.

This is a dedicated integration acceptance harness, not a benchmark. It lives
outside the default pytest testpaths so ordinary synthetic closure suites are not
polluted by an environment-dependent skip. The D3 workflow invokes this file
explicitly with locally acquired public PDFs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from claimtrace_api.llm.fake import FakeLLMProvider
from tests.grounded_fixtures import draft_json

pytestmark = pytest.mark.integration


def _resolve_spans(client: TestClient, document_id: str, spans: list[dict[str, Any]]) -> str:
    response = client.get(f"/api/v1/documents/{document_id}/pages?limit=200")
    assert response.status_code == 200, response.text
    pages = {item["page_number"]: item["text"] for item in response.json()["items"]}
    pieces: list[str] = []
    for span in spans:
        assert span["document_id"] == document_id
        text = pages[span["page_number"]]
        assert 0 <= span["start_char"] < span["end_char"] <= len(text)
        pieces.append(text[span["start_char"] : span["end_char"]])
    return "\n".join(pieces)


def _claim_locators(claim: dict[str, Any]) -> list[dict[str, Any]]:
    """Return canonical locators from the existing ClaimResponse `spans` contract."""
    spans = claim.get("spans") or []
    assert spans, f"claim {claim.get('claim_number')} has no persisted source spans"
    locators = [span["locator"] for span in spans]
    assert all(locator for locator in locators)
    return locators


def _write_evidence(out_dir: Path, evidence: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (out_dir / "product-path-evidence.json").write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    (out_dir / "product-path-evidence.sha256").write_text(
        f"{digest}  product-path-evidence.json\n", encoding="utf-8"
    )

    lines = [
        "# D3-01 real-public product-path evidence",
        "",
        f"Overall: **{evidence['overall'].upper()}**",
        "",
        "This is bounded controlled-pilot evidence for the executed corpus only. It is not a",
        "general retrieval/semantic benchmark and makes no legal conclusion.",
        "",
        "## Steps",
    ]
    for name, state in evidence.get("steps", {}).items():
        lines.append(f"- `{name}`: **{state}**")
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- source PDFs were acquired at verification time and are not committed;",
            "- fake embedding/LLM providers make this workflow deterministic and do not establish model quality;",
            "- review API exercise proves append-only reviewer workflow mechanics, not substantive human judgement;",
            "- citation/source resolution proves provenance, not entailment or legal correctness;",
            "- no infringement, validity, novelty, equivalence, inventive-step, or patentability conclusion is produced.",
            "",
        ]
    )
    if evidence.get("failure"):
        lines.extend(["## Failure", "", f"`{evidence['failure']}`", ""])
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def test_real_public_corpus_controlled_pilot(indexing_client: TestClient) -> None:
    corpus_dir_raw = os.getenv("CLAIMTRACE_D3_CORPUS_DIR")
    manifest_raw = os.getenv("CLAIMTRACE_D3_MANIFEST")
    out_raw = os.getenv("CLAIMTRACE_D3_EVIDENCE_DIR")
    assert corpus_dir_raw and manifest_raw and out_raw, (
        "D3 acceptance requires corpus, manifest, and evidence paths from the dedicated workflow"
    )

    corpus_dir = Path(corpus_dir_raw)
    manifest_path = Path(manifest_raw)
    out_dir = Path(out_raw)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = manifest["documents"]
    assert len(documents) == 2, "D3-01 intentionally uses exactly two bounded public documents"

    evidence: dict[str, Any] = {
        "schema_version": 1,
        "destination": "D3 — Real-document Controlled Pilot",
        "milestone": "D3-01",
        "overall": "fail",
        "documents": [],
        "steps": {},
        "limitations": {
            "legal_conclusions": False,
            "general_benchmark_claim": False,
            "ocr_or_scanned_pdf_support": False,
            "private_customer_corpus": False,
        },
    }

    try:
        runtime: list[dict[str, Any]] = []
        for item in documents:
            path = corpus_dir / item["local_filename"]
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            assert digest == item["expected_sha256"], item["publication_number"]

            upload = indexing_client.post(
                "/api/v1/documents",
                files={"file": (item["local_filename"], raw, "application/pdf")},
            )
            assert upload.status_code == 201, upload.text
            document_id = upload.json()["id"]
            assert upload.json()["status"] == "completed", upload.text

            pages_response = indexing_client.get(
                f"/api/v1/documents/{document_id}/pages?limit=200"
            )
            assert pages_response.status_code == 200, pages_response.text
            pages = pages_response.json()["items"]
            assert pages and any(page["text"].strip() for page in pages)
            persisted_text = "\n".join(page["text"] for page in pages)
            assert item["publication_display_number"] in re.sub(r"\s+", "", persisted_text)

            parsed = indexing_client.post(f"/api/v1/documents/{document_id}/claims/parse")
            assert parsed.status_code == 201, parsed.text
            parsed_body = parsed.json()
            assert parsed_body["result"]["status"] == "completed", parsed.text
            assert parsed_body["result"]["claim_count"] > 0, parsed.text
            claims = parsed_body["claims"]
            assert claims
            for claim in claims:
                locators = _claim_locators(claim)
                assert _resolve_spans(indexing_client, document_id, locators) == claim["text"]

            indexed = indexing_client.post(f"/api/v1/documents/{document_id}/claims/index")
            assert indexed.status_code == 201, indexed.text
            assert indexed.json()["status"] == "completed", indexed.text

            evidence["documents"].append(
                {
                    "publication_number": item["publication_number"],
                    "publication_display_number": item["publication_display_number"],
                    "source_page": item["source_page"],
                    "acquisition_url": item["acquisition_url"],
                    "sha256": digest,
                    "document_id": document_id,
                    "page_count": len(pages),
                    "claim_count": len(claims),
                    "ingestion": "pass",
                    "claim_parse": "pass",
                    "claim_index": "pass",
                    "locator_resolution": "pass",
                }
            )
            runtime.append({"id": document_id, "claims": claims, "item": item})

        evidence["steps"]["ingest_parse_index_real_documents"] = "pass"
        evidence["steps"]["persisted_source_locator_resolution"] = "pass"

        target, reference = runtime
        target_claim = target["claims"][0]
        query = re.sub(r"\s+", " ", target_claim["text"]).strip()[:300]
        assert query

        search = indexing_client.post(
            "/api/v1/search/claims",
            json={
                "query": query,
                "document_ids": [target["id"]],
                "mode": "hybrid",
                "top_k": 5,
                "dense_candidate_count": 10,
                "lexical_candidate_count": 10,
            },
        )
        assert search.status_code == 200, search.text
        search_body = search.json()
        assert search_body["results"], search.text
        assert all(result["document_id"] == target["id"] for result in search_body["results"])
        for result in search_body["results"]:
            assert _resolve_spans(indexing_client, target["id"], result["source_spans"]) == result["text"]
        evidence["steps"]["retrieval_with_source_locators"] = "pass"

        indexing_client.app.state.llm_provider = FakeLLMProvider(
            structured_text=draft_json(
                [
                    (
                        "선택된 공개 문서의 저장된 청구항 텍스트를 근거로 확인 가능한 내용을 제시한다.",
                        ("EV-001",),
                    )
                ]
            )
        )
        grounded = indexing_client.post(
            "/api/v1/grounded/answers",
            json={"query": query, "document_ids": [target["id"]], "mode": "hybrid", "top_k": 5},
        )
        assert grounded.status_code == 200, grounded.text
        grounded_body = grounded.json()
        assert grounded_body["insufficient_evidence"] is False, grounded.text
        assert grounded_body["evidence"], grounded.text
        for cited in grounded_body["evidence"]:
            assert cited["document_id"] == target["id"]
            for source_span in cited["source_spans"]:
                locator = source_span["locator"]
                resolved = _resolve_spans(indexing_client, target["id"], [locator])
                assert resolved == source_span["quote"]
        evidence["steps"]["grounded_answer_with_resolvable_citations"] = "pass"

        compared = indexing_client.post(
            "/api/v1/compare/claims",
            json={
                "target_document_id": target["id"],
                "target_claim_number": target_claim["claim_number"],
                "reference_document_id": reference["id"],
                "mode": "hybrid",
                "top_k": 5,
            },
        )
        assert compared.status_code == 200, compared.text
        comparison = compared.json()
        assert comparison["target"]["document_id"] == target["id"]
        assert _resolve_spans(
            indexing_client, target["id"], comparison["target"]["source_spans"]
        ) == comparison["target"]["text"]
        assert comparison["matches"], compared.text
        for match in comparison["matches"]:
            assert match["document_id"] == reference["id"]
            assert _resolve_spans(indexing_client, reference["id"], match["source_spans"]) == match["text"]
        evidence["steps"]["target_reference_comparison_traceability"] = "pass"

        decomposition: dict[str, Any] | None = None
        for claim in target["claims"]:
            response = indexing_client.post(
                f"/api/v1/documents/{target['id']}/claims/{claim['claim_number']}/elements/decompose"
            )
            assert response.status_code in {200, 201}, response.text
            candidate = response.json()
            if candidate["elements"]:
                decomposition = candidate
                break
        assert decomposition is not None, "real target document produced no reviewable decomposition"
        for element in decomposition["elements"]:
            assert element["spans"]
            for span in element["spans"]:
                locator = span["locator"]
                resolved = _resolve_spans(indexing_client, target["id"], [locator])
                assert resolved

        review = indexing_client.post(
            f"/api/v1/element-decomposition-runs/{decomposition['id']}/reviews",
            json={"status": "needs_correction"},
        )
        assert review.status_code == 201, review.text
        snapshot = indexing_client.get(
            f"/api/v1/element-decomposition-runs/{decomposition['id']}/reviews"
        )
        assert snapshot.status_code == 200, snapshot.text
        reviews = snapshot.json()["reviews"]
        assert len(reviews) == 1 and reviews[0]["status"] == "needs_correction"
        evidence["steps"]["decomposition_source_traceability"] = "pass"
        evidence["steps"]["append_only_review_workflow_exercise"] = "pass"
        evidence["steps"]["source_navigation_contract"] = "pass"
        evidence["review_note"] = (
            "The automated needs_correction entry exercises append-only human-review mechanics only; "
            "it is not a substantive reviewer or legal judgement."
        )
        evidence["overall"] = "pass"
    except Exception as exc:
        evidence["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _write_evidence(out_dir, evidence)
