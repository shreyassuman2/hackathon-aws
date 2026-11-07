# Runway dev commands. Run `make help`.
.DEFAULT_GOAL := help
BACKEND := cd backend &&

help: ## Show this help
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Install everything (Python via uv, Node deps)
	$(BACKEND) uv sync
	cd frontend && npm install
	cd bridge && npm install
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")

seed: ## Reset the local store and load the Acme Labs demo data
	$(BACKEND) uv run python -m runway.seed --reset

api: ## Run the API on :8000 (docs at /docs)
	$(BACKEND) uv run uvicorn runway.api:app --reload --port 8000

worker: ## Run the negotiation worker loop
	$(BACKEND) uv run python -m runway.negotiation.worker

frontend: ## Run the dashboard on :3000
	cd frontend && npm run dev

bridge: ## Run the iMessage bridge (macOS)
	cd bridge && npm run dev

emulator: ## Open the card-swipe emulator
	open tools/purchase-emulator/index.html

test: ## Run backend tests
	$(BACKEND) uv run pytest -q

lint: ## Lint + format check
	$(BACKEND) uv run ruff check runway tests && uv run ruff format --check runway tests

fmt: ## Auto-format
	$(BACKEND) uv run ruff check --fix runway tests && uv run ruff format runway tests

requirements: ## Re-export backend/requirements.txt (used by SAM) after changing deps
	$(BACKEND) uv export --no-dev --no-hashes --no-emit-project -q -o requirements.txt

deploy: requirements ## Build + deploy to AWS (see docs/DEPLOY.md first)
	cd infra && sam build && sam deploy --guided

.PHONY: help setup seed api worker frontend bridge emulator test lint fmt requirements deploy
