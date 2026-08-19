#!/usr/bin/env bash
set -euo pipefail

# Self-contained ClaimTrace runtime for Firebat Proof capture.
#
# The Proof runtime uses its own Docker Compose project so repeated portfolio
# capture never inherits documents/indexes from an ordinary ClaimTrace dev stack.
# The first run downloads the local retrieval and generation models into the
# Proof project's named volumes; later runs reuse those volumes.

MODEL="${PROOF_CLAIMTRACE_OLLAMA_MODEL:-qwen2.5:1.5b}"
COMPOSE_PROJECT="${PROOF_CLAIMTRACE_COMPOSE_PROJECT:-claimtrace-proof}"
LEGACY_PROJECT="${PROOF_CLAIMTRACE_LEGACY_PROJECT:-claimtrace}"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

export POSTGRES_PORT="${POSTGRES_PORT:-15432}"
export API_PORT="${API_PORT:-18000}"
export WEB_PORT="${WEB_PORT:-13000}"
export OLLAMA_PORT="${OLLAMA_PORT:-11435}"
export CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS:-http://127.0.0.1:${WEB_PORT}}"
export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://127.0.0.1:${API_PORT}}"
export EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-sentence-transformers}"
export EMBEDDING_MODEL="${EMBEDDING_MODEL:-intfloat/multilingual-e5-small}"
export LLM_PROVIDER=ollama
export LLM_OLLAMA_BASE_URL=http://ollama:11434
export LLM_OLLAMA_MODEL="$MODEL"
# The buyer-facing HERO needs two concise supported statements, not a long
# generation. Keep enough room for the fixed JSON schema while bounding slow or
# pathological local generations. One corrective attempt remains available.
export GROUNDED_MAX_OUTPUT_TOKENS="${GROUNDED_MAX_OUTPUT_TOKENS:-384}"
export GROUNDED_TIMEOUT_SECONDS="${GROUNDED_TIMEOUT_SECONDS:-150}"
export GROUNDED_REPAIR_MAX_ATTEMPTS="${GROUNDED_REPAIR_MAX_ATTEMPTS:-1}"

compose() {
  docker compose -p "$COMPOSE_PROJECT" --profile llm "$@"
}

printf '[PROOF] ClaimTrace runtime: project=%s web=%s api=%s postgres=%s ollama=%s\n' \
  "$COMPOSE_PROJECT" "$WEB_PORT" "$API_PORT" "$POSTGRES_PORT" "$OLLAMA_PORT"
printf '[PROOF] Models: embedding=%s llm=%s\n' "$EMBEDDING_MODEL" "$MODEL"
printf '[PROOF] Grounded bounds: max_output=%s timeout=%ss repairs=%s\n' \
  "$GROUNDED_MAX_OUTPUT_TOKENS" "$GROUNDED_TIMEOUT_SECONDS" "$GROUNDED_REPAIR_MAX_ATTEMPTS"

# Earlier Proof iterations used the repository's default Compose project name.
# Stop those containers only to release the dedicated Proof ports. Volumes are
# deliberately preserved, so this does not destroy the old state.
if docker compose -p "$LEGACY_PROJECT" ps -q 2>/dev/null | grep -q .; then
  echo "[PROOF] Stopping legacy ClaimTrace containers to release Proof ports (volumes preserved)"
  docker compose -p "$LEGACY_PROJECT" --profile llm down --remove-orphans
fi

# Start the stateful services first. The isolated Proof project begins with a
# clean application DB while retaining its own model caches across later runs.
compose up --build -d postgres ollama

# `docker compose up -d` only starts the process; it does not guarantee Ollama is
# ready to accept CLI/API calls yet. Bound the wait so a broken container fails
# clearly instead of hanging at the pull command.
echo "[PROOF] Waiting for Ollama readiness"
ollama_ready=0
for _ in $(seq 1 45); do
  if compose exec -T ollama ollama list >/dev/null 2>&1; then
    ollama_ready=1
    break
  fi
  sleep 2
done
if [[ "$ollama_ready" != "1" ]]; then
  echo "[FAIL] Ollama did not become ready within 90 seconds" >&2
  compose logs --tail=80 ollama >&2 || true
  exit 1
fi

echo "[PROOF] Ensuring local Ollama model is available: $MODEL"
compose exec -T ollama ollama pull "$MODEL"

# Migration is explicit because /health only proves process liveness; a fresh
# database can otherwise look healthy before application tables exist.
compose run --rm api alembic upgrade head

# Build/start the API with the real local providers, then the web UI. The
# sentence-transformers model is loaded/downloaded on the first index request
# during Proof seeding and then reused from the model_cache named volume.
compose up --build -d api web
