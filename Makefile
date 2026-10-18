COMPOSE = docker compose
BACKEND = $(COMPOSE) exec backend

.PHONY: up down logs seed fetch-datasets warm-cache backtest test lint reset types

up: ## build and start everything (migrations run on backend start)
	@test -f .env || cp .env.example .env
	$(COMPOSE) up -d --build
	@echo "Frontend: http://localhost:3000  API: http://localhost:8000/docs"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=200

seed: ## idempotent demo data
	$(BACKEND) python scripts/seed_demo.py

fetch-datasets:
	$(BACKEND) python scripts/fetch_datasets.py

warm-cache: ## live LLM once -> data/fixtures/llm_cache (needs OPENAI_API_KEY)
	$(COMPOSE) run --rm -e LLM_MODE=record backend python scripts/warm_cache.py

backtest:
	$(BACKEND) python scripts/run_backtest.py

test:
	$(COMPOSE) exec -e LLM_MODE=fake -e TEST_DATABASE_URL=postgresql+psycopg://calibr:$${POSTGRES_PASSWORD:-calibr}@db:5432/calibr_test backend python -m pytest -q

lint:
	cd backend && uv run ruff check .
	cd frontend && pnpm lint && pnpm exec tsc --noEmit

types: ## regenerate frontend API types from the running backend
	cd frontend && pnpm exec openapi-typescript http://localhost:8000/openapi.json -o src/lib/api-types.ts

reset: ## drop all data (asks for confirmation)
	@read -p "This deletes ALL data volumes. Continue? [y/N] " a && [ "$$a" = "y" ]
	$(COMPOSE) down -v
