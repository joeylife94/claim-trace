#!/bin/sh
set -eu

PROJECT_NAME="${CLAIMTRACE_VERIFY_PROJECT:-claimtrace-progression-retry-real}"
COMPOSE="docker compose -p ${PROJECT_NAME}"
API_PORT="${PROGRESSION_RETRY_API_PORT:-18001}"

cleanup() {
  ${COMPOSE} down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

if [ ! -f .env ]; then
  make init
fi

export EMBEDDING_PROVIDER=fake
export POSTGRES_PORT="${PROGRESSION_RETRY_POSTGRES_PORT:-15433}"
export API_PORT

${COMPOSE} config --quiet
${COMPOSE} down -v --remove-orphans
${COMPOSE} build api
${COMPOSE} up -d postgres
${COMPOSE} exec -T postgres sh -ec '
  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then exit 0; fi
    sleep 1
  done
  echo "postgres did not become ready" >&2
  exit 1'

${COMPOSE} run --rm api alembic upgrade head
${COMPOSE} run --rm -e PYTHONPATH=/app api python tests/progression_retry_real_state.py seed
${COMPOSE} up -d api

for attempt in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/api/v1/documents?limit=1&offset=0" >/dev/null; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    ${COMPOSE} logs --no-color api postgres >&2 || true
    exit 1
  fi
  sleep 1
done

(
  cd apps/web
  npm ci
  npm install --no-save --package-lock=false playwright@1.55.0
  npx playwright install --with-deps chromium
  API_INTERNAL_BASE_URL="http://127.0.0.1:${API_PORT}" node e2e/progression-retry-real.mjs
)

${COMPOSE} run --rm -e PYTHONPATH=/app api python tests/progression_retry_real_state.py verify
printf 'Real web/API/PostgreSQL retry verification passed.\n'
