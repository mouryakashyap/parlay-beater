"""
Model trainer — builds per-league features, trains 3 XGBoost models per league,
then wraps each with an isotonic regression calibrator so predicted probabilities
reflect real-world frequencies.

Pipeline per model:
  60% → train XGBoost
  20% → fit isotonic calibrator (CalibratedClassifierCV, cv='prefit')
  20% → validate and log metrics

The calibrated wrapper is what gets saved to MLflow — predict_proba on it
returns calibrated probabilities directly.

Cross-league matches (e.g. Champions League) are not predicted — no global model.

Usage:
  from ml.training.trainer import train_all
  train_all(db)
  train_all(db, leagues=["PL"])
"""

from __future__ import annotations

import logging
import os
import numpy as np
import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss
from xgboost import XGBClassifier
from sqlalchemy.orm import Session

from ml.features.builder import build_training_dataset, FEATURE_COLS
from app.core.config import settings

os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
logger = logging.getLogger(__name__)

XGB_BASE_PARAMS = {
    "n_estimators": 300,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "verbosity": 0,
}

MIN_TRAINING_ROWS = 150  # raised slightly — need enough for 3-way split

# Recency decay: half-life in days. Matches this many days old get 50% weight.
# 365 = matches from 1 year ago carry half the weight of today's matches.
RECENCY_HALF_LIFE_DAYS = 365


def train_all(db: Session, leagues: list[str] | None = None) -> dict[str, dict[str, str]]:
    """
    Train per-league calibrated models for all target leagues.
    Returns {league: {model_name: mlflow_run_id}}.
    """
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    mlflow.set_experiment("parlay-beater")

    if leagues is None:
        leagues = settings.target_leagues_list

    results = {}
    for league in leagues:
        logger.info("Training league: %s", league)
        run_ids = _train_league(db, league)
        if run_ids:
            results[league] = run_ids

    return results


def _train_league(db: Session, league: str) -> dict[str, str]:
    """Train all 3 calibrated models for a single league."""
    df = build_training_dataset(db, leagues=[league])
    logger.info("  %s — %d rows, %d features", league, len(df), len(FEATURE_COLS))

    if len(df) < MIN_TRAINING_ROWS:
        logger.warning("  %s — too few samples (%d), skipping", league, len(df))
        return {}

    X       = df[FEATURE_COLS]
    weights = _recency_weights(df["utc_date"])
    logger.info("  %s — weight range [%.3f, %.3f]", league, weights.min(), weights.max())

    run_ids = {
        "match_result": _train_multiclass(X, df["result_label"], weights, f"match_result:{league}", league),
        "btts":         _train_binary(X, df["btts_label"],       weights, f"btts:{league}",         league),
        "over_under":   _train_binary(X, df["over25_label"],     weights, f"over_under:{league}",   league),
    }

    _register_models(db, league, run_ids)
    return run_ids


def _recency_weights(dates: pd.Series, half_life_days: int = RECENCY_HALF_LIFE_DAYS) -> np.ndarray:
    """
    Exponential decay weights based on match date.
    Most recent match gets weight 1.0; a match half_life_days ago gets 0.5.
    """
    import pandas as pd
    from datetime import timezone

    # Ensure timezone-aware for comparison
    dates_utc = pd.to_datetime(dates, utc=True)
    latest    = dates_utc.max()
    days_ago  = (latest - dates_utc).dt.total_seconds() / 86400
    lam       = np.log(2) / half_life_days
    weights   = np.exp(-lam * days_ago.values)
    return weights.astype(np.float32)


def _train_multiclass(
    X: pd.DataFrame, y: pd.Series, weights: np.ndarray, run_name: str, league: str
) -> str:
    # 60 / 20 / 20 split — preserve weight alignment via index
    idx = np.arange(len(X))
    idx_train, idx_temp = train_test_split(idx, test_size=0.4, random_state=42, stratify=y)
    idx_cal,   idx_val  = train_test_split(idx_temp, test_size=0.5, random_state=42, stratify=y.iloc[idx_temp])

    X_train, y_train, w_train = X.iloc[idx_train], y.iloc[idx_train], weights[idx_train]
    X_cal,   y_cal,   w_cal   = X.iloc[idx_cal],   y.iloc[idx_cal],   weights[idx_cal]
    X_val,   y_val            = X.iloc[idx_val],    y.iloc[idx_val]

    params = {**XGB_BASE_PARAMS, "eval_metric": "mlogloss"}
    base = XGBClassifier(objective="multi:softprob", num_class=3, **params)
    base.fit(X_train, y_train, sample_weight=w_train, eval_set=[(X_cal, y_cal)], verbose=False)

    calibrated = CalibratedClassifierCV(base, method="isotonic", cv="prefit")
    calibrated.fit(X_cal, y_cal, sample_weight=w_cal)

    preds = calibrated.predict(X_val)
    proba = calibrated.predict_proba(X_val)
    acc   = accuracy_score(y_val, preds)
    auc   = roc_auc_score(y_val, proba, multi_class="ovr", average="macro")
    brier = float(sum(
        brier_score_loss((y_val == c).astype(int), proba[:, c]) for c in range(3)
    ) / 3)

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params({**params, "objective": "multi:softprob", "num_class": 3,
                           "league": league, "calibration": "isotonic",
                           "recency_half_life_days": RECENCY_HALF_LIFE_DAYS})
        mlflow.log_metrics({
            "accuracy": acc, "roc_auc_macro": auc,
            "brier": brier, "train_rows": len(X_train), "cal_rows": len(X_cal),
        })
        mlflow.sklearn.log_model(calibrated, artifact_path="match_result")

    logger.info("  match_result:%s — acc=%.3f  auc=%.3f  brier=%.3f", league, acc, auc, brier)
    return run.info.run_id


def _train_binary(
    X: pd.DataFrame, y: pd.Series, weights: np.ndarray, run_name: str, league: str
) -> str:
    idx = np.arange(len(X))
    idx_train, idx_temp = train_test_split(idx, test_size=0.4, random_state=42, stratify=y)
    idx_cal,   idx_val  = train_test_split(idx_temp, test_size=0.5, random_state=42, stratify=y.iloc[idx_temp])

    X_train, y_train, w_train = X.iloc[idx_train], y.iloc[idx_train], weights[idx_train]
    X_cal,   y_cal,   w_cal   = X.iloc[idx_cal],   y.iloc[idx_cal],   weights[idx_cal]
    X_val,   y_val            = X.iloc[idx_val],    y.iloc[idx_val]

    model_name = run_name.split(":")[0]
    params = {**XGB_BASE_PARAMS, "eval_metric": "logloss"}
    base = XGBClassifier(objective="binary:logistic", **params)
    base.fit(X_train, y_train, sample_weight=w_train, eval_set=[(X_cal, y_cal)], verbose=False)

    calibrated = CalibratedClassifierCV(base, method="isotonic", cv="prefit")
    calibrated.fit(X_cal, y_cal, sample_weight=w_cal)

    preds = calibrated.predict(X_val)
    proba = calibrated.predict_proba(X_val)[:, 1]
    acc   = accuracy_score(y_val, preds)
    auc   = roc_auc_score(y_val, proba)
    brier = brier_score_loss(y_val, proba)

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params({**params, "objective": "binary:logistic",
                           "league": league, "calibration": "isotonic",
                           "recency_half_life_days": RECENCY_HALF_LIFE_DAYS})
        mlflow.log_metrics({
            "accuracy": acc, "roc_auc": auc,
            "brier": brier, "train_rows": len(X_train), "cal_rows": len(X_cal),
        })
        mlflow.sklearn.log_model(calibrated, artifact_path=model_name)

    logger.info("  %s:%s — acc=%.3f  auc=%.3f  brier=%.3f", model_name, league, acc, auc, brier)
    return run.info.run_id


def _register_models(db: Session, league: str, run_ids: dict[str, str]):
    """Upsert model registry rows for a league and mark new versions as active."""
    from datetime import datetime, timezone
    from app.models.prediction import ModelRegistry

    version = datetime.now(timezone.utc).strftime("v%Y%m%d-%H%M")

    for model_name, run_id in run_ids.items():
        db.query(ModelRegistry).filter(
            ModelRegistry.model_name == model_name,
            ModelRegistry.league == league,
            ModelRegistry.is_active == True,
        ).update({"is_active": False})

        db.add(ModelRegistry(
            model_name    = model_name,
            league        = league,
            version       = version,
            mlflow_run_id = run_id,
            is_active     = True,
            trained_at    = datetime.now(timezone.utc),
        ))

    db.commit()
    logger.info("  %s — model registry updated (%d models)", league, len(run_ids))
