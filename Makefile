.PHONY: up down logs migrate seed shell-backend shell-db

# ── Environment ───────────────────────────────────────────────────────────────
# Copy .env.example to .env on first use
env:
	cp .env.example .env

# ── Docker ────────────────────────────────────────────────────────────────────
up:
	docker compose up --build

up-infra:
	docker compose up postgres redis -d

down:
	docker compose down

logs:
	docker compose logs -f

# ── Database Migrations ───────────────────────────────────────────────────────
# Run all pending Alembic migrations
migrate:
	docker compose exec -T backend alembic -c /data/migrations/alembic.ini upgrade head

# Roll back one migration
rollback:
	docker compose exec -T backend alembic -c /data/migrations/alembic.ini downgrade -1

# Auto-generate a new migration from model changes
migration-new:
	docker compose exec -T backend alembic -c /data/migrations/alembic.ini revision --autogenerate -m "$(name)"

# ── Dev Shortcuts ─────────────────────────────────────────────────────────────
shell-backend:
	docker compose exec backend bash

shell-db:
	docker compose exec postgres psql -U parlay -d parlay_beater

# Trigger a one-off data ingestion job
ingest:
	docker compose exec backend python -m app.workers.tasks.ingest

# Run tests (Phase 8)
test:
	docker compose exec backend pytest
