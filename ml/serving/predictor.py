"""
Prediction serving — loads trained models from MLflow, generates predictions
for a list of upcoming matches, writes results to the predictions table.

Usage:
  from ml.serving.predictor import generate_predictions
  generate_predictions(db)
"""

from __future__ import annotations

import logging
import mlflow.sklearn
from sqlalchemy.orm import Session

from ml.features.builder import build_features, FEATURE_COLS
from app.core.config import settings
from app.models.match import Match, MatchStatus
from app.models.prediction import Prediction, ModelRegistry

logger = logging.getLogger(__name__)

# Result label index → string
_RESULT_LABELS = {0: "HOME", 1: "DRAW", 2: "AWAY"}


def generate_predictions(db: Session, matches: list[Match] | None = None) -> int:
    """
    Generate predictions for upcoming (SCHEDULED) matches.

    If matches is None, fetches all SCHEDULED matches from the DB.
    Skips any match that already has a prediction from the current active model version.
    Returns the number of predictions written.
    """
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)

    models = _load_active_models(db)
    if not models:
        raise RuntimeError("No active models found. Run training first.")

    result_model  = models["match_result"]
    btts_model    = models["btts"]
    ou_model      = models["over_under"]
    model_version = _active_version(db)

    if matches is None:
        matches = db.query(Match).filter(Match.status == MatchStatus.SCHEDULED).all()

    written = 0
    for match in matches:
        # Skip if already predicted by this model version
        existing = db.query(Prediction).filter(
            Prediction.match_id == match.id,
            Prediction.model_version == model_version,
        ).first()
        if existing:
            continue

        try:
            feats = build_features(db, match)
            X = [[feats[col] for col in FEATURE_COLS]]

            result_proba = result_model.predict_proba(X)[0]   # [p_home, p_draw, p_away]
            btts_proba   = btts_model.predict_proba(X)[0][1]  # P(btts=1)
            ou_proba     = ou_model.predict_proba(X)[0][1]    # P(over_2.5=1)

            # Confidence = max probability across the result classes
            confidence = float(max(result_proba))

            pred = Prediction(
                match_id      = match.id,
                model_version = model_version,
                result_home   = float(result_proba[0]),
                result_draw   = float(result_proba[1]),
                result_away   = float(result_proba[2]),
                btts          = float(btts_proba),
                over_25       = float(ou_proba),
                confidence    = confidence,
                feature_snapshot = feats,
            )
            db.add(pred)
            written += 1
        except Exception:
            logger.exception("Failed to predict match_id=%d", match.id)

    db.commit()
    logger.info("Generated %d predictions (model_version=%s)", written, model_version)
    return written


def _load_active_models(db: Session) -> dict:
    """Load the active MLflow model artifact for each model type."""
    active = (
        db.query(ModelRegistry)
        .filter(ModelRegistry.is_active == True)
        .all()
    )
    models = {}
    for entry in active:
        run_uri = f"runs:/{entry.mlflow_run_id}/{entry.model_name}"
        try:
            models[entry.model_name] = mlflow.sklearn.load_model(run_uri)
            logger.info("Loaded %s from %s", entry.model_name, run_uri)
        except Exception:
            logger.exception("Failed to load model %s from %s", entry.model_name, run_uri)
    return models


def _active_version(db: Session) -> str:
    """Return the version string of the active match_result model (used as the row identifier)."""
    entry = (
        db.query(ModelRegistry)
        .filter(ModelRegistry.model_name == "match_result", ModelRegistry.is_active == True)
        .first()
    )
    return entry.version if entry else "unknown"
