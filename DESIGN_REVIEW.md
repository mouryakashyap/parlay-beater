# Parlay Beater — Daily Design Review

**Review Date:** 2026-04-07
**Reviewer:** Automated Senior Engineer Review
**Model:** claude-sonnet-4-6

---

## Overall Assessment

The project has advanced significantly — the full stack is now present and wired: infra, DB, repositories, services, API, Celery workers, data ingestion with mock data, and a functioning React/TanStack Query frontend. All major issues from the previous review have been resolved. The current state is end-of-Phase-4 (frontend nearly complete) with Phase 5 (ML) not yet started. Three new high-severity issues and several medium/low issues require attention before Phase 5 begins.

---

## What's Well-Designed

**1. Strict layering — zero regressions**
Routes call services, services call repos, repos run SQL. No route imports from `repositories/` or `models/` directly. No service mutates ORM objects inline (mostly — see H1). This was correct in Phase 1 and remains correct through the frontend phase. The architecture is holding.

**2. N+1 prevention via `joinedload` in hot paths (`match_repo.py:13, 28`)**
`get_by_id` and `get_upcoming` both use `joinedload(Match.home_team), joinedload(Match.away_team)`. These load teams in a single SQL JOIN, not one SELECT per match. Correctly placed in the repo layer, not the service or route.

**3. Composite index on predictions (`001_initial_schema.py:103`)**
`ix_predictions_match_model ON predictions(match_id, model_version)` covers the most common prediction access pattern — filter by match and optionally by model version. The leftmost prefix rule means it also covers match-only queries. This was added early and remains correct.

**4. Cache-aside pattern — correctly fixed (`prediction_service.py`)**
Yesterday's HIGH bug (caching integer IDs) is resolved. The service now caches `[PredictionRead.model_validate(p).model_dump() for p in predictions]` — the full serialized shape the client expects. Cache key namespacing (`predictions:match:{id}`) and configurable TTL via `settings.PREDICTION_CACHE_TTL` remain clean.

**5. Idempotent upserts with typed schemas (`match_repo.py:55`, `team_repo.py:35`)**
Both upsert functions use typed Pydantic schemas (`MatchUpsert`, `TeamCreate`) and check for existence by `api_id` before inserting. The `api_id is None` guard in `team_repo.upsert` (line 37) prevents accidentally overwriting unrelated teams. These were fixed in Phase 2 and are now correct.

**6. Celery configuration (`celery_app.py`)**
`task_acks_late=True`, `worker_prefetch_multiplier=1`, `task_track_started=True`, UTC enforced. Beat schedule is sensible: fixtures every 6h, results hourly at `:30`, retrain daily at 3am. Worker and beat in separate containers for independent scaling. Production-grade defaults.

**7. `bind=True` + retry logic on all tasks (`ingest.py`, `train.py`)**
Every Celery task uses `bind=True` with `max_retries=3, default_retry_delay=60` and calls `self.retry(exc=exc)` on failure. This is the correct pattern for transient API failures.

**8. Rate limiting in `football_api.py` (`football_api.py:81, 109, 157`)**
7-second pauses between league requests stay safely under the 10 req/min free-tier limit. The `_get()` helper handles 429 responses with a 65-second sleep and automatic single retry. Deterministic mock data shares `api_id` space with real data so `resolve_finished_matches` can update mock fixtures correctly.

**9. `useQueries` parallel prefetch in Dashboard (`Dashboard.tsx:29`)**
`useQueries` fires all prediction fetches in parallel when a day is selected. The same `queryKey: ['predictions', 'match', m.id]` is reused in `MatchCard` so those renders read from the TanStack Query cache instantly. This is exactly the right TanStack Query pattern.

**10. `feature_snapshot` column on Prediction (`prediction.py:36`)**
Storing the feature vector that generated a prediction as a JSON column enables post-hoc debugging, drift detection, and audit without re-running the feature pipeline. This is a thoughtful ML engineering detail that pays off heavily in Phase 5.

**11. `ModelRegistry` table (`prediction.py:43`)**
Tracks `model_name`, `version`, `mlflow_run_id`, `is_active`, and `metrics` in DB. The `is_active` flag enables promoting a new model version without redeploying — it's a feature flag for the production model. `MLFLOW_TRACKING_URI` in config means MLflow is wired up even before training starts.

**12. TypeScript types aligned with backend schemas (`types.ts`)**
`Match`, `Prediction`, `Team`, and `MatchListResponse` in `frontend/src/types.ts` match the Pydantic schemas exactly, including `null` handling on optional fields. The axios client returns typed promises, and TanStack Query generic types flow correctly into component props.

---

## Issues Found

### HIGH

**H1: Direct ORM mutation in `resolve_finished_matches` task — business logic leaking into worker (`ingest.py:102–106`)**
```python
match.status     = fixture.status
match.home_score = fixture.home_score
match.away_score = fixture.away_score
match.result     = fixture.result
db.commit()
```
The Celery task is directly mutating a SQLAlchemy ORM object and committing — this is repository work, not task work. The pattern established by every other write in the codebase (`match_repo.upsert`, `team_repo.upsert`, `prediction_repo.mark_result`) is that all DB writes go through a repo function. The task should call a `match_repo.update_result(db, match, fixture)` function. As written, this is the only place in the codebase where a non-repo module commits to the DB, which breaks the architectural contract and will be confusing when debugging.

**H2: N+1 query in `get_finished` — teams not eagerly loaded (`match_repo.py:43`)**
```python
def get_finished(db: Session, days_back: int = 7) -> list[Match]:
    return (
        db.query(Match)
        .filter(Match.status == MatchStatus.FINISHED)
        .filter(Match.utc_date >= cutoff)
        .order_by(Match.utc_date.desc())
        .all()
    )
```
There is no `joinedload` here. `MatchRead` includes `home_team: TeamRead` and `away_team: TeamRead`. When FastAPI serializes the response, SQLAlchemy issues one SELECT per match to load each team — 50 finished matches = 100 extra queries per `GET /matches/finished` call. `get_upcoming` has `joinedload` (line 28), but `get_finished` does not. Fix: add `.options(joinedload(Match.home_team), joinedload(Match.away_team))` to match the `get_upcoming` pattern.

**H3: `LeagueAccuracySummary` always receives an empty predictions map — bug silently suppresses output (`History.tsx:137`)**
```tsx
<LeagueAccuracySummary matches={leagueMatches} leaguePredictions={new Map()} />
```
`new Map()` is a fresh empty map every render. Inside `LeagueAccuracySummary`, `withPredictions.filter(m => leaguePredictions.get(m.id))` always returns an empty array, so `withPredictions.length === 0` and the component returns `null` every time. The accuracy summary never renders — this is a data flow bug. The predictions fetched by each `HistoryCard`'s `useQuery` are never surfaced to the parent. Fix: lift the prediction queries to the `History` component using `useQueries`, build the map from match IDs to predictions, then pass it down.

---

### MEDIUM

**M1: No cache invalidation after `resolve_finished_matches` updates prediction accuracy (`prediction_service.py`, `ingest.py`)**
When `prediction_repo.mark_result(...)` updates `result_correct`/`btts_correct`/`over_25_correct`, the stale prediction is still cached in Redis for up to `PREDICTION_CACHE_TTL` (1 hour). The History page will show incorrect accuracy badges during that window. `cache_delete` exists in `redis.py` and is imported but never called here. After marking results, add `from app.core.redis import cache_delete` and call `cache_delete(f"predictions:match:{match.id}")`. One line.

**M2: `season` missing from `MatchRead` schema and `frontend/src/types.ts`**
The `Match` model has a `season` column (added in migration 002). `MatchRead` (`schemas/match.py`) does not include it. `frontend/src/types.ts` doesn't either. The frontend can't display season, and the ML feature pipeline will need season as a categorical input feature. Fix: add `season: int | None = None` to `MatchRead` and `season: number | null` to the frontend `Match` interface.

**M3: `staleTime` unset — TanStack Query refetches on every window focus (`useCalendarMatches.ts`, `Predictions.tsx`, `History.tsx`)**
Default `staleTime=0` means every window focus event triggers a refetch for all active queries. `useCalendarMatches` fetches 30 days of upcoming + 90 days of finished on every tab switch. For data that changes at most every 6 hours (fixture schedule) or 1 hour (results), this creates unnecessary backend load and UI flicker. Suggested values: `staleTime: 5 * 60 * 1000` (5 minutes) for match queries, `staleTime: 60 * 60 * 1000` (1 hour) for prediction queries.

**M4: `Predictions.tsx` individual `useQuery` per match vs `Dashboard.tsx` parallel `useQueries`**
`Dashboard.tsx` correctly uses `useQueries` to fire all prediction fetches in parallel before rendering cards. `Predictions.tsx:PredictionCard` (line 12) uses individual `useQuery` per card — N separate requests fire as components mount, sequentially from React's perspective. This is inconsistent and will cause visible waterfall loading on the Predictions page. Lift prediction queries to the `Predictions` page level using `useQueries`, matching the Dashboard pattern.

**M5: No index on `teams.league` — full table scan on every league filter (`team_repo.py:19`, `team.py:13`)**
`team_repo.get_by_league()` runs `WHERE league = 'PL'` with no supporting index. While the teams table is small now (76 rows), the habit of leaving missing indexes is worth correcting. Add `index=True` to the `league` column in `models/team.py` and add migration 003 with `op.create_index("ix_teams_league", "teams", ["league"])`.

**M6: `retrain_all_models` logs success when it does nothing (`tasks/train.py:31`)**
```python
logger.info("Model retraining complete (stub)")
```
The Celery Beat schedule runs this daily at 3am UTC. Logs will show "Model retraining complete" even though no model was trained. This will be misleading when debugging Phase 5. Change the log message to `"Model retraining SKIPPED — ML not implemented yet (Phase 5)"` to make the stub state obvious.

---

### LOW

**L1: `PYTHONPATH=/` is fragile (`docker-compose.yml:44, 65, 80`)**
All three backend services set `PYTHONPATH=/`. This adds the filesystem root `/` as a Python search path, meaning any top-level directory name (e.g., `/data`, `/ml`) could shadow a stdlib or third-party module. Safer: `PYTHONPATH=/app` (the container's WORKDIR). The current value works because `data` and `ml` don't shadow any installed packages, but it's a footgun.

**L2: Frontend `depends_on: backend` uses default `service_started`, not `service_healthy` (`docker-compose.yml:109`)**
The frontend container starts the moment Docker marks the backend container as started, not when Uvicorn is actually ready. Early API calls from the frontend dev server will receive connection-refused errors. Add a health check to the backend service:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 5s
  timeout: 3s
  retries: 5
```
Then update `frontend.depends_on.backend.condition` to `service_healthy`.

**L3: `backfill_historical` has only 1 retry and inline `time.sleep` (`ingest.py:134–189`)**
The backfill fetches multiple seasons and leagues with `time.sleep(7)` between requests. With `max_retries=1`, a transient API failure at season 3 means the whole task fails after one retry with no way to resume where it left off. For a long-running one-shot task, consider either increasing retries or breaking the backfill into per-season sub-tasks. The `time.sleep` inside the task is also not Celery-friendly — if concurrency is 2 and a backfill task is sleeping, it blocks a worker slot.

**L4: `updated_at` uses Python-side `onupdate` lambda — bypassed by bulk SQL updates (`models/match.py:42`)**
```python
updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))
```
SQLAlchemy's `onupdate` fires only for ORM-level updates (e.g., `setattr` + `commit`). If a future migration or admin script uses `db.execute(update(Match).where(...))`, `updated_at` won't be set. For correctness across both access patterns, use `server_default=func.now(), server_onupdate=FetchedValue()` to let Postgres manage the timestamp via a trigger. Not urgent now since all updates go through the ORM, but worth knowing.

**L5: `FOOTBALL_DATA_API_KEY` defaults to empty string — produces confusing 401 errors (`config.py:19`)**
```python
FOOTBALL_DATA_API_KEY: str = ""
```
An empty string is truthy in Python, so `if settings.FOOTBALL_DATA_API_KEY:` would pass. When `USE_MOCK_DATA=False` and the key is empty, the API client sends `X-Auth-Token: ` and receives a 401, which surfaces as a generic HTTP error with no clear explanation. Change to `Optional[str] = None` and add a startup check in `main.py:lifespan` that raises a clear `ValueError` if `USE_MOCK_DATA=False` and the key is unset.

---

## Recommendations

1. **Fix H2 (`get_finished` N+1) immediately** — this is a one-line fix (`joinedload`) with measurable performance impact. Add it before Phase 5 adds more finished-match queries.

2. **Fix H3 (History accuracy bug)** — lift prediction queries to `History` component using `useQueries`, build the `leaguePredictions` map from `match.id → predictions?.[0]`, pass it down. The accuracy summary is a key product feature and silently broken.

3. **Move match field mutation to a repo function (H1)** — create `match_repo.update_from_result(db, match_id, status, home_score, away_score, result)` and call it from the Celery task. Keeps the repo boundary clean.

4. **Wire cache invalidation after result resolution (M1)** — one `cache_delete(f"predictions:match:{match.id}")` call after `prediction_repo.mark_result`. History page accuracy will be fresh immediately.

5. **Add `season` to `MatchRead` and `types.ts` (M2)** — needed before Phase 5 feature engineering. Season is a meaningful categorical feature and useful for the UI's display context.

6. **Add `staleTime` to all TanStack queries (M3)** — 5 minutes for match data, 1 hour for predictions. Prevents unnecessary refetch on every window focus.

7. **Add `teams.league` index (M5)** — migration 003, two lines.

---

## Phase Progress

**Current phase: Phase 4 (Frontend) — nearly complete. One bug remaining (H3).**

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Infrastructure (Docker, Postgres, Redis, Celery, FastAPI skeleton) | ✅ Complete |
| Phase 2 | Data model (models, migrations, schemas, repos, services, routes) | ✅ Complete |
| Phase 3 | Data ingestion (football_api client, Celery tasks, mock data, historical backfill) | ✅ Complete |
| Phase 4 | Frontend (React, TanStack Query, Dashboard, Predictions, History, components) | 🔶 Nearly complete — fix H3 accuracy bug |
| Phase 5 | ML model (feature engineering, training, serving, prediction generation) | ❌ Not started — ML dirs are empty stubs |
| Phase 6 | Advanced features (value bet detection, parlay builder, live scores) | ❌ Not started |
| Phase 7 | Production hardening (auth, monitoring, rate limiting, alerting) | ❌ Not started |

**Next concrete step after fixing H2+H3:** Begin `ml/features/` with `build_feature_vector(db, match) → dict` and `build_training_dataset(db, seasons) → pd.DataFrame`. The data is in the DB (2300+ historical matches across 3 seasons); the feature pipeline is the gate to Phase 5.

---

## System Design Interview Prep

This section covers every architectural pattern present in the codebase. For each: what it is, how this project implements it, and what to say in an interview.

---

### 1. Layered Architecture (N-Tier)

**What it is:** The application is divided into strict horizontal layers where each layer only calls the layer directly below it. Routes → Services → Repositories → Models/DB. No layer skips another; no layer reaches up.

**How this project implements it:**
- `api/v1/routes/matches.py` calls `match_service.get_upcoming_matches()` — no SQL
- `services/match_service.py` calls `match_repo.get_upcoming()` — no HTTP knowledge
- `repositories/match_repo.py` runs the query — no business rules, no cache

**The interview angle:** When asked "how would you structure a backend service?" this is the answer. The key insight: each layer can be tested in isolation. A service unit test mocks the repo. A repo integration test hits a real DB without an HTTP layer. Routes are so thin (they just validate input and call a service) that they rarely need unit tests.

**Trade-offs to discuss:** Layers add indirection. A service method that's a one-liner passthrough (like `match_service.get_upcoming_matches`) adds no immediate value — but it creates the seam for future business logic (authorization, rate limiting, cross-entity orchestration). The alternative is vertical slicing (all code for one feature collocated), which works better when features are truly independent.

**What to say:** "I use a three-layer architecture: thin routes for HTTP concerns, services for business logic, repos for SQL. Routes never import from repos. This makes each layer independently testable and means I can swap the DB layer — say, from Postgres to Redshift for analytics queries — without touching business logic."

---

### 2. Cache-Aside (Lazy Population)

**What it is:** The application — not the cache — is responsible for loading data into the cache on a miss. Read path: check cache → hit means return immediately; miss means query DB, populate cache with TTL, return. The application manages invalidation explicitly.

**How this project implements it:**
- `prediction_service.py:get_prediction_for_match` — three-step flow: `cache_get` → `prediction_repo.get_by_match` → (Phase 5: ML inference)
- `redis.py` provides `cache_get`, `cache_set`, `cache_delete`, `cache_delete_pattern` as primitives
- TTL configured via `settings.PREDICTION_CACHE_TTL = 3600` (env-overridable)

**The interview angle:** Answers "how do you reduce Postgres load for frequently-read data?" and "what caching strategy would you use for prediction results?" Contrast with write-through (update cache on every write — always consistent, more complex), read-through (cache fetches from DB itself — simpler app code, harder to control), and refresh-ahead (proactively refresh before TTL expires — good for predictable access patterns).

**Trade-offs to discuss:** Cache-aside has three failure modes worth discussing: (1) cache stampede — TTL expires under high traffic, many simultaneous misses all hit the DB; fix with distributed lock (Redlock) or probabilistic early expiration. (2) stale reads during TTL window — acceptable for predictions, not for financial balances. (3) cold start — first deployment has empty cache; fix with pre-warming in `main.py:lifespan` (there's a TODO Phase 2 comment there for exactly this).

**What to say:** "Cache-aside with Redis and a 1-hour TTL. On a cache miss the service queries Postgres, serializes via Pydantic, and stores in Redis. Cache-aside is the right choice here: predictions are read far more than written, and a 1-hour stale window is acceptable. Explicit `cache_delete` on result resolution keeps the History page accurate."

---

### 3. Connection Pooling

**What it is:** Reusing a fixed set of persistent DB connections across requests rather than opening and closing one per request. Opening a Postgres connection costs ~5–15ms (TCP handshake, auth, SSL). A pool keeps connections alive and lends them to request handlers.

**How this project implements it:**
- `database.py:21` — `create_engine(url, pool_size=10, max_overflow=20, pool_pre_ping=True)`
- `get_db()` yields a session from `SessionLocal` — session returns to the pool when the `with` block exits
- `pool_pre_ping=True` — runs `SELECT 1` before handing out a connection to detect stale ones

**The interview angle:** "How many concurrent requests can your backend handle before DB becomes a bottleneck?" `pool_size=10` = 10 simultaneous DB operations per backend container. `max_overflow=20` allows bursting to 30. Beyond that, new requests wait up to `pool_timeout` (30s default) then fail with `TimeoutError`.

**Trade-offs to discuss:** Pool size must be tuned against Postgres's `max_connections` (default 100). With three containers (backend, celery-worker, celery-beat) each at `pool_size=10`, peak is 90 connections — within the default limit. In production with horizontal scaling (multiple backend replicas), PgBouncer in front of Postgres is standard: it multiplexes N app-side connections to M DB-side connections, allowing M << N.

**What to say:** "SQLAlchemy maintains a connection pool of 10 persistent connections with burst capacity to 30. `pool_pre_ping` detects stale connections before use — important in containers where the DB can restart independently. At scale I'd add PgBouncer to decouple app-side pooling from Postgres connection limits, which tops out around 100 by default."

---

### 4. Async Job Queue (Celery + Redis)

**What it is:** Decoupling long-running or scheduled work from the request-response cycle. A producer (Celery Beat or an API call) pushes a message onto a queue; workers consume and execute asynchronously. The queue survives worker restarts and allows horizontal scaling of consumers independently of producers.

**How this project implements it:**
- `celery_app.py` — Celery with Redis as both broker and result backend; 3 Beat tasks configured
- `ingest.py` — `ingest_upcoming_fixtures` (6h), `resolve_finished_matches` (hourly), `backfill_historical` (manual)
- `train.py` — `retrain_all_models` (daily 3am stub)
- Separate `celery-worker` and `celery-beat` Docker containers for independent scaling

**The interview angle:** Answers "how do you handle work that takes longer than an HTTP timeout?" and "how do you call an external API without blocking user requests?" Key follow-ups: at-least-once vs exactly-once delivery (at-least-once is standard; exactly-once requires distributed transactions and is almost never worth the complexity), and task idempotency as the mitigation.

**Trade-offs to discuss:** (1) `task_acks_late=True` — message removed from queue only after task succeeds; crash mid-task means redelivery. Requires idempotency. (2) `worker_prefetch_multiplier=1` — prevents a worker from hoarding tasks it can't execute yet, which matters when tasks have variable duration. (3) No task routing yet — a long-running `retrain_all_models` (minutes in Phase 5) shares the default queue with `ingest_upcoming_fixtures` (seconds). This will cause visible latency on the ingestion pipeline once ML training is wired in.

**What to say:** "Celery decouples ingestion from the request path. Beat fires tasks on a cron schedule; workers pull from the Redis queue and execute. `acks_late=True` for at-least-once delivery means tasks may run more than once on crash, so every write goes through an idempotent upsert. Beat and Worker run in separate containers so I can scale workers without creating extra scheduler instances."

---

### 5. Database Indexing Strategy

**What it is:** B-tree indexes that allow the DB to locate rows matching a WHERE condition in O(log N) instead of O(N). Every index speeds reads but adds write overhead (every INSERT/UPDATE must update the index tree) and storage.

**How this project implements it:**
- `matches`: indexes on `id` (PK), `league`, `utc_date`, `status`, `season` — the four filter dimensions used in every match query
- `predictions`: single-column `match_id` + composite `(match_id, model_version)`
- `odds`: `match_id` for joins
- `teams`: `id` only (missing `league` — see M5)

**The interview angle:** The composite `(match_id, model_version)` index is a signal of engineering maturity. A composite index on `(A, B)` supports queries filtering on `A` alone (leftmost prefix) and queries filtering on both `A AND B`. It does not support queries filtering on `B` alone. An interviewer will ask: "which column should be first in the composite?" — the more selective one (higher cardinality), or the one that appears in more queries without the other.

**Trade-offs to discuss:** Index selectivity matters. An index on `status` (4 possible values across potentially millions of rows) has low selectivity — Postgres may choose a sequential scan anyway if 25% of rows match. A partial index (`WHERE status = 'SCHEDULED'`) would be highly selective and smaller. The current individual indexes are correct starters; a composite `(status, utc_date)` would be the next optimization for the upcoming-matches query.

**What to say:** "I index based on query patterns. For matches, `league`, `utc_date`, `status`, and `season` cover every filter dimension used in the codebase. For predictions, I have a composite `(match_id, model_version)` because the most common access is 'all predictions for match X from model Y' — and the leftmost prefix rule means it also covers match-only queries for free."

---

### 6. Idempotent Writes (Upsert-by-Natural-Key)

**What it is:** A write operation that produces the same result whether run once or ten times. Essential in any system with at-least-once delivery (Celery, webhooks, retry loops) because re-delivery must not corrupt data.

**How this project implements it:**
- `team_repo.upsert`: look up by `api_id` → update fields if found, create if not; guarded for `api_id=None`
- `match_repo.upsert`: same pattern, using `api_id` from football-data.org as the deduplication key
- `prediction_repo.mark_result`: checks `pred.result_correct is not None` before updating — skips already-resolved predictions

**The interview angle:** "What happens if your ingestion task runs twice?" is a classic pipeline reliability question. With upsert-by-api_id the answer is: second run produces identical state, no duplicates, no errors. This is the at-least-once + idempotency pattern — the industry standard for data pipelines.

**Trade-offs to discuss:** The current upsert is SELECT-then-INSERT/UPDATE — a TOCTOU (time-of-check to time-of-use) race if two workers run the same task concurrently. For a single ingestion worker this is fine. For concurrent writers, `INSERT ... ON CONFLICT DO UPDATE` (SQLAlchemy: `insert().on_conflict_do_update()`) is atomic at the DB level and eliminates the race. This is worth adding before scaling to multiple ingestion workers.

**What to say:** "Every ingestion write goes through an upsert keyed on the external api_id. Re-running the task on failure produces identical state. Combined with `task_acks_late=True`, this gives at-least-once delivery with no data corruption. For concurrent writers I'd replace the SELECT-then-INSERT with a native `INSERT ... ON CONFLICT DO UPDATE` to make the upsert atomic."

---

### 7. Scheduled Data Pipeline (ETL)

**What it is:** Automated extract-transform-load process running on a cron-like schedule. Data is pulled from an external source, normalized, and written to the application DB. Decoupled from user requests; failure doesn't affect API availability.

**How this project implements it:**
- Celery Beat drives three scheduled tasks (6h fixtures, 1h results, daily retrain)
- `football_api.py` handles extraction: `fetch_upcoming`, `fetch_finished`, `fetch_season`
- Repos handle loading: `upsert` functions transform FixtureData → ORM models
- Mock mode (`USE_MOCK_DATA=True`) allows full pipeline testing without API keys

**The interview angle:** "Design a system that keeps soccer match data fresh." Key decisions: polling frequency (football-data.org rate limit drives the 6h schedule), failure handling (`self.retry`), and backfill for missed windows. Celery Beat does NOT auto-backfill missed runs — if the Beat container was down, scheduled jobs are skipped without recovery. Production fix: track `last_ingested_at` in a DB or Redis key; on task start, compute the appropriate date window rather than always using "the last 7 days."

**What to say:** "The ingestion pipeline is Celery Beat-driven. Fixtures every 6 hours stay within API rate limits. Results every hour minimize latency between match end and DB update. Backfilling historical seasons for ML training is a separate one-shot task. All writes are idempotent so task retries are safe. In production I'd track `last_ingested_at` to recover from Beat outages rather than relying on fixed time windows."

---

### 8. ML Model Versioning and Feature Snapshots

**What it is:** Tracking which trained model version generated each prediction, storing the input features, and maintaining a registry of model metadata (accuracy, training date, active flag). This enables debugging, drift detection, and safe model promotion.

**How this project implements it:**
- `Prediction.model_version` — e.g., "xgb-v1.2"
- `Prediction.feature_snapshot` — JSON column with the raw feature vector at inference time
- `ModelRegistry` table — `model_name`, `version`, `mlflow_run_id`, `is_active`, `metrics` JSON
- `settings.MLFLOW_TRACKING_URI` — wired up even before training starts

**The interview angle:** "How do you safely deploy a new model without breaking the product?" The `is_active` flag in `ModelRegistry` is a feature flag for the production model. Train a new version offline, compare `metrics`, flip `is_active` without redeploying. Roll back by flipping it back. The `feature_snapshot` column answers "why did the model predict 70% home win for this match?" without needing to re-run the feature pipeline.

**Trade-offs to discuss:** Feature snapshots cost storage (JSON per prediction row) but are invaluable for debugging. An alternative is storing only the feature hash and recomputing on demand — but this requires the underlying data to be immutable. Historical match stats can be updated (e.g., xG scores arrive days after the match), making snapshot storage the only reliable option.

**What to say:** "Each prediction stores the model version and the feature vector that generated it. The ModelRegistry tracks all trained versions with MLflow run IDs and validation metrics. The `is_active` flag promotes a model to production without redeployment — I train a new version, compare metrics against the holdout season, and flip the flag. `feature_snapshot` lets me audit any prediction post-hoc."

---

### 9. Frontend Data Fetching with TanStack Query (Stale-While-Revalidate)

**What it is:** A client-side caching and synchronization library that maintains a cache of server state keyed by `queryKey`. On mount, a component checks the cache — if data is fresh (within `staleTime`), it renders from cache without a network request; if stale, it serves the cached data immediately while fetching fresh data in the background (stale-while-revalidate).

**How this project implements it:**
- `api/client.ts` — centralized axios instance; all API functions return typed promises
- `useCalendarMatches`, `useLeagueFilter` — custom hooks encapsulating query logic and filter state
- `Dashboard.tsx` — `useQueries` for parallel prediction prefetch; cards read from the same key instantly
- Consistent `queryKey` format: `['matches', 'upcoming', days]`, `['predictions', 'match', id]`

**The interview angle:** TanStack Query implements stale-while-revalidate — the browser pattern for serving cached responses while checking for freshness. The interview question is "how do you keep client state in sync with the server without blocking the UI?" The `queryKey` is the cache key; hierarchical keys enable targeted invalidation (`invalidateQueries(['predictions'])` invalidates all prediction queries).

**Trade-offs to discuss:** `staleTime=0` (the current default) means every mount and window focus triggers a refetch. This is appropriate for truly real-time data (e.g., live stock prices) but excessive for match schedules that update every 6 hours. Tuning `staleTime` is the correct fix (M3 above).

**What to say:** "TanStack Query acts as a client-side cache with stale-while-revalidate semantics. Data is served from cache immediately, then refreshed in the background. The queryKey uniquely identifies each dataset — I include all filter params so changing a filter triggers a new fetch. `useQueries` lets me fire N prediction requests in parallel before any card renders, so by the time a user expands a match, its prediction is already in cache."

---

## Learning Opportunities

1. **PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` (atomic upsert).** The current upsert pattern has a subtle TOCTOU race under concurrent writers. Learn SQLAlchemy's `insert().on_conflict_do_update()` and understand why it's atomic where SELECT-then-INSERT is not. This comes up in every data pipeline system design interview.

2. **Celery task routing and priority queues.** The single default queue will become a problem in Phase 5 when multi-minute training tasks compete with sub-second ingestion tasks. Research `task_routes`, dedicated queues with `--queues=ingestion` vs `--queues=ml`, and how `worker_prefetch_multiplier` interacts with task duration variance.

3. **TanStack Query `staleTime`, `gcTime`, and `invalidateQueries`.** The codebase uses TanStack Query with all default settings. Understanding these three levers — and how `staleTime` interacts with the backend Redis TTL to form a two-level cache — will prevent subtle staleness bugs and is a genuinely interesting system design problem (client cache + server cache + source of truth).
