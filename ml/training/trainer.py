"""
Model trainer — builds features from DB, trains 3 XGBoost models, logs to MLflow.

Models trained:
  match_result  — multi-class (0=HOME, 1=DRAW, 2=AWAY)
  btts          — binary (1 = both teams score)
  over_under    — binary (1 = over 2.5 goals)

Usage:
  from ml.training.trainer import train_all
  train_all(db)
"""

from __future__ import annotations

import logging
import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score
from xgboost import XGBClassifier
from sqlalchemy.orm import Session

from ml.features.builder import build_training_dataset, FEATURE_COLS
from app.core.config import settings

logger = logging.getLogger(__name__)

XGB_PARAMS = {
    "n_estimators": 300,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "eval_metric": "logloss",
    "random_state": 42,
    "verbosity": 0,
}


def train_all(db: Session) -> dict[str, str]:
    """
    Train all three models and register them in MLflow + the DB model registry.
    Returns a dict of {model_name: mlflow_run_id}.
    """
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    mlflow.set_experiment("parlay-beater")

    logger.info("Building training dataset...")
    df = build_training_dataset(db)
    logger.info("Training dataset: %d rows, %d features", len(df), len(FEATURE_COLS))

    if len(df) < 100:
        raise ValueError(f"Too few training samples ({len(df)}). Run backfill first.")

    X = df[FEATURE_COLS]
    run_ids = {}

    run_ids["match_result"] = _train_multiclass(X, df["result_label"], "match_result")
    run_ids["btts"]         = _train_binary(X, df["btts_label"],   "btts")
    run_ids["over_under"]   = _train_binary(X, df["over25_label"], "over_under")

    _register_models(db, run_ids)
    return run_ids


def _train_multiclass(X: pd.DataFrame, y: pd.Series, name: str) -> str:
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    model = XGBClassifier(objective="multi:softprob", num_class=3, **XGB_PARAMS)

    with mlflow.start_run(run_name=name) as run:
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

        preds = model.predict(X_val)
        proba = model.predict_proba(X_val)
        acc   = accuracy_score(y_val, preds)
        auc   = roc_auc_score(y_val, proba, multi_class="ovr", average="macro")

        mlflow.log_params({**XGB_PARAMS, "objective": "multi:softprob", "num_class": 3})
        mlflow.log_metrics({"accuracy": acc, "roc_auc_macro": auc, "train_rows": len(X_train)})
        mlflow.sklearn.log_model(model, artifact_path=name)

        logger.info("%s — accuracy=%.3f  roc_auc=%.3f", name, acc, auc)
        return run.info.run_id


def _train_binary(X: pd.DataFrame, y: pd.Series, name: str) -> str:
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    model = XGBClassifier(objective="binary:logistic", **XGB_PARAMS)

    with mlflow.start_run(run_name=name) as run:
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

        preds = model.predict(X_val)
        proba = model.predict_proba(X_val)[:, 1]
        acc   = accuracy_score(y_val, preds)
        auc   = roc_auc_score(y_val, proba)

        mlflow.log_params({**XGB_PARAMS, "objective": "binary:logistic"})
        mlflow.log_metrics({"accuracy": acc, "roc_auc": auc, "train_rows": len(X_train)})
        mlflow.sklearn.log_model(model, artifact_path=name)

        logger.info("%s — accuracy=%.3f  roc_auc=%.3f", name, acc, auc)
        return run.info.run_id


def _register_models(db: Session, run_ids: dict[str, str]):
    """Upsert model registry rows and mark new versions as active."""
    from datetime import datetime, timezone
    from app.models.prediction import ModelRegistry

    for model_name, run_id in run_ids.items():
        # Deactivate old versions
        db.query(ModelRegistry).filter(
            ModelRegistry.model_name == model_name,
            ModelRegistry.is_active == True,
        ).update({"is_active": False})

        version = datetime.now(timezone.utc).strftime("v%Y%m%d-%H%M")
        entry = ModelRegistry(
            model_name=model_name,
            version=version,
            mlflow_run_id=run_id,
            is_active=True,
            trained_at=datetime.now(timezone.utc),
        )
        db.add(entry)

    db.commit()
    logger.info("Model registry updated — %d models registered", len(run_ids))
