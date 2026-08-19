"""Seed deterministic buyer-facing Proof data through the running ClaimTrace API.

This is deliberately not a direct database fixture. The Proof path exercises the
same public application lifecycle a user does:

    synthetic PDF -> upload -> claim parse -> claim index

The source documents are the repository-owned grounded-evaluation corpus. Only
its ordinary ``collector`` and ``thermal`` documents are promoted into public
Proof; the adversarial prompt-injection document remains an evaluation asset.

Run inside the API container after migrations:

    python -m evals.proof_seed

The command is idempotent at the application level. If a Proof document with the
same repository-owned filename already exists, the seed reuses that document and
re-runs only the idempotent parse/index endpoints. This avoids relying on generated
PDF byte identity, which may vary because PDF writers can emit non-semantic binary
metadata even when the visible text is identical.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Final

import httpx

from evals.grounded_dataset import GroundedDocument, load_grounded_documents
from tests.claim_fixtures import build_korean_claims_pdf

DEFAULT_BASE_URL: Final = "http://127.0.0.1:8000"
PROOF_DOCUMENT_IDS: Final = ("collector", "thermal")
# The first real-embedding Proof run may download multilingual-e5-small before
# indexing. Later runs reuse the model-cache volume and complete much faster.
REQUEST_TIMEOUT_SECONDS: Final = 600.0


@dataclass(frozen=True, slots=True)
class SeededDocument:
    corpus_id: str
    document_id: str
    filename: str
    upload_status: int
    reused_existing: bool
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


def _list_documents(client: httpx.Client) -> list[dict[str, Any]]:
    response = client.get("/api/v1/documents?limit=100")
    _require(
        response.status_code == 200,
        f"Document listing failed ({response.status_code}): {response.text}",
    )
    payload = response.json()
    items = payload.get("items")
    _require(isinstance(items, list), "Document listing did not contain an items list")
    return items


def _existing_document_id(client: httpx.Client, filename: str) -> str | None:
    matches = [
        item
        for item in _list_documents(client)
        if item.get("original_filename") == filename and item.get("status") == "completed"
    ]
    _require(
        len(matches) <= 1,
        f"Proof state is contaminated: found {len(matches)} completed documents named {filename!r}",
    )
    if not matches:
        return None
    return str(matches[0]["id"])


def _seed_document(client: httpx.Client, document: GroundedDocument) -> SeededDocument:
    existing_id = _existing_document_id(client, document.filename)
    reused_existing = existing_id is not None

    if existing_id is None:
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
        upload_status = upload.status_code
    else:
        document_id = existing_id
        upload_status = 200

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
        upload_status=upload_status,
        reused_existing=reused_existing,
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

        listing = _list_documents(client)
        expected_names = {entry.filename for entry in seeded}
        counts = {
            filename: sum(1 for item in listing if item.get("original_filename") == filename)
            for filename in expected_names
        }
        _require(
            all(count == 1 for count in counts.values()),
            f"Proof document uniqueness check failed: {counts}",
        )

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
                        "reused_existing": entry.reused_existing,
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
