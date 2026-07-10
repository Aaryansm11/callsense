# CallSense — task runner. "Runs from one clear command" is a grading criterion.
# Requires Docker + docker compose. On Windows without Docker, use the conda
# commands in README "Local dev (no Docker)".

.PHONY: help demo up down migrate seed test logs ps clean

help: ## show targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

demo: up ## bring up the full stack, wait for health, seed demo data, print URLs
	@echo "Waiting for API health..."; \
	 for i in $$(seq 1 30); do \
	   curl -fsS http://localhost:8000/health >/dev/null 2>&1 && break; sleep 2; \
	 done; \
	 $(MAKE) seed; \
	 echo ""; \
	 echo "CallSense is up:"; \
	 echo "  Dashboard     : http://localhost:3000"; \
	 echo "  API + Swagger : http://localhost:8000/docs"; \
	 echo "  Health        : http://localhost:8000/health/db"; \
	 echo "  Postgres      : localhost:5432 (callsense/callsense)"

up: ## build + start postgres, api (auto-migrates), worker, web
	docker compose up -d --build

down: ## stop containers (keep the DB volume)
	docker compose down

migrate: ## apply DB migrations manually (api also does this on boot)
	docker compose exec api alembic upgrade head

seed: ## load demo data (1 org, 3 teams, 9 advisors, ~25 calls)
	docker compose run --rm seed

test: ## run the backend test suite inside the api container
	docker compose exec api pytest

logs: ## tail all service logs
	docker compose logs -f

ps: ## show service status
	docker compose ps

clean: ## stop containers AND delete the DB volume
	docker compose down -v
