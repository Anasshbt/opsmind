.PHONY: help dev stop backend-shell migrate seed test-backend lint-backend type-check build

BACKEND_DIR := backend
FRONTEND_DIR := frontend

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Dev ───────────────────────────────────────────────────────────────────────

dev: ## Start full stack (docker-compose)
	docker-compose up --build

dev-bg: ## Start full stack in background
	docker-compose up --build -d

stop: ## Stop all services
	docker-compose down

logs: ## Follow logs
	docker-compose logs -f

# ── Backend ───────────────────────────────────────────────────────────────────

backend-shell: ## Shell into backend container
	docker-compose exec backend bash

migrate: ## Run Alembic migrations
	docker-compose exec backend alembic upgrade head

migrate-new: ## Create new migration (NAME=description)
	docker-compose exec backend alembic revision --autogenerate -m "$(NAME)"

seed: ## Seed database with sample data
	docker-compose exec backend python ../infra/scripts/seed_db.py

test-backend: ## Run backend tests
	cd $(BACKEND_DIR) && uv run pytest -v --tb=short

lint-backend: ## Lint backend
	cd $(BACKEND_DIR) && uv run ruff check app tests

type-check: ## Type check backend
	cd $(BACKEND_DIR) && uv run mypy app

# ── Frontend ──────────────────────────────────────────────────────────────────

frontend-install: ## Install frontend deps
	cd $(FRONTEND_DIR) && npm ci

frontend-dev: ## Start frontend dev server
	cd $(FRONTEND_DIR) && npm run dev

frontend-build: ## Build frontend for production
	cd $(FRONTEND_DIR) && npm run build

# ── Build ─────────────────────────────────────────────────────────────────────

build: ## Build Docker images
	docker build -t opsmind/backend:latest -f infra/docker/Dockerfile.backend backend/
	docker build -t opsmind/frontend:latest -f infra/docker/Dockerfile.frontend frontend/

# ── K8s ───────────────────────────────────────────────────────────────────────

k8s-apply: ## Apply base K8s manifests
	kubectl apply -k infra/k8s/base/

k8s-delete: ## Delete K8s resources
	kubectl delete -k infra/k8s/base/
