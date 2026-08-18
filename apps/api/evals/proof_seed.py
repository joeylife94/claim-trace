"""Seed deterministic buyer-facing Proof data through the running ClaimTrace API.

This is deliberately not a direct database fixture. The Proof path exercises the
same public application lifecycle a user does:

    synthetic PDF -> upload -> claim parse -> claim index

The source documents are the repository-owned grounded-evaluation corpus. Only
its ordinary ``collector`` and ``thermal`` documents are promoted into public
Proof; the adversarial prompt-injection document remains an evaluation asset.

Run inside the API container after migrations:

    python -m evals.proof_seed

The command is idempotent. Duplicate PDF digests, already-completed parses, and
already-completed index runs are all normal 200 responses from the real API.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Final

import httpx

from evals.grounded_dataset import GroundedDocument, load_grounded_documents
from tests.claim_fixtures import build_korean_claims_pdf

DEFAULT_BASE_URL: Final = "http://127.0.0.1:8000"
PROOF_DOCUMENT_IDS: Final = ("collector", "thermal")
REQUEST_TIMEOUT_SECONDS: Final = 120.0


@dataclass(frozen=True, slots=True)
class SeededDocument:
    corpus_id: str
    document_id: str
    filename: str
    upload_status: int
    parse_status: int
    index_status: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _proof_documents() -> tuple[GroundedDocument, ...]:
    wanted = set(PROOF_DOCUMENT_IDS)
    documents = tuple(document for document in load_grounded_documents() if document.id in wanted)
    found = {document.id for document in documents}
    _require(found == wanted, f"Proof corpus mismatch: expected {sorted(wanted)}, found {sorted(found)}")
    return documents


def _seed_document(client: httpx.Client, document: GroundedDocument) -> SeededDocument:
    pdf = build_korean_claims_pdf(document.page_texts())
    upload = client.post(
        "/api/v1/documents",
        files={"file": (document.filename, pdf, "application/pdf")},
    )
    _require(
        upload.status_code in (200, 201),
        f"{document.id}: upload failed ({upload.status_code}): {upload.text}",
    )
    document_id = str(upload.json()["id"])

    parsed = client.post(f"/api/v1/documents/{document_id}/claims/parse")
    _require(
        parsed.status_code in (200, 201),
        f"{document.id}: parse failed ({parsed.status_code}): {parsed.text}",
    )

    indexed = client.post(f"/api/v1/documents/{document_id}/claims/index")
    _require(
        indexed.status_code in (200, 201),
        f"{document.id}: index failed ({indexed.status_code}): {indexed.text}",
    )

    return SeededDocument(
        corpus_id=document.id,
        document_id=document_id,
        filename=document.filename,
        upload_status=upload.status_code,
        parse_status=parsed.status_code,
        index_status=indexed.status_code,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed ClaimTrace buyer-facing Proof data")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Base URL of the running ClaimTrace API inside the proof runtime",
    )
    args = parser.parse_args(argv)

    with httpx.Client(
        base_url=args.base_url.rstrip("/"),
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        health = client.get("/health")
        _require(health.status_code == 200, f"API health failed: {health.status_code} {health.text}")

        seeded = [_seed_document(client, document) for document in _proof_documents()]

        listing = client.get("/api/v1/documents?limit=100")
        _require(
            listing.status_code == 200,
            f"Document verification failed ({listing.status_code}): {listing.text}",
        )
        names = {item["original_filename"] for item in listing.json()["items"]}
        missing = [entry.filename for entry in seeded if entry.filename not in names]
        _require(not missing, f"Seeded documents missing from listing: {missing}")

    print(
        json.dumps(
            {
                "proof_seed": "claimtrace-v1",
                "documents": [
                    {
                        "corpus_id": entry.corpus_id,
                        "document_id": entry.document_id,
                        "filename": entry.filename,
                        "upload_status": entry.upload_status,
                        "parse_status": entry.parse_status,
                        "index_status": entry.index_status,
                    }
                    for entry in seeded
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
