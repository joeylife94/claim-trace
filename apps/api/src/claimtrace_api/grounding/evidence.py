"""The request-local evidence catalog and its opaque identifier.

This is the mechanism the whole phase rests on. The model is never shown a
document id, a claim id, a page number, or a character offset, and it is never
asked to produce one. It is shown a numbered list of claim texts and may answer
with the numbers. The server then resolves those numbers back to the canonical
``(document_id, page_number, start_char, end_char)`` spans it already held.

That inversion is what makes a fabricated citation structurally impossible
rather than merely unlikely. A model that invents ``EV-999`` has not invented a
citation; it has named an entry that does not exist, which is a validation
failure. A model that invents a page number has not invented a citation either,
because no field anywhere in the output contract can carry one.

Three properties of the identifier matter, and each rules out a class of bug:

* **Positional.** ``EV-001`` is the first entry of *this* request's ordered
  evidence, and nothing else. It is not derived from a primary key, so it leaks
  no database state, and it is not derived from the evidence text, so a claim
  containing the string ``EV-002`` cannot influence what ``EV-002`` refers to.
* **Request-local.** The catalog is built per request and discarded with it.
  An id from an earlier request is meaningless here, and resolving one would be
  a cross-request citation - so ids are never looked up anywhere but the catalog
  that was passed to this generation.
* **Exact.** The format is matched strictly. Nothing is trimmed, lowercased, or
  fuzzily matched, because every one of those conveniences is a way for output
  the server did not authorise to become a citation.

The split between :class:`EvidenceCandidate` and :class:`EvidenceEntry` records
who decides what. A candidate is everything retrieval knows about a claim. An
entry is a candidate that the context budget admitted, together with the
identifier this request issued for it. Nothing can construct an identifier
except the builder that also puts the text in the prompt, which is what keeps
"the catalog" and "what the model was shown" the same set.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from claimtrace_api.db.models import ClaimType
from claimtrace_api.schemas.locators import SourceLocator

#: The exact accepted shape of an evidence identifier.
#:
#: ``\A``/``\Z`` rather than ``^``/``$``: in Python ``$`` also matches just
#: before a trailing newline, so ``"EV-001\n"`` would pass an ``^EV-[0-9]{3}$``
#: check. A model that emits a trailing newline inside a JSON string is not
#: producing a valid identifier, and this is not the layer to be forgiving at.
EVIDENCE_ID_PATTERN = re.compile(r"\AEV-[0-9]{3}\Z")

#: Three digits, so the format is fixed-width and sorts lexicographically in the
#: same order it was issued. The context budget caps the real count far below
#: this; the limit exists so ``evidence_id_for_position`` can never silently
#: produce a four-digit id that its own pattern would then reject.
MAX_EVIDENCE_ENTRIES = 999


def evidence_id_for_position(position: int) -> str:
    """Return the identifier for the ``position``-th evidence entry, 1-based.

    Raises:
        ValueError: the position is outside the representable range. A caller
            hitting this has bypassed the context budget, which is a
            programming error rather than a bad request.
    """
    if not 1 <= position <= MAX_EVIDENCE_ENTRIES:
        raise ValueError(f"evidence position {position} is outside 1..{MAX_EVIDENCE_ENTRIES}")
    return f"EV-{position:03d}"


def is_well_formed_evidence_id(value: str) -> bool:
    """Whether ``value`` is exactly a well-formed identifier.

    Deliberately total and deliberately unforgiving: no stripping, no case
    folding, no accepting a bare number. Being well formed is necessary but not
    sufficient - :meth:`EvidenceCatalog.get` still decides whether the id was
    actually issued for this request.
    """
    return EVIDENCE_ID_PATTERN.match(value) is not None


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    """One retrieved claim, before the context budget has ruled on it.

    Carries both the fields a model may see (``claim_number``, ``claim_type``,
    ``depends_on``, ``text``, and the document's display name) and the fields
    only the server ever sees (``spans``, ``document_id``, the per-channel
    ranks). The prompt rendering in :mod:`claimtrace_api.grounding.context`
    reads only the first group, which is what lets the second group travel with
    the evidence safely.

    ``text`` is the original stored claim text, never the normalised search
    form: what the model is asked about must be what the document says.
    """

    document_id: uuid.UUID
    #: The document's original filename. Shown to the model and to the reader;
    #: never the storage key, which is internal and would leak storage layout.
    document_name: str

    claim_number: int
    claim_type: ClaimType
    depends_on: tuple[int, ...]
    text: str

    #: The canonical source coordinates, in span order. Never rendered into a
    #: prompt. This is what a validated citation resolves to.
    spans: tuple[SourceLocator, ...]

    fused_rank: int
    fused_score: float
    dense_rank: int | None = None
    dense_score: float | None = None
    lexical_rank: int | None = None
    lexical_score: float | None = None

    @property
    def crosses_pages(self) -> bool:
        """Whether this claim's source spans more than one page."""
        return len({span.page_number for span in self.spans}) > 1


@dataclass(frozen=True, slots=True)
class EvidenceEntry:
    """A candidate that was admitted to the prompt, and the id issued for it."""

    evidence_id: str
    #: Position within this catalog, 1-based. Kept beside the candidate's own
    #: ``fused_rank`` rather than conflated with it: one is a position in this
    #: prompt, the other is a retrieval judgement, and they stop agreeing the
    #: moment anything but a plain prefix of the results is admitted.
    rank: int
    candidate: EvidenceCandidate


@dataclass(frozen=True, slots=True)
class EvidenceCatalog:
    """Every piece of evidence issued for one generation, and nothing else.

    The catalog is exactly what was put in the prompt - not what retrieval
    returned. When the context budget drops a lower-ranked claim, that claim is
    not in here either, so there is no way for a citation to resolve to text the
    model was never shown. ``omitted_candidate_count`` records the difference so
    the response can report it honestly.

    Nothing here is persisted. The catalog is constructed per request, passed to
    exactly one generation (and to its one repair attempt, which must see the
    same evidence), and dropped.
    """

    entries: tuple[EvidenceEntry, ...]
    #: How many candidates retrieval returned, before the budget was applied.
    retrieved_candidate_count: int
    #: How many of those were dropped to stay inside the context budget.
    omitted_candidate_count: int

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def is_empty(self) -> bool:
        return not self.entries

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        """Every issued id, in catalog order. Safe to show the model and to log."""
        return tuple(entry.evidence_id for entry in self.entries)

    def get(self, evidence_id: str) -> EvidenceEntry | None:
        """Return the entry for ``evidence_id``, or ``None`` if it was not issued.

        A linear scan, because the catalog holds a handful of entries bounded by
        ``GROUNDED_MAX_EVIDENCE_CANDIDATES``. An index would be faster in
        principle and slower in practice at this size, and the comparison being
        one plain ``==`` on a string is worth more here than the constant
        factor: there is exactly one place where an id becomes a citation, and
        it is this line.
        """
        for entry in self.entries:
            if entry.evidence_id == evidence_id:
                return entry
        return None

    def contains(self, evidence_id: str) -> bool:
        return self.get(evidence_id) is not None


def build_catalog(
    candidates: tuple[EvidenceCandidate, ...],
    *,
    retrieved_candidate_count: int,
) -> EvidenceCatalog:
    """Issue identifiers for ``candidates``, in order, and assemble the catalog.

    This is the only place an evidence identifier is created. Positions are
    assigned from the candidate order and nothing else - not from a score, not
    from a database id, and not from anything inside the claim text.
    """
    entries = tuple(
        EvidenceEntry(
            evidence_id=evidence_id_for_position(position),
            rank=position,
            candidate=candidate,
        )
        for position, candidate in enumerate(candidates, start=1)
    )
    return EvidenceCatalog(
        entries=entries,
        retrieved_candidate_count=retrieved_candidate_count,
        omitted_candidate_count=max(0, retrieved_candidate_count - len(entries)),
    )
