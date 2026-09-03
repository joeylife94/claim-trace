#!/bin/sh
set -eu

OUT_DIR="${CLAIMTRACE_HANDOFF_OUT:-build/controlled-pilot-handoff}"
mkdir -p "$OUT_DIR"

printf '%s\n' '== ClaimTrace controlled pilot handoff ==' 

CLAIMTRACE_VERIFY_PROJECT=claimtrace-handoff-clean-start \
  sh scripts/verify-v1-06-clean-start.sh

CLAIMTRACE_VERIFY_PROJECT=claimtrace-handoff-retry \
  PROGRESSION_RETRY_POSTGRES_PORT=15434 \
  PROGRESSION_RETRY_API_PORT=18002 \
  sh scripts/verify-progression-retry-real.sh

CLAIMTRACE_VERIFY_PROJECT=claimtrace-handoff-golden-path \
  V1_06_POSTGRES_PORT=15435 \
  V1_06_API_PORT=18003 \
  V1_06_WEB_PORT=13003 \
  sh scripts/verify-v1-06-golden-path.sh

PROOF_FILES="
docs/proof/architecture-v1.svg
docs/proof/screenshots/01-documents.png
docs/proof/screenshots/02-search-results.png
docs/proof/screenshots/03-grounded-answer.png
docs/proof/screenshots/04-comparison.png
docs/proof/screenshots/05-source-highlight.png
docs/proof/screenshots/06-human-review.png
docs/proof/demo/claimtrace-golden-path.webm
docs/proof/README.md
"

for path in $PROOF_FILES; do
  test -s "$path"
done

COMMIT_SHA="$(git rev-parse HEAD 2>/dev/null || printf 'unknown')"
{
  printf '# ClaimTrace Controlled Pilot Handoff Evidence\n\n'
  printf -- '- Repository commit: `%s`\n' "$COMMIT_SHA"
  printf -- '- Clean setup/migration: **PASS**\n'
  printf -- '- Supported failed-ingestion operator recovery: **PASS**\n'
  printf -- '- Deterministic whole-product analyst/reviewer flow: **PASS**\n'
  printf -- '- Source-navigation / human-review proof assets: **PRESENT + HASHED**\n\n'
  printf '## Exercised bounded flow\n\n'
  printf '`setup/migrate → supported ingest/recovery → retrieve/ask/compare/decompose → human review → source navigation → evidence handoff`\n\n'
  printf '## Limitations\n\n'
  printf '%s\n' '- Text-based supported PDFs/public-safe synthetic inputs only; OCR/scanned-PDF recovery is not claimed.'
  printf '%s\n' '- Citation/source resolution proves navigation to stored source evidence, not semantic entailment or legal correctness.'
  printf '%s\n' '- ClaimTrace does not determine infringement, validity, novelty, equivalence, inventive step, patentability, or other legal conclusions.'
  printf '%s\n' '- This handoff does not establish authentication/RBAC/multi-tenancy, public-cloud/Kubernetes, security certification, or general benchmark quality.'
  printf '\n## Proof asset hashes\n\n```text\n'
  sha256sum $PROOF_FILES
  printf '```\n'
} > "$OUT_DIR/README.md"

sha256sum $PROOF_FILES > "$OUT_DIR/proof-assets.sha256"
sha256sum "$OUT_DIR/README.md" > "$OUT_DIR/handoff-report.sha256"

printf 'Controlled pilot handoff verification passed. Evidence: %s\n' "$OUT_DIR/README.md"
