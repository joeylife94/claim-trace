# ClaimTrace v1.0 Master

> **Authoritative execution document for ClaimTrace v1.0.**
>
> Read this file before starting any implementation batch. This document defines the product boundary, current state, execution order, acceptance criteria, verification evidence, and closure condition for the v1.0 effort.
>
> `README.md` explains the project to readers. `docs/ARCHITECTURE.md` explains system design. `docs/ROADMAP.md` records the broader technical roadmap. **This file controls what we are actually finishing now.**

**Last scope review:** 2026-08-18  
**Baseline inspected:** `main` at Phase 4A-2 (`05effacef0737d7b4aa36b3858af099641baf19d`) plus this v1 master document.

---

## 1. Goal

Turn ClaimTrace from a strong functional MVP into a **controlled-pilot-level product that a real user can operate and a client can inspect as credible proof of delivery capability**.

The frozen v1.0 workflow is:

**ingest → parse → index → retrieve → ask → compare → decompose → review → verify source evidence**

The goal is **not** to create a production SaaS and **not** to automate legal judgement.

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

| Level | Meaning | Status |
| --- | --- | --- |
| L1 | Idea / proof of concept | Passed |
| L2 | Technical demo | Passed |
| L3 | Functional MVP | **Current** |
| L4 | Controlled pilot / usable by a real single user | **v1.0 target** |
| L5 | Production SaaS / enterprise operations | Out of scope |

### v1.0 definition

**ClaimTrace v1.0 is a single-user, on-premise patent analysis pilot for text-based Korean patent PDFs. It structures claims, retrieves related evidence, produces evidence-grounded answers, supports bounded document/claim comparison, decomposes claims into reviewable source-backed elements, preserves human review separately from machine output, and exposes limitations instead of inventing certainty.**

---

## 4. Current State

Current repository state is **Phase 4A-2 complete / late L3 Functional MVP**.

### Implemented

- FastAPI backend and Next.js frontend.
- PostgreSQL 17 + pgvector + pg_trgm.
- PDF ingestion with explicit validation and failure codes.
- Content-addressed storage and SHA-256 duplicate policy.
- Page-level persisted text and canonical `SourceLocator` provenance.
- Deterministic Korean claim structural parsing.
- Claim dependency graph and claim classifications.
- Claim spans preserving exact page-relative source ranges.
- Claim indexing lifecycle and retrieval profiles.
- Dense, lexical, and Reciprocal Rank Fusion hybrid retrieval.
- Search results with ranking metadata and source links.
- Local/self-hosted LLM provider boundary.
- Ollama and OpenAI-compatible local provider adapters.
- Deterministic fake provider for offline tests.
- Strict structured-output extraction and validation.
- Evidence-grounded answering using server-issued evidence identifiers.
- Server-side citation resolution to persisted source text.
- Explicit `insufficient_evidence` behavior.
- Grounded-answer UI with evidence links.
- Deterministic and real-local-model evaluation tiers.
- Hostile evidence / forged citation guardrail coverage.
- Docker Compose development environment.
- Backend tests, integration tests, lint/format, frontend lint, and frontend typecheck commands.

### Existing evidence

Repository documentation currently records:

- **876 backend tests** after Phase 4A-2.
- Deterministic grounded evaluation citation resolution `1.000`.
- Real `qwen2.5:1.5b` grounded evaluation citation resolution `1.000`.
- Real-model statement citation coverage `1.000`.
- Forbidden cross-document citations `0` in that evaluation.
- Honest weakness: the small local model does **not** establish production-grade patent reasoning quality.

### Current product gap

The core ingestion/retrieval/grounded-answer engine is already present. The remaining gap is **workflow closure and proof**, not another broad RAG rebuild.

Missing product-level capabilities:

1. bounded two-document claim comparison;
2. claim element decomposition;
3. persisted human review boundary for decomposition;
4. small UI flow-stitching improvements;
5. clean-checkout/demo reproducibility;
6. persistent CI evidence;
7. visual/public proof packaging.

---

## 5. Frozen v1.0 Supported Workflow

1. Upload a text-based patent PDF.
2. Validate and persist the document.
3. Extract page text with canonical source locators.
4. Parse claim structure and dependencies.
5. Inspect claims and jump to exact source spans.
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

When this workflow is complete, reproducible, validated, and packaged, **feature development for v1.0 stops**.

---

## 6. Golden Path Gap Audit — 2026-08-18

Static repository inspection completed before new implementation.

| # | Golden-path stage | Status | Existing evidence | Required v1.0 delta |
| --- | --- | --- | --- | --- |
| 1 | PDF upload | **READY** | `/documents` + `UploadForm` | Runtime re-verification only |
| 2 | Validate + persist | **READY** | ingestion service, explicit errors, persisted document record | Runtime re-verification only |
| 3 | Page text + source locator | **READY** | document page API + page viewer | Runtime re-verification only |
| 4 | Claim parse + dependency graph | **READY** | `ClaimsPanel`, parse action, persisted claim set | Runtime re-verification only |
| 5 | Claim inspection + exact source span | **READY** | `ClaimWorkspace` + `PageViewer` highlight state | Runtime re-verification only |
| 6 | Claim indexing | **READY** | `ClaimIndexPanel`, index action, index profile | Runtime re-verification only |
| 7 | Dense / lexical / hybrid search | **READY** | `/search` + `SearchPanel` | Runtime re-verification only |
| 8 | Search result → exact source | **READY** | `spanHref(...)` deep links to document page + range | Runtime re-verification only |
| 9 | Grounded Q&A | **READY** | `/grounded` + `GroundedAnswerPanel` | Runtime re-verification only |
| 10 | Explicit insufficient evidence | **READY** | grounded response/UI state | Runtime re-verification only |
| 11 | Select target + reference documents | **MISSING** | no comparison workspace/API found | Add bounded comparison request surface |
| 12 | Target claim → reference claim comparison | **MISSING** | roadmap only; no implementation found | Add comparison domain/service/API/UI |
| 13 | Claim element decomposition | **MISSING** | roadmap only; no implementation found | Add element schema/parser/service/API/UI |
| 14 | Persisted human decomposition review | **MISSING** | no implementation found | Add machine-output/review-state separation |
| 15 | Verify every analytical assertion | **PARTIAL** | grounded answers/search are source-linked; future compare/decomposition do not exist yet | Apply same provenance rule to new surfaces |

### Flow-stitching finding

The existing flow is stronger than expected:

- document detail already supports parse and index;
- completed indexing already links directly to document-scoped search;
- search results already deep-link to exact page/character ranges;
- grounded answers already link cited evidence to exact source ranges.

The main usability seam is small: **document detail does not currently expose an equally direct `Ask about this document` contextual action**, and comparison/review navigation does not exist because those features do not exist yet.

### Audit conclusion

**Do not rebuild stages 1-10.** Preserve them and prove them again later through runtime validation. New product engineering should focus on stages 11-14, then stitch the complete flow together.

---

## 7. In Scope

### Product flow closure

- clear UI path through upload, parse, index, search, grounded answer, compare, decompose, and review;
- explicit empty/loading/error/retry states for the supported path;
- contextual next actions so the primary demo does not depend on API docs.

### Claim comparison

- select two indexed documents;
- select a target claim;
- retrieve relevant claims only from the chosen reference document;
- present side-by-side textual correspondence;
- preserve target and reference source locators;
- explicit `no corresponding claim found` / insufficient-evidence state;
- reuse existing retrieval and grounding boundaries rather than creating a parallel evidence system;
- no legal conclusion fields.

### Claim element decomposition and review

- decompose claims into individually addressable elements/limitations;
- preserve page-anchored source spans for every element;
- machine output and human review state remain separate;
- reviewer can accept or mark output `needs_correction`;
- re-processing must not silently destroy existing human review state.

### Operational hardening

- clean-checkout execution path;
- reproducible database migration path;
- deterministic committed demo/sample data;
- one documented golden-path demo procedure;
- CI-backed quality gates;
- expected failure-path verification.

### Proof packaging

- proof-oriented README;
- architecture visual;
- product screenshots;
- demo GIF/video asset;
- evaluation summary;
- visible CI state;
- explicit limitations;
- v1.0 release/tag.

---

## 8. Explicit Non-Goals

The following are **not required for ClaimTrace v1.0** and must not be added unless this master document is deliberately re-scoped first:

- OCR / scanned-PDF recovery;
- authentication;
- authorization / RBAC;
- multi-tenancy;
- public cloud hosting;
- Kubernetes;
- production deployment pipelines;
- billing;
- admin console;
- team workspace features;
- chat history;
- conversation memory;
- streaming responses;
- general tool calling;
- email/notification workflows;
- broad observability platform work;
- full multilingual patent support;
- hosted third-party LLM APIs as a default path;
- legal advice;
- infringement determination;
- validity determination;
- novelty determination;
- inventive-step determination;
- patentability determination.

A feature being useful later is not sufficient reason to include it in v1.0.

---

## 9. Execution Plan

### V1-00 — Master Freeze

**Status:** CLOSED

Frozen:

- current product level = late L3 Functional MVP;
- target = L4 Controlled Pilot;
- supported workflow;
- explicit non-goals;
- acceptance criteria;
- closure condition.

### V1-01 — Golden Path Gap Audit

**Status:** CLOSED

Result:

- stages 1-10 = already implemented at code/UI level;
- stages 11-14 = missing;
- stage 15 = partial until new analytical surfaces inherit provenance guarantees;
- only small flow stitching is needed around existing features.

No feature code changed in this batch.

### V1-02 — Claim Comparison Backend

**Status:** NEXT

**Goal:** create the smallest source-backed two-document comparison capability.

**Scope:**

- comparison request/response domain contract;
- target document + target claim + reference document selection;
- strict reference-document retrieval scope;
- source locators for both target and matched reference claims;
- explicit no-correspondence/insufficient-evidence result;
- comparison API/service tests;
- reuse existing retrieval/evidence machinery where possible.

**Acceptance:**

- unknown/invalid document or claim is explicit;
- target and reference document cannot silently collapse into an unintended scope;
- returned matches belong only to the requested reference document;
- every returned target/reference source span resolves to persisted page text;
- no response field can represent infringement, validity, novelty, equivalence, or patentability;
- tests cover scope leakage and no-match behavior.

**Non-goals:**

- no comparison UI yet;
- no element decomposition yet;
- no legal semantic judgement;
- no new embedding/retrieval stack.

### V1-03 — Claim Comparison UI + Flow Stitching

**Status:** PLANNED

**Goal:** make comparison usable from the web UI and connect the existing workflow.

Primary work:

- `/compare` workspace;
- target/reference document selectors;
- target claim selector;
- side-by-side source-backed results;
- direct source navigation;
- explicit no-match/error/loading states;
- contextual links from document detail to search, grounded Q&A, and comparison where valid.

### V1-04 — Claim Element Decomposition

**Status:** PLANNED

**Goal:** create reviewable source-backed claim elements without pretending parser output is final truth.

Primary work:

- element persistence/schema;
- deterministic decomposition boundary;
- each element as a sub-span of canonical claim source;
- versioned/idempotent decomposition run;
- explicit warnings/confidence boundary for resistant claims;
- API and tests.

### V1-05 — Human Review Boundary

**Status:** PLANNED

**Goal:** persist reviewer judgement separately from machine/parser output.

Primary work:

- review record separate from decomposition run;
- `accepted` / `needs_correction` minimum state;
- review survives re-processing;
- review UI and source navigation;
- audit tests for state preservation.

### V1-06 — Operational Hardening

**Status:** PLANNED

**Goal:** prove the product is reproducible, not merely implemented.

Primary work:

- clean clone/start;
- empty-DB migration;
- deterministic demo/sample material;
- golden-path execution script/checklist;
- CI backend/unit/integration/lint/frontend checks;
- expected failure-state validation.

### V1-07 — Final Validation + Wishket Proof Packaging

**Status:** PLANNED

**Goal:** freeze externally reviewable evidence.

Primary work:

- final test run;
- retrieval/grounding regression evaluations;
- comparison/decomposition validation evidence;
- README restructuring;
- architecture visual;
- minimum four useful screenshots;
- demo asset;
- limitations snapshot;
- v1.0 release/tag.

---

## 10. Acceptance Criteria

### Functional

- [ ] Text-based PDF upload works through the supported UI.
- [ ] Claim parsing works and preserves source spans.
- [ ] Claim indexing works.
- [ ] Dense, lexical, and hybrid search work.
- [ ] Search results resolve to exact source evidence.
- [ ] Grounded Q&A returns only source-backed statements or explicit insufficient evidence.
- [ ] Two-document claim comparison works under strict document scope.
- [ ] Comparison has explicit no-correspondence/insufficient-evidence behavior.
- [ ] Claim element decomposition produces source-backed elements.
- [ ] Human review state is persisted separately from machine output.
- [ ] Primary analytical UI results navigate back to original source text.

### Operational

- [ ] Clean checkout setup is documented and verified.
- [ ] Docker Compose supported path starts successfully.
- [ ] Database migrations apply cleanly from an empty database.
- [ ] Committed demo/sample material can run the golden path.
- [ ] One deterministic demo procedure is documented.
- [ ] Expected unsupported-input states are explicit and user-readable.
- [ ] CI runs backend tests and required quality gates.
- [ ] CI runs PostgreSQL-backed integration coverage.
- [ ] Frontend lint and TypeScript checks run in CI.

### Validation

- [ ] Full automated test suite passes from the v1.0 candidate commit.
- [ ] Retrieval evaluation is reproducible.
- [ ] Grounded deterministic evaluation is reproducible.
- [ ] Real local model validation is rerun or explicitly marked not rerun.
- [ ] Citation resolution remains verified.
- [ ] Document-scope leakage tests pass.
- [ ] Forged/hostile evidence identifier tests pass.
- [ ] Comparison provenance tests pass.
- [ ] Decomposition/review persistence tests pass.
- [ ] Known model-quality limitations remain visible.

### Proof

- [ ] README communicates problem → solution → demo → evidence before deep implementation detail.
- [ ] Architecture visual exists.
- [ ] At least four useful product screenshots exist.
- [ ] Concise golden-path demo asset exists.
- [ ] CI status is externally visible.
- [ ] Proof metrics link to reproducible evidence.
- [ ] Known limitations are visible.
- [ ] v1.0 release/tag exists.

---

## 11. Execution Rules

Every implementation batch must begin by reading this file.

Each batch defines:

1. **Goal** — smallest useful outcome.
2. **Scope** — files/surfaces allowed to change.
3. **Acceptance** — observable pass conditions.
4. **Non-goals** — what must not expand into the batch.

Every batch completion report records:

### What changed
Concrete code/document/schema changes only.

### What was actually executed
Commands, test suites, migrations, evaluations, or manual flows that were really run.

### What was not verified
Anything claimed by design/code inspection but not executed.

### Remaining risks
Known gaps, uncertainty, regressions, or follow-up work.

**Implementation-agent self-report is not final verification.** `Tests should pass` is not evidence.

---

## 12. Current Batch Record

### V1-01 — Golden Path Gap Audit

**Status:** CLOSED

### What changed

- classified all 15 frozen workflow stages as `READY`, `PARTIAL`, or `MISSING`;
- confirmed stages 1-10 already exist at code/UI level;
- identified comparison, decomposition, and persisted human review as the real feature gap;
- identified only a small contextual-navigation gap in the existing product flow;
- decomposed remaining v1 work into V1-02 through V1-07.

### What was actually executed

Static repository inspection of:

- `apps/web/app/documents/page.tsx`;
- `apps/web/app/documents/[id]/page.tsx`;
- `apps/web/components/ClaimWorkspace.tsx`;
- `apps/web/components/ClaimsPanel.tsx`;
- `apps/web/components/ClaimIndexPanel.tsx`;
- `apps/web/app/search/page.tsx`;
- `apps/web/components/SearchPanel.tsx`;
- `apps/web/app/grounded/page.tsx`;
- `apps/web/components/GroundedAnswerPanel.tsx`;
- repository search for comparison/decomposition implementation;
- existing README, roadmap, evaluation reports, and recent Phase 4A-2 commit history.

### What was not verified

- application build was not executed;
- automated tests were not rerun;
- Docker Compose was not started;
- migrations were not applied;
- UI was not exercised in a browser;
- API calls were not executed against a live database.

### Remaining risks

- static inspection can confirm code paths, not runtime health;
- historical `876 tests` evidence is not a current v1 candidate run;
- clean-checkout reproducibility is still unverified;
- there is no persistent green CI state on the inspected application baseline;
- comparison/decomposition design can still introduce provenance or review-state mistakes if not constrained by existing source-locator rules.

---

## 13. Verification Evidence

Evidence here must be tied to an executed command, committed evaluation artifact, or inspected human-visible/code behavior.

| Evidence | State | Source / note |
| --- | --- | --- |
| Phase 4A-2 feature set | VERIFIED BY REPO INSPECTION | README / roadmap / implementation history |
| Existing stages 1-10 code/UI path | VERIFIED BY STATIC INSPECTION | V1-01 audited web surfaces |
| Backend test count: 876 | HISTORICAL EXECUTED EVIDENCE | Phase 4A-2 docs/commit history; rerun required |
| Deterministic citation resolution 1.000 | COMMITTED EVALUATION | grounded deterministic evaluation |
| Ollama citation resolution 1.000 | COMMITTED EVALUATION | `qwen2.5:1.5b`, synthetic corpus |
| Ollama statement citation coverage 1.000 | COMMITTED EVALUATION | synthetic corpus |
| Forbidden scoped citations 0 | COMMITTED EVALUATION | synthetic corpus |
| Search → exact source link | VERIFIED BY STATIC INSPECTION | `SearchPanel` + `spanHref` path |
| Grounded evidence → exact source link | VERIFIED BY STATIC INSPECTION | `GroundedAnswerPanel` + locator path |
| Clean-checkout reproduction | NOT VERIFIED | V1-06 |
| Current CI green state | NOT PRESENT / NOT VERIFIED | V1-06 |
| Golden-path browser run | NOT VERIFIED | V1-06 |
| Claim comparison | NOT IMPLEMENTED | V1-02/V1-03 |
| Claim element decomposition | NOT IMPLEMENTED | V1-04 |
| Persisted human review | NOT IMPLEMENTED | V1-05 |

---

## 14. Known Risks / Unverified

- A valid citation proves resolvability to stored evidence, **not semantic entailment**.
- Current real-model evaluation uses a small `qwen2.5:1.5b` model and synthetic data; it is pipeline evidence, not patent-analysis quality proof.
- OCR is deliberately unsupported; scanned/image-only PDFs must fail clearly.
- Korean deterministic claim parsing has bounded supported patterns and must not be represented as universal patent parsing.
- Comparison quality will depend on retrieval quality and must not be represented as legal similarity.
- Claim element decomposition is a domain-judgement boundary and therefore requires persisted human review rather than silent machine authority.
- Current historical test/evaluation evidence must be refreshed before release closure.
- No public multi-user security model is part of this release.

---

## 15. Closure Condition

ClaimTrace v1.0 is **CLOSED** only when all of the following are true.

### Done enough to use

- full frozen golden path is executable by a single user;
- expected failures are explicit rather than silent;
- source verification is available for analytical output;
- comparison and decomposition/review are usable at controlled-pilot level.

### Done enough to trust

- clean checkout is reproduced;
- migrations are reproduced;
- CI is green;
- automated tests pass;
- retrieval and grounding evaluations are reproducible;
- comparison/decomposition provenance checks pass;
- source-scope and hostile-evidence guardrails pass;
- unverified areas are explicitly recorded.

### Done enough to show

- README is proof-oriented;
- architecture visual exists;
- screenshots exist;
- concise demo evidence exists;
- evaluation results and limitations are visible;
- v1.0 release/tag freezes the proof state.

When these conditions are met, **stop adding features to v1.0**.

Any later OCR, authentication, multi-user, deployment, broader language, or advanced legal-analysis work starts as a separately scoped post-v1 effort.
