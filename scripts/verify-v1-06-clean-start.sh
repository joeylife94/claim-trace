#!/bin/sh
set -eu

PROJECT_NAME="${CLAIMTRACE_VERIFY_PROJECT:-claimtrace-v1-06-clean-start}"
COMPOSE="docker compose -p ${PROJECT_NAME}"

cleanup() {
  ${COMPOSE} down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

if [ ! -f .env ]; then
  make init
fi

test -f .env
${COMPOSE} config --quiet

# This project name is dedicated to verification. Removing its volumes guarantees
# that the migration check starts from an empty PostgreSQL data directory without
# touching the ordinary `claimtrace` developer project.
${COMPOSE} down -v --remove-orphans
${COMPOSE} build api
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
${COMPOSE} run --rm api alembic current
${COMPOSE} up -d api

for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if curl --fail --silent --show-error http://127.0.0.1:${API_PORT:-8000}/health >/tmp/claimtrace-health.json \
    && curl --fail --silent --show-error http://127.0.0.1:${API_PORT:-8000}/ready >/tmp/claimtrace-ready.json; then
    break
  fi
  if [ "$attempt" -eq 20 ]; then
    echo "api did not become healthy and ready" >&2
    ${COMPOSE} ps >&2 || true
    ${COMPOSE} logs api postgres >&2 || true
    exit 1
  fi
  sleep 1
done

grep -q '"status":"ok"' /tmp/claimtrace-health.json
grep -q '"status":"ready"' /tmp/claimtrace-ready.json
grep -q '"postgres":"ok"' /tmp/claimtrace-ready.json

printf 'health: '
cat /tmp/claimtrace-health.json
printf '\nready: '
cat /tmp/claimtrace-ready.json
printf '\nV1-06 clean-start verification passed.\n'
