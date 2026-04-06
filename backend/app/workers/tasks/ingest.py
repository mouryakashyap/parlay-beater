"""
Data ingestion tasks — pull from football API, write to DB.

These are Celery tasks: called asynchronously by Beat or triggered manually.

Phase 2 will fill in the actual API client calls.
The structure here (task wraps a service call) is the right pattern.
"""

import logging
from app.workers.celery_app import celery_app
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.tasks.ingest.ingest_upcoming_fixtures",
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # retry after 60s on failure
)
def ingest_upcoming_fixtures(self):
    """
    Fetch upcoming matches from football API and upsert into DB.
    Runs every 6 hours via Celery Beat.
    """
    logger.info("Starting fixture ingestion...")
    try:
        # TODO Phase 2: replace with real API client
        # from data.ingestion.football_api import fetch_upcoming
        # from app.repositories import match_repo, team_repo
        # with SessionLocal() as db:
        #     fixtures = fetch_upcoming(leagues=settings.target_leagues_list)
        #     for fixture in fixtures:
        #         team_repo.upsert(db, fixture["home_team"])
        #         team_repo.upsert(db, fixture["away_team"])
        #         match_repo.upsert(db, fixture)
        logger.info("Fixture ingestion complete (stub)")
    except Exception as exc:
        logger.error(f"Fixture ingestion failed: {exc}")
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
    logger.info("Resolving finished matches...")
    try:
        # TODO Phase 2:
        # fetch finished matches from API
        # update match.result, match.home_score, match.away_score
        # for each match, find its predictions and mark accuracy
        logger.info("Result resolution complete (stub)")
    except Exception as exc:
        logger.error(f"Result resolution failed: {exc}")
        raise self.retry(exc=exc)
