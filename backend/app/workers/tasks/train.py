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
        # TODO Phase 5:
        # from ml.training.trainer import Trainer
        # trainer = Trainer()
        # trainer.train("match_result")
        # trainer.train("btts")
        # trainer.train("over_under")
        logger.info("Model retraining complete (stub)")
    except Exception as exc:
        logger.error(f"Model retraining failed: {exc}")
        raise self.retry(exc=exc)
