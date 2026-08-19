#!/bin/sh
set -eu

PROJECT_NAME="${CLAIMTRACE_VERIFY_PROJECT:-claimtrace-v1-06-golden-path}"
COMPOSE="docker compose -p ${PROJECT_NAME}"
API_PORT="${V1_06_API_PORT:-18000}"
WEB_PORT="${V1_06_WEB_PORT:-13000}"

cleanup() {
  ${COMPOSE} down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

if [ ! -f .env ]; then
  make init
fi

test -f .env

# Keep the deterministic proof offline and isolated from the ordinary developer
# stack while preserving the same application code paths.
export EMBEDDING_PROVIDER=fake
export EMBEDDING_MODEL=deterministic-hash
export LLM_PROVIDER=fake
export POSTGRES_PORT="${V1_06_POSTGRES_PORT:-15432}"
export API_PORT
export WEB_PORT
export NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:${API_PORT}"
export V1_06_WEB_URL="http://127.0.0.1:${WEB_PORT}"

${COMPOSE} config --quiet
${COMPOSE} down -v --remove-orphans
${COMPOSE} build api web
${COMPOSE} up -d postgres

${COMPOSE} exec -T postgres sh -ec '
  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    if pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
      exit 0
    fi
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
    echo "ClaimTrace whole-product runtime did not become ready" >&2
    ${COMPOSE} ps >&2 || true
    ${COMPOSE} logs api web postgres >&2 || true
    exit 1
  fi
  sleep 2
done

V1_06_WEB_URL="${V1_06_WEB_URL}" node apps/web/e2e/v1-06-golden-path.mjs
printf 'V1-06 deterministic whole-product verification passed.\n'
