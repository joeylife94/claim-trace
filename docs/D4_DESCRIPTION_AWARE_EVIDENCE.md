# D4 — Description-aware Evidence Retrieval Pilot

> **Status (updated 2026-11-11): D4-01 is accepted and merged** (Issue #63, PR #64, merged to `main` as `a6d8b44`). `CLAIMTRACE_V1_MASTER.md` Section 13 records the destination as reached. D4-02 (mixed grounded analysis) and reranking were never opened. The section [As built](#as-built-d4-01-state-on-main-as-of-2026-11-11) below describes what `main` contains; everything after it is the original pre-implementation brief, kept as the historical record. Lines in the brief that no longer describe the current state carry a dated note.

## As built (D4-01, state on `main` as of 2026-11-11)

What exists, with its limits. The MASTER (Section 13) remains the authoritative record of the acceptance evidence.

**Storage.** Alembic migration `0007` adds three tables: `description_derivation_runs` (one run per document and segmenter version, with status `completed` or `unsupported`), `description_segments` (page number, `start_char`, `end_char`, the segment text, an optional section heading, and an `evidence_kind` fixed to `description` by a check constraint), and `description_search_records` (a normalised text projection, a `tsvector`, and a 384-dimension `vector` per segment and retrieval profile). These tables have no ORM model; the service uses SQL directly.

**Endpoints** (under `/api/v1`):

- `POST /documents/{document_id}/descriptions/derive` derives segments from the document's persisted page text. It returns `201` for a new run and `200` when the existing run is returned. The document must be `completed`.
- `POST /documents/{document_id}/descriptions/index` derives if needed, then embeds and stores search records for the current retrieval profile. A document whose structure is not supported returns status `unsupported` and indexes nothing.
- `POST /search/descriptions` runs `dense`, `lexical` or `hybrid` (default) retrieval over description segments only, optionally limited to a list of document ids, using the same retrieval-profile settings, fusion (`rrf_k`) and candidate bounds as claim search.

**Segmenter.** `korean-patent-description-sections`, version `v1` (`services/description_evidence.py`). It looks for known Korean description section headings (for example `기술분야`, `배경기술`, `발명의 상세한 설명`) in the persisted page text, stops at a claims heading, and cuts the text in between into page-local segments of bounded length. If it finds no description heading, or a heading with no substantive text, the outcome is `unsupported` with a warning (`description_heading_not_found` or `description_heading_found_but_no_substantive_text`) rather than a guess.

**Outcomes.** A derivation is `completed` or `unsupported`; nothing in between is promoted to success.

**Canonical locators.** Every segment's text is a slice of `document_pages.text` for its page, and its `source_span` is the existing `(document_id, page_number, start_char, end_char)` locator. The normalised search text is only a search projection and is never used as a citation coordinate. No second coordinate system was added.

**Distinguishing evidence kinds.** Every description segment and search result carries `evidence_kind: "description"`. Claim search (`POST /search/claims`) is a separate endpoint and returns claims only; the two are not merged into one result list.

**Navigation.** Each result includes a `source_url` of the form `/documents/{document_id}?page={page}&start={start}&end={end}`. The existing document page opens that page and highlights that range. There is no dedicated description-search page, and no page, component or browser test in `apps/web` calls the description endpoints; description search is API-only.

**Grounded generation is unchanged and claim-only.** Description evidence is not an input to `POST /grounded/answers` or to the Case-grounded results, and no reranker exists.

**Evidence tiers.** Database-free tests are in `apps/api/tests/test_description_evidence.py`. The real-public Korean patent acceptance path is `apps/api/tests/d4_acceptance/test_real_public_description.py`, run by the `Progression D4 Description Evidence` workflow against the two hash-pinned public PDFs listed in `docs/real-public-corpus/manifest.json` (downloaded at run time, not committed; the directory is excluded from default pytest).

**Not claimed.** No benchmark-quality retrieval accuracy, legal conclusion, or semantic entailment is claimed; a description result that resolves to stored text shows where the text is, not that it answers the query. The segmenter was exercised on synthetic input and on the two public documents above, not on a general corpus.

---

## Original brief (historical record, written 2026-09-09)

The text below is the pre-implementation handoff as it was written. It is unchanged except for dated notes where a line no longer describes the repository.

> Human-approved progression direction recorded 2026-09-09.
>
> This document is a bounded implementation handoff for D4. `CLAIMTRACE_V1_MASTER.md` remains the authoritative product/proof contract and must be reconciled before D4 acceptance or merge.
>
> _Note (2026-11-11): the reconciliation happened; D4-01 was accepted and merged. See the status banner and "As built" above._

## Objective

Extend ClaimTrace from claim-only retrieval into source-verifiable retrieval over patent description evidence while preserving the existing canonical source-locator model and all frozen legal/product non-claims.

D4 is not a legal-accuracy benchmark, OCR project, customer-corpus project, authentication project, or production deployment project.

## D4-01 — Description structure + retrieval

The first milestone is intentionally narrow.

Required behavior:

1. derive description-oriented segments from already persisted page text without creating a second source coordinate system;
2. every segment must resolve back to canonical persisted source text using the existing document/page/span provenance model;
3. clearly distinguish claim evidence from description evidence in persisted/indexed/retrieved representations;
4. support description evidence retrieval through the existing retrieval architecture with bounded dense/lexical/hybrid behavior where practical;
5. expose enough API/UI surface for a reviewer to open a description result at the exact persisted source range;
   _(Note, 2026-11-11: delivered as API endpoints plus a `source_url` deep link into the existing document page. No dedicated UI was built.)_
6. execute a bounded synthetic regression and at least one real-public Korean patent document path;
7. preserve existing claim retrieval, grounded analysis, comparison, decomposition, review, and D1/D2/D3 regression gates.

## Acceptance

_(Note, 2026-11-11: this acceptance was met and recorded in the MASTER, Section 13.)_

D4-01 is accepted only when exact-head executable evidence proves:

- description segments are reproducibly derived from persisted source text;
- segment boundaries remain source-resolvable and do not fabricate page/offset metadata;
- at least one query retrieves a relevant description passage from a real-public accepted patent document and the reviewer can navigate to its exact stored source span;
- claim-only retrieval behavior does not regress under existing accepted gates;
- unsupported/ambiguous document structure is explicit rather than silently promoted to PASS;
- no legal, benchmark-quality, OCR, private-corpus, auth/RBAC, multi-tenant, cloud/Kubernetes, security-certification, or production-readiness claim is added.

## Conditional later work

D4-02 may add mixed claim + description grounded analysis only after D4-01 is accepted and a Destination Review confirms it is the smallest remaining D4 gap.

_(Note, 2026-11-11: D4-02 was not opened and no reranker exists; the D4 destination review found no executed blocker requiring either.)_

Reranking is conditional, not pre-authorized as automatic implementation. It may be selected only if an executed D4 acceptance path shows relevant evidence is retrieved but ordering/top-k precision is the concrete blocker.

## Anti-micro-loop

Do not open parser/retrieval threshold permutations merely to continue activity. After at most two consecutive milestones on the same narrow retrieval/segmentation axis, force Destination Review. A third narrow milestone requires a blocker demonstrated by a destination-level executable run.

## Deferred / Human Review boundaries

- OCR / scanned or image-only PDF recovery;
- private/customer corpus onboarding;
- authentication, RBAC, multi-tenancy;
- generalized semantic/legal accuracy or benchmark claims;
- public cloud/Kubernetes/production deployment;
- security/compliance certification.

## Closure

After each accepted milestone:

PR exact-head verification → review → merge → Issue close → `CLAIMTRACE_V1_MASTER.md` reconciliation → Destination Review.

If D4 is reached, progression may advance only to another explicitly pre-authorized destination recorded in the authoritative MASTER. Otherwise return to Human Review.

_(Note, 2026-11-11: superseded as a statement of what comes next. D4 was reached, D5 and D6 followed, and D6 was closed by Human Review on 2026-11-11. No milestone is active and the next destination is not selected; see MASTER Section 16.)_
