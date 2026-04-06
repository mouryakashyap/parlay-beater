"""
Prediction service — orchestrates cache-aside + ML model serving.

Flow:
  1. Check Redis cache → hit? return immediately
  2. Miss → query DB for existing prediction
  3. DB miss → run ML predictor → save to DB → cache → return

Phase 5 will wire in the real ML predictor.
"""

import json
from sqlalchemy.orm import Session

from app.core.redis import cache_get, cache_set
from app.repositories import prediction_repo
from app.models.prediction import Prediction


def _cache_key(match_id: int) -> str:
    return f"predictions:match:{match_id}"


def get_prediction_for_match(db: Session, match_id: int) -> list[Prediction] | None:
    """
    Cache-aside: Redis → DB → (ML predictor in Phase 5).
    Returns list of predictions (one per model version).
    """
    # 1. Cache check
    cached = cache_get(_cache_key(match_id))
    if cached is not None:
        return cached  # raw dicts from cache — route will serialize

    # 2. DB check
    predictions = prediction_repo.get_by_match(db, match_id)
    if predictions:
        cache_set(_cache_key(match_id), [p.id for p in predictions])
        return predictions

    # 3. TODO Phase 5: call ML predictor, persist, cache, return
    return []


def get_recent_predictions(db: Session, limit: int = 50) -> list[Prediction]:
    return prediction_repo.get_recent(db, limit=limit)
