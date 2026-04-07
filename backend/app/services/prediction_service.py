"""
Prediction service — orchestrates cache-aside + ML model serving.

Flow:
  1. Check Redis cache → hit? return immediately
  2. Miss → query DB for existing prediction
  3. DB miss → run ML predictor on-demand → save to DB → cache → return
"""

import logging
from sqlalchemy.orm import Session

from app.core.redis import cache_get, cache_set
from app.repositories import prediction_repo
from app.models.prediction import Prediction, ModelRegistry
from app.schemas.prediction import PredictionRead

logger = logging.getLogger(__name__)


def _cache_key(match_id: int) -> str:
    return f"predictions:match:{match_id}"


def get_prediction_for_match(db: Session, match_id: int) -> list[Prediction]:
    """
    Cache-aside: Redis → DB → ML predictor (on-demand fallback).
    Returns list of predictions (one per model version).
    """
    # 1. Cache check
    cached = cache_get(_cache_key(match_id))
    if cached is not None:
        return cached

    # 2. DB check
    predictions = prediction_repo.get_by_match(db, match_id)
    if predictions:
        cache_set(_cache_key(match_id), [PredictionRead.model_validate(p).model_dump() for p in predictions])
        return predictions

    # 3. On-demand ML prediction (only if trained models exist)
    has_models = db.query(ModelRegistry).filter(ModelRegistry.is_active == True).first()
    if not has_models:
        return []

    try:
        from app.repositories import match_repo
        from ml.serving.predictor import generate_predictions
        match = match_repo.get_by_id(db, match_id)
        if match is None:
            return []
        generate_predictions(db, matches=[match])
        predictions = prediction_repo.get_by_match(db, match_id)
        if predictions:
            cache_set(_cache_key(match_id), [PredictionRead.model_validate(p).model_dump() for p in predictions])
    except Exception:
        logger.exception("On-demand prediction failed for match_id=%d", match_id)

    return predictions


def get_recent_predictions(db: Session, limit: int = 50) -> list[Prediction]:
    return prediction_repo.get_recent(db, limit=limit)
