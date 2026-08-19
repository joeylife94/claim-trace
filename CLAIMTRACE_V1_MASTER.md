# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-19  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-04 — Claim Element Decomposition  
**Current batch state:** **IN PROGRESS — first bounded implementation slice pending**

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
| 13 element decomposition | MISSING | V1-04 active |
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

#### PR #8 — comparison workspace

- exact head `eed3222d117de5d79f2ab3a28c32c4c732b1ec2f`;
- workflow run `32228257540` → **success**;
- `npm ci`, ESLint, TypeScript → **PASS**;
- merged to `main` as `3a12c6601da8ece8c71ea5233c77100d2229bbb9`.

#### PR #9 — contextual flow stitching

- exact head `302d813a1eb12190275646c1327a430587ce94e8`;
- workflow run `32228493202` → **success**;
- dependency install, ESLint, TypeScript → **PASS**;
- merged to `main` as `6088fbbfbc4abad2e0983b03e464a74919b8124d`.

#### PR #10 — browser golden-path closure

- final exact head `1f093cbc6d611ef1aaedbea1ed934ff1f88d860c`;
- V1-02 regression run `32242502338` → **success**;
- V1-03 run `32242502306` → **success**;
- `web-checks`: install, ESLint, TypeScript → **PASS**;
- `browser-golden-path`: exact-head checkout, deterministic runtime config, API/Web image build, PostgreSQL migration, deterministic two-document seed, API/Web startup, Chromium install, and browser golden-path execution → **PASS**;
- no unresolved review threads;
- changed files were bounded to `.github/workflows/v1-03-verify.yml`, `apps/api/tests/v1_03_browser_seed.py`, and `apps/web/e2e/v1-03-golden-path.mjs`;
- merged with expected-head guard to `main` as `6de5a391715ace893189378710f8852b4542dfaa`.

V1-03 acceptance is fully met. The older cancelled run on `53c4abc...` is retained only as history and is not authoritative over the final exact-head GREEN evidence.

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

- reconciled stale V1-03 MASTER state with current PR #10 exact-head evidence;
- verified PR #10 exact head `1f093cbc...` had both required PR-visible workflows GREEN;
- confirmed PR #10 was mergeable, non-draft, scope-bounded, and had no unresolved review threads;
- merged PR #10 with expected-head guard to `main` as `6de5a391715ace893189378710f8852b4542dfaa`;
- closed V1-03 and activated V1-04;
- no decomposition implementation has been merged yet.

### What was actually executed

- current PR #10 metadata fetched from GitHub;
- exact-head workflow lookup for `1f093cbc6d611ef1aaedbea1ed934ff1f88d860c`;
- run `32242502338` → **success**;
- run `32242502306` → **success**;
- browser job step evidence confirmed `Execute V1-03 browser golden path` → **success**;
- PR changed-file scope inspected;
- PR review threads inspected: all resolved;
- expected-head guarded merge executed successfully.

### What was not verified

- V1-04 decomposition implementation has not yet been executed or tested;
- no claim-element persistence/API exists yet on `main` at this checkpoint.

### Remaining risks

- element boundaries must remain strictly inside canonical claim provenance;
- deterministic splitting rules can over-segment or under-segment Korean claim syntax, so resistant shapes need explicit warnings rather than silent authority;
- human review state must remain a separate later concern and must not be embedded into machine decomposition records.

### Exact next action

**Inspect the existing claim persistence/parser/service patterns, then implement the smallest V1-04 slice: a deterministic in-memory/domain decomposition boundary with ordered element source sub-spans and focused unit tests. Do not add review persistence or UI in this slice. Open a bounded PR and use current exact-head executable evidence before merge.**

---

## 6. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| Existing stages 1–10 | VERIFIED BY STATIC INSPECTION | V1-01 |
| V1-02 comparison backend | EXECUTED GREEN / CLOSED | PR #7, run `32225430081` |
| V1-02 DB-free tests | 26 PASS | exact PR head |
| V1-02 PostgreSQL | 3 PASS / 0 skipped | exact PR head |
| V1-03 workspace slice | EXECUTED GREEN / MERGED | PR #8, run `32228257540` |
| V1-03 contextual links | EXECUTED GREEN / MERGED | PR #9, run `32228493202` |
| V1-03 browser golden path | EXECUTED GREEN / CLOSED | PR #10, run `32242502306` |
| V1-03 regression | EXECUTED GREEN | PR #10, run `32242502338` |
| Element decomposition | NOT IMPLEMENTED | V1-04 active |
| Persisted human review | NOT IMPLEMENTED | V1-05 |

---

## 7. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; decomposition is a domain-judgement boundary and therefore requires final human review.

v1.0 closes only when it is **usable, trustable, and showable**: full frozen workflow usable; expected failures explicit; source verification present; comparison + decomposition/review usable; clean checkout/migrations reproduced; general CI green; automated tests/evaluations reproducible; proof README/visuals/screenshots/demo/limitations/release tag complete.
