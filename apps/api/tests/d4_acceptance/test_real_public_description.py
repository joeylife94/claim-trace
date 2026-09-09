"""D4-01 bounded real-public description retrieval acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def _pages(client: TestClient, document_id: str) -> dict[int, str]:
    response = client.get(f"/api/v1/documents/{document_id}/pages?limit=200")
    assert response.status_code == 200, response.text
    return {item["page_number"]: item["text"] for item in response.json()["items"]}


def _resolve(pages: dict[int, str], locator: dict[str, Any]) -> str:
    text = pages[locator["page_number"]]
    start = locator["start_char"]
    end = locator["end_char"]
    assert 0 <= start < end <= len(text)
    return text[start:end]


def _verify_navigation_url(result: dict[str, Any]) -> None:
    parsed = urlparse(result["source_url"])
    assert parsed.path == f"/documents/{result['document_id']}"
    query = parse_qs(parsed.query)
    locator = result["source_span"]
    assert query == {
        "page": [str(locator["page_number"])],
        "start": [str(locator["start_char"])],
        "end": [str(locator["end_char"])],
    }


def _write_evidence(out_dir: Path, evidence: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (out_dir / "description-evidence.json").write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    (out_dir / "description-evidence.sha256").write_text(
        f"{digest}  description-evidence.json\n", encoding="utf-8"
    )
    (out_dir / "README.md").write_text(
        "\n".join(
            [
                "# D4-01 description-aware retrieval evidence",
                "",
                f"Overall: **{evidence['overall'].upper()}**",
                "",
                "Bounded evidence over the recorded public Korean patent corpus.",
                "Description retrieval results resolve to persisted page-relative spans.",
                "This is not a legal or general semantic/retrieval benchmark.",
                "",
                "## Limitations",
                "",
                "- text-native public PDFs only; no OCR claim;",
                "- deterministic fake embeddings prove mechanics, not model quality;",
                "- source resolution proves provenance, not entailment or legal correctness;",
                "- no private/customer corpus or production-readiness claim.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_real_public_description_retrieval(indexing_client: TestClient) -> None:
    corpus_raw = os.getenv("CLAIMTRACE_D4_CORPUS_DIR")
    manifest_raw = os.getenv("CLAIMTRACE_D4_MANIFEST")
    evidence_raw = os.getenv("CLAIMTRACE_D4_EVIDENCE_DIR")
    assert corpus_raw and manifest_raw and evidence_raw

    corpus_dir = Path(corpus_raw)
    manifest = json.loads(Path(manifest_raw).read_text(encoding="utf-8"))
    out_dir = Path(evidence_raw)
    item = manifest["documents"][0]
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "destination": "D4 — Description-aware Evidence Retrieval Pilot",
        "milestone": "D4-01",
        "overall": "fail",
        "document": {
            "publication_number": item["publication_number"],
            "source_page": item["source_page"],
            "acquisition_url": item["acquisition_url"],
        },
        "steps": {},
        "limitations": {
            "legal_conclusions": False,
            "general_benchmark_claim": False,
            "ocr_support": False,
            "private_customer_corpus": False,
        },
    }

    try:
        raw = (corpus_dir / item["local_filename"]).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert digest == item["expected_sha256"]
        evidence["document"]["sha256"] = digest

        upload = indexing_client.post(
            "/api/v1/documents",
            files={"file": (item["local_filename"], raw, "application/pdf")},
        )
        assert upload.status_code == 201, upload.text
        document_id = upload.json()["id"]
        assert upload.json()["status"] == "completed", upload.text
        pages = _pages(indexing_client, document_id)
        evidence["steps"]["public_pdf_ingest"] = "pass"

        derived = indexing_client.post(f"/api/v1/documents/{document_id}/descriptions/derive")
        assert derived.status_code == 201, derived.text
        derivation = derived.json()
        assert derivation["status"] == "completed", derived.text
        assert derivation["segments"], derived.text
        for segment in derivation["segments"]:
            assert segment["evidence_kind"] == "description"
            assert segment["source_span"]["document_id"] == document_id
            assert _resolve(pages, segment["source_span"]) == segment["text"]
            _verify_navigation_url({**segment, "document_id": document_id})
        evidence["steps"]["persisted_description_spans"] = "pass"
        evidence["segment_count"] = len(derivation["segments"])

        indexed = indexing_client.post(f"/api/v1/documents/{document_id}/descriptions/index")
        assert indexed.status_code in {200, 201}, indexed.text
        assert indexed.json()["status"] == "completed", indexed.text
        assert indexed.json()["indexed_segment_count"] == len(derivation["segments"])
        evidence["steps"]["description_index"] = "pass"

        seed = max(derivation["segments"], key=lambda segment: len(segment["text"]))
        query = re.sub(r"\s+", " ", seed["text"]).strip()[:160]
        assert query
        search = indexing_client.post(
            "/api/v1/search/descriptions",
            json={
                "query": query,
                "document_ids": [document_id],
                "mode": "hybrid",
                "top_k": 5,
                "dense_candidate_count": 10,
                "lexical_candidate_count": 10,
            },
        )
        assert search.status_code == 200, search.text
        results = search.json()["results"]
        assert results, search.text
        assert any(result["id"] == seed["id"] for result in results)
        for result in results:
            assert result["evidence_kind"] == "description"
            assert result["document_id"] == document_id
            assert _resolve(pages, result["source_span"]) == result["text"]
            _verify_navigation_url(result)
        evidence["steps"]["hybrid_retrieval"] = "pass"
        evidence["steps"]["reviewer_exact_source_navigation"] = "pass"

        parsed = indexing_client.post(f"/api/v1/documents/{document_id}/claims/parse")
        assert parsed.status_code == 201, parsed.text
        assert parsed.json()["result"]["status"] == "completed", parsed.text
        claim_index = indexing_client.post(f"/api/v1/documents/{document_id}/claims/index")
        assert claim_index.status_code == 201, claim_index.text
        claim_query = parsed.json()["claims"][0]["text"][:160]
        claim_search = indexing_client.post(
            "/api/v1/search/claims",
            json={"query": claim_query, "document_ids": [document_id], "mode": "hybrid"},
        )
        assert claim_search.status_code == 200, claim_search.text
        assert claim_search.json()["results"], claim_search.text
        evidence["steps"]["claim_retrieval_regression"] = "pass"
        evidence["overall"] = "pass"
    except Exception as exc:
        evidence["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _write_evidence(out_dir, evidence)
