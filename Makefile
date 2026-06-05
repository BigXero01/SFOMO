.PHONY: help up down build logs shell-backend shell-frontend migrate seed backtest lint test

help:
	@echo "SFOMO — AI Agent Trading Bot"
	@echo ""
	@echo "Commands:"
	@echo "  make up            Start all services"
	@echo "  make down          Stop all services"
	@echo "  make build         Rebuild Docker images"
	@echo "  make logs          Tail all service logs"
	@echo "  make migrate       Run DB migrations"
	@echo "  make seed          Seed initial data"
	@echo "  make backtest      Run strategy backtests"
	@echo "  make lint          Lint backend code"
	@echo "  make test          Run test suite"

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build --no-cache

logs:
	docker compose logs -f

shell-backend:
	docker compose exec backend bash

shell-frontend:
	docker compose exec frontend sh

migrate:
	docker compose exec backend alembic upgrade head

seed:
	docker compose exec backend python scripts/seed.py

backtest:
	docker compose exec backend python scripts/backtest.py

lint:
	cd backend && ruff check . && mypy .

test:
	cd backend && pytest -v

dev-backend:
	cd backend && uvicorn main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev
