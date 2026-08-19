# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-20  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-06 — Operational Hardening  
**Current batch state:** **IN PROGRESS — clean start/empty-DB and deterministic whole-product reproducibility are executed GREEN; general CI + expected failure-state hardening remain**

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

Existing engine: FastAPI + Next.js, PostgreSQL + pgvector/pg_trgm, PDF persistence/provenance, deterministic Korean claim parsing, dense/lexical/RRF retrieval, exact source links, local/self-hosted LLM boundary, grounded Q&A with server-issued evidence IDs, citation resolution, explicit insufficient evidence, deterministic/real-local-model evaluation tiers, hostile-evidence guards, Docker Compose.

Historical evidence retained until final rerun: 876 backend tests after Phase 4A-2; deterministic grounded citation resolution `1.000`; `qwen2.5:1.5b` citation resolution `1.000`; statement citation coverage `1.000`; forbidden cross-document citations `0`.

Golden-path state:

| Stage | Status | v1 delta |
| --- | --- | --- |
| 1–10 ingest → grounded Q&A | EXECUTED GREEN in deterministic whole-product run | final V1-07 evaluation rerun remains |
| 11 target/reference selection | EXECUTED GREEN | V1-03 + V1-06 whole-product proof |
| 12 claim comparison | EXECUTED GREEN | V1-02/V1-03 + V1-06 whole-product proof |
| 13 element decomposition | EXECUTED GREEN | V1-04 + V1-06 whole-product proof |
| 14 persisted human review | EXECUTED GREEN | V1-05 + V1-06 whole-product proof |
| 15 source verification everywhere | EXECUTED GREEN for frozen golden path | search, grounded, comparison, review source navigation verified |

**Do not rebuild stages 1–14.**

---

## 3. Execution Plan

### V1-00 — Master Freeze
**CLOSED**

### V1-01 — Golden Path Gap Audit
**CLOSED**

### V1-02 — Claim Comparison Backend
**CLOSED**

Closure evidence: PR #7, run `32225430081` success; DB-free comparison **26 PASS**; PostgreSQL **3 PASS / 0 skipped**; Ruff PASS; merge `db5e39d2118e42527a3794a32173e08535f18cec`.

### V1-03 — Comparison UI + Flow Stitching
**CLOSED**

Closure evidence: PR #10, run `32242502306` success including browser golden path; merge `6de5a391715ace893189378710f8852b4542dfaa`.

### V1-04 — Claim Element Decomposition
**CLOSED**

Closure evidence: PR #11 run `32252992292` success; PR #12 run `32259126905` success; Issue #13 / PR #14 run `32260927368` success, parser **6 PASS**, PostgreSQL persistence/API **7 PASS / 0 skipped**, Ruff PASS; merge `875e29529963fb28bd3d5efa44e98bee7848c689`.

### V1-05 — Human Review Boundary
**CLOSED**

- Issue #15 / PR #16: persistence/API, exact-head run `32264262027` success, PostgreSQL **2 PASS / 0 skipped**, Ruff PASS; merge `bf8623b0bdeb12c6b037bc538cea597ec0ecc50d`.
- Issue #17 / PR #18: review UI/source navigation, exact-head V1-03 regression `32265797797` and V1-05 `32265797594` success; browser document → decomposition → accepted review → persisted history → exact source highlight; merge `2c0471dde083c36a4c3c8ecbf893fa051df0e2b4`.
- Issue #19 was created from a stale snapshot and immediately closed as duplicate; no implementation attached.

### V1-06 — Operational Hardening
**IN PROGRESS**

Goal: prove the supported product is reproducible and operationally repeatable, not merely implemented on isolated feature PRs.

Acceptance areas:

- [x] clean clone/start path;
- [x] empty-DB migration path;
- [x] deterministic demo/sample material sufficient for the full supported golden path;
- [x] one repeatable whole-product golden-path procedure;
- [ ] general CI backend/integration/lint/frontend gates;
- [ ] expected unsupported/failure-state validation.

#### Closed work item — Issue #20 / PR #21: clean checkout + empty DB

**Changed**

- isolated Compose verifier `scripts/verify-v1-06-clean-start.sh`;
- exact-head PR-visible `.github/workflows/v1-06-clean-start.yml`;
- safe `.env` initialization, empty isolated PostgreSQL state, full migration chain, API health/readiness;
- workflow coverage includes Compose/env/API/Makefile/PostgreSQL init inputs and uses ephemeral host ports.

**Actually Executed**

- final exact PR head `5030fb023e34b9a58b1c3a2c4d8d3d2ed9d978ea`;
- run `32275712641`, job `96142528344` → **SUCCESS**;
- full Alembic `0001 → 0006 (head)` from empty database;
- `/health` → `{"status":"ok"}`;
- `/ready` → `{"status":"ready","dependencies":{"postgres":"ok"}}`;
- three review correctness findings fixed in the same PR and resolved;
- expected-head squash merge `380abc91ad703c3cf3d01e2466dc494d0a2ac6a1`;
- Issue #20 auto-closed `completed`.

**Verified**

- fresh GitHub-hosted checkout + committed defaults can construct configuration and start an isolated DB/API path;
- empty database reaches current migration head;
- API is live and DB-ready;
- verifier is exact-head, PR-visible, and non-skipping.

**Not Verified / Remaining Risk after this work item**

- complete deterministic user workflow was not part of Issue #20; closed separately by #22/#23 below;
- general CI and expected failure states remain.

#### Closed work item — Issue #22 / PR #23: deterministic whole-product golden path

**Changed**

- reused committed synthetic Korean patent-like corpus and the existing real ingestion → parse → index seed path; no new product data subsystem;
- added `scripts/verify-v1-06-golden-path.sh` for isolated deterministic fake-embedding/fake-LLM runtime;
- added `apps/web/e2e/v1-06-golden-path.mjs` connecting Search → Grounded Q&A → Compare → Decompose/Review → exact source highlighting after real seeded ingest/parse/index;
- added exact-head PR-visible `.github/workflows/v1-06-golden-path.yml` with frontend lint/typecheck plus whole-product browser gate;
- search/grounded selectors explicitly verify the selected target document, and source hrefs are checked against the expected target/reference document path so document-scope leakage cannot silently pass.

**Actually Executed**

- first exact-head V1-06 run `32276297759` reached a healthy migrated/seeded runtime but failed on an ambiguous Playwright `Question` selector; only that concrete selector was repaired;
- second run `32276794552` completed the combined path but review identified insufficient document-scope assertions; only those assertions were added and the review thread was resolved;
- final exact PR head `a1490d9154cb871adbe6f84de85e8efd24273ede`;
- final V1-06 run `32277157847`, job `96147171139` → **SUCCESS**;
- final V1-03 regression run `32277157837` → **SUCCESS**;
- final V1-05 regression run `32277157902` → **SUCCESS**, including review persistence/API, Ruff, frontend lint/typecheck, and browser review path;
- final whole-product logs show exact-head checkout, `.env` creation from committed defaults, API/Web build, empty PostgreSQL start, Alembic `0001 → 0006`, deterministic ingestion/parse/index of `synthetic-sensor-collector.pdf` and `synthetic-battery-thermal.pdf`, healthy API/Web start, and `V1-06 whole-product golden path: PASS`;
- PR #23 diff remained limited to three verification assets and had no unresolved review thread;
- expected-head squash merge `b7f3326f35d47537a9415845ab26f3b3ce0b024e`;
- Issue #22 auto-closed `completed`.

**Verified**

- deterministic committed sample material is sufficient for two-document comparison and the full frozen user workflow;
- clean isolated runtime executes ingest → parse → index before browser steps;
- document-scoped hybrid search exposes an exact target source highlight;
- grounded Q&A exposes exact target evidence or the supported explicit insufficient-evidence path;
- comparison target/reference selection and source navigation remain in their respective document scopes;
- decomposition creates source-backed elements; accepted human review persists separately and is visible in review history;
- the final review source opens the exact persisted source highlight;
- frontend lint/typecheck and V1-03/V1-05 regression workflows remain GREEN on the final exact head.

**Not Verified**

- one consolidated general CI policy covering the repository’s required backend/unit/integration/lint/frontend gates on ordinary changes;
- the final V1-06 set of deliberately unsupported/expected failure states under a clean current-head run;
- V1-07 final retrieval/grounding evaluation reruns and proof packaging.

**Remaining Risks**

- quality evidence is still distributed across feature-specific workflows; V1-06 requires a clear general CI gate before closure;
- expected failure behavior has historical/unit coverage but has not yet been frozen as the final current V1-06 failure-state set;
- GitHub-hosted npm install output currently reports dependency audit findings; dependency-remediation work is not silently considered complete by lint/typecheck success and should only be pulled into v1.0 if required by the bounded V1-06/V1-07 acceptance contract.

**Exact Next Action**

**Search current open Issues for one that exactly represents the next V1-06 acceptance gap: general CI covering backend tests/integration/Ruff plus frontend lint/typecheck on ordinary repository changes. Reuse only an exact active Issue; otherwise create exactly one bounded Issue before implementation. After that work item merges and MASTER is reconciled, re-evaluate V1-06 closure before selecting the final expected-failure-state gap.**

### V1-07 — Final Validation + Wishket Proof
**PLANNED**

Final test/evaluation rerun; README; architecture visual; ≥4 screenshots; demo asset; limitations; release/tag. Human Review remains the final release/proof gate before proof freeze.

---

## 4. Execution Rules

Every batch records **Goal / Scope / Acceptance / Non-goals / What changed / What was actually executed / Verified / Not Verified / Remaining risks / Exact Next Action**.

Start every run in this order:

**current repository/PR state → current exact head → exact-head required workflows → MASTER reconciliation → action**.

Active PR first. For new gaps: exact active Issue first, otherwise exactly one bounded Issue before branch/commit/implementation. Keep one active implementation Issue at a time. Do not create Issues for concrete CI/review fixes inside the active work item.

PR lifecycle: current exact-head RED/CANCELLED/TIMED_OUT/ACTION_REQUIRED/stale IN_PROGRESS → fix only the first concrete executed failure. GREEN + in scope + no unresolved blocker → merge with expected-head guard, confirm intended Issue closure, reconcile MASTER on `main`, then re-evaluate closure before selecting another Issue.

Any SHA/run ID here is historical evidence only; **current repository/PR state always wins**. Missing push status is not evidence. Agent self-report is not proof. BLOCKED/HOLD is not terminal; technical blockers stay recorded while the scheduled task remains enabled. Freeze/disable only at explicit Human Review / FREEZE / proof-candidate-ready / completion / user-requested stop.

---

## 5. Verification Evidence

| Evidence | State | Note |
| --- | --- | --- |
| V1-02 comparison backend | EXECUTED GREEN / CLOSED | PR #7, run `32225430081` |
| V1-03 browser golden path | EXECUTED GREEN / CLOSED | PR #10, run `32242502306` |
| V1-04 decomposition | EXECUTED GREEN / CLOSED | PR #11/#12/#14 |
| V1-05 review persistence/API + UI/source | EXECUTED GREEN / CLOSED | Issues #15/#17, PRs #16/#18 |
| V1-06 clean checkout + empty DB migration | EXECUTED GREEN / CLOSED | Issue #20 / PR #21, run `32275712641`, merge `380abc91...` |
| V1-06 deterministic whole-product reproducibility | EXECUTED GREEN / CLOSED | Issue #22 / PR #23, final exact-head run `32277157847`, regressions `32277157837`/`32277157902`, merge `b7f3326f...` |
| V1-06 general CI | NOT VERIFIED | next bounded acceptance gap |
| V1-06 final expected failure-state set | NOT VERIFIED | follow-on only after general CI reconciliation |

---

## 6. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current real-model evidence uses a small model and synthetic data; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; human review records local reviewer judgement and does not certify legal correctness.

v1.0 closes only when it is **usable, trustable, and showable**: full frozen workflow usable; expected failures explicit; source verification present; comparison + decomposition/review usable; clean checkout/migrations reproduced; general CI green; automated tests/evaluations reproducible; proof README/visuals/screenshots/demo/limitations/release tag complete.
