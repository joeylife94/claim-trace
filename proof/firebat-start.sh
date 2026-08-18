#!/usr/bin/env bash
set -euo pipefail

# Self-contained ClaimTrace runtime for Firebat Proof capture.
# Uses dedicated host ports and the repository's optional Ollama service so the
# buyer-facing grounded-answer screenshot never depends on a fake generation.
# Model weights persist in the existing ollama_models named volume.

MODEL="${PROOF_CLAIMTRACE_OLLAMA_MODEL:-qwen2.5:1.5b}"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

export POSTGRES_PORT="${POSTGRES_PORT:-15432}"
export API_PORT="${API_PORT:-18000}"
export WEB_PORT="${WEB_PORT:-13000}"
export OLLAMA_PORT="${OLLAMA_PORT:-11435}"
export CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS:-http://127.0.0.1:${WEB_PORT}}"
export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://127.0.0.1:${API_PORT}}"
export EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-fake}"
export LLM_PROVIDER=ollama
export LLM_OLLAMA_BASE_URL=http://ollama:11434
export LLM_OLLAMA_MODEL="$MODEL"

printf '[PROOF] ClaimTrace runtime: web=%s api=%s postgres=%s ollama=%s model=%s\n' \
  "$WEB_PORT" "$API_PORT" "$POSTGRES_PORT" "$OLLAMA_PORT" "$MODEL"

# Start the stateful services first. Ollama uses a named volume, so the model is
# downloaded only on the first run (subsequent pulls verify/reuse local layers).
docker compose --profile llm up --build -d postgres ollama

# `docker compose up -d` only starts the process; it does not guarantee Ollama is
# ready to accept CLI/API calls yet. Bound the wait so a broken container fails
# clearly instead of hanging at the pull command.
echo "[PROOF] Waiting for Ollama readiness"
ollama_ready=0
for _ in $(seq 1 45); do
  if docker compose --profile llm exec -T ollama ollama list >/dev/null 2>&1; then
    ollama_ready=1
    break
  fi
  sleep 2
done
if [[ "$ollama_ready" != "1" ]]; then
  echo "[FAIL] Ollama did not become ready within 90 seconds" >&2
  docker compose --profile llm logs --tail=80 ollama >&2 || true
  exit 1
fi

echo "[PROOF] Ensuring local Ollama model is available: $MODEL"
docker compose --profile llm exec -T ollama ollama pull "$MODEL"

# Migration is explicit because /health only proves process liveness; a fresh
# database can otherwise look healthy before application tables exist.
docker compose --profile llm run --rm api alembic upgrade head

# Build/start the API with the real local provider, then the web UI.
docker compose --profile llm up --build -d api web
