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
	docker compose exec -T backend python -c "from app.workers.tasks.ingest import ingest_upcoming_fixtures; ingest_upcoming_fixtures()"

backfill:
	docker compose exec -T backend python -c "from app.workers.tasks.ingest import backfill_historical; backfill_historical()"

# Train ML models
train:
	docker compose exec -T backend python -c "from ml.training.trainer import train_all; from app.core.database import SessionLocal; db=SessionLocal(); train_all(db); db.close(); print('Training complete')"

# Generate predictions for upcoming matches
predict:
	docker compose exec -T backend python -c "from ml.serving.predictor import generate_predictions; from app.core.database import SessionLocal; db=SessionLocal(); n=generate_predictions(db); db.close(); print(f'Generated {n} predictions')"

# Run tests (Phase 8)
test:
	docker compose exec backend pytest
