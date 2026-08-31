# ClaimTrace developer commands.
#
# Container targets need Docker. Host targets (test/lint) need uv for the API and
# npm for the web app. Run `make help` for the full list.

SHELL := /bin/sh
COMPOSE := docker compose
API_DIR := apps/api
WEB_DIR := apps/web

.DEFAULT_GOAL := help
.PHONY: help init up up-detached down logs ps build restart \
        migrate migration revision psql shell-api \
        test test-docker test-unit verify-v1-02 verify-deterministic-regression lint format fmt-check \
        web-install web-lint web-typecheck check clean \
        eval eval-fake

## --- Meta -------------------------------------------------------------------

help: ## List available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

init: ## Create .env from the template (never overwrites an existing .env)
	@if [ -f .env ]; then echo ".env already exists - leaving it untouched"; \
	else cp .env.example .env; echo "created .env from .env.example"; fi

## --- Docker environment -----------------------------------------------------

up: ## Build and start postgres, api, and web in the foreground
	$(COMPOSE) up --build

up-detached: ## Same as up, in the background
	$(COMPOSE) up --build -d

down: ## Stop and remove containers (keeps the postgres volume)
	$(COMPOSE) down

logs: ## Follow logs from all services
	$(COMPOSE) logs -f

ps: ## Show service status and health
	$(COMPOSE) ps

build: ## Rebuild images without starting them
	$(COMPOSE) build

restart: ## Restart the api service
	$(COMPOSE) restart api

## --- Database ---------------------------------------------------------------

migrate: ## Apply all migrations inside the api container
	$(COMPOSE) run --rm api alembic upgrade head

migration: ## Autogenerate a migration: make migration m="add documents"
	$(COMPOSE) run --rm api alembic revision --autogenerate -m "$(m)"

revision: ## Create an empty migration: make revision m="enable extension"
	$(COMPOSE) run --rm api alembic revision -m "$(m)"

psql: ## Open a psql shell on the running postgres container
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-claimtrace} -d $${POSTGRES_DB:-claimtrace}

shell-api: ## Open a shell in the api container
	$(COMPOSE) exec api sh

## --- Quality gates ----------------------------------------------------------

test: ## Run the backend test suite on the host (PostgreSQL tier skipped if unreachable)
	cd $(API_DIR) && uv run pytest

test-docker: ## Run the backend test suite in the api container, including the PostgreSQL tier
	$(COMPOSE) run --rm api pytest

test-unit: ## Run only the tests that need no database
	cd $(API_DIR) && uv run pytest -m "not integration"

verify-v1-02: init ## Run the exact Claim Comparison Backend closure gates in Docker
	$(COMPOSE) config --quiet
	$(COMPOSE) build api
	$(COMPOSE) up -d postgres
	$(COMPOSE) exec -T postgres sh -ec '\
		for attempt in 1 2 3 4 5 6 7 8 9 10; do \
			if pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}" >/dev/null 2>&1; then exit 0; fi; \
			sleep 1; \
		done; \
		echo "postgres did not become ready" >&2; \
		exit 1'
	$(COMPOSE) run --rm api pytest \
		tests/test_claim_comparison_service.py \
		tests/test_claim_comparison_edge_cases.py \
		tests/test_claim_comparison_schema.py \
		tests/test_claim_comparison_api.py
	$(COMPOSE) run --rm api sh -ec '\
		output=$$(pytest --disable-warnings tests/test_claim_comparison_integration.py); \
		printf "%s\n" "$$output"; \
		printf "%s\n" "$$output" | grep -Eq "[0-9]+ passed"; \
		! printf "%s\n" "$$output" | grep -Eq "[0-9]+ skipped"'
	$(COMPOSE) run --rm -e RUFF_CACHE_DIR=/tmp/ruff-cache api ruff check .
	$(COMPOSE) run --rm -e RUFF_CACHE_DIR=/tmp/ruff-cache api ruff format --check .

verify-deterministic-regression: init ## Re-run and enforce public-safe deterministic regressions
	$(COMPOSE) config --quiet
	$(COMPOSE) build api
	$(COMPOSE) up -d postgres
	$(COMPOSE) exec -T postgres sh -ec '\
		for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
			if pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}" >/dev/null 2>&1; then exit 0; fi; \
			sleep 1; \
		done; \
		echo "postgres did not become ready" >&2; \
		exit 1'
	$(COMPOSE) run --rm -e EMBEDDING_PROVIDER=fake api python -m evals.run --provider fake
	$(COMPOSE) run --rm -e EMBEDDING_PROVIDER=fake api python -m evals.grounded_run --tier deterministic
	$(COMPOSE) run --rm api python -c 'import json; from pathlib import Path; r=json.loads(Path("evals/results/results.json").read_text()); assert r["profile"]["embedding_provider"] == "fake"; m=r["metrics"]; assert m["dense"]["recall_at_5"] == 0.7255; assert m["dense"]["mrr_at_10"] == 0.6725; assert m["lexical"]["recall_at_5"] == 0.9118; assert m["lexical"]["mrr_at_10"] == 0.9608; assert m["hybrid"]["recall_at_5"] == 0.8824; assert m["hybrid"]["mrr_at_10"] == 0.8431; g=json.loads(Path("evals/results/grounded/results-deterministic.json").read_text()); gm=g["metrics"]; assert gm["structured_output_rate"] == 1.0; assert gm["answerability_accuracy"] == 1.0; assert gm["citation_resolution_rate"] == 1.0; assert gm["statement_citation_coverage"] == 1.0; assert gm["selection_recall"] == 0.8333; assert gm["end_to_end_success_rate"] == 0.875; assert gm["forbidden_citation_count"] == 0; assert all(item["refused"] for item in g["guardrails"]); print("deterministic fake-provider regression baseline: PASS")'
	$(COMPOSE) run --rm -e RUFF_CACHE_DIR=/tmp/ruff-cache api ruff check evals
	$(COMPOSE) run --rm -e RUFF_CACHE_DIR=/tmp/ruff-cache api ruff format --check evals

lint: ## Lint the backend (ruff)
	cd $(API_DIR) && uv run ruff check .

format: ## Format the backend (ruff)
	cd $(API_DIR) && uv run ruff format .

fmt-check: ## Verify backend formatting without writing
	cd $(API_DIR) && uv run ruff format --check .

web-install: ## Install web dependencies
	cd $(WEB_DIR) && npm install

web-lint: ## Lint the web app (eslint)
	cd $(WEB_DIR) && npm run lint

web-typecheck: ## Type-check the web app (tsc)
	cd $(WEB_DIR) && npm run typecheck

check: lint fmt-check test web-lint web-typecheck ## Run every quality gate

## --- Retrieval evaluation ---------------------------------------------------

eval: ## Run the retrieval evaluation with the configured embedding model
	$(COMPOSE) run --rm api python -m evals.run

eval-fake: ## Same, with the deterministic provider (no model download)
	$(COMPOSE) run --rm api python -m evals.run --provider fake

## --- Housekeeping -----------------------------------------------------------

clean: ## Remove containers, volumes, and local build/cache artifacts
	-$(COMPOSE) down -v --remove-orphans
	-rm -rf $(API_DIR)/.venv $(API_DIR)/.pytest_cache $(API_DIR)/.ruff_cache
	-find $(API_DIR) -type d -name __pycache__ -prune -exec rm -rf {} +
	-rm -rf $(WEB_DIR)/.next $(WEB_DIR)/node_modules
