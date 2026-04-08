"""
Prediction serving — loads per-league trained models, generates predictions
for upcoming matches, writes results to the predictions table.

Cross-league matches (e.g. Champions League) are skipped — no global model fallback.

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


def generate_predictions(db: Session, matches: list[Match] | None = None) -> int:
    """
    Generate predictions for upcoming (SCHEDULED) matches.
    Loads the league-specific model for each match.
    Skips matches whose league has no trained model.
    Returns the number of predictions written.
    """
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)

    if matches is None:
        matches = db.query(Match).filter(Match.status == MatchStatus.SCHEDULED).all()

    # Group matches by league so we load each model set once
    by_league: dict[str, list[Match]] = {}
    for m in matches:
        by_league.setdefault(m.league, []).append(m)

    written = 0
    for league, league_matches in by_league.items():
        models = _load_league_models(db, league)
        if not models:
            logger.info("No trained models for league %s — skipping %d matches", league, len(league_matches))
            continue

        version = _active_version(db, league)
        written += _predict_matches(db, league_matches, models, version)

    return written


def _predict_matches(
    db: Session,
    matches: list[Match],
    models: dict,
    model_version: str,
) -> int:
    written = 0
    result_model = models["match_result"]
    btts_model   = models["btts"]
    ou_model     = models["over_under"]

    for match in matches:
        existing = db.query(Prediction).filter(
            Prediction.match_id == match.id,
            Prediction.model_version == model_version,
        ).first()
        if existing:
            continue

        try:
            feats = build_features(db, match)
            X = [[feats[col] for col in FEATURE_COLS]]

            result_proba = result_model.predict_proba(X)[0]
            btts_proba   = btts_model.predict_proba(X)[0][1]
            ou_proba     = ou_model.predict_proba(X)[0][1]
            confidence   = float(max(result_proba))

            db.add(Prediction(
                match_id         = match.id,
                model_version    = model_version,
                result_home      = float(result_proba[0]),
                result_draw      = float(result_proba[1]),
                result_away      = float(result_proba[2]),
                btts             = float(btts_proba),
                over_25          = float(ou_proba),
                confidence       = confidence,
                feature_snapshot = feats,
            ))
            written += 1
        except Exception:
            logger.exception("Failed to predict match_id=%d", match.id)

    db.commit()
    return written


def _load_league_models(db: Session, league: str) -> dict:
    """Load active MLflow models for a specific league. Returns {} if none found."""
    active = (
        db.query(ModelRegistry)
        .filter(ModelRegistry.league == league, ModelRegistry.is_active == True)
        .all()
    )
    if not active:
        return {}

    models = {}
    for entry in active:
        artifact = entry.model_name  # "match_result", "btts", "over_under"
        run_uri = f"runs:/{entry.mlflow_run_id}/{artifact}"
        try:
            models[entry.model_name] = mlflow.sklearn.load_model(run_uri)
        except Exception:
            logger.exception("Failed to load %s:%s from %s", entry.model_name, league, run_uri)

    # Only return if all 3 models loaded successfully
    if len(models) < 3:
        logger.warning("Incomplete model set for league %s (%d/3 loaded)", league, len(models))
        return {}

    return models


def _active_version(db: Session, league: str) -> str:
    entry = (
        db.query(ModelRegistry)
        .filter(
            ModelRegistry.model_name == "match_result",
            ModelRegistry.league == league,
            ModelRegistry.is_active == True,
        )
        .first()
    )
    return f"{entry.version}:{league}" if entry else f"unknown:{league}"
