#!/bin/sh
set -eu

PROJECT_NAME="${CLAIMTRACE_VERIFY_PROJECT:-claimtrace-v1-07-proof}"
COMPOSE="docker compose -p ${PROJECT_NAME}"
API_PORT="${V1_07_API_PORT:-18000}"
WEB_PORT="${V1_07_WEB_PORT:-13000}"
PROOF_DIR="${V1_07_PROOF_DIR:-docs/proof}"

cleanup() {
  ${COMPOSE} down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

if [ ! -f .env ]; then
  make init
fi

test -f .env
test -s docs/proof/architecture-v1.svg

export EMBEDDING_PROVIDER=fake
export EMBEDDING_MODEL=deterministic-hash
export LLM_PROVIDER=fake
export POSTGRES_PORT="${V1_07_POSTGRES_PORT:-15432}"
export API_PORT
export WEB_PORT
export NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:${API_PORT}"
export V1_07_WEB_URL="http://127.0.0.1:${WEB_PORT}"
export V1_07_PROOF_DIR="${PROOF_DIR}"

rm -rf "${PROOF_DIR}/screenshots" "${PROOF_DIR}/demo"
mkdir -p "${PROOF_DIR}/screenshots" "${PROOF_DIR}/demo"

${COMPOSE} config --quiet
${COMPOSE} down -v --remove-orphans
${COMPOSE} build api web
${COMPOSE} up -d postgres

${COMPOSE} exec -T postgres sh -ec '
  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    if pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then exit 0; fi
    sleep 1
  done
  echo "postgres did not become ready" >&2
  exit 1
'

${COMPOSE} run --rm api alembic upgrade head
${COMPOSE} run --rm api python tests/v1_03_browser_seed.py
${COMPOSE} up -d api web

for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
  if curl --fail --silent "http://127.0.0.1:${API_PORT}/ready" >/dev/null 2>&1 \
    && curl --fail --silent "http://127.0.0.1:${WEB_PORT}/documents" >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "ClaimTrace proof runtime did not become ready" >&2
    ${COMPOSE} ps >&2 || true
    ${COMPOSE} logs api web postgres >&2 || true
    exit 1
  fi
  sleep 2
done

V1_07_WEB_URL="${V1_07_WEB_URL}" V1_07_PROOF_DIR="${PROOF_DIR}" \
  node apps/web/e2e/v1-07-proof-capture.mjs

count=$(find "${PROOF_DIR}/screenshots" -type f -name '*.png' | wc -l | tr -d ' ')
[ "${count}" -ge 4 ]
test -s "${PROOF_DIR}/demo/claimtrace-golden-path.webm"
printf 'V1-07 proof capture passed: %s screenshots + demo; architecture is repository-tracked.\n' "${count}"
