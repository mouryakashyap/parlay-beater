"""
Model training tasks — triggered by Celery Beat or manually.

Phase 5 will wire in the real ML pipeline.
"""

import logging
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.tasks.train.retrain_all_models",
    bind=True,
    max_retries=1,
)
def retrain_all_models(self):
    """
    Retrain all prediction models on latest data.
    Runs daily at 3am UTC via Celery Beat.
    """
    logger.info("Starting model retraining...")
    try:
        from ml.training.trainer import train_all
        from app.core.database import SessionLocal
        with SessionLocal() as db:
            run_ids = train_all(db)
        logger.info("Model retraining complete — run_ids=%s", run_ids)
    except Exception as exc:
        logger.error("Model retraining failed: %s", exc)
        raise self.retry(exc=exc)
