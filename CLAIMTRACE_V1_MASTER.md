# ClaimTrace v1.0 Master

> **Authoritative execution document for ClaimTrace v1.0.**
>
> Read this file before every implementation batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains system design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what ClaimTrace v1.0 is actually finishing now.**

**Last execution update:** 2026-08-19  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-03 — Comparison UI + Flow Stitching  
**Current batch state:** **IN PROGRESS**

---

## 1. Goal

Turn ClaimTrace from a strong late-L3 Functional MVP into a **single-user controlled-pilot product that can be operated, reviewed, reproduced, and shown as credible delivery proof**.

Frozen v1.0 flow:

**ingest → parse → index → retrieve → ask → compare → decompose → review → verify source evidence**

The v1.0 goal is **not** production SaaS and **not** automated legal judgement.

---

## 2. Product Boundary

Target user:

- one analyst, engineer, researcher, or reviewer;
- trusted workstation or controlled on-premise environment;
- text-based Korean patent PDFs;
- analytical output must be checkable against original source text.

### Explicit non-goals

Do not add these unless this master is deliberately re-scoped:

- OCR / scanned-PDF recovery;
- authentication / RBAC / multi-tenancy;
- public cloud hosting / Kubernetes / production deployment pipelines;
- billing / admin console / team workspace;
- chat history / memory / streaming / general tool calling / notifications;
- broad observability platform work;
- full multilingual support;
- hosted third-party LLM APIs as the default path;
- legal advice or determinations of infringement, validity, novelty, equivalence, inventive step, or patentability.

---

## 3. Current State

### Existing engine

Already implemented before v1 hardening:

- FastAPI + Next.js, PostgreSQL 17 + pgvector + pg_trgm;
- PDF validation/persistence, SHA-256 identity, explicit ingestion failures;
- page-level text with canonical `SourceLocator` provenance;
- deterministic Korean claim parsing, dependencies, and page-relative claim spans;
- dense, lexical, and RRF hybrid retrieval with exact source links;
- local/self-hosted LLM boundary: Ollama, OpenAI-compatible local endpoint, deterministic fake provider;
- strict structured-output validation and evidence-grounded Q&A using server-issued evidence IDs;
- server-side citation resolution, explicit `insufficient_evidence`, grounded UI/source navigation;
- deterministic + real-local-model evaluation tiers and hostile-evidence guardrails;
- Docker Compose development environment.

### Historical evidence

- 876 backend tests recorded after Phase 4A-2;
- deterministic grounded citation resolution `1.000`;
- `qwen2.5:1.5b` grounded citation resolution `1.000`;
- real-model statement citation coverage `1.000`;
- forbidden cross-document citations `0` in committed evaluation.

These remain historical/committed evidence until rerun for the v1 candidate.

### Golden-path state

| Stage | Status | v1 delta |
| --- | --- | --- |
| 1–10: ingest through grounded Q&A | READY | Runtime re-verification only |
| 11: target/reference selection | PARTIAL | Backend contract ready; UI is V1-03 |
| 12: claim comparison | BACKEND CLOSED | Executed V1-02 verification GREEN |
| 13: element decomposition | MISSING | V1-04 |
| 14: persisted human review | MISSING | V1-05 |
| 15: source verification on all analytical surfaces | PARTIAL | Search/Q&A + comparison backend provenance ready; UI/decomposition must inherit guarantee |

**Do not rebuild stages 1–10.**

---

## 4. Execution Plan

### V1-00 — Master Freeze
**Status:** CLOSED

### V1-01 — Golden Path Gap Audit
**Status:** CLOSED

### V1-02 — Claim Comparison Backend
**Status:** **CLOSED**

Goal: smallest source-backed two-document claim comparison capability.

Acceptance:

- [x] comparison request/response contract exists;
- [x] target and reference documents must be distinct;
- [x] target claim text is the comparison query, not arbitrary caller text;
- [x] target comparison requires a completed claim parse result;
- [x] unknown target/reference document handling is explicit;
- [x] retrieval is scoped to exactly one reference document;
- [x] service performs a defensive second scope-leak check;
- [x] target and reference results carry canonical source spans;
- [x] each comparison claim response requires at least one source span and every span belongs to that claim's document;
- [x] `reference_not_indexed` and `no_matches` are distinguishable;
- [x] API response has no legal-conclusion field;
- [x] response model enforces coherent scope/count/no-correspondence state;
- [x] database-free service/API/edge/schema tests exist and executed successfully;
- [x] PostgreSQL-backed integration tests exist and executed successfully for strict reference scope and source-span resolution;
- [x] focused closure command exists: `make verify-v1-02`;
- [x] exact-head GitHub Actions verification succeeded;
- [x] comparison pytest tests executed successfully;
- [x] Ruff lint/format checks executed successfully;
- [x] live PostgreSQL-backed scoped retrieval executed successfully.

Executed closure evidence:

- verification PR: **#7** `ci: expose V1-02 verification on pull requests`;
- PR exact head: `f62b8847ec3bfd6df4ecf1750b6a0e5d90202f6c`;
- final PR-head workflow run: **32225430081** — `success`;
- database-free comparison tests: **26 PASS**;
- PostgreSQL-backed comparison integration tests: **3 PASS, 0 skipped**;
- Ruff lint: **All checks passed**;
- Ruff format: **141 files already formatted**;
- Docker API build and PostgreSQL readiness succeeded;
- fixes inside PR #7 were limited to concrete executed failures: PR-visible trigger, `reference_not_indexed` fixture count, pytest summary guard, writable Ruff cache, one unused import, and Ruff formatting;
- PR #7 merged to `main` as `db5e39d2118e42527a3794a32173e08535f18cec`.

### V1-03 — Comparison UI + Flow Stitching
**Status:** **IN PROGRESS**

Goal: make the closed comparison backend usable from the web UI and connect it to the existing document workflow.

Scope:

- `/compare` workspace;
- target/reference document selectors;
- target-claim selector;
- side-by-side source-backed results;
- direct source navigation;
- explicit no-match/error/loading states;
- contextual links from document detail to search, grounded Q&A, and comparison.

Acceptance:

- [ ] user can choose two distinct documents and one target claim in the web UI;
- [ ] UI calls the existing `POST /api/v1/compare/claims` contract without inventing a parallel comparison path;
- [ ] target and reference results render separately and preserve document identity;
- [ ] every rendered comparison result can navigate to exact source text;
- [ ] `reference_not_indexed` and `no_matches` are explicit user-visible states;
- [ ] loading and API error states are explicit;
- [ ] document detail exposes contextual navigation to search, grounded Q&A, and comparison where valid;
- [ ] focused frontend checks for changed V1-03 surfaces execute successfully on exact PR head.

Non-goals:

- no comparison backend re-hardening unless a concrete V1-03 execution failure proves it is required;
- no claim element decomposition;
- no human review persistence;
- no legal semantic judgement;
- no redesign of unrelated pages.

### V1-04 — Claim Element Decomposition
**Status:** PLANNED

- element schema/persistence;
- deterministic decomposition boundary;
- source sub-spans;
- versioned/idempotent run;
- warnings for resistant claims;
- API + tests.

### V1-05 — Human Review Boundary
**Status:** PLANNED

- review record separate from machine output;
- `accepted` / `needs_correction`;
- review survives reprocessing;
- review UI + source navigation;
- persistence tests.

### V1-06 — Operational Hardening
**Status:** PLANNED

- clean clone/start;
- empty-DB migration;
- deterministic demo data;
- golden-path procedure;
- general CI backend/integration/lint/frontend gates;
- failure-state validation.

### V1-07 — Final Validation + Wishket Proof
**Status:** PLANNED

- final test/evaluation run;
- README restructure;
- architecture visual;
- ≥4 useful screenshots;
- demo asset;
- limitations snapshot;
- v1.0 release/tag.

---

## 5. Execution Rules

Every batch defines: **Goal / Scope / Acceptance / Non-goals**.

Every batch update records:

### What changed
Concrete source/schema/document changes.

### What was actually executed
Commands, tests, migrations, evaluations, or inspected runtime behavior actually performed.

### What was not verified
Anything not executed.

### Remaining risks
Known uncertainty or follow-up work.

### Exact next action
One smallest non-redundant action that advances the active batch.

**Implementation-agent self-report is not final verification. `Tests should pass` is not evidence.**

PR lifecycle for focused batch work:

1. inspect active focused PR and its exact-head pull-request-visible workflows first;
2. RED → inspect first failing job/step/log and fix only the executed failure;
3. GREEN + in scope + no unresolved review/security/human-decision blocker → merge with expected-head guard;
4. update this MASTER on `main` with concrete executed evidence and main SHA;
5. continue to the next smallest batch step.

Human Review is the final release/proof gate, not a requirement for ordinary bounded intermediate PR merges.

---

## 6. Current Batch Record — V1-03

### What changed

- synchronized stale V1-02 BLOCKED state to the executed PR #7 GREEN evidence;
- closed V1-02 because every listed V1-02 acceptance criterion is now covered by executed evidence;
- advanced the active batch to V1-03;
- no V1-03 source behavior has been merged yet.

### What was actually executed

- read this MASTER before implementation;
- inspected open PRs and confirmed there is no active focused V1-03 PR;
- verified PR #7 is merged;
- verified PR #7 exact head `f62b8847ec3bfd6df4ecf1750b6a0e5d90202f6c`;
- verified workflow run `32225430081` is completed with conclusion `success`;
- verified `main` points to merge commit `db5e39d2118e42527a3794a32173e08535f18cec` before this MASTER synchronization;
- inspected the existing comparison backend contract and current frontend library/page structure to prepare the smallest V1-03 PR.

### What was not verified

- no V1-03 frontend implementation has executed yet;
- no `/compare` browser flow exists yet;
- no V1-03 frontend lint/typecheck evidence exists yet.

### Remaining risks

- V1-03 must reuse the existing backend contract exactly rather than creating a parallel client-side comparison model;
- source links must preserve exact document/page/character identity;
- the unrelated draft proof PR #6 is outside this active batch and must not be mixed into V1-03.

### Exact next action

**Create the smallest bounded V1-03 PR that adds the typed web comparison client + `/compare` workspace with document/claim selection and source-backed result rendering, then use exact-head PR-visible frontend checks to decide whether it is safe to merge.**

---

## 7. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| Phase 4A-2 engine | VERIFIED BY REPO INSPECTION | existing implementation |
| Historical backend tests: 876 | HISTORICAL EXECUTED EVIDENCE | rerun required before release |
| Deterministic citation resolution 1.000 | COMMITTED EVALUATION | pre-v1 baseline |
| Ollama citation resolution 1.000 | COMMITTED EVALUATION | synthetic corpus |
| Forbidden scoped citations 0 | COMMITTED EVALUATION | grounded baseline |
| Existing stages 1–10 | VERIFIED BY STATIC INSPECTION | V1-01 |
| V1-02 comparison backend | **EXECUTED GREEN / CLOSED** | PR #7, run `32225430081` |
| V1-02 database-free tests | **26 PASS** | exact PR head |
| V1-02 PostgreSQL integration | **3 PASS / 0 skipped** | exact PR head |
| V1-02 Ruff lint | **PASS** | `All checks passed` |
| V1-02 Ruff format | **PASS** | `141 files already formatted` |
| V1-02 merged main | **VERIFIED** | `db5e39d2118e42527a3794a32173e08535f18cec` |
| V1-03 comparison UI | NOT IMPLEMENTED | active batch |
| Element decomposition | NOT IMPLEMENTED | V1-04 |
| Persisted human review | NOT IMPLEMENTED | V1-05 |

---

## 8. Known Risks / Unverified

- Citation resolvability is not semantic entailment.
- Current real-model evidence uses a small `qwen2.5:1.5b` model and synthetic data.
- OCR is intentionally unsupported.
- Korean rule-based claim parsing supports bounded patterns, not all patents.
- Comparison quality depends on retrieval quality and is **not legal similarity**.
- Element decomposition is a domain-judgement boundary and requires human review.
- Current test/evaluation evidence must be refreshed before release closure.
- No public multi-user security model belongs to v1.0.

---

## 9. Closure Condition

ClaimTrace v1.0 is **CLOSED** only when all three are true:

### Done enough to use

- full frozen workflow usable by a single user;
- expected failures explicit;
- source verification available for analytical output;
- comparison + decomposition/review usable at controlled-pilot level.

### Done enough to trust

- clean checkout + migrations reproduced;
- general CI green by release hardening;
- automated tests pass;
- retrieval/grounding evaluations reproducible;
- comparison/decomposition provenance checks pass;
- scope and hostile-evidence guards pass;
- unverified areas explicitly recorded.

### Done enough to show

- proof-oriented README;
- architecture visual;
- screenshots;
- concise demo evidence;
- visible evaluation results and limitations;
- v1.0 release/tag freezes proof state.

When these conditions are met, **stop adding features to v1.0**.
