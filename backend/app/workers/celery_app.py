"""
Celery application + Beat schedule.

Celery = distributed task queue.
Celery Beat = periodic task scheduler (like cron, but integrated with Celery).

Why two separate containers (worker + beat)?
  - Worker: executes tasks
  - Beat: only schedules — sends tasks to the queue on a timer
  Separating them allows scaling workers independently.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "parlay_beater",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.tasks.ingest",
        "app.workers.tasks.train",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,        # re-queue on worker crash
    worker_prefetch_multiplier=1,  # one task per worker at a time (safe default)
)

# ── Periodic Schedule (Celery Beat) ───────────────────────────────────────────
celery_app.conf.beat_schedule = {
    # Pull upcoming fixtures every 6 hours
    "ingest-fixtures-every-6h": {
        "task": "app.workers.tasks.ingest.ingest_upcoming_fixtures",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    # Pull results for finished matches every hour
    "resolve-results-every-1h": {
        "task": "app.workers.tasks.ingest.resolve_finished_matches",
        "schedule": crontab(minute=30),  # at :30 past every hour
    },
    # Retrain models daily at 3am UTC
    "retrain-models-daily": {
        "task": "app.workers.tasks.train.retrain_all_models",
        "schedule": crontab(hour=3, minute=0),
    },
}
