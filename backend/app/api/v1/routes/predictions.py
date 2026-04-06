from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import prediction_service
from app.schemas.prediction import PredictionRead

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/match/{match_id}", response_model=list[PredictionRead])
def get_predictions_for_match(match_id: int, db: Session = Depends(get_db)):
    """
    Return predictions for a specific match.
    Cache-aside: served from Redis if warm, otherwise DB.
    """
    return prediction_service.get_prediction_for_match(db, match_id)


@router.get("/recent", response_model=list[PredictionRead])
def get_recent_predictions(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return prediction_service.get_recent_predictions(db, limit=limit)
