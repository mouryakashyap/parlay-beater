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
| Backfill historical data | `make backfill` |
| Backfill xG stats | `make xg-backfill` |
| Train ML models | `make train` |
| Generate predictions | `make predict` |
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

## ML Model Design

- **Per-league models** — PL/PD/SA/BL1/FL1 each get 3 independent models: `match_result` (multi-class HOME/DRAW/AWAY), `btts`, `over_under`. Cross-league matches (e.g. Champions League) are not predicted.
- **Feature engineering** — 25 features per match in `ml/features/builder.py`. Form features (last 5 matches) are scoped to the same competition only. H2H is cross-competition. All features use strictly pre-match data (no leakage). See `FEATURE_COLS` for the canonical ordered list.
- **Training split** — 60% train XGBoost / 20% fit isotonic calibrator / 20% validate.
- **Calibration** — `CalibratedClassifierCV(method='isotonic', cv='prefit')` corrects XGBoost's systematic overconfidence. The calibrated model is what gets saved to MLflow and served.
- **Recency weighting** — exponential decay with 365-day half-life. Matches from 1 year ago get 50% weight; 2-year-old matches ~15%. Applied to both XGBoost and calibrator fits.
- **xG** — fetched from Understat.com via `understatapi`. Matched to DB records by date ±26h + fuzzy team name (threshold 0.6). League map: `PL→EPL, PD→La_Liga, SA→Serie_A, BL1→Bundesliga, FL1→Ligue_1`.
- **MLflow URI** — `sqlite:////data/mlflow.db` (4 slashes = absolute path inside container). The 3-slash form resolves relative to `/app` and will silently create a second DB.
- **Model registry** — `ModelRegistry` table tracks active models per `(model_name, league)`. Predictor requires all 3 models for a league to be present; missing any = no predictions for that league.
- Design rationale for all decisions is in `DECISIONS.md`.

## Key Config

- API docs at `http://localhost:8000/docs` (Swagger) when backend is running.
- All env vars in `backend/app/core/config.py` (`Settings`). Access via `from app.core.config import settings`.
- `USE_MOCK_DATA=true` bypasses real API calls — default for dev.
- `TARGET_LEAGUES` — comma-separated league codes (PL, PD, SA, BL1, FL1).
- Container DB host is `postgres` (not `localhost`).

## Celery Beat Schedule

- Ingest fixtures: every 6h
- Resolve finished matches: hourly at :30
- Retrain models: daily at 3am UTC
- Update recent xG: daily at 4am UTC
