# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls the frozen v1.0 Proof boundary.**

**Last execution update:** 2026-09-08  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-07 — Final Validation + Wishket Proof  
**Current batch state:** **CLAIMTRACE PROOF v1.0 CLOSED / FREEZE — HUMAN REVIEW PASSED**  
**Reviewed/tagged commit:** `bcb37b1a86ae70e2f35cdab6708da9310d7e9e2d`  
**Proof tag:** `v1.0-proof`  
**Post-v1 progression state:** **D3 DESTINATION REACHED — HUMAN REVIEW REQUIRED FOR ANY FARTHER DESTINATION**

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

### Milestones P1–P13

The accepted P1–P13 progression history remains preserved in repository history and in the pre-D3 MASTER revisions. Those milestones established deterministic regression reproducibility, bounded ingestion/parse failure terminalization and retry behavior, documentation/roadmap reconciliation, real-stack retry evidence, bounded Korean lexical fallback regression coverage, and D1 controlled-pilot readiness without moving or reinterpreting `v1.0-proof`.

Their accepted implementation/evidence commits and Issue/PR lifecycle remain authoritative in Git history. This reconciliation does not rewrite those accepted results or broaden any claim; it compacts the historical ledger only to keep the active authoritative document focused on accepted destination state.

## 11. Destination Review

### D1 — L4 Controlled ClaimTrace Pilot

**Status:** `DESTINATION REACHED — CONTROLLED PILOT`

The accepted repository evidence sufficiently covers the D1 destination for one analyst/reviewer on a trusted workstation or controlled on-premise environment:

- clean checkout / empty-database migration and deterministic whole-product execution are verified;
- supported text-based Korean patent PDFs can be ingested into source-verifiable persisted page text;
- deterministic claim parsing/dependency handling is inside the accepted boundary, with recoverable ingestion and claim-graph persistence failures terminalized through bounded client-safe contracts;
- explicit operator retry for failed ingestion is available in the Documents UI and has real web/API/PostgreSQL/storage integration evidence;
- hybrid retrieval, grounded ask, target/reference comparison, deterministic decomposition, append-only human review, and navigation back to persisted source evidence are covered by the frozen controlled-pilot Proof and continuing regression workflows;
- deterministic one-command regression plus exact-head CI/evaluation/proof workflows provide reproducible evidence for the supported synthetic/public-safe boundary;
- proof screenshots, architecture visual, source-highlight evidence, human-review evidence, and the golden-path WebM are committed and reproducible.

This destination decision does **not** broaden the product claim boundary. OCR/scanned-PDF recovery, legal conclusions, benchmark-quality general retrieval/semantic correctness, authentication/RBAC/multi-tenancy, public-cloud/Kubernetes readiness, private/customer corpus requirements, and security/compliance certification remain unverified and out of scope.

### Milestone P14 — Package delivery-ready controlled pilot handoff

**Status:** `ACCEPTED / MERGED`  
**Issue:** #59 — `Progression: package a delivery-ready controlled pilot handoff`  
**PR:** #60 — `Package delivery-ready controlled pilot handoff`  
**Accepted PR exact head:** `2fa7dbefd63ea7787165c50be7c31894da358ec1`  
**Resulting main merge SHA:** `e4c21c3e5d506ab3839a071d9995884480c8355e`

#### Changed

- added a repository-native controlled-pilot handoff entry point that reuses existing clean-start, supported failed-ingestion recovery, deterministic whole-product, source-navigation, human-review, and Proof-package assets instead of adding another product/error capability;
- extracted the already-accepted real web/API/PostgreSQL retry proof into a reusable verifier and orchestrated it with clean setup/migration and deterministic whole-product verification;
- added a reviewer-facing evidence/provenance output with committed Proof-asset SHA-256 hashes and an explicit bounded limitations statement;
- added an exact-head PR workflow that executes the coherent handoff and uploads the generated evidence package;
- documented clean-host prerequisites, including Docker Compose plus Node.js 22+ and npm for the reused browser verifier;
- no OCR/scanned-PDF recovery, retrieval/parser/grounding expansion, auth/RBAC/multi-tenancy, cloud/Kubernetes, private-corpus requirement, legal conclusion capability, general semantic benchmark claim, frozen Proof rewrite, or `v1.0-proof` movement was introduced.

#### Actually Executed

On PR #60 exact head `2fa7dbefd63ea7787165c50be7c31894da358ec1`:

- `General CI` run `33770691441`: **GREEN**;
- `Progression Controlled Pilot Handoff` run `33770691476`: **GREEN**;
- generated artifact `controlled-pilot-handoff-2fa7dbefd63ea7787165c50be7c31894da358ec1` was uploaded as artifact ID `9899812446`, digest `sha256:74a1ba0862e101104224e4f7e8091d2b94d34aa2e4f9cad79744bfeac86661ae`;
- downloaded artifact contents were inspected and the report recorded PASS for clean setup/migration, supported failed-ingestion operator recovery, deterministic whole-product analyst/reviewer flow, and present+hashed source-navigation/human-review Proof assets;
- review documentation blocker about Node.js/npm prerequisites was corrected before merge;
- PR #60 was squash-merged with an expected-head SHA guard and Issue #59 auto-closed as `completed`.

#### Verified

- one repository-native documented command packages the supported clean setup/migration → ingest/recovery → retrieve/ask/compare/decompose → human review → source navigation → evidence-handoff path using existing accepted public-safe/synthetic flows;
- exact-head General CI and the dedicated controlled-pilot handoff workflow are GREEN;
- the generated reviewer-facing package contains deterministic evidence hashes and explicit limitations;
- Issue #59 lifecycle completed through guarded merge/close;
- frozen v1.0 Proof baseline and Sections 6–7 limitations/non-claims remain unchanged.

#### Not Verified

- the handoff does not establish OCR/scanned-PDF recovery, production infrastructure resilience, authentication/RBAC/multi-tenancy, public-cloud/Kubernetes readiness, private/customer corpus behavior, security/compliance certification, benchmark-quality general patent retrieval, semantic entailment, or legal correctness;
- the generated artifact is bounded controlled-pilot delivery evidence, not a production certification package.

#### Remaining Risks

- operator handoff still assumes the documented trusted-workstation/on-premise environment and supported text-based/public-safe input boundary;
- handoff reproducibility depends on the documented Docker Compose and Node.js/npm prerequisites;
- all frozen v1.0 limitations and non-claims remain in force.

### D2 Acceptance Update — Delivery-ready Controlled Pilot Handoff

**Status:** `DESTINATION REACHED — DELIVERY-READY CONTROLLED PILOT HANDOFF`

P14 closes the D2 coherence gap. The repository has a single documented, exact-head executable handoff path that reuses accepted capabilities to verify clean setup/migration, one supported operator recovery path, deterministic whole-product analyst/reviewer behavior, source navigation, human review, and a bounded evidence/provenance output with explicit non-claims.

This acceptance is intentionally limited to the same trusted-workstation/on-premise, supported text-based/public-safe boundary. It does not convert source resolvability into semantic entailment or legal correctness and does not establish production security/cloud readiness.

## 12. D3 — Real-document Controlled Pilot

**Human Review decision date:** `2026-09-07`  
**Destination state:** `DESTINATION REACHED — REAL-DOCUMENT CONTROLLED PILOT`  
**Accepted bounded milestone:** `D3-01 — verify a real-public-document controlled pilot corpus`  
**Issue:** #61  
**PR:** #62  
**Accepted PR exact head:** `5b3752c271283e345310f25b15e0da4941f3cb80`  
**Resulting main merge SHA:** `2f587a09ffac70a9c338799a782c9a069ed7dcef`

D3 reuses the accepted D1 Controlled Pilot and D2 Delivery-ready Controlled Pilot Handoff assets to establish whether one analyst/reviewer can repeatedly use ClaimTrace on a small bounded corpus of real public **text-based Korean patent documents** while preserving source-verifiable ingest → parse → retrieve → ask/compare/decompose → human review → source navigation behavior.

D3 is not a general patent-analysis accuracy benchmark and does not broaden the frozen legal/non-claim boundary. Real-corpus evidence supplements the accepted deterministic public-safe/synthetic evidence; it does not replace or reinterpret it.

### D3-01 acceptance boundary

D3-01 remains one bounded real-public-document acceptance milestone. Its accepted verifier:

- records canonical source/provenance metadata sufficient for a reviewer to retrieve/check each selected public document;
- consumes public PDFs during verification rather than committing third-party PDF bytes;
- pins the SHA-256 and publication identity of every accepted input and fails closed on mismatch;
- distinguishes supported text-based PDFs from unsupported/scanned/image-only inputs and persists explicit failure evidence before nonzero exit;
- executes ingestion, text extraction, supported claim parsing, indexing, retrieval, grounded citation resolution, comparison, decomposition, append-only review mechanics, and source navigation against the real corpus;
- emits reproducible per-document/per-step evidence;
- reruns the deterministic synthetic regression/evidence gates as regression protection.

### Accepted source provenance

The accepted bounded corpus contains two public Korean patent publications:

1. `KR20150055205A` — publication display `10-2015-0055205`, title `다중 경로 안내 텔레매틱스 시스템`, accepted PDF SHA-256 `e9a6cf151af6ec5e3837b9c2912f198fd937c6b29b0ed61bcb1aa79af3b80819`.
2. `KR20170054782A` — publication display `10-2017-0054782`, title `내비게이션 경로 재탐색을 위한 장치 및 방법`, accepted PDF SHA-256 `206ed95187b78d7793753c924dfc2f3a4023ce6c6188bd75613efc57915167f5`.

The source PDFs were acquired from public patent publication surfaces at verification time and were **not committed** to the repository. The verifier validates both pinned SHA-256 and expected publication identity before an input can become `supported_text_pdf`.

### D3-01 acceptance evidence

#### Changed

- added a bounded manifest-driven real-public corpus definition with canonical source/provenance metadata, publication identity, and pinned SHA-256 values;
- added repository-owned fail-closed input verification that persists unsupported/failure classifications into structured evidence;
- added a dedicated D3 exact-head workflow and product-path acceptance harness reusing existing ClaimTrace APIs and accepted deterministic providers;
- preserved frozen v1.0, D1, D2, legal/non-claim boundaries, synthetic regression evidence, and `v1.0-proof` without movement or reinterpretation.

#### Actually Executed

On PR #62 exact head `5b3752c271283e345310f25b15e0da4941f3cb80`:

- all 13 triggered PR workflows completed **GREEN**;
- `Progression D3 Real Public Corpus` run `34162022664`: **GREEN**;
- `General CI` run `34162022697`: **GREEN**;
- `Progression Deterministic Regression` run `34162022646`: **GREEN**;
- `V1-02 Claim Comparison Verification` run `34162022607`: **GREEN**;
- `V1-03 Comparison UI Verification` run `34162022609`: **GREEN**;
- `V1-04 Claim Element Verification` run `34162022626`: **GREEN**;
- `V1-05 Human Review Verification` run `34162022638`: **GREEN**;
- `V1-06 Clean Start Verification` run `34162022643`: **GREEN**;
- `V1-06 Whole-Product Golden Path` run `34162022655`: **GREEN**;
- `V1-06 Expected Failure States` run `34162022637`: **GREEN**;
- `V1-07 Final Evaluations` run `34162022610`: **GREEN**;
- `V1-07 Proof Package` run `34162022671`: **GREEN**;
- `Progression Controlled Pilot Handoff` run `34162022613`: **GREEN**;
- D3 artifact `d3-real-public-corpus-5b3752c271283e345310f25b15e0da4941f3cb80` was uploaded as artifact ID `10032926414`, digest `sha256:829fa3708874325b6df8532bc66f2028cefa5f0bf34abf0b19bd8b1185bde1bd`;
- the artifact was inspected and records PASS across the accepted per-document and analyst/reviewer product-path steps;
- both PR review blockers—source identity/hash pinning and structured unsupported/failure evidence persistence—were corrected and both threads were resolved;
- PR #62 was squash-merged with expected-head protection to main merge SHA `2f587a09ffac70a9c338799a782c9a069ed7dcef`;
- Issue #61 auto-closed as `completed`.

#### Verified

For both accepted real public documents:

- runtime acquisition matched the pinned SHA-256 and expected Korean publication identity;
- text-support classification was `supported_text_pdf` rather than an implicit fallback;
- ingestion and persisted page extraction completed;
- supported claim parsing and indexing completed;
- canonical source locators resolved back to persisted source text;
- retrieval returned source-backed locators;
- the grounded analytical path produced resolvable citations under the deterministic provider contract;
- target/reference comparison remained traceable to persisted source spans;
- decomposition remained traceable to persisted source text;
- append-only human-review mechanics were exercised;
- source-navigation contracts remained usable;
- existing deterministic synthetic regression/evidence protection remained GREEN;
- unsupported/failure states remain fail-closed and artifact-preserving rather than silently promoted to PASS.

#### Not Verified / limitations

D3-01 does **not** verify or claim:

- infringement, validity, novelty, equivalence, inventive step, patentability, legal advice, or any other legal conclusion;
- benchmark-quality general retrieval, semantic accuracy, entailment, or universal Korean patent parsing correctness;
- model quality from the deterministic fake embedding/LLM providers;
- substantive reviewer/legal judgement from the automated `needs_correction` review exercise; that step verifies append-only review mechanics only;
- OCR/scanned/image-only PDF recovery;
- private/customer corpus onboarding, copying, publication, or private-data behavior;
- authentication, RBAC, multi-tenancy, billing, public cloud/Kubernetes, production admin readiness, or security/compliance certification;
- broad parser/retrieval/model quality expansion.

#### Remaining Risks

- the accepted corpus is intentionally small and establishes only the bounded real-document controlled-pilot invariant, not general patent-analysis correctness;
- public acquisition surfaces or bytes can change; pinned SHA-256 and publication identity therefore remain fail-closed acceptance guards rather than assumptions;
- deterministic fake providers exercise workflow/provenance mechanics but not real-model semantic quality;
- substantive analyst/reviewer judgement remains a human boundary;
- all frozen v1.0 Sections 6–7 limitations and non-claims remain in force.

### D3 Destination Review

**Status:** `D3 DESTINATION REACHED — REAL-DOCUMENT CONTROLLED PILOT`

D3-01 closes the demonstrated D3 gap. The accepted evidence now shows that the existing controlled-pilot/handoff assets can execute against a bounded corpus of real public text-based Korean patent PDFs while preserving source-verifiable ingest → parse → retrieve → grounded analysis → comparison/decomposition → append-only review mechanics → source navigation, with exact-head reproducible evidence and explicit unsupported/failure handling.

No demonstrated blocker currently justifies D3-02. Opening another corpus variant, retrieval metric, parser edge-case sweep, or additional proof-of-proof layer solely to continue progression would violate the anti-micro-loop boundary. OCR, private/customer corpora, generalized semantic/legal accuracy, authentication/multi-tenancy, cloud/Kubernetes, or comparable expansion would require a separate Human Review product decision.

### Exact Next Action

`HUMAN REVIEW — NEXT DESTINATION DECISION`

Do not open another automatic ClaimTrace progression milestone. Preserve `v1.0-proof`, accepted D1/D2/D3 evidence, the controlled-pilot boundary, public-safe source handling, and all legal/non-claim limitations until a human explicitly selects a farther destination.
