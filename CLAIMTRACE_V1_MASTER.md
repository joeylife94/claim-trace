# ClaimTrace v1.0 Master

> **Authoritative execution contract for ClaimTrace v1.0.** Read this before every batch. `README.md` is external-facing, `docs/ARCHITECTURE.md` explains design, and `docs/ROADMAP.md` records broader possibilities. **This file controls what v1.0 is finishing now.**

**Last execution update:** 2026-08-22  
**Current target:** L4 Controlled Pilot  
**Current active batch:** V1-07 — Final Validation + Wishket Proof  
**Current batch state:** **HUMAN REVIEW PASS / FREEZE APPROVED — RELEASE TAG PENDING**

---

## 1. Goal and Product Boundary

Frozen v1.0 flow:

**ingest → parse → index → retrieve → ask → compare → decompose → review → verify source evidence**

Target: one analyst/reviewer on a trusted workstation or controlled on-premise environment, working with text-based Korean patent PDFs and source-verifiable analytical output.

ClaimTrace v1.0 does **not** provide legal advice and does not determine infringement, validity, novelty, equivalence, inventive step, patentability, or any other legal conclusion.

## 2. Human Review Closure

Human Review completed on 2026-08-22.

### Result

`PASS — FREEZE APPROVED`

The current controlled-pilot Proof candidate was reviewed against current `main`, the public README, committed Proof assets, recent V1-07 PR history, and the documented executed verification boundary.

Human Review accepted the current bounded Proof claims because:

- the public README explicitly frames ClaimTrace as a controlled single-user/on-premise pilot;
- legal conclusions are explicit non-claims;
- synthetic retrieval and grounded-evaluation metrics are explicitly regression evidence, not general patent-analysis accuracy claims;
- citation resolvability is explicitly not semantic entailment or legal correctness;
- current real-local-model quality is explicitly `NOT RERUN` / not claimed for V1-07;
- six committed product screenshots, one architecture visual, and one committed golden-path WebM exist under `docs/proof/`;
- V1-07 Proof Package and final regression/evaluation work were merged after executed PR-visible evidence;
- no open implementation PR remains for the reviewed v1.0 boundary.

## 3. Verified v1.0 Capability Boundary

The frozen Proof supports the following bounded product claims:

- ingest text-based Korean patent PDFs;
- validate/store/extract page text with canonical source locators;
- deterministic claim parsing and dependency handling within the supported parser boundary;
- dense, lexical, and hybrid retrieval with source navigation;
- evidence-grounded Q&A with explicit insufficient-evidence behavior;
- target/reference claim comparison under strict reference-document scope;
- deterministic source-backed claim-element decomposition;
- append-only human review state separate from machine output;
- navigation from reviewed/generated analytical surfaces back to persisted source text;
- reproducible deterministic whole-product browser flow on the committed synthetic corpus.

## 4. Executed Evidence

The reviewed Proof package and public README record executed evidence including:

### Operational verification

- clean checkout + empty database migration: **GREEN**;
- Alembic `0001 → 0006 (head)` from an empty PostgreSQL database: **PASS**;
- deterministic whole-product browser golden path: **PASS**;
- backend database-free tier: **785 PASS**;
- PostgreSQL integration tier: **135 PASS / 0 skipped**;
- Ruff lint/format and frontend ESLint/TypeScript: **GREEN**;
- expected failure-state verification: **5 PASS**.

### Retrieval regression evaluation

Synthetic regression corpus: **26 claims / 19 queries**.

| Mode | Recall@1 | Recall@3 | Recall@5 | MRR@10 |
| --- | ---: | ---: | ---: | ---: |
| Dense | 0.7696 | 0.9265 | 0.9706 | 0.9608 |
| Lexical | 0.7402 | 0.8971 | 0.9118 | 0.9608 |
| Hybrid RRF | 0.7990 | 0.9265 | 0.9412 | 1.0000 |

These are synthetic regression metrics for reproducibility/ranking regressions, not benchmark-quality claims about general patent retrieval.

### Grounded deterministic evaluation

16 committed cases:

- structured output: `1.000`;
- answerability: `1.000`;
- insufficient-evidence precision / recall: `1.000 / 1.000`;
- citation resolution: `1.000`;
- statement citation coverage: `1.000`;
- evidence-ID validity: `1.000`;
- evidence selection precision / recall: `1.000 / 0.9167`;
- end-to-end success: `0.9375`;
- forbidden cross-document citations: `0`;
- hostile grounding payloads refused: **6 / 6**.

Known weak case `g01-single-storage` remains visible; end-to-end success is intentionally not represented as `1.000`.

## 5. Proof Assets

Committed buyer-facing Proof package:

- `docs/proof/architecture-v1.svg`
- `docs/proof/screenshots/01-documents.png`
- `docs/proof/screenshots/02-search-results.png`
- `docs/proof/screenshots/03-grounded-answer.png`
- `docs/proof/screenshots/04-comparison.png`
- `docs/proof/screenshots/05-source-highlight.png`
- `docs/proof/screenshots/06-human-review.png`
- `docs/proof/demo/claimtrace-golden-path.webm`
- `docs/proof/README.md`

These assets are generated from the deterministic repository proof flow and are not hand-authored product mockups.

## 6. Not Verified / Explicit Non-Claims

The following remain outside the approved v1.0 Proof claim boundary:

- legal correctness, infringement, validity, novelty, equivalence, inventive step, or patentability;
- benchmark-quality general patent retrieval performance;
- semantic entailment merely because a citation resolves to stored source text;
- OCR or scanned/image-only PDF recovery;
- universal Korean patent parsing correctness;
- current real-local-model quality for V1-07: GitHub-hosted evaluation had no local Ollama endpoint, so historical local-model runs remain historical only;
- authentication, RBAC, multi-tenancy, public-cloud deployment, Kubernetes, billing, or admin-console production readiness;
- production security/compliance certification.

## 7. Remaining Risks

- Synthetic deterministic Proof demonstrates workflow/provenance behavior, not general legal or semantic correctness.
- Retrieval/evaluation corpora are intentionally small and regression-oriented.
- Human review is part of the product boundary; machine decomposition is not reviewer judgement.
- Text-based PDF support only remains an intentional v1.0 limitation.

## 8. Release / Tag Status

Human Review has approved FREEZE, but a repository release/tag has **not been verified as created in the currently connected GitHub tooling**.

Therefore the authoritative closure state is intentionally:

`HUMAN REVIEW PASS / FREEZE APPROVED — RELEASE TAG PENDING`

Do **not** upgrade this to `CLAIMTRACE PROOF v1.0 CLOSED` until a real repository tag/release is created and verified.

Recommended proof tag name, if no repository convention conflicts:

`v1.0-proof`

The tag must point to the reviewed/frozen current main state or to a later documentation-only closure commit that does not alter the reviewed product/runtime behavior.

## 9. Closure Ledger

**Changed**
- Human Review decision recorded;
- Proof claim boundary and explicit non-claims frozen;
- automatic v1.0 implementation stopped.

**Actually Executed**
- V1-00 through V1-07 implementation/verification work already executed through the repository's bounded Issue/PR lifecycle;
- final Human Review checked current README, committed Proof assets, current main state, and recent V1-07 merged PR evidence.

**Verified**
- current bounded Proof is suitable for Wishket/freelance demonstration with the limitations stated above;
- current public README is sufficiently conservative for the approved Proof boundary;
- Proof asset inventory exists in current main.

**Not Verified**
- release/tag creation remains mechanically pending;
- all explicit non-claims in Section 6 remain unverified and must not be promoted to PASS.

**Exact Next Action**
- `FREEZE` all automatic ClaimTrace v1.0 development.
- Create/verify the real repository Proof tag/release (`v1.0-proof` recommended if compatible with repository convention).
- After tag/release verification, update this MASTER once to `CLAIMTRACE PROOF v1.0 CLOSED / FREEZE` and make no further v1.0 implementation changes unless a new paid-delivery or explicit Proof requirement creates a new acceptance gap.
