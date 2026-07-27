"""The evidence catalog and its identifier.

These tests are about one property: that an evidence identifier means exactly
what the server decided it means, and cannot be influenced by retrieval scores,
database ids, or the content of the claims themselves.
"""

from __future__ import annotations

import pytest

from claimtrace_api.db.models import ClaimType
from claimtrace_api.grounding.evidence import (
    EVIDENCE_ID_PATTERN,
    MAX_EVIDENCE_ENTRIES,
    build_catalog,
    evidence_id_for_position,
    is_well_formed_evidence_id,
)
from tests.grounded_fixtures import (
    CLAIM_ONE,
    DOCUMENT_A,
    DOCUMENT_B,
    INJECTION_CLAIM_TEXTS,
    make_candidate,
    make_catalog,
)


class TestEvidenceIdFormat:
    def test_positions_are_zero_padded_and_one_based(self):
        assert evidence_id_for_position(1) == "EV-001"
        assert evidence_id_for_position(12) == "EV-012"
        assert evidence_id_for_position(999) == "EV-999"

    @pytest.mark.parametrize("position", [0, -1, MAX_EVIDENCE_ENTRIES + 1])
    def test_out_of_range_positions_are_refused(self, position: int):
        # A four-digit id would not match the pattern that validates it, so
        # producing one would create an id the server itself would later reject.
        with pytest.raises(ValueError, match="outside"):
            evidence_id_for_position(position)

    @pytest.mark.parametrize("value", ["EV-001", "EV-000", "EV-999"])
    def test_well_formed_ids_are_accepted(self, value: str):
        assert is_well_formed_evidence_id(value)

    @pytest.mark.parametrize(
        "value",
        [
            "ev-001",  # lowercased
            "EV-1",  # unpadded
            "EV-0001",  # too many digits
            " EV-001",  # leading whitespace
            "EV-001 ",  # trailing whitespace
            "EV-001\n",  # the case a `$` anchor would wrongly accept
            "1",  # a bare claim number
            "EV_001",
            "EV-00A",
            "",
            "EV-001, EV-002",
        ],
    )
    def test_near_misses_are_rejected(self, value: str):
        """No trimming, no case folding, no fuzzy matching, no numeric fallback.

        Each of these is a plausible thing a model emits and a plausible thing a
        forgiving parser would accept. Accepting any of them would let output the
        server never issued become a citation.
        """
        assert not is_well_formed_evidence_id(value)

    def test_pattern_is_anchored_against_embedded_matches(self):
        assert EVIDENCE_ID_PATTERN.match("see EV-001 above") is None


class TestCatalogConstruction:
    def test_ids_are_assigned_positionally_in_retrieval_order(self):
        catalog = build_catalog(
            (
                make_candidate(claim_number=7, fused_rank=1),
                make_candidate(claim_number=2, fused_rank=2),
                make_candidate(claim_number=4, fused_rank=3),
            ),
            retrieved_candidate_count=3,
        )

        assert catalog.evidence_ids == ("EV-001", "EV-002", "EV-003")
        # The id follows position, not the claim number and not the score.
        assert [entry.candidate.claim_number for entry in catalog.entries] == [7, 2, 4]
        assert [entry.rank for entry in catalog.entries] == [1, 2, 3]

    def test_assignment_is_deterministic_for_the_same_input(self):
        first = make_catalog(4)
        second = make_catalog(4)
        assert first.evidence_ids == second.evidence_ids
        assert [entry.candidate.text for entry in first.entries] == [
            entry.candidate.text for entry in second.entries
        ]

    def test_ids_are_unique_within_one_catalog(self):
        catalog = make_catalog(6)
        assert len(set(catalog.evidence_ids)) == len(catalog.evidence_ids)

    def test_ids_are_not_derived_from_database_identity(self):
        """Two catalogs over completely different rows issue the same ids.

        Which is the point: the identifier carries no database state, so it
        cannot leak one and cannot be guessed from one.
        """
        first = build_catalog(
            (make_candidate(document_id=DOCUMENT_A),), retrieved_candidate_count=1
        )
        second = build_catalog(
            (make_candidate(document_id=DOCUMENT_B, claim_number=17),),
            retrieved_candidate_count=1,
        )
        assert first.evidence_ids == second.evidence_ids == ("EV-001",)

    def test_claim_text_naming_an_id_does_not_affect_assignment(self):
        """A claim demanding to be cited as EV-999 is still EV-001.

        Assignment reads the ordering and nothing else. The text is data.
        """
        catalog = build_catalog(
            (
                make_candidate(text=INJECTION_CLAIM_TEXTS["forge_unknown_id"]),
                make_candidate(text=CLAIM_ONE, claim_number=2),
            ),
            retrieved_candidate_count=2,
        )
        assert catalog.evidence_ids == ("EV-001", "EV-002")
        assert not catalog.contains("EV-999")

    def test_omitted_count_is_the_difference_from_what_retrieval_returned(self):
        catalog = build_catalog(
            (make_candidate(), make_candidate(claim_number=2)), retrieved_candidate_count=9
        )
        assert len(catalog) == 2
        assert catalog.retrieved_candidate_count == 9
        assert catalog.omitted_candidate_count == 7

    def test_an_empty_catalog_is_empty_rather_than_absent(self):
        catalog = build_catalog((), retrieved_candidate_count=0)
        assert catalog.is_empty
        assert catalog.evidence_ids == ()
        assert catalog.get("EV-001") is None


class TestCatalogLookup:
    def test_issued_ids_resolve_to_their_entry(self):
        catalog = make_catalog(3)
        entry = catalog.get("EV-002")
        assert entry is not None
        assert entry.candidate.claim_number == 2

    @pytest.mark.parametrize("value", ["EV-999", "ev-001", "EV-001 ", "1", "EV-004"])
    def test_anything_not_issued_resolves_to_nothing(self, value: str):
        assert make_catalog(3).get(value) is None

    def test_an_id_from_another_request_does_not_resolve(self):
        """There is no cross-request lookup, because there is no store to look in.

        ``EV-001`` is a legal id in both catalogs and refers to a different claim
        in each; resolution happens only against the catalog handed to this
        generation, so the second catalog's entry is the one that is returned.
        """
        first = build_catalog(
            (make_candidate(claim_number=1, document_id=DOCUMENT_A),),
            retrieved_candidate_count=1,
        )
        second = build_catalog(
            (make_candidate(claim_number=42, document_id=DOCUMENT_B),),
            retrieved_candidate_count=1,
        )

        entry = second.get("EV-001")
        assert entry is not None
        assert entry.candidate.claim_number == 42
        assert entry.candidate.document_id == DOCUMENT_B
        assert first.get("EV-001") is not entry


class TestEvidenceProvenance:
    def test_multi_page_spans_are_preserved_in_order(self):
        candidate = make_candidate(pages=((3, 900, 1000), (4, 0, 120)))
        assert [span.page_number for span in candidate.spans] == [3, 4]
        assert candidate.crosses_pages

    def test_a_single_page_claim_does_not_claim_to_cross_pages(self):
        assert not make_candidate(pages=((2, 10, 90),)).crosses_pages

    def test_retrieval_metadata_survives_into_the_catalog(self):
        catalog = build_catalog(
            (make_candidate(fused_rank=1, fused_score=0.031, dense_rank=None, dense_score=None),),
            retrieved_candidate_count=1,
        )
        entry = catalog.entries[0]
        # A channel that did not retrieve the claim stays null rather than zero.
        assert entry.candidate.dense_rank is None
        assert entry.candidate.dense_score is None
        assert entry.candidate.lexical_rank == 2
        assert entry.candidate.fused_score == pytest.approx(0.031)

    def test_the_original_claim_text_is_carried_unmodified(self):
        candidate = make_candidate(text=CLAIM_ONE)
        assert candidate.text == CLAIM_ONE

    def test_entries_carry_the_canonical_document_id_and_type(self):
        candidate = make_candidate(
            document_id=DOCUMENT_B, claim_type=ClaimType.DEPENDENT, depends_on=(1,)
        )
        assert candidate.document_id == DOCUMENT_B
        assert candidate.claim_type is ClaimType.DEPENDENT
        assert candidate.depends_on == (1,)
        assert all(span.document_id == DOCUMENT_B for span in candidate.spans)


def test_the_catalog_is_not_persisted_anywhere():
    """A structural check, worth having because the guarantee is a negative.

    Nothing in the grounding package imports a session, a model, or a table.
    If persistence is ever added, this fails and the decision becomes explicit
    rather than accidental.
    """
    import claimtrace_api.grounding.context as context_module
    import claimtrace_api.grounding.evidence as evidence_module
    import claimtrace_api.grounding.validation as validation_module

    for module in (evidence_module, context_module, validation_module):
        names = dir(module)
        assert "AsyncSession" not in names, module.__name__
        assert "select" not in names, module.__name__
        assert "Base" not in names, module.__name__
