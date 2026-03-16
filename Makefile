.PHONY: dev dev-backend dev-frontend test test-unit test-integration test-e2e \
        lint typecheck migrate seed ingest load-test help

# ── Development ────────────────────────────────────────────────────────────────

dev:  ## Start the full stack (API + frontend + all services) with hot-reload
	docker compose up --build

dev-backend:  ## Start only backend services (no frontend)
	docker compose up --build api celery-worker postgres redis qdrant

dev-frontend:  ## Start the Next.js dev server locally (requires backend running)
	cd frontend && npm run dev

# ── Testing ────────────────────────────────────────────────────────────────────

test:  ## Run all automated tests with coverage report
	pytest -m "unit or integration or e2e" --cov=app --cov-report=term-missing -q

test-unit:  ## Run unit tests only (fastest — no DB)
	pytest -m unit -q

test-integration:  ## Run integration tests (in-memory SQLite, no external services)
	pytest -m integration -q

test-e2e:  ## Run end-to-end scenario tests
	pytest -m e2e -q

load-test:  ## Run Locust load test (requires backend running on :8000)
	locust -f tests/locustfile.py --headless -u 20 -r 5 --run-time 60s --host http://localhost:8000

# ── Code quality ───────────────────────────────────────────────────────────────

lint:  ## Run all linters (ruff + eslint)
	ruff check app/ tests/
	cd frontend && npm run lint

typecheck:  ## Run all type checkers (mypy + tsc)
	mypy app/ --ignore-missing-imports
	cd frontend && npm run typecheck

# ── Database ───────────────────────────────────────────────────────────────────

migrate:  ## Apply all pending Alembic migrations
	alembic upgrade head

seed:  ## Seed the database with sample data
	python -m scripts.seed_db

ingest:  ## Ingest documents into Qdrant vector store
	python -m scripts.ingest_docs

# ── Help ───────────────────────────────────────────────────────────────────────

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
