# ClaimTrace Controlled Pilot Handoff

This is the repository-native acceptance path for handing ClaimTrace to one analyst/reviewer on a trusted workstation or controlled on-premise environment.

## One-command acceptance

Prerequisites for a clean checkout:

- Docker with Docker Compose support;
- Node.js 22+;
- npm.

The Node.js/npm requirement is intentional: the reused browser-verification path installs and executes the existing web test tooling outside Docker. The exact-head GitHub workflow provisions Node.js 22 before running the same handoff command.

From a clean checkout with those prerequisites available:

```sh
sh scripts/verify-controlled-pilot-handoff.sh
```

The verifier deliberately reuses accepted ClaimTrace assets rather than adding a new product capability. It executes:

1. clean isolated PostgreSQL startup and migration to Alembic head;
2. the existing real web → Next action → FastAPI → PostgreSQL failed-ingestion retry flow using the repository-authored public-safe synthetic PDF state;
3. the deterministic whole-product browser golden path, covering supported ingest/retrieve/grounded ask/target-reference compare/decompose/human-review/source-navigation surfaces;
4. presence and SHA-256 hashing of the committed reviewer-facing proof assets.

A successful run writes a bounded handoff package under `build/controlled-pilot-handoff/`:

- `README.md` — executed acceptance state, bounded flow, and explicit limitations;
- `proof-assets.sha256` — hashes of the committed source-navigation/review/proof assets;
- `handoff-report.sha256` — hash of the generated reviewer-facing report.

The generated package is evidence of this supported deterministic controlled-pilot acceptance path only. It is not a general semantic benchmark, production-readiness certification, or legal-analysis result.

## Boundary

Supported inputs remain text-based PDFs and repository-authored/public-safe synthetic evidence used by the existing verification paths. OCR or scanned/image-only PDF recovery is outside this handoff.

Citation/source resolution demonstrates navigation to persisted source evidence. It does **not** establish semantic entailment or legal correctness.

ClaimTrace does **not** determine infringement, validity, novelty, equivalence, inventive step, patentability, or any other legal conclusion.

This handoff also does not claim authentication/RBAC/multi-tenancy, public-cloud or Kubernetes readiness, customer/private-corpus support, security/compliance certification, or benchmark-quality general patent retrieval accuracy.

## Existing proof reused

The handoff reuses the frozen v1.0 proof assets under `docs/proof/` and post-v1 accepted deterministic/recovery verification paths. It does not move or reinterpret `v1.0-proof`.
