# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-19  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-04 — Claim Element Decomposition  
**Current batch state:** **IN PROGRESS — PR #11 exact-head verification pending**

---

## 1. Goal and Product Boundary

Frozen v1.0 flow:

**ingest → parse → index → retrieve → ask → compare → decompose → review → verify source evidence**

Target: one analyst/reviewer on a trusted workstation or controlled on-premise environment, working with text-based Korean patent PDFs and source-verifiable analytical output.

Explicit non-goals unless deliberately re-scoped:

- OCR / scanned-PDF recovery;
- auth / RBAC / multi-tenancy;
- public cloud / Kubernetes / production deployment pipelines;
- billing / admin / team workspace;
- chat history / memory / streaming / generic tool calling / notifications;
- broad observability or full multilingual support;
- hosted third-party LLM APIs as default path;
- legal advice or determinations of infringement, validity, novelty, equivalence, inventive step, or patentability.

Human Review is the **final release/proof gate**, not a requirement for ordinary bounded intermediate PR merges.

---

## 2. Current State

Existing pre-v1 engine: FastAPI + Next.js, PostgreSQL + pgvector/pg_trgm, PDF persistence/provenance, deterministic Korean claim parsing, dense/lexical/RRF retrieval, exact source links, local/self-hosted LLM boundary, grounded Q&A with server-issued evidence IDs, citation resolution, explicit insufficient evidence, deterministic/real-local-model evaluation tiers, hostile-evidence guards, Docker Compose.

Historical evidence retained until final rerun: 876 backend tests after Phase 4A-2; deterministic grounded citation resolution `1.000`; `qwen2.5:1.5b` citation resolution `1.000`; statement citation coverage `1.000`; forbidden cross-document citations `0`.

Golden-path state:

| Stage | Status | v1 delta |
| --- | --- | --- |
| 1–10 ingest → grounded Q&A | READY | final runtime re-verification only |
| 11 target/reference selection | EXECUTED GREEN | V1-03 closed |
| 12 claim comparison | EXECUTED GREEN | V1-02/V1-03 closed |
| 13 element decomposition | IN PROGRESS | first deterministic boundary in PR #11 |
| 14 persisted human review | MISSING | V1-05 |
| 15 source verification everywhere | PARTIAL | comparison source-linked; decomposition must inherit guarantee |

**Do not rebuild stages 1–12.**

---

## 3. Execution Plan

### V1-00 — Master Freeze
**CLOSED**

### V1-01 — Golden Path Gap Audit
**CLOSED**

### V1-02 — Claim Comparison Backend
**CLOSED**

Executed closure evidence:

- PR #7 exact head `f62b8847ec3bfd6df4ecf1750b6a0e5d90202f6c`;
- workflow run `32225430081` → **success**;
- database-free comparison tests **26 PASS**;
- PostgreSQL integration **3 PASS / 0 skipped**;
- Ruff lint + format **PASS**;
- Docker API build + PostgreSQL readiness **PASS**;
- merged to `main` as `db5e39d2118e42527a3794a32173e08535f18cec`.

### V1-03 — Comparison UI + Flow Stitching
**CLOSED**

Executed closure evidence:

- PR #8 workspace → run `32228257540` **success**, merged `3a12c6601da8ece8c71ea5233c77100d2229bbb9`;
- PR #9 flow stitching → run `32228493202` **success**, merged `6088fbbfbc4abad2e0983b03e464a74919b8124d`;
- PR #10 final exact head `1f093cbc6d611ef1aaedbea1ed934ff1f88d860c`;
- V1-02 regression run `32242502338` → **success**;
- V1-03 run `32242502306` → **success**;
- browser job completed exact-head checkout, deterministic runtime config, API/Web image build, PostgreSQL migration, deterministic two-document seed, API/Web startup, Chromium install, and browser golden-path execution → **PASS**;
- no unresolved review threads;
- merged with expected-head guard to `main` as `6de5a391715ace893189378710f8852b4542dfaa`.

### V1-04 — Claim Element Decomposition
**IN PROGRESS**

Goal: decompose a persisted claim into individually reviewable elements/limitations while preserving canonical source provenance and keeping machine output explicitly non-authoritative.

Acceptance:

- [ ] element domain/schema exists with stable identifiers and ordered elements;
- [ ] every element is represented as a sub-span of the canonical persisted claim source;
- [ ] decomposition run is versioned and idempotent/re-runnable without ambiguous duplication;
- [ ] resistant/unsupported claim shapes produce explicit warnings or bounded failure instead of invented structure;
- [ ] API exposes decomposition result without legal-conclusion fields;
- [ ] focused tests cover ordering, source-span containment, idempotency, and resistant-claim behavior;
- [ ] exact-head executable checks are GREEN before ordinary bounded PR merge.

Current bounded slice — PR #11:

- branch `v1-04-element-boundary`;
- current exact head at creation `7da399405ff7332143ea3376f701a48a4c70defd` (historical handoff only; fetch current head before acting);
- pure `DeterministicElementParser` boundary only;
- conservative explicit semicolon splitting;
- exact page-relative source sub-span mapping, including cross-page claims;
- no-delimiter claim stays one element with `no_structural_delimiter` warning;
- provenance mismatch raises instead of approximating;
- focused unit tests cover ordering, source containment, cross-page source mapping, resistant/no-delimiter behavior, and provenance mismatch;
- PR-visible `V1-04 Claim Element Verification` workflow added;
- no persistence/API/UI/human-review changes in this slice.

Non-goals:

- no human-review persistence yet (V1-05);
- no claim comparison changes;
- no LLM-based legal interpretation;
- no OCR/auth/cloud/Kubernetes work;
- no unrelated UI redesign.

### V1-05 — Human Review Boundary
**PLANNED**

Review record separate from machine output; `accepted` / `needs_correction`; survives reprocessing; review UI/source navigation; persistence tests.

### V1-06 — Operational Hardening
**PLANNED**

Clean clone/start; empty-DB migration; deterministic demo data; golden-path procedure; general CI backend/integration/lint/frontend gates; failure-state validation.

### V1-07 — Final Validation + Wishket Proof
**PLANNED**

Final test/evaluation; README; architecture visual; ≥4 screenshots; demo asset; limitations; release/tag. **Human Review remains the final release/proof gate.**

---

## 4. Execution Rules

Every batch defines **Goal / Scope / Acceptance / Non-goals** and records **What changed / What was actually executed / What was not verified / Remaining risks / Exact next action**.

PR lifecycle:

1. inspect current active focused PR and current exact-head pull-request-visible workflows first;
2. RED/CANCELLED/TIMED_OUT/ACTION_REQUIRED/stale IN_PROGRESS → inspect first concrete job/step/log; fix only that executed failure;
3. GREEN + in scope + no unresolved review/security/human-decision blocker → merge with expected-head guard;
4. update this MASTER on `main` with concrete evidence and main SHA;
5. continue to the next smallest step in the earliest unfinished batch.

Any SHA/run ID written here is historical evidence only. **Current repository/PR state always wins.** Missing push status is not evidence; prefer PR-visible exact-head workflow evidence. Agent self-report is not proof.

---

## 5. Current Batch Record — V1-04

### What changed

- reconciled and closed V1-03 from current PR #10 exact-head GREEN evidence;
- merged PR #10 with expected-head guard to `main` as `6de5a391715ace893189378710f8852b4542dfaa`;
- activated V1-04;
- created branch `v1-04-element-boundary` from current `main`;
- added `apps/api/src/claimtrace_api/parsing/elements.py` with a pure deterministic, provenance-preserving decomposition boundary;
- added focused tests in `apps/api/tests/test_claim_element_parser.py`;
- added `.github/workflows/v1-04-verify.yml` to execute the new tests plus Ruff on the PR exact head;
- opened bounded PR #11;
- no persistence/API/UI/human-review scope was added.

### What was actually executed

- PR #10 current exact head and workflows fetched before merge;
- run `32242502338` → **success**;
- run `32242502306` → **success**;
- browser golden-path execution step → **success**;
- PR #10 changed-file scope and review threads inspected; all review threads resolved;
- expected-head guarded merge of PR #10 → **success**;
- existing claim ORM, parser contracts, parsing service, `PAGE_SPAN_SEPARATOR`, and V1-02 verification conventions inspected before V1-04 implementation;
- PR #11 created and current review threads checked: none at creation;
- PR #11 workflow lookup immediately after creation returned no runs yet; therefore no executable V1-04 PASS is claimed.

### What was not verified

- PR #11 current exact-head `V1-04 Claim Element Verification` has not yet produced accepted GREEN evidence;
- focused element tests have not yet been accepted from GitHub Actions;
- persistence, API, idempotent decomposition runs, and human review are not implemented in this slice.

### Remaining risks

- first exact-head run may expose concrete implementation/format/type failures;
- semicolon-only decomposition is deliberately conservative and may under-segment claims without explicit delimiters; that case is surfaced as a warning rather than silently inferred;
- element persistence still needs a versioned/idempotent design after this pure boundary proves stable;
- human review must remain separate in V1-05.

### Exact next action

**Fetch PR #11 CURRENT head and CURRENT exact-head PR-visible workflows. If any required check is RED/CANCELLED/TIMED_OUT/ACTION_REQUIRED, inspect the first concrete failing step/log and fix only that failure. If checks are GREEN, inspect current scope/review/security state and merge with expected-head guard. Then update this MASTER with the actual merge SHA/evidence and continue V1-04 to the smallest persistence/idempotency slice. Do not add API/UI/review until preceding slices are GREEN.**

---

## 6. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| Existing stages 1–10 | VERIFIED BY STATIC INSPECTION | V1-01 |
| V1-02 comparison backend | EXECUTED GREEN / CLOSED | PR #7, run `32225430081` |
| V1-02 DB-free tests | 26 PASS | exact PR head |
| V1-02 PostgreSQL | 3 PASS / 0 skipped | exact PR head |
| V1-03 workspace slice | EXECUTED GREEN / MERGED | PR #8 |
| V1-03 contextual links | EXECUTED GREEN / MERGED | PR #9 |
| V1-03 browser golden path | EXECUTED GREEN / CLOSED | PR #10, run `32242502306` |
| V1-03 regression | EXECUTED GREEN | PR #10, run `32242502338` |
| V1-04 element boundary | PR OPEN / NOT YET VERIFIED | PR #11 |
| Persisted human review | NOT IMPLEMENTED | V1-05 |

---

## 7. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; decomposition is a domain-judgement boundary and therefore requires final human review.

v1.0 closes only when it is **usable, trustable, and showable**: full frozen workflow usable; expected failures explicit; source verification present; comparison + decomposition/review usable; clean checkout/migrations reproduced; general CI green; automated tests/evaluations reproducible; proof README/visuals/screenshots/demo/limitations/release tag complete.
