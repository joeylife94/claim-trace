# ClaimTrace v1.0 Master

> **Authoritative execution document for ClaimTrace v1.0.**
>
> Read this file before every implementation batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains system design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what ClaimTrace v1.0 is actually finishing now.**

**Last execution update:** 2026-08-18  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-02 — Claim Comparison Backend

---

## 1. Goal

Turn ClaimTrace from a strong late-L3 Functional MVP into a **single-user controlled-pilot product that can be operated, reviewed, reproduced, and shown as credible delivery proof**.

Frozen v1.0 flow:

**ingest → parse → index → retrieve → ask → compare → decompose → review → verify source evidence**

The v1.0 goal is **not** production SaaS and **not** automated legal judgement.

---

## 2. Target User / Product Boundary

Target user:

- one analyst, engineer, researcher, or reviewer;
- trusted workstation or controlled on-premise environment;
- text-based Korean patent PDFs;
- needs retrieval/comparison output that can be checked against original source text.

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

### Existing engine — already implemented

- FastAPI + Next.js, PostgreSQL 17 + pgvector + pg_trgm.
- PDF validation/persistence, SHA-256 identity, explicit ingestion failures.
- Page-level text with canonical `SourceLocator` provenance.
- Deterministic Korean claim parsing, dependencies, and page-relative claim spans.
- Dense, lexical, and RRF hybrid retrieval with exact source links.
- Local/self-hosted LLM boundary: Ollama, OpenAI-compatible local endpoint, deterministic fake provider.
- Strict structured-output validation and evidence-grounded Q&A using server-issued evidence IDs.
- Server-side citation resolution, explicit `insufficient_evidence`, grounded UI/source navigation.
- Deterministic + real-local-model evaluation tiers and hostile-evidence guardrails.
- Docker Compose development environment.

### Historical evidence before v1 hardening

- 876 backend tests recorded after Phase 4A-2.
- Deterministic grounded citation resolution: `1.000`.
- `qwen2.5:1.5b` grounded citation resolution: `1.000`.
- Real-model statement citation coverage: `1.000`.
- Forbidden cross-document citations: `0` in the committed evaluation.

These are **historical/committed evidence**, not a current v1 release-candidate rerun.

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

Result: stages 1–10 already exist; real feature gap is comparison, decomposition, persisted review, then operational/proof closure.

### V1-02 — Claim Comparison Backend
**Status:** **IN PROGRESS**

Goal: smallest source-backed two-document claim comparison capability.

Acceptance:

- [x] comparison request/response contract exists;
- [x] target and reference documents must be distinct;
- [x] target claim text is the comparison query, not arbitrary caller text;
- [x] retrieval is scoped to exactly one reference document;
- [x] service performs a defensive second scope-leak check;
- [x] target and reference results carry canonical source spans;
- [x] `reference_not_indexed` and `no_matches` are distinguishable;
- [x] API response has no legal-conclusion field;
- [x] database-free service tests added for scope/no-index/same-document behavior;
- [x] API contract tests added;
- [x] PostgreSQL-backed integration tests added for strict reference scope and source-span resolution;
- [x] edge-state tests added for `no_matches`, missing target parse, and missing target claim;
- [ ] new tests actually executed successfully;
- [ ] lint/format checks actually executed successfully;
- [ ] live PostgreSQL-backed scoped retrieval actually executed successfully.

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

## 7. v1.0 Acceptance Criteria

### Functional

- [ ] Full stages 1–15 workflow usable from supported UI.
- [ ] Search/Q&A/comparison/decomposition analytical output has source navigation.
- [ ] Comparison strictly respects reference document scope and exposes no-correspondence state.
- [ ] Decomposition yields source-backed elements.
- [ ] Human review is persisted separately from machine output.

### Operational

- [ ] Clean checkout documented and verified.
- [ ] Docker Compose path starts.
- [ ] Empty-DB migrations apply.
- [ ] Demo/sample material reproduces golden path.
- [ ] CI runs backend tests, PostgreSQL integration, lint/format, frontend lint/typecheck.

### Validation

- [ ] Full automated suite passes on v1 candidate.
- [ ] Retrieval evaluation reproducible.
- [ ] Grounded deterministic evaluation reproducible.
- [ ] Real local-model validation rerun or explicitly marked not rerun.
- [ ] Citation resolution verified.
- [ ] Scope-leak and hostile-evidence guards pass.
- [ ] Comparison provenance checks pass.
- [ ] Decomposition/review persistence checks pass.
- [ ] Model-quality limitations remain visible.

### Proof

- [ ] README leads with problem → solution → demo → evidence.
- [ ] Architecture visual exists.
- [ ] At least four useful screenshots exist.
- [ ] Concise demo asset exists.
- [ ] CI status visible.
- [ ] Metrics linked to reproducible evidence.
- [ ] Limitations visible.
- [ ] v1.0 release/tag exists.

---

## 8. Execution Rules

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

## 9. Current Batch Record — V1-02

### What changed

- added comparison schema/service/dependency/API router and `POST /api/v1/compare/claims`;
- target persisted claim text is the only comparison query;
- retrieval is forced to `[reference_document_id]` with a defensive second scope-leak check;
- target/reference results preserve canonical source spans;
- explicit `reference_not_indexed` vs `no_matches` state exists;
- database-free service and API contract tests cover scope, request validation, and source-locator response shape;
- added PostgreSQL-backed comparison integration coverage using the committed two-document synthetic corpus;
- integration coverage specifies both-direction reference scoping and exact target/reference span resolution against persisted page text;
- refined integration test formatting to the repository `line-length = 100` convention;
- added `test_claim_comparison_edge_cases.py` to pin three remaining service contracts: indexed reference + zero candidates → `no_matches`; missing target parse → `claim_parse_not_found`; missing target claim → `claim_not_found`.

### What was actually executed

- read this master before changes;
- re-inspected comparison service/schema/API, existing claim parsing/search behavior, integration fixtures, and synthetic retrieval corpus;
- confirmed the committed retrieval corpus currently contains exactly the expected `sensor` and `battery` documents used by comparison integration coverage;
- wrote `apps/api/tests/test_claim_comparison_edge_cases.py` to GitHub `main` at commit `38ddf6dec6efe745278dca8c71054ab672b87390`;
- reproduced that exact new test source in the execution sandbox and ran `python -m py_compile`: **PASS**;
- measured the new test file maximum line length: **99**, within the repository Ruff `line-length = 100` convention;
- checked GitHub combined status for `38ddf6dec6efe745278dca8c71054ab672b87390`: no status checks were present;
- attempted local dependency availability for PostgreSQL execution; the sandbox lacks `psycopg` and `pgvector`, and offline installation was unavailable.

### What was not verified

- comparison pytest tests were **not actually run**;
- Ruff/format checks were not run with Ruff itself;
- FastAPI startup was not run;
- no live comparison HTTP request was executed;
- PostgreSQL-backed scoped retrieval was not executed;
- Docker Compose was not executed;
- `py_compile` proves Python syntax only; it does not prove imports, fixtures, service behavior, or database behavior.

### Remaining risks

- comparison code/tests remain runtime-unverified because this execution environment cannot obtain a runnable repository/dependency set;
- integration tests may still expose import/runtime/database defects when first executed;
- the core remaining V1-02 gate is executed pytest/Ruff/PostgreSQL verification, not additional feature scope;
- `searched_index_run_count == 0` must later render clearly as unindexed/incompatible profile rather than ordinary no-match;
- comparison is textual correspondence only and must never be presented as legal equivalence or infringement analysis;
- persistent CI remains intentionally deferred to V1-06.

---

## 10. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| Phase 4A-2 engine | VERIFIED BY REPO INSPECTION | existing implementation |
| Historical backend tests: 876 | HISTORICAL EXECUTED EVIDENCE | rerun required |
| Deterministic citation resolution 1.000 | COMMITTED EVALUATION | pre-v1 baseline |
| Ollama citation resolution 1.000 | COMMITTED EVALUATION | synthetic corpus |
| Forbidden scoped citations 0 | COMMITTED EVALUATION | grounded baseline |
| Existing stages 1–10 | VERIFIED BY STATIC INSPECTION | V1-01 |
| Comparison contract/service/API | IMPLEMENTED, NOT RUNTIME-VERIFIED | V1-02 |
| Comparison database-free tests | WRITTEN, NOT EXECUTED | V1-02 |
| Comparison PostgreSQL integration coverage | WRITTEN + STATICALLY REVIEWED, NOT EXECUTED | strict scope + exact provenance |
| Comparison edge-state test source | PY_COMPILE PASS, PYTEST NOT EXECUTED | syntax + line-length only |
| Current CI green | NOT PRESENT | V1-06 |
| Clean checkout reproduction | NOT VERIFIED | V1-06 |
| Golden-path browser run | NOT VERIFIED | V1-06 |
| Element decomposition | NOT IMPLEMENTED | V1-04 |
| Persisted human review | NOT IMPLEMENTED | V1-05 |

---

## 11. Known Risks / Unverified

- Citation resolvability is not semantic entailment.
- Current real-model evidence uses a small `qwen2.5:1.5b` model and synthetic data.
- OCR is intentionally unsupported.
- Korean rule-based claim parsing supports bounded patterns, not all patents.
- Comparison quality depends on retrieval quality and is **not legal similarity**.
- Element decomposition is a domain-judgement boundary and requires human review.
- Current test/evaluation evidence must be refreshed before release closure.
- No public multi-user security model belongs to v1.0.

---

## 12. Closure Condition

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