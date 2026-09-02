"""Temporary issue-53 diagnostic for the known g01 evidence miss.

This file is intentionally branch-local investigation support. It prints only
synthetic/public-safe evaluation identifiers and scores; it must be removed
before the milestone PR is merged.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from claimtrace_api.main import create_app
from evals.grounded_dataset import load_grounded_cases, load_grounded_documents
from evals.grounded_run import _eval_settings, _index_corpus, _install_oracle, _prepare_database


def main() -> int:
    settings = _eval_settings("deterministic")
    _prepare_database(settings)
    app = create_app(settings)

    case = next(item for item in load_grounded_cases() if item.id == "g01-single-storage")

    with TestClient(app) as client:
        corpus = _index_corpus(client, load_grounded_documents())

        search = client.post(
            "/api/v1/search/claims",
            json={"query": case.question, "mode": "hybrid", "top_k": 23},
        )
        search.raise_for_status()
        ranked = [
            {
                "document": item["document_filename"],
                "claim": item["claim_number"],
                "fused_rank": item["fused_rank"],
                "dense_rank": item["dense_rank"],
                "lexical_rank": item["lexical_rank"],
                "fused_score": item["fused_score"],
                "dense_score": item["dense_score"],
                "lexical_score": item["lexical_score"],
            }
            for item in search.json()["results"]
        ]
        print("G01_RANKS=" + json.dumps(ranked, ensure_ascii=False))

        _install_oracle(client, case, corpus)
        answer = client.post(
            "/api/v1/grounded/answers",
            json={"query": case.question, "top_k": 6},
        )
        answer.raise_for_status()
        body = answer.json()
        print(
            "G01_GROUNDED="
            + json.dumps(
                {
                    "evidence": [
                        [item["document_name"], item["claim_number"]] for item in body["evidence"]
                    ],
                    "retrieval": body["retrieval"],
                },
                ensure_ascii=False,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
