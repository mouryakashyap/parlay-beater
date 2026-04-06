"""
Prediction repository — all Prediction DB queries live here.
"""

from sqlalchemy.orm import Session
from app.models.prediction import Prediction


def get_by_match(db: Session, match_id: int, model_version: str | None = None) -> list[Prediction]:
    q = db.query(Prediction).filter(Prediction.match_id == match_id)
    if model_version:
        q = q.filter(Prediction.model_version == model_version)
    return q.order_by(Prediction.created_at.desc()).all()


def get_recent(db: Session, limit: int = 50) -> list[Prediction]:
    return db.query(Prediction).order_by(Prediction.created_at.desc()).limit(limit).all()


def create(db: Session, prediction_data: dict) -> Prediction:
    prediction = Prediction(**prediction_data)
    db.add(prediction)
    db.commit()
    db.refresh(prediction)
    return prediction


def mark_result(db: Session, prediction_id: int, result_correct: bool, btts_correct: bool, over_25_correct: bool) -> Prediction | None:
    """Update accuracy fields once match result is known."""
    prediction = db.query(Prediction).filter(Prediction.id == prediction_id).first()
    if not prediction:
        return None
    prediction.result_correct  = result_correct
    prediction.btts_correct    = btts_correct
    prediction.over_25_correct = over_25_correct
    db.commit()
    db.refresh(prediction)
    return prediction
