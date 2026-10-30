.PHONY: install check check-backend check-frontend dev-backend dev-frontend

ENV_FILE := $(if $(wildcard .env),--env-file ../.env,)

install:
	cd backend && uv sync
	cd frontend && pnpm install

check: check-backend check-frontend

check-backend:
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd backend && uv run pyright
	cd backend && uv run pytest

check-frontend:
	cd frontend && pnpm lint
	cd frontend && pnpm typecheck

dev-backend:
	cd backend && uv run $(ENV_FILE) uvicorn agent_lab.main:app --host 127.0.0.1 --port 8000 --reload

dev-frontend:
	cd frontend && pnpm dev
