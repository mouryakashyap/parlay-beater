from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.models.base import Base


class Prediction(Base):
    """
    Model-generated prediction for a match.
    One row per match per model_version (allows comparing model iterations).
    """
    __tablename__ = "predictions"

    id            = Column(Integer, primary_key=True, index=True)
    match_id      = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    model_version = Column(String, nullable=False)  # e.g. "xgb-v1.2"

    # ── Prediction outputs ────────────────────────────────────────────────────
    result_home   = Column(Float)    # probability: home win
    result_draw   = Column(Float)    # probability: draw
    result_away   = Column(Float)    # probability: away win

    btts          = Column(Float)    # probability: both teams score
    over_25       = Column(Float)    # probability: over 2.5 goals

    confidence    = Column(Float)    # composite confidence 0–1

    # ── Post-match tracking ───────────────────────────────────────────────────
    # Filled in once the match is finished — used to measure model accuracy
    result_correct    = Column(Boolean)
    btts_correct      = Column(Boolean)
    over_25_correct   = Column(Boolean)

    # Raw feature snapshot used to generate this prediction (for debugging)
    feature_snapshot  = Column(JSON)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    match = relationship("Match", back_populates="predictions")


class ModelRegistry(Base):
    """
    Tracks trained model versions. Linked to MLflow run IDs.
    Use this to know which model version generated which predictions.
    """
    __tablename__ = "model_registry"

    id            = Column(Integer, primary_key=True)
    model_name    = Column(String, nullable=False)   # e.g. "btts", "over_under", "match_result"
    league        = Column(String, nullable=False, default="")  # e.g. "PL", "PD", "SA"
    version       = Column(String, nullable=False)   # e.g. "v20260408-0003"
    mlflow_run_id = Column(String)
    trained_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active     = Column(Boolean, default=False)   # only one active per (model_name, league)

    # Validation metrics at training time
    metrics       = Column(JSON)                     # e.g. {"accuracy": 0.61, "roc_auc": 0.71}
