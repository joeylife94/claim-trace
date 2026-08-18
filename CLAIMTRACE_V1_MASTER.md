# ClaimTrace v1.0 Master

> **Authoritative execution document for ClaimTrace v1.0.**
>
> Read this file before every implementation batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains system design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what ClaimTrace v1.0 is actually finishing now.**

**Last execution update:** 2026-08-19  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-02 — Claim Comparison Backend

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
- needs analytical output that can be checked against original source text.

> **ClaimTrace v1.0 is a single-user, on-premise patent analysis pilot for text-based Korean patent PDFs. It structures claims, retrieves related evidence, produces evidence-grounded answers, supports bounded document/claim comparison, decomposes claims into reviewable source-backed elements, preserves human review separately from machine output, and exposes limitations instead of inventing certainty.**

| Level | Meaning | Status |
| --- | --- | --- |
| L1 | Idea / PoC | Passed |
| L2 | Technical demo | Passed |
| L3 | Functional MVP | **Current baseline** |
| L4 | Controlled pilot | **v1.0 target** |
| L5 | Production SaaS / enterprise operations | Out of scope |

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

These are **historical/committed evidence**, not a current v1 release-candidate rerun.

### Golden-path gap state

| Stage | Status | v1 delta |
| --- | --- | --- |
| 1–10: ingest through grounded Q&A | READY | Runtime re-verification only |
| 11: target/reference selection | PARTIAL | Backend contract exists; UI is V1-03 |
| 12: claim comparison | PARTIAL | Backend exists; executed verification incomplete |
| 13: element decomposition | MISSING | V1-04 |
| 14: persisted human review | MISSING | V1-05 |
| 15: source verification on all analytical surfaces | PARTIAL | Search/Q&A ready; new surfaces must inherit guarantee |

**Do not rebuild stages 1–10.**

---

## 4. Frozen v1.0 Workflow

1. Upload text-based patent PDF.
2. Validate and persist document.
3. Extract page text with canonical source locators.
4. Parse claim structure and dependencies.
5. Inspect claims and jump to exact source spans.
6. Index claims.
7. Search with dense / lexical / hybrid retrieval.
8. Open search result at original source location.
9. Ask evidence-grounded question.
10. Receive cited statements or explicit insufficient evidence.
11. Select target and reference documents.
12. Select target claim and compare against related claims in the reference document.
13. Decompose claim into reviewable source-backed elements.
14. Persist reviewer judgement separately from machine output.
15. Verify every rendered analytical assertion against persisted source evidence.

**When this workflow is complete, reproducible, validated, and packaged, feature development for v1.0 stops.**

---

## 5. Scope

### In scope

- bounded target-claim vs one-reference-document comparison;
- reference-document-only retrieval and target/reference canonical source locators;
- explicit `reference_not_indexed` / `no_matches` states;
- claim element decomposition anchored to canonical claim source;
- versioned/idempotent machine output plus persisted `accepted` / `needs_correction` human review;
- clean checkout/start, empty-DB migration reproduction, deterministic demo data, CI quality gates;
- proof-oriented README, architecture visual, screenshots, demo asset, evaluation summary, visible CI, limitations, v1.0 release/tag.

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

## 6. Execution Plan

### V1-00 — Master Freeze
**Status:** CLOSED

### V1-01 — Golden Path Gap Audit
**Status:** CLOSED

### V1-02 — Claim Comparison Backend
**Status:** **IN PROGRESS**

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
- [x] database-free service/API/edge/schema tests exist;
- [x] PostgreSQL-backed integration tests exist for strict reference scope and source-span resolution;
- [x] a single focused closure command exists: `make verify-v1-02`;
- [x] closure command cannot silently pass when all three comparison integration tests are skipped;
- [ ] `make verify-v1-02` actually executes successfully in a real checkout with Docker;
- [ ] comparison pytest tests actually execute successfully;
- [ ] Ruff/format checks actually execute successfully;
- [ ] live PostgreSQL-backed scoped retrieval actually executes successfully.

**Do not close V1-02 until executed verification exists.**

### V1-03 — Comparison UI + Flow Stitching
**Status:** PLANNED

- `/compare` workspace;
- target/reference selectors and target-claim selector;
- side-by-side results with direct source navigation;
- no-match/error/loading states;
- contextual links from document detail to search, grounded Q&A, comparison.

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
- CI backend/integration/lint/frontend gates;
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

## 7. Execution Rules

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

**Implementation-agent self-report is not final verification. `Tests should pass` is not evidence.**

---

## 8. Current Batch Record — V1-02

### What changed

The V1-02 backend now contains:

- comparison schema/service/dependency/API router and `POST /api/v1/compare/claims`;
- persisted target claim text as the comparison query;
- strict `[reference_document_id]` retrieval plus defensive scope-leak rejection;
- target/reference canonical source spans;
- explicit `reference_not_indexed` vs `no_matches`;
- response invariants for document separation, reference scope, match count, no-correspondence state, and source-span ownership;
- completed-target-parse lifecycle enforcement;
- database-free service/API/edge/schema tests and PostgreSQL-backed strict-scope/provenance integration tests.

**2026-08-19 closure-path hardening:**

- `make verify-v1-02` first runs the four database-free comparison modules;
- the PostgreSQL-backed comparison integration module now runs separately inside the API Docker container;
- its output is checked for exactly the current three passing integration tests, so a PostgreSQL-unreachable `skip` outcome cannot silently satisfy the V1-02 closure gate;
- Ruff lint and Ruff format-check still run after the tests;
- this remains V1-02 verification hardening and does **not** pull GitHub Actions/CI work forward from V1-06.

### What was actually executed

Current run:

- read this MASTER before changes;
- re-inspected the root `Makefile`, `docker-compose.yml`, comparison integration test module, and shared integration fixtures through the GitHub connector;
- identified that the shared PostgreSQL fixture intentionally calls `pytest.skip(...)` when PostgreSQL is unreachable, meaning the previous closure command could theoretically exit successfully without proving live PostgreSQL comparison execution;
- attempted a fresh repository clone: **FAILED** with `Could not resolve host: github.com`;
- updated the source `Makefile` at commit `9059e9de36ebfb3ffaafa7055bec4ad3732c18cd` so the integration test run must report all current three tests as passed;
- reconstructed the updated Make target locally and executed `make -n -f /tmp/Makefile.v102 verify-v1-02`: **PASS**; command expansion is syntactically valid and preserves the mandatory integration-result check;
- checked GitHub combined status for source commit `9059e9de36ebfb3ffaafa7055bec4ad3732c18cd`: no statuses/checks are present.

Earlier retained V1-02 evidence:

- locally reconstructed comparison source passed syntax-level `python -m py_compile` checks;
- isolated response-validator execution passed for one coherent response and rejected contradictory responses as intended;
- `.github/workflows` is absent and `main` has no required status checks;
- prior `make verify-v1-02` dry-run passed command-construction inspection.

### What was not verified

- `make verify-v1-02` itself was **not actually executed** against a real repository checkout;
- repository comparison pytest tests were not actually run against the real package checkout;
- Ruff/format checks were not run with Ruff itself;
- FastAPI startup was not run;
- no live comparison HTTP request was executed;
- PostgreSQL-backed scoped retrieval was not executed;
- Docker Compose was not executed;
- the new integration pass-count guard was only dry-run validated, not observed against a live passing/failing Docker test session.

### Remaining risks

- comparison code/tests remain runtime-unverified until `make verify-v1-02` runs successfully in a real checkout;
- integration tests may expose import/runtime/database defects on first execution;
- the closure target currently encodes the integration module's current three-test count and must be updated if that module intentionally gains/removes tests before V1-02 closes;
- provenance invariants may reveal mapper/fixture assumptions when real pytest runs;
- the core remaining V1-02 gate is executed pytest/Ruff/PostgreSQL verification, **not additional feature scope**;
- comparison remains textual correspondence only and must never be represented as legal equivalence or infringement analysis;
- persistent CI remains intentionally deferred to V1-06.

---

## 9. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| Phase 4A-2 engine | VERIFIED BY REPO INSPECTION | existing implementation |
| Historical backend tests: 876 | HISTORICAL EXECUTED EVIDENCE | rerun required |
| Deterministic citation resolution 1.000 | COMMITTED EVALUATION | pre-v1 baseline |
| Ollama citation resolution 1.000 | COMMITTED EVALUATION | synthetic corpus |
| Forbidden scoped citations 0 | COMMITTED EVALUATION | grounded baseline |
| Existing stages 1–10 | VERIFIED BY STATIC INSPECTION | V1-01 |
| Comparison contract/service/API | IMPLEMENTED, NOT FULLY RUNTIME-VERIFIED | V1-02 |
| Comparison tests | WRITTEN, NOT PYTEST-EXECUTED | database-free + PostgreSQL integration |
| Comparison response invariant logic | ISOLATED EXECUTION PASS | prior V1-02 run |
| V1-02 closure command | IMPLEMENTED + HARDENED + MAKE DRY-RUN PASS | integration skip cannot silently close batch |
| Real Docker V1-02 closure run | NOT VERIFIED | next required gate |
| Current CI green | NOT PRESENT | intentionally V1-06 |
| Clean checkout reproduction | NOT VERIFIED | V1-06 |
| Element decomposition | NOT IMPLEMENTED | V1-04 |
| Persisted human review | NOT IMPLEMENTED | V1-05 |

---

## 10. Known Risks / Unverified

- Citation resolvability is not semantic entailment.
- Current real-model evidence uses a small `qwen2.5:1.5b` model and synthetic data.
- OCR is intentionally unsupported.
- Korean rule-based claim parsing supports bounded patterns, not all patents.
- Comparison quality depends on retrieval quality and is **not legal similarity**.
- Element decomposition is a domain-judgement boundary and requires human review.
- Current test/evaluation evidence must be refreshed before release closure.
- No public multi-user security model belongs to v1.0.

---

## 11. Closure Condition

ClaimTrace v1.0 is **CLOSED** only when all three are true:

### Done enough to use

- full frozen workflow usable by a single user;
- expected failures explicit;
- source verification available for analytical output;
- comparison + decomposition/review usable at controlled-pilot level.

### Done enough to trust

- clean checkout + migrations reproduced;
- CI green;
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
- visible metrics and limitations;
- v1.0 release/tag.

**When these conditions are met, stop adding features to v1.0.**