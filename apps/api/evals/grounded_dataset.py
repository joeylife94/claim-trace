"""Loading the grounded-generation corpus and its labels.

Kept separate from :mod:`evals.dataset` because the two evaluations measure
different things over deliberately different corpora - see the readme block in
``data/grounded_corpus.json`` for why the documents are not shared.

The page rendering is identical to the retrieval corpus's, so the same Korean
claim parser reads both, and a document that parses in one evaluation parses in
the other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

#: Claims per rendered page. Matches evals.dataset: the synthetic PDF writer
#: lays out one line per heading and one per body, and splitting well below a
#: page's capacity keeps a claim from being clipped off the bottom.
CLAIMS_PER_PAGE = 7


@dataclass(frozen=True, slots=True)
class GroundedClaim:
    number: int
    text: str


@dataclass(frozen=True, slots=True)
class GroundedDocument:
    """One synthetic patent document."""

    id: str
    filename: str
    title: str
    claims: tuple[GroundedClaim, ...]

    def page_texts(self) -> tuple[str, ...]:
        """Render the claims as Korean page text the claim parser can read.

        The first page opens with ``【청구범위】`` exactly as a real Korean patent
        does, so the parser's claims-region detection is exercised rather than
        bypassed.
        """
        pages: list[str] = []
        for start in range(0, len(self.claims), CLAIMS_PER_PAGE):
            chunk = self.claims[start : start + CLAIMS_PER_PAGE]
            lines: list[str] = []
            if start == 0:
                lines.append("【청구범위】")
            for claim in chunk:
                lines.append(f"【청구항 {claim.number}】")
                # A newline inside a claim would end it as far as the parser is
                # concerned. The adversarial document's payloads contain them,
                # and flattening is also how the text would arrive from a real
                # PDF's extraction.
                lines.append(claim.text.replace("\n", " "))
            pages.append("\n".join(lines))
        return tuple(pages)


@dataclass(frozen=True, slots=True)
class GroundedCase:
    """One question and what a correct answer to it looks like."""

    id: str
    category: str
    question: str
    #: Corpus document id the question is restricted to, or ``None``.
    scope: str | None
    #: Whether the corpus states the answer at all.
    answerable: bool
    #: ``(document id, claim number)`` pairs a correct answer should cite.
    relevant: frozenset[tuple[str, int]]
    #: Further pairs that would also be reasonable. Counted as correct for
    #: precision but never required for recall, so a defensible extra citation
    #: costs nothing.
    acceptable: frozenset[tuple[str, int]]
    #: Pairs that must never be cited.
    forbidden: frozenset[tuple[str, int]]
    #: Acceptable ``insufficient_reason`` values.
    reasons: frozenset[str]

    @property
    def is_ambiguous(self) -> bool:
        """Whether declining is as defensible as answering.

        True when a case is labelled answerable *and* carries acceptable
        insufficiency reasons - the conflicting-threshold case is the example:
        citing both disagreeing claims and reporting the conflict are both
        honest, and scoring one of them wrong would be a judgement about style
        rather than about grounding.
        """
        return self.answerable and bool(self.reasons)

    @property
    def all_credited(self) -> frozenset[tuple[str, int]]:
        return self.relevant | self.acceptable


def load_grounded_documents() -> tuple[GroundedDocument, ...]:
    payload = json.loads((DATA_DIR / "grounded_corpus.json").read_text(encoding="utf-8"))
    return tuple(
        GroundedDocument(
            id=entry["id"],
            filename=entry["filename"],
            title=entry["title"],
            claims=tuple(
                GroundedClaim(number=claim["number"], text=claim["text"])
                for claim in entry["claims"]
            ),
        )
        for entry in payload["documents"]
    )


def load_grounded_cases() -> tuple[GroundedCase, ...]:
    payload = json.loads((DATA_DIR / "grounded_cases.json").read_text(encoding="utf-8"))
    return tuple(
        GroundedCase(
            id=entry["id"],
            category=entry["category"],
            question=entry["question"],
            scope=entry["scope"],
            answerable=entry["answerable"],
            relevant=_pairs(entry["relevant"]),
            acceptable=_pairs(entry["acceptable"]),
            forbidden=_pairs(entry["forbidden"]),
            reasons=frozenset(entry["reasons"]),
        )
        for entry in payload["cases"]
    )


def total_grounded_claim_count() -> int:
    return sum(len(document.claims) for document in load_grounded_documents())


def _pairs(entries: list[list[object]]) -> frozenset[tuple[str, int]]:
    return frozenset((str(document_id), int(number)) for document_id, number in entries)
