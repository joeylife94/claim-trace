# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls the frozen v1.0 Proof boundary.**

**Last execution update:** 2026-09-01  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-07 — Final Validation + Wishket Proof  
**Current batch state:** **CLAIMTRACE PROOF v1.0 CLOSED / FREEZE — HUMAN REVIEW PASSED**  
**Reviewed/tagged commit:** `bcb37b1a86ae70e2f35cdab6708da9310d7e9e2d`  
**Proof tag:** `v1.0-proof`  
**Post-v1 progression state:** **ENABLED — latest bounded milestone accepted**

---

## 1. Goal and Product Boundary

Frozen v1.0 flow:

**ingest → parse → index → retrieve → ask → compare → decompose → review → verify source evidence**

Target: one analyst/reviewer on a trusted workstation or controlled on-premise environment, working with text-based Korean patent PDFs and source-verifiable analytical output.

ClaimTrace v1.0 does **not** provide legal advice and does not determine infringement, validity, novelty, equivalence, inventive step, patentability, or any other legal conclusion.

## 2. Human Review Closure

Human Review completed on 2026-08-22.

### Result

`PASS — FREEZE APPROVED`

The controlled-pilot Proof candidate at reviewed commit `bcb37b1a86ae70e2f35cdab6708da9310d7e9e2d` was reviewed against `main`, the public README, committed Proof assets, recent V1-07 PR history, and the documented executed verification boundary.

Human Review accepted the current bounded Proof claims because:

- the public README explicitly frames ClaimTrace as a controlled single-user/on-premise pilot;
- legal conclusions are explicit non-claims;
- synthetic retrieval and grounded-evaluation metrics are explicitly regression evidence, not general patent-analysis accuracy claims;
- citation resolvability is explicitly not semantic entailment or legal correctness;
- current real-local-model quality is explicitly `NOT RERUN` / not claimed for V1-07;
- six committed product screenshots, one architecture visual, and one committed golden-path WebM exist under `docs/proof/`;
- V1-07 Proof Package and final regression/evaluation work were merged after executed PR-visible evidence;
- no open implementation PR remained for the reviewed v1.0 boundary.

## 3. Verified v1.0 Capability Boundary

The frozen Proof supports the following bounded product claims:

- ingest text-based Korean patent PDFs;
- validate/store/extract page text with canonical source locators;
- deterministic claim parsing and dependency handling within the supported parser boundary;
- dense, lexical, and hybrid retrieval with source navigation;
- evidence-grounded Q&A with explicit insufficient-evidence behavior;
- target/reference claim comparison under strict reference-document scope;
- deterministic source-backed claim-element decomposition;
- append-only human review state separate from machine output;
- navigation from reviewed/generated analytical surfaces back to persisted source text;
- reproducible deterministic whole-product browser flow on the committed synthetic corpus.

## 4. Executed Evidence

The reviewed Proof package and public README record executed evidence including:

### Operational verification

- clean checkout + empty database migration: **GREEN**;
- Alembic `0001 → 0006 (head)` from an empty PostgreSQL database: **PASS**;
- deterministic whole-product browser golden path: **PASS**;
- backend database-free tier: **785 PASS**;
- PostgreSQL integration tier: **135 PASS / 0 skipped**;
- Ruff lint/format and frontend ESLint/TypeScript: **GREEN**;
- expected failure-state verification: **5 PASS**.

### Retrieval regression evaluation

Synthetic regression corpus: **26 claims / 19 queries**.

| Mode | Recall@1 | Recall@3 | Recall@5 | MRR@10 |
| --- | ---: | ---: | ---: | ---: |
| Dense | 0.7696 | 0.9265 | 0.9706 | 0.9608 |
| Lexical | 0.7402 | 0.8971 | 0.9118 | 0.9608 |
| Hybrid RRF | 0.7990 | 0.9265 | 0.9412 | 1.0000 |

These are synthetic regression metrics for reproducibility/ranking regressions, not benchmark-quality claims about general patent retrieval.

### Grounded deterministic evaluation

16 committed cases:

- structured output: `1.000`;
- answerability: `1.000`;
- insufficient-evidence precision / recall: `1.000 / 1.000`;
- citation resolution: `1.000`;
- statement citation coverage: `1.000`;
- evidence-ID validity: `1.000`;
- evidence selection precision / recall: `1.000 / 0.9167`;
- end-to-end success: `0.9375`;
- forbidden cross-document citations: `0`;
- hostile grounding payloads refused: **6 / 6**.

Known weak case `g01-single-storage` remains visible; end-to-end success is intentionally not represented as `1.000`.

## 5. Proof Assets

Committed buyer-facing Proof package:

- `docs/proof/architecture-v1.svg`
- `docs/proof/screenshots/01-documents.png`
- `docs/proof/screenshots/02-search-results.png`
- `docs/proof/screenshots/03-grounded-answer.png`
- `docs/proof/screenshots/04-comparison.png`
- `docs/proof/screenshots/05-source-highlight.png`
- `docs/proof/screenshots/06-human-review.png`
- `docs/proof/demo/claimtrace-golden-path.webm`
- `docs/proof/README.md`

These assets are generated from the deterministic repository proof flow and are not hand-authored product mockups.

## 6. Not Verified / Explicit Non-Claims

The following remain outside the approved v1.0 Proof claim boundary:

- legal correctness, infringement, validity, novelty, equivalence, inventive step, or patentability;
- benchmark-quality general patent retrieval performance;
- semantic entailment merely because a citation resolves to stored source text;
- OCR or scanned/image-only PDF recovery;
- universal Korean patent parsing correctness;
- current real-local-model quality for V1-07: GitHub-hosted evaluation had no local Ollama endpoint, so historical local-model runs remain historical only;
- authentication, RBAC, multi-tenancy, public-cloud deployment, Kubernetes, billing, or admin-console production readiness;
- production security/compliance certification.

## 7. Remaining Risks

- Synthetic deterministic Proof demonstrates workflow/provenance behavior, not general legal or semantic correctness.
- Retrieval/evaluation corpora are intentionally small and regression-oriented.
- Human review is part of the product boundary; machine decomposition is not reviewer judgement.
- Text-based PDF support only remains an intentional v1.0 limitation.

## 8. Release / Tag Status

**CLOSED / FREEZE VERIFIED.**

The remote annotated tag `v1.0-proof` exists and dereferences to reviewed commit:

`bcb37b1a86ae70e2f35cdab6708da9310d7e9e2d`

The tag object is annotated with the message `ClaimTrace v1.0 Proof - Human Review PASS` and was created after Human Review approval. At closure reconciliation time, `main` was still exactly the reviewed commit, so no newer product/runtime change invalidated the reviewed boundary.

The tag is unsigned; signature verification is therefore **not** claimed. Tag existence and dereference to the reviewed commit are verified.

Authoritative closure state:

`CLAIMTRACE PROOF v1.0 CLOSED / FREEZE — HUMAN REVIEW PASSED`

No new v1.0 feature, evaluation, metric, screenshot, Issue, PR, release, or tag is required for this closure.

## 9. Closure Ledger

### Changed

- Human Review decision retained as `PASS — FREEZE APPROVED`;
- verified annotated tag `v1.0-proof` recorded;
- reviewed/tagged SHA `bcb37b1a86ae70e2f35cdab6708da9310d7e9e2d` recorded;
- authoritative state reconciled from tag-pending to `CLAIMTRACE PROOF v1.0 CLOSED / FREEZE — HUMAN REVIEW PASSED`;
- no product/runtime implementation changed.

### Actually Executed

- V1-00 through V1-07 implementation/verification work already executed through the repository's bounded Issue/PR lifecycle;
- final Human Review checked README, committed Proof assets, reviewed main state, and recent V1-07 merged PR evidence;
- remote `refs/tags/v1.0-proof` fetched;
- annotated tag object dereferenced;
- current `main` fetched and confirmed as the reviewed commit before closure reconciliation.

### Verified

- Human Review: **PASS**;
- reviewed/frozen commit: `bcb37b1a86ae70e2f35cdab6708da9310d7e9e2d`;
- remote annotated tag: `v1.0-proof`;
- tag dereference target: `bcb37b1a86ae70e2f35cdab6708da9310d7e9e2d`;
- existing executed operational, retrieval, grounded, provenance, and proof-package evidence remains the accepted Proof boundary;
- public Proof remains suitable for Wishket/freelance demonstration only within the limitations and non-claims in Sections 6–7.

### Not Verified

- all explicit non-claims in Section 6 remain unverified and must not be promoted to PASS;
- tag cryptographic signature is not verified because the annotated tag is unsigned;
- no new evaluation was run for closure because implementation/Proof packaging is frozen.

### Remaining Risks

- all limitations and risks in Sections 6–7 remain in force;
- closure does not convert regression evidence into legal, semantic, benchmark, security, or production-readiness claims.

### Exact Next Action

`FREEZE / no automatic v1.0 work`

Do not resume automatic ClaimTrace v1.0 development. Any future paid-delivery requirement, explicit new Proof requirement, or post-v1 scope must begin as a separately authorized work item outside this frozen v1.0 closure.

## 10. Post-v1 Progression Ledger

The frozen v1.0 baseline above remains immutable. Progression work is tracked separately and must not rewrite, move, or reinterpret `v1.0-proof`.

### Milestone P1 — Deterministic regression one-command reproducibility

**Status:** `ACCEPTED / MERGED`  
**Issue:** #33 — `Progression: make deterministic regression verification one-command reproducible`  
**PR:** #34  
**Accepted PR exact head:** `58a290d617f072947347462c47c86b9fb0cdf0a1`  
**Resulting main merge SHA:** `257b30918eaa219956e92ec8740e88f65ce6d469`

#### Changed

- added repository-native `make verify-deterministic-regression`;
- added PR-visible `Progression Deterministic Regression` workflow;
- verifier runs the existing public-safe synthetic retrieval evaluation with the deterministic fake embedding provider, the existing deterministic grounded evaluation, hostile grounding guardrails, and Ruff checks;
- verifier asserts a deterministic fake-provider regression baseline rather than reusing the frozen sentence-transformers quality metrics;
- no product/runtime capability, corpus, legal claim, model claim, Proof asset, or `v1.0-proof` tag changed.

#### Actually Executed

On PR #34 exact head `58a290d617f072947347462c47c86b9fb0cdf0a1`:

- `Progression Deterministic Regression` run `33391315752`: **GREEN**;
- `General CI` run `33391315831`: **GREEN**;
- `V1-02 Claim Comparison Verification` run `33391315754`: **GREEN**;
- `V1-06 Clean Start Verification` run `33391315634`: **GREEN**;
- `V1-06 Whole-Product Golden Path` run `33391315635`: **GREEN**;
- `V1-07 Proof Package` run `33391315633`: **GREEN**;
- first progression run on prior head failed because fake-provider execution was incorrectly compared against frozen sentence-transformers metrics; its uploaded artifact was inspected and the correction was limited to that executed mismatch.

#### Verified

- one command now exercises the existing deterministic retrieval/evidence regression path from a clean PR checkout;
- regression assertions fail on mismatched deterministic results rather than merely generating reports;
- current fake-provider baseline is explicitly plumbing/reproducibility evidence, not semantic retrieval quality;
- unresolved PR review threads at merge: `0`;
- Issue #33 auto-closed as `completed` after PR #34 merge;
- frozen v1.0 Proof tag and all Sections 6–7 non-claims remain unchanged.

#### Not Verified

- no new benchmark-quality patent retrieval performance is claimed;
- fake-provider dense/hybrid metrics do not establish semantic model quality;
- no new real-local-model evaluation was run;
- no legal, security-certification, OCR, auth, multi-tenant, cloud, or Kubernetes capability was added or verified.

#### Remaining Risks

- deterministic fake-provider regression is sensitive to intentional changes in deterministic retrieval plumbing and will require an evidence-backed baseline update if such a change is deliberately accepted;
- the synthetic corpora remain small and regression-oriented;
- citation resolution still proves source resolvability, not entailment or legal correctness.

#### Exact Next Action

`Run one bounded Progression Review from current main. If a concrete use/show/delivery milestone with executable acceptance exists, create exactly one Issue before implementation; otherwise remain enabled in lightweight HOLD/no-mutation mode.`

### Milestone P2 — Terminalize post-registration storage read failures

**Status:** `ACCEPTED / MERGED`  
**Issue:** #35 — `Progression: terminalize stored-file read failures during ingestion`  
**PR:** #36  
**Accepted PR exact head:** `ebcc642fdc51487edc8127ee674220789f37a2ca`  
**Resulting main merge SHA:** `5b02337d2d98c8c73e43b93cfe0b0fa567b7ac45`

#### Changed

- mapped post-registration `FileStorage.read(...)` `StorageError` into the existing `storage_failure` ingestion contract;
- the existing `_ParseRejected` / `_mark_failed` path now terminalizes the registered document as `FAILED` instead of allowing this failure to strand it in `PROCESSING`;
- added focused regression coverage for the client-safe error, terminal document state, persisted `error_code=storage_failure`, and safe completion event;
- corrected the recovery message after review so it does not recommend an identical-byte re-upload that digest deduplication would short-circuit;
- no OCR, parser semantics, retrieval, ranking, grounding, comparison, review, auth, cloud, legal capability, frozen Proof asset, metric, or `v1.0-proof` tag changed.

#### Actually Executed

On PR #36 exact head `ebcc642fdc51487edc8127ee674220789f37a2ca`:

- `General CI` run `33457327009`: **GREEN**;
  - database-free backend tests: **PASS**;
  - PostgreSQL integration tests without skip fallback: **PASS**;
  - Ruff lint: **PASS**;
  - Ruff format check: **PASS**;
  - frontend ESLint and TypeScript typecheck: **PASS**;
- `Progression Deterministic Regression` run `33457327043`: **GREEN**;
- `V1-02 Claim Comparison Verification` run `33457326937`: **GREEN**;
- `V1-03 Comparison UI Verification` run `33457326987`: **GREEN**;
- `V1-04 Claim Element Verification` run `33457327080`: **GREEN**;
- `V1-05 Human Review Verification` run `33457327034`: **GREEN**;
- `V1-06 Clean Start Verification` run `33457326989`: **GREEN**;
- `V1-06 Whole-Product Golden Path` run `33457327006`: **GREEN**;
- `V1-06 Expected Failure States` run `33457327110`: **GREEN**;
- `V1-07 Final Evaluations` run `33457326971`: **GREEN**;
- `V1-07 Proof Package` run `33457327050`: **GREEN**.

#### Verified

- forced post-registration storage-read failure no longer leaks raw `StorageError` through the ingestion contract;
- the registered document reaches terminal `FAILED` with `error_code=storage_failure` through the tested service path;
- completion-event regression coverage checks `status=failed` and `error_code=storage_failure` and excludes the synthetic internal exception detail;
- current exact-head backend, PostgreSQL integration, lint/format, frontend, deterministic regression, clean-start, whole-product, failure-state, evaluation, and proof-package workflows are GREEN;
- the one review blocker about misleading retry guidance was corrected and its thread resolved;
- unresolved PR review threads at merge: `0`;
- Issue #35 auto-closed as `completed` after PR #36 merge;
- frozen v1.0 Proof tag and all Sections 6–7 non-claims remain unchanged.

#### Not Verified

- this milestone does not prove recovery/reprocessing of an already-failed deduplicated document; the message explicitly leaves that as operator recovery;
- no redesign of general database persistence failures or unrelated ingestion stages was attempted;
- no new benchmark, real-local-model, legal, OCR, auth, multi-tenant, cloud, Kubernetes, or security-certification claim is made.

#### Remaining Risks

- identical-byte re-upload of an already-failed document still follows existing digest deduplication behavior rather than an automatic reprocess path;
- other post-registration failure modes remain governed by their existing contracts and were not broadened in this milestone;
- all frozen v1.0 limitations and non-claims remain in force.

#### Exact Next Action

`Run one bounded Progression Review from current main. If a concrete use/show/delivery milestone with executable acceptance exists, create exactly one Issue before implementation; otherwise remain enabled in lightweight HOLD/no-mutation mode.`
