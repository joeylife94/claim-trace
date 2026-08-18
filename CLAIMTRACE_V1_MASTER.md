# ClaimTrace v1.0 Master

> **Authoritative execution document for ClaimTrace v1.0.**
>
> Read this file before starting any implementation batch. This document defines the product boundary, current state, acceptance criteria, verification evidence, and closure condition for the v1.0 effort.
>
> `README.md` explains the project to readers. `docs/ARCHITECTURE.md` explains system design. `docs/ROADMAP.md` records the broader technical roadmap. **This file controls what we are actually finishing now.**

---

## 1. Goal

Turn ClaimTrace from a strong functional MVP into a **controlled-pilot-level product that a real user can operate and a client can inspect as credible proof of delivery capability**.

ClaimTrace v1.0 must demonstrate that a single user can take text-based Korean patent PDFs through a complete, reviewable workflow:

**ingest → parse → index → retrieve → ask → compare → review → verify source evidence**

The goal is not to create a production SaaS or to automate legal judgement.

---

## 2. Target User

Primary target:

- one analyst, engineer, researcher, or reviewer;
- operating on a trusted workstation or controlled on-premise environment;
- working with text-based Korean patent PDFs;
- needing retrieval and comparison results that can be checked against original source text.

The v1.0 user is **not** a public anonymous internet user and **not** a multi-tenant enterprise deployment.

---

## 3. Target Product Level

### Level model

| Level | Meaning | Status |
| --- | --- | --- |
| L1 | Idea / proof of concept | Passed |
| L2 | Technical demo | Passed |
| L3 | Functional MVP | **Current** |
| L4 | Controlled pilot / usable by a real single user | **v1.0 target** |
| L5 | Production SaaS / enterprise operations | Out of scope |

### v1.0 definition

**ClaimTrace v1.0 is a single-user, on-premise patent analysis pilot for text-based Korean patent PDFs. It structures claims, retrieves related evidence, produces evidence-grounded answers, supports bounded document/claim comparison, preserves reviewable source provenance, and exposes limitations instead of inventing certainty.**

---

## 4. Current State

Current repository state is **Phase 4A-2 complete / late Functional MVP**.

### Implemented and already proven

- FastAPI backend and Next.js frontend.
- PostgreSQL 17 + pgvector + pg_trgm.
- PDF ingestion with upload validation and explicit failure codes.
- Content-addressed local storage and SHA-256 duplicate policy.
- Page-level persisted text and canonical `SourceLocator` provenance.
- Deterministic Korean claim structural parsing.
- Claim dependency graph and claim classifications.
- Claim spans that preserve exact page-relative source ranges.
- Claim indexing lifecycle and retrieval profiles.
- Dense retrieval with multilingual embeddings.
- Korean-aware lexical retrieval.
- Reciprocal Rank Fusion hybrid retrieval.
- Search results carrying per-channel ranking metadata and source spans.
- Local/self-hosted LLM provider boundary.
- Ollama provider.
- OpenAI-compatible local provider boundary.
- Deterministic fake provider for offline tests.
- Strict structured-output parsing and validation.
- Evidence-grounded answering using server-issued evidence identifiers.
- Server-side citation resolution back to persisted source text.
- Explicit `insufficient_evidence` behavior.
- Grounded-answer UI with evidence links.
- Deterministic and real-local-model evaluation tiers.
- Hostile evidence / forged citation guardrail coverage.
- Docker Compose development environment.
- Backend, integration, lint, formatting, frontend lint, and typecheck commands.

### Existing verification evidence

Repository documentation currently records:

- **876 backend tests** after Phase 4A-2.
- Grounded deterministic evaluation with citation resolution `1.000`.
- Real `qwen2.5:1.5b` grounded evaluation with citation resolution `1.000`.
- Statement citation coverage `1.000` in that real-model evaluation.
- Forbidden cross-document citations: `0` in that evaluation.
- Honest model-quality weakness remains: the small local model does not establish production-grade patent reasoning quality.

### Current product gap

The system has strong components but the **real user workflow is not closed yet**.

The main missing product-level capabilities are:

1. bounded claim/document comparison;
2. claim element decomposition with a human review boundary;
3. a coherent UI golden path that connects existing capabilities;
4. reproducible clean-checkout/demo validation;
5. persistent CI evidence;
6. visual/public proof packaging suitable for third-party review.

---

## 5. v1.0 Supported Workflow

The v1.0 golden path is frozen as follows:

1. Upload a text-based patent PDF.
2. Validate and persist the document.
3. Extract page text with canonical source locators.
4. Parse claim structure and dependencies.
5. Review claims and jump to exact source spans.
6. Index claims for retrieval.
7. Search using dense, lexical, or hybrid retrieval.
8. Open any retrieval result at its original source location.
9. Ask an evidence-grounded question.
10. Receive cited statements or an explicit insufficient-evidence outcome.
11. Select a target document and a reference document.
12. Select a target claim and retrieve/compare related claims in the reference document.
13. Decompose a claim into reviewable elements/limitations while preserving source spans.
14. Allow the human reviewer to accept or mark decomposition output as needing correction.
15. Verify every rendered analytical assertion back to persisted source evidence.

If this workflow is complete, reproducible, and validated, **feature development for v1.0 stops**.

---

## 6. In Scope

### Product flow closure

- A clear UI path through upload, parse, index, search, grounded answer, compare, and review.
- Explicit empty/loading/error/retry states for the supported path.
- No requirement for users to use raw API endpoints for the primary demonstration workflow.

### Claim comparison

- Select two indexed documents.
- Select a target claim.
- Retrieve relevant claims from the reference document under strict document scope.
- Present side-by-side textual correspondence.
- Reuse existing evidence catalog and source locator guarantees.
- Support explicit `no corresponding claim found` / insufficient-evidence behavior.
- Never output infringement, validity, novelty, equivalence, or patentability conclusions.

### Claim element decomposition and review

- Decompose claims into individually addressable elements/limitations.
- Preserve page-anchored source spans for every element.
- Keep parser/model output separate from human review state.
- Allow review acceptance or `needs correction` state.
- Ensure re-processing does not silently destroy human review history.

### Operational hardening

- Clean-checkout execution path.
- Reproducible database migration path.
- Deterministic committed demo/sample data.
- One documented golden-path demo procedure.
- CI-backed quality gates.
- Failure states for expected unsupported inputs.
- Logging/privacy behavior consistent with the existing on-premise boundary.

### Proof packaging

- README optimized for fast external review.
- Architecture visual.
- Product screenshots.
- Demo GIF or short demo recording plan/assets.
- Evaluation summary.
- Visible CI state.
- Explicit limitations.
- v1.0 release/tag.

---

## 7. Explicit Non-Goals

The following are **not required for ClaimTrace v1.0** and must not be added unless this master document is deliberately re-scoped first:

- OCR or scanned-PDF recovery.
- Authentication.
- Authorization / RBAC.
- Multi-tenancy.
- Public cloud hosting.
- Kubernetes.
- Production deployment pipelines.
- Billing.
- Admin console.
- Team workspace features.
- Chat history.
- Conversation memory.
- Streaming responses.
- General tool calling.
- Email/notification workflows.
- Broad observability platform work.
- Full multilingual patent support.
- Hosted third-party LLM APIs as a default product path.
- Legal advice.
- Patent infringement determination.
- Validity determination.
- Novelty determination.
- Inventive-step determination.
- Patentability determination.

A feature being useful later is not sufficient reason to include it in v1.0.

---

## 8. Work Tracks

### Track P1 — Product Flow Closure

**Goal:** make the supported workflow usable end-to-end from the web UI.

Primary work:

- audit the current pages and transitions;
- remove dead ends in the golden path;
- add explicit next actions between stages;
- add missing loading, empty, failure, and retry states;
- ensure source verification is reachable from every analytical result.

**Closure:** a user can complete the v1.0 primary workflow without relying on API docs or manual database work.

### Track P2 — Analysis Completion

**Goal:** close the minimum analytical workflow missing from the current MVP.

Primary work:

- claim comparison workspace;
- strict document-scoped comparison retrieval;
- no-correspondence state;
- claim element decomposition;
- element-level provenance;
- persisted human review boundary.

**Closure:** a target claim can be compared with a reference document and decomposed into reviewable source-backed elements without producing legal conclusions.

### Track P3 — Operational Hardening

**Goal:** make the supported product reproducible rather than locally anecdotal.

Primary work:

- clean clone/start verification;
- migration verification;
- deterministic sample/demo dataset;
- repeatable demo procedure;
- CI quality gates;
- expected failure-path verification;
- operational documentation gaps.

**Closure:** a clean checkout can reproduce the supported demo path using documented commands and produces persistent green quality evidence.

### Track P4 — Validation and Proof Packaging

**Goal:** convert the completed product into externally reviewable proof.

Primary work:

- final regression/evaluation run;
- proof metrics snapshot;
- architecture visual;
- screenshots;
- demo capture;
- README restructuring;
- limitations snapshot;
- release/tag.

**Closure:** a reviewer can understand the problem, inspect the solution, see evidence, and reproduce the demo from the repository without reading the full architecture document first.

---

## 9. Acceptance Criteria

### Functional acceptance

- [ ] Text-based PDF upload works through the supported UI.
- [ ] Claim parsing works and preserves source spans.
- [ ] Claim indexing works.
- [ ] Dense, lexical, and hybrid search work.
- [ ] Search results resolve to exact source evidence.
- [ ] Grounded Q&A returns only source-backed statements or explicit insufficient evidence.
- [ ] Two-document claim comparison works under strict document scope.
- [ ] Comparison has an explicit no-correspondence/insufficient-evidence state.
- [ ] Claim element decomposition produces source-backed elements.
- [ ] Human review state for decomposition is persisted separately from machine output.
- [ ] Primary analytical UI results can navigate back to original source text.

### Operational acceptance

- [ ] Clean checkout setup is documented and verified.
- [ ] Docker Compose supported path starts successfully.
- [ ] Database migrations apply cleanly from an empty database.
- [ ] Committed demo/sample material is sufficient to run the golden path.
- [ ] One deterministic demo procedure is documented.
- [ ] Expected unsupported-input states are explicit and user-readable.
- [ ] CI runs backend tests and required quality gates.
- [ ] CI runs PostgreSQL-backed integration coverage.
- [ ] Frontend lint and TypeScript checks run in CI.

### Validation acceptance

- [ ] Full automated test suite passes from the v1.0 candidate commit.
- [ ] Retrieval evaluation is reproducible.
- [ ] Grounded-generation deterministic evaluation is reproducible.
- [ ] Real local model validation is rerun or explicitly marked not rerun.
- [ ] Citation resolution remains verified.
- [ ] Document-scope leakage test passes.
- [ ] Forged/hostile evidence identifier tests pass.
- [ ] Known model-quality limitations are reported without being hidden by grounding metrics.

### Proof acceptance

- [ ] README communicates the problem and solution before deep implementation details.
- [ ] Architecture visual exists.
- [ ] At least four useful product screenshots exist.
- [ ] A concise golden-path demo asset exists or is captured.
- [ ] CI status is externally visible.
- [ ] Proof metrics are linked to reproducible evidence.
- [ ] Known limitations are visible.
- [ ] v1.0 proof release/tag exists.

---

## 10. Execution Rules

Every implementation batch must begin by reading this file.

A batch must define:

1. **Goal** — the smallest useful outcome of the batch.
2. **Scope** — files/surfaces allowed to change.
3. **Acceptance** — observable pass conditions.
4. **Non-goals** — what the batch must not expand into.

Every batch completion report must contain exactly these evidence categories:

### What changed

Concrete code/document/schema changes only.

### What was actually executed

Commands, test suites, migrations, evaluations, or manual flows that were really run.

### What was not verified

Anything claimed by design or code inspection but not executed.

### Remaining risks

Known gaps, uncertainty, regressions, or follow-up work.

**Implementation-agent self-report is not final verification.** A statement such as `tests should pass` is not evidence.

---

## 11. Current Batch

### Batch V1-00 — Master Freeze

**Status:** CLOSED

**Goal:** define the current product level, v1.0 target, product boundary, execution tracks, acceptance criteria, and closure condition before further implementation.

**Changed:**

- created `CLAIMTRACE_V1_MASTER.md`;
- defined current state as late L3 Functional MVP;
- froze v1.0 target as L4 Controlled Pilot;
- froze the supported workflow;
- froze explicit non-goals;
- defined four execution tracks;
- defined acceptance and closure criteria.

**Executed:**

- repository state reviewed against current `README.md`, `docs/ROADMAP.md`, current web surfaces, committed evaluation reports, and recent Phase 4A-2 commit history before creating this document.

**Not verified in this batch:**

- no application build was run;
- no test suite was rerun;
- no Docker environment was started;
- no migration was applied;
- no UI flow was manually executed.

**Remaining risks:**

- actual clean-checkout reproducibility is not yet proven;
- current UI workflow may contain dead ends not visible from static repository inspection;
- the documented 876-test result is historical evidence until rerun on the current v1 candidate;
- there is currently no persistent CI status on the inspected HEAD;
- comparison and element-review capabilities remain unimplemented.

---

## 12. Next Batch

### Batch V1-01 — Golden Path Gap Audit

**Status:** NEXT

**Goal:** establish the exact delta between the existing UI/API and the frozen v1.0 supported workflow before implementing new product features.

### Required output

A concise gap table covering each golden-path stage:

- existing implementation;
- existing UI entry point;
- missing transition/action/state;
- required change for v1.0;
- evidence needed to close it.

### Acceptance

- every stage in Section 5 is classified as `READY`, `PARTIAL`, or `MISSING`;
- comparison and element-review gaps are decomposed into the smallest implementation batches;
- no feature outside Section 6 is added;
- the result updates `Current State`, `Current Batch`, `Verification Evidence`, and `Remaining Risks` in this file.

### Non-goals

- do not implement Phase 5A in this batch;
- do not add OCR/auth/cloud/deployment features;
- do not redesign the entire UI;
- do not rewrite existing architecture documentation.

---

## 13. Verification Evidence

Evidence accepted here must be tied to an executed command, committed evaluation artifact, or human-visible inspected behavior.

### Baseline evidence before v1.0 hardening

| Evidence | State | Source / note |
| --- | --- | --- |
| Phase 4A-2 feature set | VERIFIED BY REPO INSPECTION | README / roadmap / implementation history |
| Backend test count: 876 | HISTORICAL EXECUTED EVIDENCE | Phase 4A-2 documentation and commit history; must be rerun for v1 candidate |
| Deterministic citation resolution 1.000 | COMMITTED EVALUATION | grounded deterministic evaluation |
| Ollama citation resolution 1.000 | COMMITTED EVALUATION | `qwen2.5:1.5b`, synthetic corpus |
| Ollama statement citation coverage 1.000 | COMMITTED EVALUATION | synthetic corpus |
| Forbidden scoped citations 0 | COMMITTED EVALUATION | synthetic corpus |
| Clean-checkout reproduction | NOT VERIFIED | V1-03 work |
| Current CI green state | NOT PRESENT / NOT VERIFIED | persistent CI to be added |
| Golden-path manual UI run | NOT VERIFIED | V1-01/V1-03 work |
| Claim comparison | NOT IMPLEMENTED | V1-02 work |
| Claim element review | NOT IMPLEMENTED | V1-02+ work |

---

## 14. Known Risks / Unverified

- A valid citation proves resolvability to stored evidence, **not semantic entailment**.
- Current real-model evaluation uses a small `qwen2.5:1.5b` model and synthetic data; it is pipeline evidence, not patent-analysis quality proof.
- OCR is deliberately unsupported; scanned/image-only PDFs must fail clearly.
- Korean deterministic claim parsing has bounded supported patterns and should not be represented as universal patent parsing.
- Comparison quality will depend on retrieval quality and must not be represented as legal similarity.
- Claim element decomposition is a domain-judgement boundary and therefore requires persisted human review rather than silent machine authority.
- Current historical test/evaluation evidence must be refreshed before release closure.
- No public multi-user security model is part of this release.

---

## 15. Closure Condition

ClaimTrace v1.0 is **CLOSED** only when all of the following are true:

### Done enough to use

- the full frozen golden path is executable by a single user;
- expected failures are explicit rather than silent;
- source verification is available for analytical output;
- comparison and decomposition/review are usable at the controlled-pilot level.

### Done enough to trust

- clean checkout is reproduced;
- migrations are reproduced;
- CI is green;
- automated tests pass;
- retrieval and grounding evaluations are reproducible;
- source-scope and hostile-evidence guardrails pass;
- unverified areas are explicitly recorded.

### Done enough to show

- README is proof-oriented;
- architecture visual exists;
- screenshots exist;
- concise demo evidence exists;
- evaluation results and limitations are visible;
- a v1.0 release/tag freezes the proof state.

When these conditions are met, **stop adding features to v1.0**.

Any later OCR, authentication, multi-user, deployment, broader language, or advanced analysis work starts as a separately scoped post-v1 effort.
