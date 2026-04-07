from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import prediction_service
from app.schemas.prediction import PredictionRead

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/match/{match_id}", response_model=list[PredictionRead])
def get_predictions_for_match(match_id: int, db: Session = Depends(get_db)):
    """
    Return all predictions for a given match.

    Flow (cache-aside):
      1. Check Redis — return immediately on hit
      2. Miss → query DB
      3. DB miss → placeholder until ML model is wired in (Phase 5)

    Each item in the response is one model version's prediction,
    containing win/draw/loss probabilities, btts, over_2.5, and confidence.
    """
    return prediction_service.get_prediction_for_match(db, match_id)


@router.get("/recent", response_model=list[PredictionRead])
def get_recent_predictions(
    # ge=1: must be at least 1 — le=200: capped at 200 to prevent huge queries
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Return the most recently generated predictions across all matches."""
    return prediction_service.get_recent_predictions(db, limit=limit)
