"""Seed two parsed/indexed synthetic documents for the V1-03 browser gate.

This uses the real ingestion, claim parsing, and indexing HTTP surfaces through
FastAPI's TestClient. The workflow configures the deterministic fake embedding
provider so the browser gate stays offline and reproducible.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from claimtrace_api.core.config import Settings
from claimtrace_api.main import create_app
from evals.dataset import load_documents
from tests.claim_fixtures import build_korean_claims_pdf


def main() -> None:
    settings = Settings(
        embedding_provider="fake",
        embedding_model="deterministic-hash",
        storage_root=Path("/tmp/claimtrace-v1-03-browser"),
    )
    documents = load_documents()[:2]
    if len(documents) != 2:
        raise RuntimeError("V1-03 browser gate requires exactly two synthetic documents")

    with TestClient(create_app(settings)) as client:
        for document in documents:
            upload = client.post(
                "/api/v1/documents",
                files={
                    "file": (
                        document.filename,
                        build_korean_claims_pdf(document.page_texts()),
                        "application/pdf",
                    )
                },
            )
            if upload.status_code not in (200, 201):
                raise RuntimeError(f"upload failed for {document.filename}: {upload.text}")

            document_id = upload.json()["id"]
            parsed = client.post(f"/api/v1/documents/{document_id}/claims/parse")
            if parsed.status_code not in (200, 201):
                raise RuntimeError(f"parse failed for {document.filename}: {parsed.text}")

            indexed = client.post(f"/api/v1/documents/{document_id}/claims/index")
            if indexed.status_code not in (200, 201):
                raise RuntimeError(f"index failed for {document.filename}: {indexed.text}")

            if indexed.json()["status"] != "completed":
                raise RuntimeError(f"index did not complete for {document.filename}")

    print("V1-03 browser seed complete:")
    for document in documents:
        print(f"- {document.filename}")


if __name__ == "__main__":
    main()
