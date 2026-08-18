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

Product-level definition:

> **ClaimTrace v1.0 is a single-user, on-premise patent analysis pilot for text-based Korean patent PDFs. It structures claims, retrieves related evidence, produces evidence-grounded answers, supports bounded document/claim comparison, decomposes claims into reviewable source-backed elements, preserves human review separately from machine output, and exposes limitations instead of inventing certainty.**

---

## 3. Product Level

| Level | Meaning | Status |
| --- | --- | --- |
| L1 | Idea / PoC | Passed |
| L2 | Technical demo | Passed |
| L3 | Functional MVP | **Current baseline** |
| L4 | Controlled pilot | **v1.0 target** |
| L5 | Production SaaS / enterprise operations | Out of scope |

---

## 4. Current State

### Existing engine — already implemented

- FastAPI backend + Next.js frontend.
- PostgreSQL 17 + pgvector + pg_trgm.
- PDF validation, persistence, SHA-256 identity, explicit ingestion failures.
- Page-level persisted text and canonical `SourceLocator` provenance.
- Deterministic Korean claim structural parsing and dependency graph.
- Claim source spans, including page-crossing claims.
- Claim indexing lifecycle and retrieval profiles.
- Dense, lexical, and RRF hybrid retrieval.
- Search result ranking metadata + exact source links.
- Local/self-hosted LLM boundary with Ollama, OpenAI-compatible local endpoint, deterministic fake provider.
- Strict structured-output validation.
- Evidence-grounded Q&A with server-issued evidence IDs.
- Server-side citation resolution to stored page text.
- Explicit `insufficient_evidence` behavior.
- Grounded-answer UI and source navigation.
- Deterministic + real-local-model evaluation tiers.
- Hostile evidence / forged citation guardrail tests.
- Docker Compose development environment.

### Historical evidence before v1 hardening

- 876 backend tests recorded after Phase 4A-2.
- Deterministic grounded citation resolution: `1.000`.
- `qwen2.5:1.5b` grounded citation resolution: `1.000`.
- Real-model statement citation coverage: `1.000`.
- Forbidden cross-document citations: `0` in the committed evaluation.

These are **historical/committed evidence**, not a current v1 release-candidate rerun.

---

## 5. Frozen v1.0 Workflow

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

## 6. Golden Path Gap Audit

| # | Stage | Status | v1 delta |
| --- | --- | --- | --- |
| 1 | PDF upload | READY | Runtime re-verification only |
| 2 | Validate + persist | READY | Runtime re-verification only |
| 3 | Page text + locator | READY | Runtime re-verification only |
| 4 | Claim parse + dependency | READY | Runtime re-verification only |
| 5 | Claim → exact source | READY | Runtime re-verification only |
| 6 | Claim indexing | READY | Runtime re-verification only |
| 7 | Dense/lexical/hybrid search | READY | Runtime re-verification only |
| 8 | Search → exact source | READY | Runtime re-verification only |
| 9 | Grounded Q&A | READY | Runtime re-verification only |
| 10 | Insufficient evidence | READY | Runtime re-verification only |
| 11 | Target/reference selection | **PARTIAL** | Backend contract now exists; UI not yet implemented |
| 12 | Claim comparison | **PARTIAL** | V1-02 implementation present; runtime verification incomplete |
| 13 | Element decomposition | MISSING | V1-04 |
| 14 | Persisted human review | MISSING | V1-05 |
| 15 | Source verification on all analytical surfaces | PARTIAL | Search/Q&A ready; comparison/decomposition must inherit guarantee |

Do **not** rebuild stages 1–10.

---

## 7. In Scope

### Claim comparison

- target document + target claim + one reference document;
- reference-document-only retrieval scope;
- target/reference canonical source locators;
- side-by-side textual correspondence;
- explicit `reference_not_indexed` / `no_matches` state;
- reuse existing retrieval stack;
- no legal-conclusion fields.

### Claim element decomposition + review

- individually addressable elements/limitations;
- each element anchored to canonical claim source;
- versioned/idempotent machine output;
- persisted human `accepted` / `needs_correction` minimum review state;
- re-processing must not silently erase review history.

### Operational hardening

- clean checkout/start;
- empty-DB migration reproduction;
- committed deterministic demo data;
- documented golden path;
- CI quality gates;
- expected failure-path verification.

### Proof packaging

- proof-oriented README;
- architecture visual;
- screenshots;
- concise demo asset;
- evaluation summary;
- visible CI;
- limitations;
- v1.0 release/tag.

---

## 8. Explicit Non-Goals

Do not add these to v1.0 unless this master is deliberately re-scoped:

- OCR / scanned-PDF recovery;
- authentication / RBAC;
- multi-tenancy;
- public cloud hosting;
- Kubernetes;
- production deployment pipelines;
- billing / admin console / team workspace;
- chat history / conversation memory / streaming;
- general tool calling;
- notifications;
- broad observability platform work;
- full multilingual support;
- hosted third-party LLM APIs as the default path;
- legal advice or determinations of infringement, validity, novelty, equivalence, inventive step, or patentability.

---

## 9. Execution Plan

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
- [x] focused service tests added for scope/no-index/same-document behavior;
- [x] focused API contract tests added;
- [ ] new tests actually executed successfully;
- [ ] lint/format checks actually executed successfully;
- [ ] live PostgreSQL-backed scoped retrieval verified.

**Do not close V1-02 until executed verification exists.**

### V1-03 — Comparison UI + Flow Stitching
**Status:** PLANNED

- `/compare` workspace;
- target/reference selectors;
- target claim selector;
- side-by-side results;
- source navigation;
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

## 10. Acceptance Criteria

### Functional

- [ ] Full stages 1–15 workflow usable from supported UI.
- [ ] Search/Q&A/comparison/decomposition analytical output has source navigation.
- [ ] Comparison strictly respects reference document scope.
- [ ] Comparison exposes no-correspondence state.
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
- [ ] Scope-leak guards pass.
- [ ] Hostile evidence guards pass.
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

## 11. Execution Rules

Every batch must define:

1. **Goal** — smallest useful outcome.
2. **Scope** — allowed surfaces.
3. **Acceptance** — observable pass conditions.
4. **Non-goals** — explicit scope boundary.

Every batch update must record:

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

## 12. Current Batch Record — V1-02

### What changed

- added `apps/api/src/claimtrace_api/schemas/comparison.py`;
- added bounded request validation with `extra="forbid"` and distinct target/reference documents;
- added `apps/api/src/claimtrace_api/services/claim_comparison.py`;
- target claim persisted text is reused as the retrieval query;
- search is forced to `[reference_document_id]` and a second service-level leak check rejects out-of-scope results;
- added explicit `reference_not_indexed` vs `no_matches` outcome reason;
- added `COMPARISON_INVALID_REQUEST` application error code;
- wired `ClaimComparisonService` through FastAPI dependencies;
- added `POST /api/v1/compare/claims`;
- registered the comparison router;
- added database-free service tests for reference scope, scope leak rejection, unindexed reference, and same-document rejection;
- added HTTP contract tests for source locators, forbidden legal fields, same-document validation, and extra-field rejection.

### What was actually executed

- read current `CLAIMTRACE_V1_MASTER.md` before changes;
- inspected existing `ClaimSearchService`, search API, retrieval schemas, claim API, parsing snapshot, dependency wiring, error taxonomy, test fixtures, and project Ruff/Python configuration;
- wrote the comparison source and test files to GitHub `main`;
- fetched `main` after writes and confirmed HEAD advanced to `1f29f675dfb4e0e4d7c8e0bc2d1440b74f5ac7bb` before this master update;
- checked GitHub combined status for that HEAD: no status checks were present;
- attempted a clean public `git clone` in the execution container in order to run tests; the command failed before clone because the environment could not resolve `github.com`.

### What was not verified

- no Python test was actually run;
- no Ruff/format check was actually run;
- no FastAPI app startup was executed;
- no comparison request was executed against a live API;
- no PostgreSQL-backed comparison retrieval was executed;
- no Docker Compose path was executed.

### Remaining risks

- new comparison code is statically inspected but not runtime-verified;
- test files may still expose import/style/runtime defects until executed;
- real retrieval must still prove that reference-document scope produces only reference-document claims;
- `searched_index_run_count == 0` currently represents an unindexed/incompatible active profile and must be rendered clearly in the future UI;
- comparison ranks textual correspondence only and must never be presented as legal equivalence or infringement analysis;
- CI is still absent, so no persistent green evidence exists yet.

---

## 13. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| Phase 4A-2 engine | VERIFIED BY REPO INSPECTION | existing implementation |
| Historical backend tests: 876 | HISTORICAL EXECUTED EVIDENCE | rerun required |
| Deterministic citation resolution 1.000 | COMMITTED EVALUATION | pre-v1 baseline |
| Ollama citation resolution 1.000 | COMMITTED EVALUATION | synthetic corpus |
| Forbidden scoped citations 0 | COMMITTED EVALUATION | grounded baseline |
| Existing stages 1–10 | VERIFIED BY STATIC INSPECTION | V1-01 |
| Comparison contract/service/API | IMPLEMENTED, NOT RUNTIME-VERIFIED | V1-02 |
| Comparison focused tests | WRITTEN, NOT EXECUTED | V1-02 |
| Current CI green | NOT PRESENT | V1-06 |
| Clean checkout reproduction | NOT VERIFIED | V1-06 |
| Golden-path browser run | NOT VERIFIED | V1-06 |
| Element decomposition | NOT IMPLEMENTED | V1-04 |
| Persisted human review | NOT IMPLEMENTED | V1-05 |

---

## 14. Known Risks / Unverified

- Citation resolvability is not semantic entailment.
- Current real-model evidence uses a small `qwen2.5:1.5b` model and synthetic data.
- OCR is intentionally unsupported.
- Korean rule-based claim parsing supports bounded patterns, not all patents.
- Comparison quality depends on retrieval quality and is **not legal similarity**.
- Element decomposition is a domain-judgement boundary and requires human review.
- Current test/evaluation evidence must be refreshed before release closure.
- No public multi-user security model belongs to v1.0.

---

## 15. Closure Condition

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
