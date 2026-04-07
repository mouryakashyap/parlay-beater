# Parlay Beater

A full-stack sports betting prediction system that ingests football match data, runs ML models to predict outcomes, and surfaces predictions via a web dashboard.

## Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Uvicorn |
| Async Workers | Celery + Redis |
| Database | PostgreSQL + SQLAlchemy + Alembic |
| ML | XGBoost, scikit-learn, MLflow |
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Infrastructure | Docker Compose |

## Getting Started

**1. Clone and configure**
```bash
git clone https://github.com/mouryakashyap/parlay-beater.git
cd parlay-beater
cp .env.example .env
```

Edit `.env` and add your football API keys:
- `FOOTBALL_DATA_API_KEY` — get one at [football-data.org](https://www.football-data.org/)
- `API_FOOTBALL_KEY` — get one at [api-football.com](https://www.api-football.com/)

**2. Start all services**
```bash
make up
```

**3. Run database migrations**
```bash
make migrate
```

**4. Open the app**
- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs

## Commands

```bash
make up              # Build and start all services
make up-infra        # Start only Postgres + Redis (no app)
make down            # Stop all services
make migrate         # Apply pending migrations
make rollback        # Roll back one migration
make migration-new name="description"  # Generate migration from model changes
make ingest          # Trigger a one-off data ingestion
make test            # Run backend tests
make shell-backend   # Bash shell inside backend container
make shell-db        # Postgres shell
```

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────────┐
│  React/Vite │────▶│  FastAPI  (routes → services → repos)    │
│  :5173      │     │  :8000                                    │
└─────────────┘     └────────────┬─────────────────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
               PostgreSQL      Redis      Celery Workers
               (data store)   (cache/     (ingest, train)
                               queue)
```

**Backend layers** (strictly enforced):
```
routes/ → services/ → repositories/ → models/
```
- Routes: request validation + response shaping only
- Services: business logic, cache-aside pattern
- Repositories: all DB queries
- Models: SQLAlchemy ORM

**ML pipeline** (`ml/`):
```
features/ → training/ → models/ → serving/
```
Experiment tracking via MLflow. Model versions tracked in `model_registry` DB table.

**Celery Beat schedule:**
- Ingest upcoming fixtures — every 6 hours
- Resolve finished match results — hourly at :30
- Retrain models — daily at 3am UTC

## Target Leagues

Configured via `TARGET_LEAGUES` in `.env` (comma-separated):

| Code | League |
|---|---|
| `PL` | Premier League |
| `PD` | La Liga |
| `SA` | Serie A |
| `BL1` | Bundesliga |
| `FL1` | Ligue 1 |

## Development Notes

- Set `USE_MOCK_DATA=true` in `.env` to bypass real API calls during development
- All commands run inside Docker — no local Python or Node install required
- Migrations use Alembic; config lives at `/data/migrations/alembic.ini` inside the container
