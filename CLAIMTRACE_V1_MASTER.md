# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-19  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-03 — Comparison UI + Flow Stitching  
**Current batch state:** **IN PROGRESS**

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
| 11 target/reference selection | UI IMPLEMENTED, FLOW STITCHING OPEN | V1-03 |
| 12 claim comparison | BACKEND + FIRST UI SLICE GREEN | V1-02 closed; V1-03 ongoing |
| 13 element decomposition | MISSING | V1-04 |
| 14 persisted human review | MISSING | V1-05 |
| 15 source verification everywhere | PARTIAL | comparison UI now source-linked; decomposition must inherit guarantee |

**Do not rebuild stages 1–10.**

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
- PR-visible workflow run `32225430081` → **success**;
- database-free comparison tests **26 PASS**;
- PostgreSQL integration **3 PASS / 0 skipped**;
- Ruff lint **All checks passed**;
- Ruff format **141 files already formatted**;
- Docker API build + PostgreSQL readiness succeeded;
- fixes were limited to executed failures only;
- merged to `main` as `db5e39d2118e42527a3794a32173e08535f18cec`.

### V1-03 — Comparison UI + Flow Stitching
**IN PROGRESS**

Goal: make closed comparison backend usable from web UI and connect it to the existing document flow.

Acceptance:

- [x] user can choose two distinct documents and one target claim in web UI;
- [x] UI calls existing `POST /api/v1/compare/claims`, with no parallel comparison path;
- [x] target and reference results render separately and preserve document identity;
- [x] rendered comparison source spans navigate to exact source text using existing deep-link semantics;
- [x] `reference_not_indexed` and `no_matches` are explicit user-visible states;
- [x] loading and API error states are explicit;
- [ ] document detail exposes contextual navigation to search, grounded Q&A, and comparison where valid;
- [x] focused frontend checks for the first V1-03 slice executed successfully on exact PR head.

First bounded V1-03 slice evidence:

- PR #8 `feat(web): add bounded claim comparison workspace`;
- exact head `eed3222d117de5d79f2ab3a28c32c4c732b1ec2f`;
- workflow run `32228257540` → **success**;
- `npm ci` **PASS**;
- ESLint **PASS**;
- TypeScript `tsc --noEmit` **PASS**;
- no unresolved review threads;
- merged with expected-head guard to `main` as `3a12c6601da8ece8c71ea5233c77100d2229bbb9`;
- merged scope: typed comparison client, comparison server action, `/compare` workspace, target/reference + target-claim selection, explicit no-match/error/loading states, source-backed result links, focused PR verification workflow.

Non-goals:

- no comparison backend re-hardening without executed V1-03 failure;
- no element decomposition;
- no human review persistence;
- no legal semantic judgement;
- no unrelated redesign.

### V1-04 — Claim Element Decomposition
**PLANNED**

Element schema/persistence; deterministic decomposition boundary; source sub-spans; versioned/idempotent run; warnings for resistant claims; API + tests.

### V1-05 — Human Review Boundary
**PLANNED**

Review record separate from machine output; `accepted` / `needs_correction`; survives reprocessing; review UI/source navigation; persistence tests.

### V1-06 — Operational Hardening
**PLANNED**

Clean clone/start; empty-DB migration; deterministic demo data; golden-path procedure; general CI backend/integration/lint/frontend gates; failure-state validation.

### V1-07 — Final Validation + Wishket Proof
**PLANNED**

Final test/evaluation; README; architecture visual; ≥4 screenshots; demo asset; limitations; release/tag.

---

## 4. Execution Rules

Every batch defines **Goal / Scope / Acceptance / Non-goals** and records **What changed / What was actually executed / What was not verified / Remaining risks / Exact next action**.

PR lifecycle:

1. inspect active focused PR and exact-head pull-request-visible workflows first;
2. RED → inspect first failing job/step/log; fix only that executed failure;
3. GREEN + in scope + no unresolved review/security/human-decision blocker → merge with expected-head guard;
4. update this MASTER on `main` with concrete evidence and main SHA;
5. continue to the next smallest step in the earliest unfinished batch.

Missing push status is not evidence. Prefer PR-visible workflow evidence. Agent self-report is not proof.

---

## 5. Current Batch Record — V1-03

### What changed

- synchronized V1-02 to executed GREEN evidence and closed it;
- implemented and merged the first V1-03 comparison UI slice via PR #8;
- added typed web comparison client and server action;
- added `/compare` workspace with target/reference document and target-claim selection;
- rendered target/reference results separately with exact source links;
- exposed explicit loading, API error, `reference_not_indexed`, and `no_matches` states;
- added bounded PR-visible frontend lint/typecheck workflow.

### What was actually executed

- PR #8 exact-head workflow run `32228257540` completed **success**;
- dependency installation **PASS**;
- ESLint **PASS**;
- TypeScript typecheck **PASS**;
- review threads: none;
- merge completed with expected head `eed3222d117de5d79f2ab3a28c32c4c732b1ec2f`;
- resulting `main` SHA after merge: `3a12c6601da8ece8c71ea5233c77100d2229bbb9`.

### What was not verified

- browser-level interaction of `/compare` has not yet been exercised;
- document-detail contextual links are not implemented yet;
- V1-03 is therefore not closed.

### Remaining risks

- target/reference selector UX must remain coherent when preselected from document detail;
- source-link behavior is typechecked but awaits final browser-level golden-path validation;
- unrelated draft proof PR #6 remains out of scope.

### Exact next action

**Create the next smallest V1-03 PR: add contextual document-detail links to document-scoped Search, Grounded Q&A, and `/compare?target=<document-id>`; teach `/compare` to honor that target preselection; run exact-head frontend lint/typecheck, merge GREEN, then reassess whether V1-03 can close or needs browser-level validation before closure.**

---

## 6. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| Existing stages 1–10 | VERIFIED BY STATIC INSPECTION | V1-01 |
| V1-02 comparison backend | EXECUTED GREEN / CLOSED | PR #7, run `32225430081` |
| V1-02 DB-free tests | 26 PASS | exact PR head |
| V1-02 PostgreSQL | 3 PASS / 0 skipped | exact PR head |
| V1-02 Ruff | PASS | lint + format |
| V1-03 first UI slice | EXECUTED GREEN / MERGED | PR #8, run `32228257540` |
| V1-03 frontend lint | PASS | exact PR head |
| V1-03 TypeScript | PASS | exact PR head |
| V1-03 merged main | VERIFIED | `3a12c6601da8ece8c71ea5233c77100d2229bbb9` |
| Element decomposition | NOT IMPLEMENTED | V1-04 |
| Persisted human review | NOT IMPLEMENTED | V1-05 |

---

## 7. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; decomposition is a domain-judgement boundary and therefore requires final human review.

v1.0 closes only when it is **usable, trustable, and showable**: full frozen workflow usable; expected failures explicit; source verification present; comparison + decomposition/review usable; clean checkout/migrations reproduced; general CI green; automated tests/evaluations reproducible; proof README/visuals/screenshots/demo/limitations/release tag complete.
