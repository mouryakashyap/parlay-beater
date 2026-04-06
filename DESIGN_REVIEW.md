# Parlay Beater — Daily Design Review

**Review Date:** 2026-04-06
**Reviewer:** Automated Senior Engineer Review
**Model:** claude-sonnet-4-6

---

## Overall Assessment

The project is a well-structured FastAPI/Celery/React stack at the end of Phase 1 — infrastructure is solid, layered architecture is correctly enforced, and the skeleton is genuinely production-grade for a personal learning project. There is one high-severity bug in the cache-aside implementation and several medium-severity issues that should be fixed before Phase 2 starts.

---

## What's Well-Designed

**Strict layered architecture enforced throughout**
`routes/ → services/ → repositories/ → models/` is cleanly followed in every module. No route touches the DB directly. No repository contains business logic. This discipline is rare in early-stage personal projects and demonstrates strong architectural instincts.

**Connection pooling properly configured** (`backend/app/core/database.py`, lines 21–26)
`pool_pre_ping=True`, `pool_size=10`, `max_overflow=20` — all sensible defaults for a Postgres-backed FastAPI app. The comment explaining the context manager pattern adds real learning value.

**`joinedload` used in match_repo** (`backend/app/repositories/match_repo.py`, lines 11–14 and 28–30)
Both `get_by_id` and `get_upcoming` eagerly load `home_team` and `away_team` in a single query. This is the correct fix for the N+1 problem when returning match lists with team data embedded. Junior engineers almost always miss this.

**`upsert` pattern in both team_repo and match_repo**
Idempotent writes are essential for data ingestion pipelines — re-running an ingestion job won't create duplicate rows. `team_repo.upsert` is especially clean using `model_dump(exclude_unset=True)` to only update provided fields.

**Celery configured defensively** (`backend/app/workers/celery_app.py`, lines 35–37)
`task_acks_late=True` and `worker_prefetch_multiplier=1` are production-grade settings that prevent message loss on worker crash and ensure fair task distribution. Most tutorials leave these at their unsafe defaults.

**`bind=True` with retry logic on ingest tasks** (`backend/app/workers/tasks/ingest.py`, lines 17–22)
The pattern of catching exceptions and calling `self.retry(exc=exc)` with `max_retries=3` and `default_retry_delay=60` is exactly right. External API calls will fail transiently and should not permanently discard work.

**Beat schedule is well-reasoned** (`celery_app.py`, lines 40–56)
Fixtures every 6 hours is sensible (match schedules don't change hourly). Results at `:30` past every hour is a smart offset to avoid thundering-herd with other hourly jobs. Daily retraining at 3am UTC avoids peak traffic windows.

**Pydantic `model_config = {"from_attributes": True}`** on all Read schemas
This is the SQLAlchemy 2.0 / Pydantic v2 correct way to enable ORM serialization. All three schemas (`MatchRead`, `PredictionRead`, `TeamRead`) have this — no schema will silently fail to serialize ORM objects.

**`ModelRegistry` table designed upfront** (`backend/app/models/prediction.py`, lines 43–58)
Tracking `model_name`, `version`, `mlflow_run_id`, `is_active`, and `metrics` as a DB table (not just MLflow) enables querying which model version generated which predictions directly in SQL. This is a thoughtful design that pays off heavily in Phase 5.

**Cache-aside key namespacing** (`backend/app/services/prediction_service.py`, line 21)
`predictions:match:{match_id}` uses colon-delimited namespacing — the Redis community standard. This makes `cache_delete_pattern` queries readable and avoids key collisions.

**Frontend API client is clean** (`frontend/src/api/client.ts`)
Single Axios instance with `baseURL` configured centrally. All API functions are one-liners that return `.data` directly. TanStack Query wraps these correctly in Dashboard.tsx with `queryKey` and `queryFn`.

---

## Issues Found

### HIGH Severity

**BUG: Cache stores prediction IDs but route expects Prediction objects**
- **File:** `backend/app/services/prediction_service.py`, line 37
- **Problem:** `cache_set(_cache_key(match_id), [p.id for p in predictions])` stores a list of integers. When the cache is warm, `cache_get` returns `[1, 2, 3]` (ints). The route at `predictions.py` line 17 immediately returns this to FastAPI, which tries to serialize it as `list[PredictionRead]`. This will throw a validation error on every cache hit.
- **Fix:** Cache the full prediction dicts using the Pydantic schema: `cache_set(_cache_key(match_id), [PredictionRead.model_validate(p).model_dump() for p in predictions])`. The cache should store the same shape the client expects, and the route should return the cached dicts directly without re-serializing through the ORM.

---

### MEDIUM Severity

**`datetime.utcnow()` is deprecated in Python 3.12+**
- **File:** `backend/app/models/match.py` lines 41–42, `backend/app/models/prediction.py` line 38, `backend/app/repositories/match_repo.py` line 58
- **Problem:** `datetime.utcnow()` was deprecated in Python 3.12 and issues a `DeprecationWarning`. It returns a naive datetime (no timezone info), which can cause subtle bugs when comparing with timezone-aware datetimes.
- **Fix:** Replace with `datetime.now(timezone.utc)` (import `timezone` from `datetime`). Also consider using SQLAlchemy's `func.now()` for `server_default` to let the database handle timestamp generation.

**Migration uses `sa.String()` for enum columns — diverges from ORM**
- **File:** `data/migrations/versions/001_initial_schema.py`, lines 40, 43
- **Problem:** The ORM uses `Column(Enum(MatchStatus))` and `Column(Enum(MatchResult))`, which maps to a PostgreSQL native ENUM type. The migration uses `sa.String()`, which maps to `VARCHAR`. These are not equivalent — PostgreSQL won't enforce valid enum values at the DB level, and Alembic autogenerate will detect a drift and generate a spurious migration.
- **Fix:** Use `sa.Enum('SCHEDULED', 'LIVE', 'FINISHED', 'POSTPONED', name='matchstatus')` and `sa.Enum('HOME', 'DRAW', 'AWAY', name='matchresult')` in the migration. Or switch the ORM to use `String` with a check constraint if you prefer simpler migrations.

**Missing composite index on `(match_id, model_version)` in predictions**
- **File:** `backend/app/models/prediction.py` / `data/migrations/versions/001_initial_schema.py`
- **Problem:** `prediction_repo.get_by_match` filters on both `match_id` and optionally `model_version`. The current index is only on `match_id`. When filtering by both, Postgres cannot use a composite index and must do a full scan of the `match_id` subset.
- **Fix:** Add `Index('ix_predictions_match_model', 'match_id', 'model_version')` to the `Prediction` model and a corresponding `op.create_index` in the migration.

**`match_repo.upsert` accepts raw `dict` — not type-safe**
- **File:** `backend/app/repositories/match_repo.py`, line 52
- **Problem:** `team_repo.upsert` accepts a `TeamCreate` schema (type-safe). `match_repo.upsert` accepts a raw `dict`. This inconsistency means the ingestion task (Phase 2) can pass arbitrary keys and won't get Pydantic validation. A typo in a field name would silently be ignored.
- **Fix:** Create a `MatchCreate` or `MatchUpsert` Pydantic schema and use it in `match_repo.upsert`, consistent with the pattern in `team_repo`.

**`team_repo.upsert` breaks if `api_id` is `None`**
- **File:** `backend/app/repositories/team_repo.py`, line 37
- **Problem:** `get_by_api_id(db, team_in.api_id)` where `api_id` is `None` generates `WHERE api_id IS NULL`. This could accidentally return an existing team with no `api_id` set, and then overwrite its fields with the new team's data.
- **Fix:** Guard at the top of `upsert`: `if team_in.api_id is None: return create(db, team_in)`.

**No task routing — training task can starve ingestion tasks**
- **File:** `backend/app/workers/celery_app.py`
- **Problem:** All three tasks (ingest fixtures, resolve results, retrain models) share the same default queue. A long-running `retrain_all_models` task (which in Phase 5 could take minutes) will block `ingest_upcoming_fixtures` on the same worker if concurrency is exhausted.
- **Fix:** Route the training task to a dedicated `ml` queue: add `task_routes = {"app.workers.tasks.train.*": {"queue": "ml"}}` to `celery_app.conf`. Run a dedicated `ml-worker` container with `--queues=ml`.

---

### LOW Severity

**`queryKey` in Dashboard.tsx doesn't include filter params**
- **File:** `frontend/src/pages/Dashboard.tsx`, line 6
- **Problem:** `queryKey: ["upcoming-matches"]` is a static key. If the component is ever extended to accept a `league` filter prop, changing the filter won't invalidate the TanStack Query cache because the key doesn't include the param.
- **Fix:** Always include all query parameters in the key: `queryKey: ["upcoming-matches", league, days]`. Make it a habit even when filters don't exist yet.

**`match: any` type in Dashboard.tsx**
- **File:** `frontend/src/pages/Dashboard.tsx`, line 21
- **Problem:** Bypasses all TypeScript type checking on match data access. A typo like `match.home_teem.name` would not be caught at compile time.
- **Fix:** Define a `Match` TypeScript interface in `frontend/src/api/types.ts` matching `MatchRead` from the backend schema and use it in the `map` callback.

**`FOOTBALL_DATA_API_KEY` defaults to empty string**
- **File:** `backend/app/core/config.py`, lines 19–20
- **Problem:** An empty string is truthy — `if settings.FOOTBALL_DATA_API_KEY` would pass, and the API client would make requests with an empty auth header, getting a 401 instead of a clear "key not configured" error.
- **Fix:** Use `Optional[str] = None` and check `if settings.FOOTBALL_DATA_API_KEY is not None`. Add startup validation in `lifespan()` that raises if `USE_MOCK_DATA=False` and keys are `None`.

**No Celery monitoring (Flower) in docker-compose**
- **File:** `docker-compose.yml`
- **Problem:** There's no way to inspect task queue depth, task history, or worker status during development. Debugging ingestion failures in Phase 2 will be painful without it.
- **Fix:** Add a `flower` service: `celery -A app.workers.celery_app flower --port=5555` and expose port 5555.

**`team.league` column has no index**
- **File:** `backend/app/models/team.py`, `data/migrations/versions/001_initial_schema.py`
- **Problem:** `team_repo.get_by_league` runs without an index — full table scan on every league-filtered request.
- **Fix:** Add `index=True` to the `league` column in `team.py` and `op.create_index("ix_teams_league", "teams", ["league"])` to the migration.

**Backend service has no healthcheck in docker-compose**
- **File:** `docker-compose.yml`, lines 36–52
- **Problem:** `frontend` uses `depends_on: backend` without a health condition. If the backend is still starting up (running migrations, loading models), the frontend container starts and initial API calls may fail.
- **Fix:** Add a healthcheck to the backend service: `test: ["CMD", "curl", "-f", "http://localhost:8000/health"]` and change `frontend.depends_on.backend.condition` to `service_healthy`.

---

## Recommendations

1. **Fix the cache bug immediately** — it's the only thing that actively breaks the prediction flow. After fixing, add a unit test that mocks `cache_get` to return a pre-serialized list and verifies the route returns the correct shape.

2. **Align migration enums with ORM** before Phase 2 writes any real data. Fixing enum drift after data exists requires a complex migration.

3. **Add a `MatchCreate`/`MatchUpsert` schema** before writing the Phase 2 ingestion client. Type safety at the repo boundary is much easier to add now.

4. **Add Flower to docker-compose now.** You will need it the moment real API calls start failing in Phase 2.

5. **Fix `datetime.utcnow()`** as a small cleanup — it's a one-liner per file and keeps the codebase clean on Python 3.12+.

6. **Write at least one integration test** before Phase 2. Test the `/api/v1/matches/upcoming` route with a real DB session using pytest fixtures. The repo and service layers are clean enough to test easily now; doing it before ingestion makes regression detection much simpler.

---

## Phase Progress

**Current Phase: End of Phase 1 (Infrastructure + Skeleton) — Complete**

What's in place:
- Docker Compose with full 5-service stack (postgres, redis, backend, celery-worker, celery-beat, frontend)
- Database models for all entities: teams, matches, match_stats, odds, predictions, model_registry
- Alembic migration covering all tables and indexes (minor enum drift issue)
- Repository layer: all CRUD operations for all models, idempotent upserts, N+1-safe joinedloads
- Service layer: business logic skeleton with cache-aside wired in prediction_service
- API routes: all read endpoints functional and correctly thin
- Celery workers: beat schedule defined, tasks stubbed with correct retry scaffolding
- Frontend: scaffold with TanStack Query wired to a single Dashboard page

**What's next (Phase 2 — Data Ingestion):**
- `data/ingestion/football_api.py` — HTTP client to football-data.org using `httpx`
- Implement the TODO blocks in `ingest.py` using the existing repo/service layer
- Seed the database with real fixture data from the API
- Validate the end-to-end flow: Beat triggers → worker fetches API → repos upsert to DB → frontend displays matches

---

## System Design Interview Prep

This section covers each architectural pattern present in the codebase — what it is, how it's implemented here, and how to talk about it in an interview.

---

### 1. Layered Architecture (N-Tier)

**What it is:** The codebase is divided into strict horizontal layers where each layer only calls the layer directly below it. Routes call Services. Services call Repositories. Repositories call Models/DB. No layer skips another.

**How this project implements it:**
`matches.py` → `match_service.get_upcoming_matches()` → `match_repo.get_upcoming()` → SQLAlchemy ORM query. No route file imports from `repositories/` or `models/` directly — this is enforced structurally by convention, not a framework rule.

**The interview angle:** Interviewers ask "how do you structure a backend?" or "how would you make this codebase testable?" Layered architecture is the canonical answer. The key trade-off: it adds indirection (more files, more function calls) but makes each layer independently testable and swappable. A service layer can be unit tested by mocking the repo with no DB connection. A repo can be tested against a test DB with no HTTP layer.

**Follow-up questions an interviewer would ask:**
- "When does this pattern break down?" → When every service method is a one-liner passthrough (as `match_service.py` currently is). The service layer earns its keep as the system grows by handling authorization, caching, and cross-repo orchestration.
- "How would you handle cross-cutting concerns like logging and authentication?" → Middleware (already in main.py) and FastAPI's dependency injection system (the `Depends` pattern).

**What to say in an interview:** "I separate DB queries into a repository layer so every database access is in one place and can be tested independently. Services hold business logic and orchestrate multiple repos. Routes are thin HTTP adapters — they validate input, call the right service, and return the response. This means I can swap the database or the cache without touching business logic."

---

### 2. Cache-Aside Pattern

**What it is:** On a read request, check the cache first. On a cache hit, return immediately without touching the DB. On a miss, fetch from the DB, populate the cache with a TTL, then return. The application code manages cache population — hence "cache-aside" as opposed to "read-through" where the cache itself fetches from the source of truth.

**How this project implements it:**
`prediction_service.get_prediction_for_match()` (`services/prediction_service.py`, lines 24–41). Redis helpers `cache_get`, `cache_set`, `cache_delete` are in `core/redis.py`. TTL is `PREDICTION_CACHE_TTL = 3600` seconds, configurable via environment variable.

**The interview angle:** This answers "how do you reduce DB load on frequently read data?" and "how do you scale reads past a single DB instance?" Key trade-offs: cache invalidation complexity, stale data window (the TTL), and cold-start behavior (first request after deploy is always a DB hit). Cache-aside is appropriate when reads heavily outnumber writes and some staleness is acceptable — true for match predictions.

**Follow-up questions an interviewer would ask:**
- "What happens if the cache and DB disagree?" → TTL-based expiry means eventual convergence. For correctness-sensitive data, explicit invalidation (`cache_delete`) on writes is needed — this project has the helper but it's not yet called when predictions are created or updated.
- "What about thundering herd?" → When a popular cache key expires, many concurrent requests all miss simultaneously and all hit the DB at once. Solutions: probabilistic early expiration, distributed locks (Redlock pattern), or staggered TTLs.
- "Why cache-aside instead of read-through?" → Read-through requires a cache that understands your data model. Cache-aside keeps Redis as a dumb key-value store, which is simpler, more portable, and works with any cache backend.

**What to say in an interview:** "Cache-aside means the application checks Redis before querying Postgres. On a miss, it fetches from the DB, writes to Redis with a TTL, and returns. This offloads repeated reads for the same prediction. The key trade-off is eventual consistency — during the TTL window, a stale value may be served. I handle invalidation explicitly by deleting the cache key whenever a prediction is updated."

---

### 3. Connection Pooling

**What it is:** Instead of opening a new database connection on every request — expensive at ~5–15ms per TCP handshake plus authentication — maintain a pool of persistent connections that requests reuse.

**How this project implements it:**
`database.py` lines 21–26: `pool_size=10, max_overflow=20, pool_pre_ping=True`. `get_db()` yields a session from `SessionLocal` (which draws from the pool). The context manager pattern (`with SessionLocal() as db`) ensures the session is returned to the pool after the request.

**The interview angle:** "How do you handle N concurrent requests to a service backed by a single DB?" The pool is the answer. `pool_size` is the steady-state number of open connections. `max_overflow` allows burst capacity above that. With these settings: up to 30 concurrent DB operations per backend container before requests queue for a free connection.

**Follow-up questions an interviewer would ask:**
- "What happens when all pool slots are taken?" → Requests queue for up to `pool_timeout` seconds (default 30s). If the queue exceeds that, SQLAlchemy raises `TimeoutError`, which surfaces as a 500 to the client.
- "What's `pool_pre_ping` for?" → Before handing a connection from the pool, SQLAlchemy runs `SELECT 1`. If the connection is stale (dropped by Postgres or a firewall timeout), it discards it and opens a fresh one. Without this, stale connections cause cryptic errors under low-traffic conditions.
- "How do you size the pool?" → Rule of thumb: `pool_size` ≥ max concurrent requests per worker process. With 2 uvicorn workers and 10 concurrent requests each, you'd want `pool_size=20`. Always profile under realistic load.

**What to say in an interview:** "Connection pooling keeps a fixed set of open Postgres connections ready. Each request borrows one, uses it, and returns it. Without pooling, at 1000 req/s with a 10ms connection overhead you're burning 10 seconds per second just on handshakes. Pool sizing is a trade-off: too small and requests wait; too large and you exhaust Postgres's `max_connections` parameter."

---

### 4. Async Job Queue (Celery + Redis as Broker)

**What it is:** Work that doesn't need to happen synchronously during an HTTP request is pushed to a queue and processed by separate worker processes. The queue decouples producers (the Beat scheduler or an API trigger) from consumers (workers). Redis here serves dual purpose: message broker and result backend.

**How this project implements it:**
`celery_app.py` configures Celery with Redis as broker and backend. `ingest.py` and `train.py` define tasks with `@celery_app.task`. `celery-worker` and `celery-beat` are separate Docker containers sharing the same image.

**The interview angle:** "How would you handle a batch job that runs every 6 hours?" or "How do you avoid blocking the API on slow operations?" The key trade-offs: added operational complexity (queue, workers, and beat to run and monitor), at-least-once delivery semantics (tasks may run more than once on worker crash — idempotency is required), and harder observability (tracing a failure through a queue vs. a request stack).

**Follow-up questions an interviewer would ask:**
- "What's the difference between the worker and beat containers?" → Beat only schedules — it fires tasks by pushing them onto the Redis queue on a cron timer. Workers pull from the queue and execute. Separating them allows independent scaling: add more workers to increase throughput without touching the scheduler.
- "Why `task_acks_late=True`?" → By default Celery acknowledges (removes from queue) a message when the worker picks it up, before executing. If the worker crashes mid-execution, the task is lost. `acks_late=True` delays acknowledgment until after successful completion, so crashed tasks are redelivered. The trade-off: tasks must be idempotent since they may run more than once.
- "What's `worker_prefetch_multiplier=1`?" → By default Celery prefetches multiple messages per worker to improve throughput. Setting it to 1 means each worker takes only one task at a time — essential for long-running tasks that would otherwise hold many messages hostage.

**What to say in an interview:** "Celery decouples ingestion from the request path. Beat schedules tasks on a cron; workers pull from the Redis queue and execute them. The API never blocks waiting for a fixture fetch. Key design choices: `acks_late=True` for at-least-once delivery, upsert in the repo for idempotency so re-runs never create duplicates, and separate worker/beat containers so workers can be scaled independently."

---

### 5. Database Indexing Strategy

**What it is:** Indexes are B-tree data structures that allow the database to locate rows matching a WHERE condition without a full sequential scan. They trade write overhead (every insert/update must update the index) and storage for dramatic read speedups.

**How this project implements it:**
- `matches`: indexes on `id` (PK), `league`, `utc_date`, `status`
- `predictions`: indexes on `id`, `match_id`
- `odds`: index on `match_id`
- `teams`: index on `id` only — `league` is missing (a gap)

**The interview angle:** "How would you optimize a slow query filtering by league and date?" The primary query in `match_repo.get_upcoming` filters on `status = SCHEDULED`, `utc_date >= now`, `utc_date <= cutoff`, and optionally `league`. The current individual indexes are a reasonable start; the ideal next step is a composite index on `(status, utc_date)` since status is highly selective (3 values).

**Follow-up questions an interviewer would ask:**
- "When does an index hurt?" → Every write must update all indexes on the table. Write-heavy tables (like an event log) should minimize indexes. The `matches` table is mostly written by the background ingestion job, so the 4-index overhead is acceptable.
- "What's a covering index?" → An index that includes all columns a query needs, so Postgres can answer from the index without reading the heap. Example: if `get_upcoming` only needed `utc_date` and `status`, an index on `(status, utc_date)` would be covering.
- "How do you find missing indexes in production?" → `EXPLAIN ANALYZE` in Postgres. Look for `Seq Scan` on large tables. `pg_stat_user_indexes` shows which indexes are actually being used versus dead weight.

**What to say in an interview:** "I index columns that appear in WHERE clauses of frequent queries. For matches, `league`, `utc_date`, and `status` cover the most common read pattern — upcoming matches in a given league. For foreign keys like `match_id` on predictions and odds, indexes are critical to avoid full table scans during joins. The trade-off is write amplification: every insert into matches must update 4 indexes."

---

### 6. Idempotent Write Operations (Upsert)

**What it is:** An operation that produces the same result whether run once or N times. In data pipelines, this is essential because jobs fail and retry, network timeouts can cause duplicate delivery, and Celery's `acks_late` guarantees at-least-once execution.

**How this project implements it:**
`team_repo.upsert` (`repositories/team_repo.py`, lines 35–44): looks up by `api_id`, updates if found, creates if not. `match_repo.upsert` (`repositories/match_repo.py`, lines 52–66): same pattern. Both use the external `api_id` (from football-data.org) as the deduplication key.

**The interview angle:** "What happens if your ingestion job runs twice?" This trips up candidates who haven't thought about failure modes. With idempotent upserts, the answer is: the second run overwrites the first with the same data — no duplicates, no errors.

**Follow-up questions an interviewer would ask:**
- "Is this upsert atomic?" → No — the current implementation is SELECT then INSERT/UPDATE, a TOCTOU race condition under concurrent writers. For a single-writer ingestion job (one Celery task), this is fine. For concurrent writers, use `INSERT ... ON CONFLICT DO UPDATE` (SQLAlchemy: `insert().on_conflict_do_update()`), which is atomic at the DB level.
- "How does this interact with `task_acks_late=True`?" → Together they form a guarantee: tasks execute at least once, and re-execution is safe. This is a robust pattern for data pipelines.

**What to say in an interview:** "All ingestion writes go through an upsert that checks for existence by external API ID before inserting. This makes the ingestion job idempotent — re-running it on failure doesn't create duplicate rows. Combined with `task_acks_late=True` in Celery, I get at-least-once delivery with no data corruption."

---

### 7. Scheduled Data Pipeline (ETL)

**What it is:** A system that extracts data from an external source on a schedule, optionally transforms it, and loads it into the application database. Here implemented as a Celery Beat-driven pipeline: Beat fires tasks on a cron, workers execute them.

**How this project implements it:**
Three Beat jobs in `celery_app.py`: fixtures every 6h, results every 1h at `:30`, model retraining daily at 3am UTC. Task stubs in `ingest.py` show the intended flow: fetch from API → upsert via repos.

**The interview angle:** "Design a system that keeps soccer match data current." Key decisions: polling frequency (rate limits, API cost, freshness requirements), failure handling (retry with backoff), and catch-up for missed runs (Celery Beat does NOT auto-backfill).

**Follow-up questions an interviewer would ask:**
- "How do you handle API rate limits?" → Exponential backoff in retries (the current `default_retry_delay=60` is linear; production would use `countdown=60 * 2**self.request.retries`). Also, scheduling 6h intervals keeps API call volume low.
- "What if the Beat container was down for 2 days?" → All 8 fixture jobs are missed with no backfill. A production solution would track `last_ingested_at` in the DB and have the task compute the appropriate time window on startup.
- "Why separate the results job from the fixtures job?" → Different cadences: fixture schedules change slowly; results land within an hour of the final whistle. Polling results at 1h intervals with a `:30` offset minimizes latency while keeping volume low.

**What to say in an interview:** "The pipeline uses Celery Beat as a distributed cron. Fixtures are polled every 6 hours to stay within API rate limits. Results are checked hourly since they land quickly after matches end. Daily retraining at 3am ensures the model trains on fresh data without competing with peak traffic. All tasks are idempotent so Celery retries on failure are safe."

---

## Learning Opportunities

1. **PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` (native atomic upsert).** The current upsert pattern has a subtle TOCTOU race condition under concurrent writes. Learn how `insert().on_conflict_do_update()` in SQLAlchemy 2.0 makes upsert atomic at the DB level. This comes up often in system design interviews when discussing data pipeline correctness and concurrent ingestion workers.

2. **Celery task routing and priority queues.** The current single-queue setup will become a problem when training tasks (potentially minutes-long in Phase 5) compete with ingestion tasks (seconds-long). Research `task_routes` in Celery and how to dedicate workers per queue with `--queues=ingestion` vs `--queues=ml`. This directly maps to the interview question: "how do you prevent slow jobs from blocking fast jobs?"

3. **TanStack Query cache invalidation strategy.** The current static `queryKey: ["upcoming-matches"]` is a common React Query pitfall. Study how TanStack Query's hierarchical queryKey works for cache invalidation — specifically `invalidateQueries` with partial key matching and how including filter params in the key enables correct cache behavior when filters change. This is the frontend analog of the cache-aside invalidation problem.
