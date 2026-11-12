# ClaimTrace Controlled Pilot Handoff

This is the repository-native acceptance path for handing ClaimTrace to one analyst/reviewer on a trusted workstation or controlled on-premise environment.

## One-command acceptance

Prerequisites for a clean checkout:

- Docker with Docker Compose support (the stack, its images and the migrations run in Docker);
- Node.js 22+ and npm;
- `make`, `curl` and `sha256sum` on the host: the sub-scripts call `make init` when no `.env` exists (which copies `.env.example` to `.env` in the checkout and never overwrites an existing one), poll the services with `curl`, and the handoff step hashes the proof assets with `sha256sum`;
- network access to pull container images, run `npm ci`, and download Playwright and Chromium;
- permission to install Chromium's system dependencies: the retry step runs `npx playwright install --with-deps chromium`, which on Linux may need root or `apt` access;
- free host ports `15434`, `18002`, `13011`, `15435`, `18003` and `13003` (set by the handoff script and, for `13011`, by the retry step's browser script; changing them means editing those files; the clean-start step uses ephemeral ports).

`git` is optional: it is only used to record the commit SHA in the generated report, which falls back to `unknown`.

The Node.js/npm requirement is intentional: the reused browser-verification path installs and executes the existing web test tooling outside Docker. The exact-head GitHub workflow provisions Node.js 22 before running the same handoff command. Each step starts and tears down its own Compose project, separate from the ordinary developer stack.

From a clean checkout with those prerequisites available:

```sh
sh scripts/verify-controlled-pilot-handoff.sh
```

The verifier deliberately reuses accepted ClaimTrace assets rather than adding a new product capability. It executes:

1. clean isolated PostgreSQL startup and migration to Alembic head;
2. the existing real web → Next action → FastAPI → PostgreSQL failed-ingestion retry flow using the repository-authored public-safe synthetic PDF state;
3. the deterministic whole-product browser golden path over two synthetic documents, covering retrieve/grounded ask/target-reference compare/decompose/human-review/source-navigation surfaces. The two documents are seeded before the browser starts: `apps/api/tests/v1_03_browser_seed.py` uploads, parses and indexes them through the API's HTTP surfaces using FastAPI's `TestClient`. No browser script uploads a PDF; the only browser-level ingestion action exercised is the retry of a seeded failed document in step 2;
4. presence and SHA-256 hashing of the committed reviewer-facing proof assets.

A successful run writes a bounded handoff package under `build/controlled-pilot-handoff/`:

- `README.md` — executed acceptance state, bounded flow, and explicit limitations;
- `proof-assets.sha256` — hashes of the committed source-navigation/review/proof assets;
- `handoff-report.sha256` — hash of the generated reviewer-facing report.

The generated package is evidence of this supported deterministic controlled-pilot acceptance path only. It is not a general semantic benchmark, production-readiness certification, or legal-analysis result.

## What this handoff does not exercise

This handoff was accepted at milestone P14 (destination D2) and reuses only paths that existed then. It does not exercise any of the later destinations. Each is verified elsewhere:

| Not exercised here | Where it is verified instead |
| --- | --- |
| D3 real-public corpus (two hash-pinned public Korean patent PDFs, downloaded at run time) | `Progression D3 Real Public Corpus` workflow; `scripts/verify-d3-real-corpus-inputs.sh`; `apps/api/tests/d3_acceptance/test_real_public_corpus.py` |
| D4 description-evidence derive/index/search | `Progression D4 Description Evidence` workflow; `apps/api/tests/d4_acceptance/test_real_public_description.py`; `apps/api/tests/test_description_evidence.py` |
| D5 analyst Cases and persisted Case-grounded results | General CI (PostgreSQL integration tier): `apps/api/tests/test_analyst_cases_integration.py` |
| D6 mixed-PDF text-layer classification and fail-closed rejection | General CI: `apps/api/tests/test_parsing.py` and `apps/api/tests/test_documents_upload.py` (`test_mixed_text_layer_pdf_fails_closed`) |

D3 and D4 use real public documents and are not part of a default `pytest` run. Cases and description search are API-only; the browser flows in this handoff do not touch them.

## Boundary

Supported inputs remain text-based PDFs and repository-authored/public-safe synthetic evidence used by the existing verification paths. OCR or scanned/image-only PDF recovery is outside this handoff.

Since the handoff was accepted, PDF ingestion also fails closed on mixed text layers: a PDF in which any page has no extractable text is rejected as mixed or ambiguous, not ingested partially. This rule is not exercised by the handoff run itself (see the table above). A text-native PDF that merely contains a blank or drawing-only page is rejected too, and a scan that already carries an embedded text layer is treated as text; neither is OCR.

Citation/source resolution demonstrates navigation to persisted source evidence. It does **not** establish semantic entailment or legal correctness.

ClaimTrace does **not** determine infringement, validity, novelty, equivalence, inventive step, patentability, or any other legal conclusion.

This handoff also does not claim authentication/RBAC/multi-tenancy, public-cloud or Kubernetes readiness, customer/private-corpus support, security/compliance certification, or benchmark-quality general patent retrieval accuracy.

## Existing proof reused

The handoff reuses the frozen v1.0 proof assets under `docs/proof/` and the post-v1 accepted deterministic/recovery verification paths up to P14 (clean start, failed-ingestion retry, golden path). It does not move or reinterpret `v1.0-proof`.
