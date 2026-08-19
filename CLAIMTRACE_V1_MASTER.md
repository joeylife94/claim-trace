# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-20  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-07 — Final Validation + Wishket Proof  
**Current batch state:** **IN PROGRESS — current-head validation/retrieval/grounded deterministic evaluation is executed GREEN; external proof packaging + release/Human Review remain**

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

Current V1-07 evaluation evidence is now authoritative for the deterministic proof tier:

- retrieval corpus: 26 synthetic claims / 19 queries;
- dense Recall@1/3/5 `0.7696 / 0.9265 / 0.9706`, MRR@10 `0.9608`;
- lexical Recall@1/3/5 `0.7402 / 0.8971 / 0.9118`, MRR@10 `0.9608`;
- hybrid Recall@1/3/5 `0.7990 / 0.9265 / 0.9412`, MRR@10 `1.0000`;
- grounded deterministic: 16 cases, structured-output `1.000`, answerability `1.000`, insufficient precision/recall `1.000 / 1.000`, citation resolution `1.000`, statement citation coverage `1.000`, evidence-ID validity `1.000`, selection precision/recall `1.000 / 0.9167`, end-to-end success `0.9375`, forbidden citations `0`;
- hostile-grounding guardrails: **6/6 refused**;
- known grounded weak case remains `g01-single-storage`: retrieval did not supply the required labelled claim, so deterministic end-to-end success is intentionally not represented as `1.000`.

Real-local-model evaluation is **NOT RERUN** in V1-07: the exact-head GitHub-hosted runner executed a socket check and confirmed no Ollama endpoint at `host.docker.internal:11434`. The historical `qwen2.5:1.5b` run remains historical evidence only; no hosted provider was substituted.

Current operational evidence: V1-06 General CI proved **785 database-free PASS + 135 PostgreSQL integration PASS / 0 skipped**, with Ruff and frontend lint/typecheck GREEN, and PR #29 reran General CI GREEN on the final-evaluation exact head.

Golden-path state:

| Stage | Status | v1 delta |
| --- | --- | --- |
| 1–10 ingest → grounded Q&A | EXECUTED GREEN | current V1-07 retrieval + grounded deterministic evaluations completed |
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

PR #7, run `32225430081` success; DB-free comparison **26 PASS**; PostgreSQL **3 PASS / 0 skipped**; Ruff PASS; merge `db5e39d2118e42527a3794a32173e08535f18cec`.

### V1-03 — Comparison UI + Flow Stitching
**CLOSED**

PR #10, run `32242502306` success including browser golden path; merge `6de5a391715ace893189378710f8852b4542dfaa`.

### V1-04 — Claim Element Decomposition
**CLOSED**

PR #11 run `32252992292` success; PR #12 run `32259126905` success; Issue #13 / PR #14 run `32260927368` success, parser **6 PASS**, PostgreSQL persistence/API **7 PASS / 0 skipped**, Ruff PASS; merge `875e29529963fb28bd3d5efa44e98bee7848c689`.

### V1-05 — Human Review Boundary
**CLOSED**

- Issue #15 / PR #16: persistence/API, run `32264262027` success, PostgreSQL **2 PASS / 0 skipped**, Ruff PASS; merge `bf8623b0bdeb12c6b037bc538cea597ec0ecc50d`.
- Issue #17 / PR #18: review UI/source navigation, V1-03 regression `32265797797` + V1-05 `32265797594` success; browser document → decomposition → accepted review → persisted history → exact source highlight; merge `2c0471dde083c36a4c3c8ecbf893fa051df0e2b4`.
- Issue #19 was created from a stale snapshot and immediately closed as duplicate; no implementation attached.

### V1-06 — Operational Hardening
**CLOSED**

Acceptance areas:

- [x] clean clone/start path;
- [x] empty-DB migration path;
- [x] deterministic demo/sample material sufficient for the full supported golden path;
- [x] one repeatable whole-product golden-path procedure;
- [x] general CI backend/integration/lint/frontend gates;
- [x] expected unsupported/failure-state validation.

#### Closed — Issue #20 / PR #21: clean checkout + empty DB

- run `32275712641`, job `96142528344` → **SUCCESS**;
- Alembic `0001 → 0006 (head)` from empty DB;
- `/health` = `ok`; `/ready` = PostgreSQL `ok`;
- merge `380abc91ad703c3cf3d01e2466dc494d0a2ac6a1`; Issue #20 auto-closed.

#### Closed — Issue #22 / PR #23: deterministic whole-product golden path

- final V1-06 run `32277157847` → **SUCCESS**;
- V1-03 regression `32277157837` and V1-05 regression `32277157902` → **SUCCESS**;
- empty PostgreSQL + migrations, deterministic seed, API/Web health, full frozen browser flow, persisted human review, exact source navigation → **PASS**;
- merge `b7f3326f35d47537a9415845ab26f3b3ce0b024e`; Issue #22 auto-closed.

#### Closed — Issue #24 / PR #25: general repository CI

- General CI run `32278344808` → **SUCCESS**;
- database-free backend **785 PASS / 135 deselected**;
- PostgreSQL integration **135 PASS / 0 skipped / 785 deselected**;
- Ruff `All checks passed`; format `157 files already formatted`;
- frontend `npm ci` + ESLint + TypeScript typecheck → **SUCCESS**;
- merge `664ad95675b51356c42d5f98ec14d80bf6b56ed2`; Issue #24 auto-closed.

#### Closed — Issue #26 / PR #27: expected unsupported/failure states

- exact-head focused run `32278992050`, job `96153015153` → **5 PASS**;
- General CI `32278991988` → **SUCCESS**;
- explicitly verified non-PDF 415, image-only/no-text 422 without OCR, grounded no-evidence insufficiency, comparison `no_matches`, comparison `reference_not_indexed`;
- merge `1bc636985ba85754a0e99e3743b7ca5794c5d357`; Issue #26 auto-closed.

### V1-07 — Final Validation + Wishket Proof
**IN PROGRESS**

Acceptance areas:

- [x] final current-head automated validation/evaluation rerun;
- [x] retrieval evaluation reproduced;
- [x] grounded deterministic evaluation reproduced;
- [x] real local model validation rerun **or explicitly and visibly marked not rerun**;
- [ ] README communicates problem → solution → demo → evidence before deep implementation detail;
- [ ] architecture visual exists and matches current v1 boundaries;
- [ ] at least four useful product screenshots exist;
- [ ] concise golden-path demo asset exists;
- [ ] CI state/evidence is externally visible from proof surfaces;
- [ ] proof metrics link to reproducible evidence;
- [ ] known limitations are visible on proof surfaces;
- [ ] v1.0 proof release/tag exists;
- [ ] final Human Review / FREEZE decision.

#### Closed — Issue #28 / PR #29: current final evaluations

**Changed**
- added `.github/workflows/v1-07-final-evals.yml` as the PR-visible exact-head evaluation acceptance surface;
- reused the committed retrieval corpus/runner and deterministic grounded corpus/runner;
- generated current result/report artifacts without changing corpus labels or product code;
- added an executed hosted-runner availability check for the local Ollama endpoint.

**Actually Executed**
- first run `32279481096` failed after completing retrieval computation because the container UID could not overwrite bind-mounted committed result files (`PermissionError`); no metric was claimed from that failed exact head;
- smallest repair: make only `apps/api/evals/results` writable for the evaluation container in CI;
- final exact head `f4bf6dcfc32300270946c23a78b91471e97d3cb5`;
- V1-07 Final Evaluations run `32279743568`, job `96155426065` → **SUCCESS**;
- General CI regression run `32279743552` → **SUCCESS**;
- artifact `9375395190`, `v1-07-current-evaluations-f4bf6dcfc32300270946c23a78b91471e97d3cb5`, digest `sha256:2be19a6eaae3db89f14dcc3e55987c661bd647737d37ffca9119a91f707d4896`;
- review write-permission blocker resolved after the successful rerun;
- expected-head squash merge `3573f426c369265ede4eb49c721b108cbe9fa9d4`;
- Issue #28 auto-closed `completed`.

**Verified — Retrieval**
- configured embedding model `intfloat/multilingual-e5-small`, 384d, normalized;
- dense Recall@1/3/5 `0.7696 / 0.9265 / 0.9706`, MRR@10 `0.9608`;
- lexical Recall@1/3/5 `0.7402 / 0.8971 / 0.9118`, MRR@10 `0.9608`;
- hybrid Recall@1/3/5 `0.7990 / 0.9265 / 0.9412`, MRR@10 `1.0000`;
- these are a small synthetic regression corpus, **not a benchmark-quality claim about patent retrieval**.

**Verified — Grounded deterministic**
- 16 cases; structured output `1.000`; answerability `1.000`; insufficient precision/recall `1.000 / 1.000`;
- evidence-ID validity `1.000`; citation resolution `1.000`; statement citation coverage `1.000`;
- evidence selection precision/recall `1.000 / 0.9167`; end-to-end success `0.9375`; forbidden citations `0`;
- hostile guardrails **6/6 refused**;
- one known weak case (`g01-single-storage`) remains visible rather than being hidden.

**Real-local-model status**
- **NOT RERUN** on the V1-07 GitHub-hosted runtime;
- executed socket check confirmed no local Ollama endpoint on `host.docker.internal:11434`;
- no hosted provider was substituted; historical `qwen2.5:1.5b` evidence is not represented as current V1-07 model quality.

**Not Verified / Remaining Risks**
- proof-facing README/visuals/screenshots/demo still need to be refreshed from the current product state;
- the deterministic tier proves pipeline/source-control properties, not model semantic quality;
- citation resolvability ≠ semantic entailment;
- release/tag and final Human Review are intentionally not done in this evaluation work item.

**Exact Next Action**

**Re-read current main/MASTER and process any current active PR relevant to V1-07 proof packaging first. If none exists, search open Issues for one exactly covering proof-facing README + current architecture visual + ≥4 screenshots + concise demo asset + visible evidence/limitations. Reuse only an exact Issue; otherwise create one bounded proof-packaging Issue before implementation. Do not create the release/tag until proof packaging has executed verification and merged.**

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
| V1-06 clean checkout + empty DB migration | EXECUTED GREEN / CLOSED | Issue #20 / PR #21, run `32275712641` |
| V1-06 deterministic whole-product reproducibility | EXECUTED GREEN / CLOSED | Issue #22 / PR #23, run `32277157847` |
| V1-06 general CI | EXECUTED GREEN / CLOSED | Issue #24 / PR #25, run `32278344808`, DB-free **785 PASS**, PostgreSQL **135 PASS / 0 skipped**, Ruff + frontend PASS |
| V1-06 expected failure states | EXECUTED GREEN / CLOSED | Issue #26 / PR #27, run `32278992050`, **5 PASS** |
| V1-06 batch | **CLOSED** | every V1-06 acceptance area has current executed evidence |
| V1-07 current retrieval + deterministic grounded evaluations | EXECUTED GREEN / CLOSED | Issue #28 / PR #29, run `32279743568`, artifact `9375395190` |
| V1-07 real local model | **NOT RERUN — EXPLICIT** | executed hosted-runner check: no Ollama endpoint; no substitution |
| V1-07 proof packaging | NOT VERIFIED | next acceptance gap |

---

## 6. Known Risks / Closure Condition

Known limits: citation resolvability ≠ semantic entailment; current V1-07 deterministic evaluation is pipeline evidence, not model semantic-quality proof; OCR intentionally unsupported; Korean parser supports bounded patterns; comparison quality is retrieval quality, **not legal similarity**; human review records local reviewer judgement and does not certify legal correctness.

V1-06 is **CLOSED**. v1.0 closes only when it is **usable, trustable, and showable**: V1-07 proof README/visuals/screenshots/demo/limitations are current and evidence-backed; release/tag freezes that state; and the resulting candidate reaches explicit **IMPLEMENTATION / PROOF CANDIDATE READY — HUMAN REVIEW REQUIRED** before final FREEZE.
