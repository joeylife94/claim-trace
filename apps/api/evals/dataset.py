"""Loading and rendering the synthetic evaluation corpus.

The corpus is stored as data rather than as Python so that the claim text and the
relevance labels can be read and reviewed without reading code. This module turns
it into the two things the evaluation and the integration tests need: Korean page
text in the format the claim parser expects, and a lookup from
``(document id, claim number)`` to a relevance judgement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

#: Claims per rendered page. The synthetic PDF writer lays out one line per
#: heading and one per body, and a page holds roughly fifty; splitting well below
#: that keeps a claim from being silently clipped off the bottom.
CLAIMS_PER_PAGE = 7


@dataclass(frozen=True, slots=True)
class SyntheticClaim:
    number: int
    text: str


@dataclass(frozen=True, slots=True)
class SyntheticDocument:
    """One synthetic patent document."""

    id: str
    filename: str
    title: str
    claims: tuple[SyntheticClaim, ...]

    def page_texts(self) -> tuple[str, ...]:
        """Render the claims as Korean page text the claim parser can read.

        The first page opens with the ``【청구범위】`` section heading, exactly as a
        real Korean patent does, so the parser's claims-region detection is
        exercised rather than bypassed.
        """
        pages: list[str] = []
        for start in range(0, len(self.claims), CLAIMS_PER_PAGE):
            chunk = self.claims[start : start + CLAIMS_PER_PAGE]
            lines: list[str] = []
            if start == 0:
                lines.append("【청구범위】")
            for claim in chunk:
                lines.append(f"【청구항 {claim.number}】")
                lines.append(claim.text)
            pages.append("\n".join(lines))
        return tuple(pages)


@dataclass(frozen=True, slots=True)
class EvalQuery:
    """One query and the claims a reader judged relevant to it."""

    id: str
    category: str
    query: str
    #: ``(document id, claim number)`` pairs. Empty for a query that should
    #: return nothing relevant.
    relevant: frozenset[tuple[str, int]]

    @property
    def has_relevant(self) -> bool:
        return bool(self.relevant)


def load_documents() -> tuple[SyntheticDocument, ...]:
    payload = json.loads((DATA_DIR / "corpus.json").read_text(encoding="utf-8"))
    return tuple(
        SyntheticDocument(
            id=entry["id"],
            filename=entry["filename"],
            title=entry["title"],
            claims=tuple(
                SyntheticClaim(number=claim["number"], text=claim["text"])
                for claim in entry["claims"]
            ),
        )
        for entry in payload["documents"]
    )


def load_queries() -> tuple[EvalQuery, ...]:
    payload = json.loads((DATA_DIR / "queries.json").read_text(encoding="utf-8"))
    return tuple(
        EvalQuery(
            id=entry["id"],
            category=entry["category"],
            query=entry["query"],
            relevant=frozenset((document_id, number) for document_id, number in entry["relevant"]),
        )
        for entry in payload["queries"]
    )


def total_claim_count() -> int:
    return sum(len(document.claims) for document in load_documents())
