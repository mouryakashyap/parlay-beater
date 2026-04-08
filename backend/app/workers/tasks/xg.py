"""
xG ingestion tasks — pulls expected goals from Understat and stores in match_stats.
"""

import logging
from app.workers.celery_app import celery_app
from app.core.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.tasks.xg.backfill_xg",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def backfill_xg(self, seasons: list[int] | None = None):
    """
    Backfill xG data for historical seasons.
    Defaults to the same 3-season window as the match backfill.
    """
    from data.ingestion.understat import backfill_xg as _backfill
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    current = now.year if now.month >= 8 else now.year - 1
    if seasons is None:
        seasons = [current - 2, current - 1, current]

    leagues = settings.target_leagues_list
    logger.info("Starting xG backfill — leagues=%s seasons=%s", leagues, seasons)

    try:
        with SessionLocal() as db:
            total = _backfill(db, leagues, seasons)
        logger.info("xG backfill complete — %d rows upserted", total)
    except Exception as exc:
        logger.error("xG backfill failed: %s", exc)
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.xg.update_recent_xg",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def update_recent_xg(self):
    """
    Refresh xG for recently finished matches. Runs daily alongside resolve_finished_matches.
    """
    from data.ingestion.understat import update_recent_xg as _update

    logger.info("Updating recent xG data...")
    try:
        with SessionLocal() as db:
            total = _update(db, settings.target_leagues_list)
        logger.info("xG update complete — %d rows upserted", total)
    except Exception as exc:
        logger.error("xG update failed: %s", exc)
        raise self.retry(exc=exc)
