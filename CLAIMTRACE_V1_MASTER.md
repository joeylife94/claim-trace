# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls the frozen v1.0 Proof boundary.**

**Last execution update:** 2026-09-02  
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

### Milestone P3 — Terminalize page-persistence failures during ingestion

**Status:** `ACCEPTED / MERGED`  
**Issue:** #37 — `Progression: terminalize page-persistence failures during ingestion`  
**PR:** #38  
**Accepted PR exact head:** `26adfe4f82ccc724f7e46259a1e00e0ffb073971`  
**Resulting main merge SHA:** `5fd8ed6471203e831358c56bb0e749593b2fe92e`

#### Changed

- converted a failed page/completion persistence transaction into the existing client-safe `internal_error` ingestion contract after rollback;
- preserved the atomic guarantee that partial page rows and a false `COMPLETED` state do not survive the failed transaction;
- routed the registered document through the existing `_mark_failed` path so the terminal state becomes `FAILED` instead of remaining stranded in `PROCESSING`;
- preserved `document.id` before rollback so SQLAlchemy attribute expiration cannot trigger `MissingGreenlet` while logging the failure before terminalization;
- added focused deterministic regression coverage for rollback semantics, terminal state, safe error text, and completion-event evidence;
- aligned the pre-existing page-persistence regression with the new terminal failure contract;
- no OCR, retry/resume queue, parser semantics, retrieval, ranking, grounding, comparison, review, auth, cloud, legal capability, frozen Proof asset, metric, or `v1.0-proof` tag changed.

#### Actually Executed

On PR #38 exact head `26adfe4f82ccc724f7e46259a1e00e0ffb073971`:

- `General CI` run `33468745009`: **GREEN**;
  - database-free backend tests: **PASS**;
  - PostgreSQL integration tests without skip fallback: **PASS**;
  - Ruff lint: **PASS**;
  - Ruff format check: **PASS**;
  - frontend ESLint and TypeScript typecheck: **PASS**;
- `Progression Deterministic Regression` run `33468745036`: **GREEN**;
- `V1-02 Claim Comparison Verification` run `33468745033`: **GREEN**;
- `V1-03 Comparison UI Verification` run `33468745015`: **GREEN**;
- `V1-04 Claim Element Verification` run `33468745002`: **GREEN**;
- `V1-05 Human Review Verification` run `33468745037`: **GREEN**;
- `V1-06 Clean Start Verification` run `33468744967`: **GREEN**;
- `V1-06 Whole-Product Golden Path` run `33468744989`: **GREEN**;
- `V1-06 Expected Failure States` run `33468745053`: **GREEN**;
- `V1-07 Final Evaluations` run `33468745001`: **GREEN**;
- `V1-07 Proof Package` run `33468745011`: **GREEN**;
- prior head `0cb21d1eb5bd54934b6f6352375c93116c5888b4` exposed a stale database-free test that still expected the old raw `RuntimeError` behavior; that test was corrected inside Issue #37;
- prior head `57757a4c5cdb61f51415d73094371797d73bf442` passed database-free and PostgreSQL integration tests but failed Ruff on an unused import in the new focused regression; that lint defect was removed before the accepted exact-head run.

#### Verified

- a forced page/completion persistence failure reaches the stable `DocumentIngestionError` / `internal_error` contract rather than leaking the raw database exception;
- the registered document reaches terminal `FAILED` through the tested service path;
- the modeled failed transaction leaves no partial `DocumentPage` rows and no false `COMPLETED` state;
- completion-event coverage checks `status=failed`, the stable error code, and absence of the synthetic database detail;
- exact-head database-free tests, real PostgreSQL integration, Ruff lint/format, frontend checks, deterministic regression, clean-start, whole-product, expected-failure, evaluation, and proof-package workflows are GREEN;
- the review P1 about SQLAlchemy rollback attribute expiration was fixed by preserving the document ID before rollback, and the review thread was resolved;
- unresolved PR review threads at merge: `0`;
- Issue #37 auto-closed as `completed` after PR #38 merge;
- frozen v1.0 Proof tag and all Sections 6–7 non-claims remain unchanged.

#### Not Verified

- this milestone does not add or verify automatic retry, resume, or reprocessing after a database outage;
- `internal_error` remains intentionally generic; no broader database error taxonomy was introduced;
- the forced failure is synthetic regression coverage and does not prove every PostgreSQL/network outage mode;
- no new benchmark, real-local-model, legal, OCR, auth, multi-tenant, cloud, Kubernetes, or security-certification claim is made.

#### Remaining Risks

- recovery after a terminal page-persistence failure remains operator-mediated;
- future persistence failure modes outside this bounded transaction may require their own evidence-backed contracts;
- all frozen v1.0 limitations and non-claims remain in force.

#### Exact Next Action

`Run one bounded Progression Review from current main. If a concrete use/show/delivery milestone with executable acceptance exists, create exactly one Issue before implementation; otherwise remain enabled in lightweight HOLD/no-mutation mode.`

### Milestone P4 — Terminalize processing-transition failures during ingestion

**Status:** `ACCEPTED / MERGED`  
**Issue:** #39 — `Progression: terminalize processing-transition failures during ingestion`  
**PR:** #40  
**Accepted PR exact head:** `8802c6e907c7a6608a8a34adccfe9d625a307bd5`  
**Resulting main merge SHA:** `1c2b4e7cfd9be9082929cec95c1ff5aff6965b5d`

#### Changed

- converted a failed post-registration `UPLOADED -> PROCESSING` commit into the existing client-safe `internal_error` ingestion contract;
- after rollback, the already-registered document is terminalized through `_mark_failed` when recovery persistence succeeds;
- added focused deterministic regression coverage that fails only the second commit and verifies terminal state, safe error text, and completion-event evidence;
- preserved duplicate-race handling, initial registration cleanup, storage-read/page-persistence behavior, parser/retrieval/grounding semantics, Proof assets, frozen metrics, and `v1.0-proof`.

#### Actually Executed

On PR #40 exact head `8802c6e907c7a6608a8a34adccfe9d625a307bd5`:

- `General CI` run `33472375086`: **GREEN**;
- `Progression Deterministic Regression` run `33472375078`: **GREEN**;
- `V1-02 Claim Comparison Verification` run `33472375090`: **GREEN**;
- `V1-03 Comparison UI Verification` run `33472375071`: **GREEN**;
- `V1-04 Claim Element Verification` run `33472375077`: **GREEN**;
- `V1-05 Human Review Verification` run `33472375081`: **GREEN**;
- `V1-06 Clean Start Verification` run `33472375069`: **GREEN**;
- `V1-06 Whole-Product Golden Path` run `33472375172`: **GREEN**;
- `V1-06 Expected Failure States` run `33472375112`: **GREEN**;
- `V1-07 Final Evaluations` run `33472375088`: **GREEN**;
- `V1-07 Proof Package` run `33472375076`: **GREEN**.

#### Verified

- the focused regression forces only the post-registration processing-transition commit to fail and verifies terminal `FAILED` with `internal_error` after modeled rollback/recovery persistence;
- the client-visible error and structured completion event exclude the synthetic database detail and report `status=failed` with the stable error code;
- exact-head General CI and all ten triggered progression/v1 regression workflows are GREEN;
- unresolved PR review threads at merge: `0`;
- Issue #39 auto-closed as `completed` after PR #40 merge;
- frozen v1.0 Proof tag and all Sections 6–7 non-claims remain unchanged.

#### Not Verified

- the forced second-commit failure itself is covered by a deterministic `StubSession`; no dedicated real-PostgreSQL fault-injection test was added for this exact failure point;
- General CI's real PostgreSQL integration tier passed and protects broader SQLAlchemy/PostgreSQL compatibility, but that alone is not treated as proof that every rollback/expiration behavior at this exact injected transition failure is covered;
- no automatic retry/resume/operator UI, OCR, parser/retrieval expansion, benchmark, real-local-model, legal, auth, multi-tenant, cloud, Kubernetes, or security-certification capability is claimed.

#### Remaining Risks

- terminalization still depends on the recovery persistence performed by `_mark_failed`; a simultaneous continued database outage can prevent that recovery commit, which remains an operator-visible failure rather than a durable retry path;
- exact real-database fault injection for the processing-transition commit remains a possible future hardening milestone only if concrete use/show/delivery value justifies it;
- all frozen v1.0 limitations and non-claims remain in force.

#### Exact Next Action

`Run one bounded Progression Review from current main. If a concrete use/show/delivery milestone with executable acceptance exists, create exactly one Issue before implementation; otherwise remain enabled in lightweight HOLD/no-mutation mode.`

### Milestone P5 — Reconcile ingestion failure documentation with accepted runtime behavior

**Status:** `ACCEPTED / MERGED`  
**Issue:** #41 — `Progression: reconcile ingestion failure documentation with accepted runtime behavior`  
**PR:** #42  
**Accepted PR exact head:** `ec8811613c36d1dc190a3f42bff0affc2cf483f4`  
**Resulting main merge SHA:** `343b7f23a0314395b8d83aa86646a42dd9516208`

#### Changed

- reconciled `docs/ARCHITECTURE.md` ingestion flow and failure table with accepted P2/P3/P4 runtime behavior;
- documented post-registration stored-file reads and the accepted terminal failure contracts for storage-read, processing-transition, and page/completion persistence failures;
- explicitly separated verified terminalization from unverified automatic retry/resume behavior and recorded that identical-byte deduplication does not itself re-run a failed ingestion;
- recorded the P4 evidence boundary: deterministic fault injection verified the service contract, but no dedicated real-PostgreSQL commit-fault injection was executed;
- added the already-existing `storage_failure` and `internal_error` HTTP 500 mappings to the ingestion error table;
- no product/runtime code, schema, Proof asset, frozen metric, legal/non-claim boundary, or `v1.0-proof` tag changed.

#### Actually Executed

On PR #42 exact head `ec8811613c36d1dc190a3f42bff0affc2cf483f4`:

- compared the PR head to `main`: exactly one changed file, `docs/ARCHITECTURE.md`, with `+21/-7`;
- fetched and reviewed the exact-head architecture section after the commit, including all three reconciled failure paths and the retry/resume limitation text;
- cross-checked the documentation against current `services/ingestion.py` and `core/errors.py` on `main`;
- reviewed the PR patch and recorded a bounded review; unresolved review threads at merge: `0`;
- merged PR #42 with an expected-head SHA guard;
- confirmed Issue #41 auto-closed as `completed`;
- re-fetched the annotated `v1.0-proof` tag and dereferenced it to the unchanged reviewed commit `bcb37b1a86ae70e2f35cdab6708da9310d7e9e2d`.

#### Verified

- architecture documentation no longer states that page/completion persistence failure necessarily leaves a document stranded in `processing`;
- P2 storage-read and P4 processing-transition failure semantics are now represented alongside P3 page/completion persistence semantics;
- `storage_failure` and `internal_error` remain mapped to HTTP 500 in the current error taxonomy;
- documentation explicitly avoids claiming background retry/resume or automatic identical-byte reprocessing;
- documentation explicitly avoids overstating P4 as real-PostgreSQL fault-injection evidence;
- PR scope remained documentation-only and the frozen v1.0 tag target remained unchanged.

#### Not Verified

- no new runtime test suite or PR workflow executed on PR #42 because the repository's current General CI path filter excludes `docs/**`, and no dedicated documentation-lint workflow exists;
- this milestone therefore verifies repository/document consistency, not new runtime behavior;
- no dedicated real-PostgreSQL commit-fault injection was added or run for P4;
- no automatic retry/resume/operator recovery mechanism was added or verified;
- all frozen v1.0 non-claims remain unverified.

#### Remaining Risks

- future runtime changes can make architecture text stale again unless documentation reconciliation is kept inside the same accepted change lifecycle;
- ingestion recovery after terminal failure remains operator-mediated and is not a durable retry mechanism;
- all frozen v1.0 limitations and non-claims remain in force.

#### Exact Next Action

`Run one bounded Progression Review from current main. If a concrete use/show/delivery milestone with executable acceptance exists, create exactly one Issue before implementation; otherwise remain enabled in lightweight HOLD/no-mutation mode.`

### Milestone P6 — Reconcile roadmap with accepted v1.0 capability state

**Status:** `ACCEPTED / MERGED`  
**Issue:** #43 — `Progression: reconcile roadmap with accepted v1.0 capability state`  
**PR:** #44  
**Accepted PR exact head:** `23363ed4848fe304f4d8202007d4579837c863b6`  
**Resulting main merge SHA:** `7230da037e9132f3ca074c7b6bddad14a8acb0fe`

#### Changed

- reconciled `docs/ROADMAP.md` so Phase 2C and Phase 5A are no longer presented as future/unimplemented despite being inside the frozen accepted v1.0 capability boundary;
- described claim decomposition, append-only review, source navigation, and target/reference comparison only within the controlled-pilot/source-verifiable/non-legal boundary;
- explicitly marked Phase 3B description retrieval/reranking as future/unverified;
- preserved OCR, auth/RBAC, multi-tenancy, cloud production readiness, legal determinations, benchmark-quality retrieval, and other frozen non-claims as unverified/out of scope;
- no runtime, schema, evaluation, Proof asset, frozen metric, or `v1.0-proof` tag changed.

#### Actually Executed

On PR #44 exact head `23363ed4848fe304f4d8202007d4579837c863b6`:

- verified the PR changed exactly one file: `docs/ROADMAP.md`;
- reviewed the exact-head patch against the current MASTER capability and non-claim sections;
- narrowed an initially over-broad roadmap rewrite before acceptance so unrelated historical sections were not unnecessarily rewritten;
- confirmed unresolved PR review threads: `0`;
- confirmed the docs-only exact head triggered no GitHub Actions workflow under the repository's current path filters;
- merged PR #44 with expected-head SHA guard;
- confirmed Issue #43 auto-closed as `completed`.

#### Verified

- ROADMAP no longer marks accepted v1.0 claim decomposition/review or claim comparison as `next`;
- ROADMAP now keeps the accepted comparison/decomposition/review/source-navigation claims inside the same controlled-pilot and non-legal boundary as the MASTER;
- Phase 3B remains explicitly future/unverified rather than being promoted to completion;
- PR scope remained one documentation file and no runtime PASS claim was created by this milestone;
- frozen v1.0 evidence, limitations, non-claims, and tag target remain authoritative and unchanged.

#### Not Verified

- no new runtime suite or PR workflow executed for PR #44 because the docs-only change did not match current workflow path filters;
- this milestone verifies repository/document consistency only, not new executable behavior;
- no description retrieval/reranking, OCR, auth/RBAC, multi-tenancy, cloud production readiness, legal conclusion, benchmark-quality retrieval, or security certification was added or verified.

#### Remaining Risks

- roadmap text can become stale again if future accepted capability changes are not reconciled in the same lifecycle;
- documentation consistency does not replace executable verification for future runtime changes;
- all frozen v1.0 limitations and non-claims remain in force.

#### Exact Next Action

`Run one bounded Progression Review from current main. If a concrete use/show/delivery milestone with executable acceptance exists, create exactly one Issue before implementation; otherwise remain enabled in lightweight HOLD/no-mutation mode.`

### Milestone P7 — Remove stale duplicate Phase 5 roadmap contract

**Status:** `ACCEPTED / MERGED`  
**Issue:** #45 — `Progression: remove stale duplicate Phase 5 roadmap contract`  
**PR:** #46  
**Accepted PR exact head:** `22788c56380da6d4379fc02ac7142c1865c212b6`  
**Resulting main merge SHA:** `8bde1cd6a0d8532bbf34663f313bf4784b8992b7`

#### Changed

- removed only the stale duplicate generic `Phase 5 - Claim decomposition and evidence comparison` section from `docs/ROADMAP.md`;
- preserved completed Phase 2C / Phase 5A wording, Phase 3B future/unverified status, Phase 6, the controlled-pilot boundary, frozen non-claims, Proof evidence, metrics, and `v1.0-proof`;
- no runtime, schema, evaluation corpus, Proof asset, metric, or legal/product capability changed.

#### Actually Executed

On PR #46 exact head `22788c56380da6d4379fc02ac7142c1865c212b6`:

- confirmed the PR changed exactly one file, `docs/ROADMAP.md`, with `+0/-22`;
- reviewed the merged commit patch and verified it removes only the stale duplicate Phase 5 block;
- confirmed PR #46 merged to `main` as `8bde1cd6a0d8532bbf34663f313bf4784b8992b7`;
- confirmed Issue #45 closed as `completed`;
- no runtime/evaluation workflow evidence was promoted from this docs-only change.

#### Verified

- ROADMAP no longer represents accepted decomposition/comparison capability both as completed and as a second future generic Phase 5 contract;
- PR scope remained documentation-only and bounded to the stale duplicate block;
- Issue #45 lifecycle is complete through merge/close;
- frozen v1.0 Proof baseline and Sections 6–7 limitations/non-claims remain unchanged.

#### Not Verified

- no new runtime or evaluation PASS is claimed from PR #46;
- no description retrieval/reranking, OCR, auth/RBAC, multi-tenancy, cloud production readiness, legal conclusion, benchmark-quality retrieval, or security certification was added or verified;
- documentation consistency does not establish new executable behavior.

#### Remaining Risks

- roadmap/documentation can become stale again if future accepted changes are not reconciled in the same lifecycle;
- all frozen v1.0 limitations and non-claims remain in force.

#### Exact Next Action

`Run one bounded Progression Review from current main. If a concrete use/show/delivery milestone with executable acceptance exists, create exactly one Issue before implementation; otherwise remain enabled in lightweight HOLD/no-mutation mode.`

### Milestone P8 — Retry failed ingestion from persisted original

**Status:** `ACCEPTED / MERGED`  
**Issue:** #47 — `Progression: retry failed ingestion from the persisted original`  
**PR:** #48  
**Accepted PR exact head:** `f7b813ac0863b547ebea9ec518d908b1cc6a4642`  
**Resulting main merge SHA:** `df3c4df0d46d6e941b34e50ff421721afab69f82`

#### Changed

- added an explicit operator-driven `POST /api/v1/documents/{id}/retry` recovery endpoint for existing terminal `FAILED` documents;
- retry reuses the existing document row, SHA-256 digest, storage key, and persisted original bytes and does not accept a replacement upload;
- added stable `document_retry_not_allowed` / HTTP 409 behavior for non-failed document states;
- retry transitions the existing row through `PROCESSING` and reuses the existing parser and atomic page-persistence path; successful retry clears prior ingestion error metadata;
- added focused database-free and real-PostgreSQL integration coverage for same-row recovery, source page persistence, and non-failed rejection;
- documented the operator-driven recovery boundary without claiming a worker, queue, automatic retry policy, OCR recovery, or production resilience;
- no schema migration, retrieval/ranking, grounding/comparison/review semantics, Proof asset, frozen metric, legal claim, or `v1.0-proof` tag changed.

#### Actually Executed

On PR #48 exact head `f7b813ac0863b547ebea9ec518d908b1cc6a4642`:

- `General CI` run `33634178261`: **GREEN**;
  - database-free backend tests: **PASS**;
  - PostgreSQL integration tests without skip fallback: **PASS**;
  - Ruff lint/format: **PASS**;
  - frontend ESLint and TypeScript typecheck: **PASS**;
- `Progression Deterministic Regression` run `33634178253`: **GREEN**;
- `V1-02 Claim Comparison Verification` run `33634178277`: **GREEN**;
- `V1-03 Comparison UI Verification` run `33634178199`: **GREEN**;
- `V1-04 Claim Element Verification` run `33634178221`: **GREEN**;
- `V1-05 Human Review Verification` run `33634178295`: **GREEN**;
- `V1-06 Clean Start Verification` run `33634178168`: **GREEN**;
- `V1-06 Whole-Product Golden Path` run `33634178222`: **GREEN**;
- `V1-06 Expected Failure States` run `33634178192`: **GREEN**;
- `V1-07 Final Evaluations` run `33634178342`: **GREEN**;
- `V1-07 Proof Package` run `33634178197`: **GREEN**;
- reviewed the exact-head five-file diff and confirmed unresolved review threads: `0`;
- merged PR #48 with expected-head SHA guard and confirmed Issue #47 auto-closed as `completed`.

#### Verified

- a supported stored text PDF can be retried from `FAILED` to `COMPLETED` without creating a second document row or accepting replacement bytes;
- real-PostgreSQL integration coverage verifies one persisted document row, unchanged digest/storage key, cleared prior error metadata, and persisted source-verifiable page rows after successful retry;
- non-failed retry is rejected with stable HTTP 409 / `document_retry_not_allowed` behavior;
- retry remains explicit/operator-driven and reuses the existing ingestion parser/page-persistence contracts;
- exact-head General CI and all ten additional triggered progression/v1 workflows are GREEN;
- frozen v1.0 Proof baseline, Sections 6–7 limitations/non-claims, and reviewed tag boundary remain unchanged.

#### Not Verified

- no background worker, automatic retry scheduling, durable retry queue, or automatic outage recovery was added or verified;
- no frontend/operator retry control was added; the accepted recovery primitive is API/service-level;
- no exhaustive fault injection proves every concurrent storage/network/database outage during retry;
- OCR/scanned-PDF recovery remains unsupported;
- no new legal, benchmark-quality retrieval, real-local-model, auth/RBAC, multi-tenant, cloud/Kubernetes, or security-certification claim is made.

#### Remaining Risks

- retry depends on the persisted original still being readable and on the underlying storage/database fault being recovered;
- the recovery action is operator-driven and API-level rather than a production job system;
- all frozen v1.0 limitations and non-claims remain in force.

#### Exact Next Action

`Run one bounded Progression Review from current main. If a concrete use/show/delivery milestone with executable acceptance exists, create exactly one Issue before implementation; otherwise remain enabled in lightweight HOLD/no-mutation mode.`

### Milestone P9 — Expose failed-ingestion retry in the Documents UI

**Status:** `ACCEPTED / MERGED`  
**Issue:** #49 — `Progression: expose failed-ingestion retry in the documents UI`  
**PR:** #50  
**Accepted PR exact head:** `abf99f327f106fe5665feab02d7f8bcdfd259d99`  
**Resulting main merge SHA:** `c021428639df3756346abfee81759782558a2e5c`

#### Changed

- connected the accepted P8 `POST /api/v1/documents/{id}/retry` contract to the existing Documents UI through the existing Next.js server-side API boundary;
- rendered `Retry ingestion` only for documents whose current state is `failed`;
- successful retry revalidates the documents list and document detail so the same document can render as `completed` without its prior failure metadata or retry affordance;
- retry failure surfaces only the API's client-safe `detail` and keeps the failed document retryable;
- after review, post-registration upload failures that return a persisted failed document now revalidate `/documents`, so the retry affordance appears without a manual reload;
- added a deterministic mock-API + actual Next server-action + Playwright verifier and a PR-visible `Progression Retry UI Verification` workflow;
- no schema migration, backend retry semantics, automatic/background retry policy, OCR support, retrieval/grounding/comparison/review semantics, frozen Proof asset, metric, legal claim, or `v1.0-proof` tag changed.

#### Actually Executed

On PR #50 exact head `abf99f327f106fe5665feab02d7f8bcdfd259d99`:

- `Progression Retry UI Verification` run `33641883472`: **GREEN**;
- `General CI` run `33641883477`: **GREEN**;
  - frontend ESLint and TypeScript typecheck: **PASS**;
  - database-free backend tests: **PASS**;
  - PostgreSQL integration tests without skip fallback: **PASS**;
  - Ruff lint/format: **PASS**;
- `V1-03 Comparison UI Verification` run `33641883460`: **GREEN**;
- `V1-05 Human Review Verification` run `33641883465`: **GREEN**;
- `V1-06 Whole-Product Golden Path` run `33641883385`: **GREEN**;
- `V1-07 Proof Package` run `33641883418`: **GREEN**;
- the first retry-UI verifier run exposed an incorrect test-harness API environment variable; the harness was corrected to use the application's actual `API_INTERNAL_BASE_URL` contract;
- the next verifier iteration exposed nondeterministic dev-server cleanup in the harness; it was narrowed to direct Next process spawning plus explicit mock-server connection cleanup before acceptance;
- review found that a newly persisted failed upload could return before list revalidation; that same-gap defect was fixed on the accepted exact head and the thread resolved after exact-head verification;
- PR #50 was squash-merged with an expected-head SHA guard and Issue #49 auto-closed as `completed`.

#### Verified

- deterministic browser evidence shows a failed document has the retry affordance while an already-completed document does not;
- the first modeled retry failure displays only the client-safe API detail and leaves the same failed document retryable;
- the second modeled retry succeeds on the same document, refreshes the list to `completed`, removes the prior failure message, and removes the retry affordance;
- exact-head General CI plus the relevant existing comparison, review, whole-product, and Proof-package workflows are GREEN;
- unresolved PR review threads at merge: `0`;
- Issue #49 lifecycle completed through merge/close;
- frozen v1.0 Proof boundary and Sections 6–7 limitations/non-claims remain unchanged.

#### Not Verified

- the new browser verifier uses a deterministic mock API; it verifies the UI/server-action contract but does not establish production infrastructure resilience;
- P8 remains the authoritative real-PostgreSQL evidence for same-row backend retry behavior;
- no background worker, automatic retry scheduling, batch recovery, OCR/scanned-PDF recovery, auth/RBAC, multi-tenancy, cloud/Kubernetes readiness, legal conclusion, benchmark-quality retrieval, or security certification was added or verified.

#### Remaining Risks

- retry remains operator-driven and depends on the persisted original plus the underlying storage/database condition being recoverable;
- repeated retry can still fail safely when the underlying cause remains unresolved;
- deterministic browser coverage does not replace production deployment/resilience evidence;
- all frozen v1.0 limitations and non-claims remain in force.

#### Exact Next Action

`Run one bounded Progression Review from current main. If a concrete use/show/delivery milestone with executable acceptance exists, create exactly one Issue before implementation; otherwise remain enabled in lightweight HOLD/no-mutation mode.`
