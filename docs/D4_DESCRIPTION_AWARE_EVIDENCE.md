# D4 — Description-aware Evidence Retrieval Pilot

> Human-approved progression direction recorded 2026-09-09.
>
> This document is a bounded implementation handoff for D4. `CLAIMTRACE_V1_MASTER.md` remains the authoritative product/proof contract and must be reconciled before D4 acceptance or merge.

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
6. execute a bounded synthetic regression and at least one real-public Korean patent document path;
7. preserve existing claim retrieval, grounded analysis, comparison, decomposition, review, and D1/D2/D3 regression gates.

## Acceptance

D4-01 is accepted only when exact-head executable evidence proves:

- description segments are reproducibly derived from persisted source text;
- segment boundaries remain source-resolvable and do not fabricate page/offset metadata;
- at least one query retrieves a relevant description passage from a real-public accepted patent document and the reviewer can navigate to its exact stored source span;
- claim-only retrieval behavior does not regress under existing accepted gates;
- unsupported/ambiguous document structure is explicit rather than silently promoted to PASS;
- no legal, benchmark-quality, OCR, private-corpus, auth/RBAC, multi-tenant, cloud/Kubernetes, security-certification, or production-readiness claim is added.

## Conditional later work

D4-02 may add mixed claim + description grounded analysis only after D4-01 is accepted and a Destination Review confirms it is the smallest remaining D4 gap.

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
