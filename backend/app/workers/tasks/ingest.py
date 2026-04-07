"""
Data ingestion tasks — pull from football API, write to DB.

These are Celery tasks: called asynchronously by Beat or triggered manually.
"""

import logging
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.core.config import settings
from app.core.database import SessionLocal
import app.models  # ensures all ORM models are registered before any query runs

logger = logging.getLogger(__name__)

# Seasons to backfill: last 3 completed seasons before current
def _current_season() -> int:
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 8 else now.year - 1

def _upsert_fixture(db, fixture, team_repo, match_repo, TeamCreate, MatchUpsert):
    """Shared upsert logic used by both ingest and backfill tasks."""
    ht = fixture.home_team
    at = fixture.away_team
    home = team_repo.upsert(db, TeamCreate(
        api_id=ht.api_id, name=ht.name, short_name=ht.short_name,
        league=ht.league, country=ht.country,
    ))
    away = team_repo.upsert(db, TeamCreate(
        api_id=at.api_id, name=at.name, short_name=at.short_name,
        league=at.league, country=at.country,
    ))
    match_repo.upsert(db, MatchUpsert(
        api_id       = fixture.api_id,
        league       = fixture.league,
        season       = fixture.season,
        matchday     = fixture.matchday,
        utc_date     = fixture.utc_date,
        status       = fixture.status,
        home_team_id = home.id,
        away_team_id = away.id,
        home_score   = fixture.home_score,
        away_score   = fixture.away_score,
        result       = fixture.result,
    ))


@celery_app.task(
    name="app.workers.tasks.ingest.ingest_upcoming_fixtures",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def ingest_upcoming_fixtures(self):
    """
    Fetch upcoming matches from football API and upsert into DB.
    Runs every 6 hours via Celery Beat.
    """
    from data.ingestion.football_api import fetch_upcoming
    from app.repositories import match_repo, team_repo
    from app.schemas.team import TeamCreate
    from app.schemas.match import MatchUpsert

    logger.info("Starting fixture ingestion (mock=%s)...", settings.USE_MOCK_DATA)
    try:
        fixtures = fetch_upcoming(settings.target_leagues_list)
        with SessionLocal() as db:
            for fixture in fixtures:
                _upsert_fixture(db, fixture, team_repo, match_repo, TeamCreate, MatchUpsert)
        logger.info("Fixture ingestion complete — %d matches upserted", len(fixtures))
    except Exception as exc:
        logger.error("Fixture ingestion failed: %s", exc)
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.ingest.resolve_finished_matches",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def resolve_finished_matches(self):
    """
    Fetch results for recently finished matches.
    Updates match scores + marks predictions as correct/incorrect.
    """
    from data.ingestion.football_api import fetch_finished
    from app.repositories import match_repo, prediction_repo

    logger.info("Resolving finished matches (mock=%s)...", settings.USE_MOCK_DATA)
    try:
        finished = fetch_finished(settings.target_leagues_list)
        resolved = 0

        with SessionLocal() as db:
            for fixture in finished:
                match = match_repo.get_by_api_id(db, fixture.api_id)
                if match is None:
                    continue

                match.status     = fixture.status
                match.home_score = fixture.home_score
                match.away_score = fixture.away_score
                match.result     = fixture.result
                db.commit()

                if fixture.result is None:
                    continue

                predictions = prediction_repo.get_by_match(db, match.id)
                for pred in predictions:
                    if pred.result_correct is not None:
                        continue

                    result_correct  = pred.result_home is not None and _top_outcome(pred) == fixture.result
                    actual_btts     = (fixture.home_score or 0) > 0 and (fixture.away_score or 0) > 0
                    btts_correct    = pred.btts is not None and (pred.btts >= 0.5) == actual_btts
                    total_goals     = (fixture.home_score or 0) + (fixture.away_score or 0)
                    over_25_correct = pred.over_25 is not None and (pred.over_25 >= 0.5) == (total_goals > 2)

                    prediction_repo.mark_result(db, pred.id, result_correct, btts_correct, over_25_correct)

                resolved += 1

        logger.info("Result resolution complete — %d matches resolved", resolved)
    except Exception as exc:
        logger.error("Result resolution failed: %s", exc)
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.ingest.backfill_historical",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
)
def backfill_historical(self, seasons: list[int] | None = None):
    """
    Backfill historical seasons into the DB for ML training.

    Fetches all finished matches for each (league, season) pair and upserts them.
    Idempotent — safe to re-run; existing rows are updated not duplicated.

    Default: last 3 completed seasons across all target leagues.
    Pass seasons=[2022, 2023] to backfill specific years.
    """
    from data.ingestion.football_api import fetch_season
    from app.repositories import match_repo, team_repo
    from app.schemas.team import TeamCreate
    from app.schemas.match import MatchUpsert
    import time

    current = _current_season()
    if seasons is None:
        # Free tier of football-data.org: current season - 2 is the oldest accessible
        seasons = [current - 2, current - 1, current]

    leagues = settings.target_leagues_list
    total_upserted = 0

    logger.info(
        "Starting historical backfill — leagues=%s seasons=%s (mock=%s)",
        leagues, seasons, settings.USE_MOCK_DATA,
    )

    try:
        for season in seasons:
            for i, league in enumerate(leagues):
                if i > 0:
                    time.sleep(7)  # respect 10 req/min rate limit

                logger.info("Fetching %s season %d...", league, season)
                fixtures = fetch_season(league, season)

                if not fixtures:
                    logger.warning("No data returned for %s season %d — skipping", league, season)
                    continue

                with SessionLocal() as db:
                    for fixture in fixtures:
                        _upsert_fixture(db, fixture, team_repo, match_repo, TeamCreate, MatchUpsert)

                total_upserted += len(fixtures)
                logger.info("  %s %d → %d matches upserted", league, season, len(fixtures))

        logger.info("Backfill complete — %d total matches upserted", total_upserted)
    except Exception as exc:
        logger.error("Backfill failed: %s", exc)
        raise self.retry(exc=exc)


def _top_outcome(pred) -> str:
    candidates = {
        "HOME": pred.result_home or 0.0,
        "DRAW": pred.result_draw or 0.0,
        "AWAY": pred.result_away or 0.0,
    }
    return max(candidates, key=candidates.get)
