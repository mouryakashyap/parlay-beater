# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Sports betting prediction system ("Parlay Beater") — ingests football match data, runs ML models to predict outcomes, and surfaces predictions via a web UI.

## Commands

Everything runs in Docker. First-time setup: `cp .env.example .env`, then `make up`.

| Task | Command |
|---|---|
| Start all services | `make up` |
| Start only Postgres + Redis | `make up-infra` |
| Run migrations | `make migrate` |
| New migration | `make migration-new name="description"` |
| Rollback one migration | `make rollback` |
| Run tests | `make test` |
| Manual data ingest | `make ingest` |
| Backend shell | `make shell-backend` |
| Postgres shell | `make shell-db` |

No local Python/Node install needed — all commands run inside containers.

## Architecture

**Four Docker services** share the same backend image:
- `backend` — FastAPI (uvicorn), serves API on :8000
- `celery-worker` — executes async tasks (ingest, training)
- `celery-beat` — cron-like scheduler that enqueues periodic tasks
- `frontend` — React/Vite on :5173

**Backend layers** (`backend/app/`): routes → services → repositories → models. Routes are thin; business logic lives in `services/`. DB access is isolated in `repositories/`.

**Data pipeline** (`data/`): `ingestion/` pulls from football APIs, `migrations/` holds Alembic migrations. Alembic config path inside the container is `/data/migrations/alembic.ini`.

**ML pipeline** (`ml/`): `features/` → `training/` → `models/` → `serving/`. MLflow tracks experiments (SQLite-backed by default).

## Key Config

- All env vars consolidated in `backend/app/core/config.py` (`Settings` class). Access via `from app.core.config import settings`.
- `USE_MOCK_DATA=true` bypasses real API calls — default for dev.
- `TARGET_LEAGUES` is comma-separated league codes (PL, PD, SA, BL1, FL1).
- Container DB host is `postgres` (not `localhost`); `DATABASE_URL` in `.env` uses the Docker service name.

## Celery Beat Schedule

- Ingest fixtures: every 6h
- Resolve finished matches: hourly at :30
- Retrain models: daily at 3am UTC
