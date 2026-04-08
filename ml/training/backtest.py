"""
Backtesting pipeline — validates prediction quality on held-out season data.

Approach:
  - Train per-league models on TRAIN_SEASONS only
  - Predict all FINISHED matches in TEST_SEASON using those models
  - Compare predictions vs actual results
  - Report accuracy, calibration, Brier score, and confidence-stratified accuracy

Usage:
  from ml.training.backtest import run_backtest
  report = run_backtest(db)
  print_report(report)
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from datetime import timezone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
from sqlalchemy.orm import Session

from ml.features.builder import build_features, build_training_dataset, FEATURE_COLS
from app.models.match import Match, MatchStatus
from app.core.config import settings

os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
logger = logging.getLogger(__name__)

TRAIN_SEASONS = [2023, 2024]
TEST_SEASON   = 2025
CONFIDENCE_THRESHOLDS = [0.40, 0.45, 0.50, 0.55, 0.60]
CALIBRATION_BINS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


@dataclass
class ModelMetrics:
    accuracy: float = 0.0
    roc_auc: float  = 0.0
    brier: float    = 0.0
    calibration: list[dict] = field(default_factory=list)


@dataclass
class LeagueReport:
    league: str
    train_rows: int
    test_rows: int

    # Raw (uncalibrated) metrics
    raw_result:     ModelMetrics = field(default_factory=ModelMetrics)
    raw_btts:       ModelMetrics = field(default_factory=ModelMetrics)
    raw_ou:         ModelMetrics = field(default_factory=ModelMetrics)

    # Calibrated metrics
    cal_result:     ModelMetrics = field(default_factory=ModelMetrics)
    cal_btts:       ModelMetrics = field(default_factory=ModelMetrics)
    cal_ou:         ModelMetrics = field(default_factory=ModelMetrics)

    # Confidence-stratified result accuracy (calibrated): {threshold: (n, accuracy)}
    confidence_accuracy: dict[float, tuple[int, float]] = field(default_factory=dict)

    # Kept for backwards compat with print_report
    @property
    def result_accuracy(self): return self.cal_result.accuracy
    @property
    def result_roc_auc(self):  return self.cal_result.roc_auc
    @property
    def result_brier(self):    return self.cal_result.brier
    @property
    def result_calibration(self): return self.cal_result.calibration
    @property
    def btts_accuracy(self):   return self.cal_btts.accuracy
    @property
    def btts_roc_auc(self):    return self.cal_btts.roc_auc
    @property
    def btts_brier(self):      return self.cal_btts.brier
    @property
    def btts_calibration(self): return self.cal_btts.calibration
    @property
    def ou_accuracy(self):     return self.cal_ou.accuracy
    @property
    def ou_roc_auc(self):      return self.cal_ou.roc_auc
    @property
    def ou_brier(self):        return self.cal_ou.brier


@dataclass
class BacktestReport:
    train_seasons: list[int]
    test_season: int
    leagues: list[LeagueReport] = field(default_factory=list)


# ── Public API ────────────────────────────────────────────────────────────────

def run_backtest(
    db: Session,
    train_seasons: list[int] = TRAIN_SEASONS,
    test_season: int = TEST_SEASON,
    leagues: list[str] | None = None,
) -> BacktestReport:
    """
    Run full backtest. Trains temporary per-league models on train_seasons,
    predicts test_season, compares vs actuals.
    Does NOT write to the model registry or predictions table.
    """
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)

    if leagues is None:
        leagues = settings.target_leagues_list

    report = BacktestReport(train_seasons=train_seasons, test_season=test_season)

    for league in leagues:
        logger.info("Backtesting league: %s  (train=%s  test=%d)", league, train_seasons, test_season)
        league_report = _backtest_league(db, league, train_seasons, test_season)
        if league_report:
            report.leagues.append(league_report)

    return report


def print_report(report: BacktestReport):
    """Pretty-print the backtest report to stdout."""
    print(f"\n{'='*70}")
    print(f"  BACKTEST REPORT — train={report.train_seasons}  test={report.test_season}")
    print(f"{'='*70}")

    for lr in report.leagues:
        print(f"\n── {lr.league}  (train={lr.train_rows} rows  test={lr.test_rows} rows)")

        # ── Summary table: raw vs calibrated ─────────────────────────────────
        print(f"\n  {'Model':<14} {'Metric':<10} {'Raw':>8}  {'Calibrated':>11}  {'Δ':>8}")
        print(f"  {'-'*55}")
        rows = [
            ("Match Result", "Accuracy",  lr.raw_result.accuracy, lr.cal_result.accuracy),
            ("Match Result", "ROC AUC",   lr.raw_result.roc_auc,  lr.cal_result.roc_auc),
            ("Match Result", "Brier ↓",   lr.raw_result.brier,    lr.cal_result.brier),
            ("BTTS",         "Accuracy",  lr.raw_btts.accuracy,   lr.cal_btts.accuracy),
            ("BTTS",         "ROC AUC",   lr.raw_btts.roc_auc,    lr.cal_btts.roc_auc),
            ("BTTS",         "Brier ↓",   lr.raw_btts.brier,      lr.cal_btts.brier),
            ("Over 2.5",     "Accuracy",  lr.raw_ou.accuracy,     lr.cal_ou.accuracy),
            ("Over 2.5",     "ROC AUC",   lr.raw_ou.roc_auc,      lr.cal_ou.roc_auc),
            ("Over 2.5",     "Brier ↓",   lr.raw_ou.brier,        lr.cal_ou.brier),
        ]
        for model, metric, raw, cal in rows:
            delta = cal - raw
            # For Brier, lower is better so negative delta is improvement
            improved = (delta < 0) if "Brier" in metric else (delta > 0)
            sign = ("↑" if improved else "↓") if abs(delta) > 0.001 else " "
            print(f"  {model:<14} {metric:<10} {raw:>8.3f}  {cal:>11.3f}  {delta:>+7.3f} {sign}")

        # ── Confidence-stratified accuracy (calibrated) ───────────────────────
        print(f"\n  Confidence-Stratified Result Accuracy (calibrated model)")
        print(f"  {'Threshold':>10}  {'N':>6}  {'Accuracy':>9}  {'vs overall':>11}")
        for thresh, (n, acc) in sorted(lr.confidence_accuracy.items()):
            delta = acc - lr.cal_result.accuracy
            print(f"  {thresh:>10.0%}  {n:>6}  {acc:>9.3f}  {delta:>+10.3f}")

        # ── Calibration: raw vs calibrated ────────────────────────────────────
        print(f"\n  Result Calibration — Gap = Actual − Predicted  (closer to 0 is better)")
        print(f"  {'Bin':>12}  {'Raw pred':>9}  {'Raw gap':>8}  {'Cal pred':>9}  {'Cal gap':>8}  {'N':>5}")
        raw_cal_by_bin  = {r['bin']: r for r in lr.raw_result.calibration}
        cal_cal_by_bin  = {r['bin']: r for r in lr.cal_result.calibration}
        all_bins = sorted(set(raw_cal_by_bin) | set(cal_cal_by_bin))
        for b in all_bins:
            raw_row = raw_cal_by_bin.get(b)
            cal_row = cal_cal_by_bin.get(b)
            if raw_row and cal_row:
                rg = cal_row['actual'] - raw_row['predicted']
                cg = cal_row['actual'] - cal_row['predicted']
                print(f"  {b:>12}  {raw_row['predicted']:>9.3f}  {rg:>+8.3f}  {cal_row['predicted']:>9.3f}  {cg:>+8.3f}  {cal_row['n']:>5}")

        print(f"\n  BTTS Calibration")
        print(f"  {'Bin':>12}  {'Raw pred':>9}  {'Raw gap':>8}  {'Cal pred':>9}  {'Cal gap':>8}  {'N':>5}")
        raw_btts_by_bin = {r['bin']: r for r in lr.raw_btts.calibration}
        cal_btts_by_bin = {r['bin']: r for r in lr.cal_btts.calibration}
        all_bins = sorted(set(raw_btts_by_bin) | set(cal_btts_by_bin))
        for b in all_bins:
            raw_row = raw_btts_by_bin.get(b)
            cal_row = cal_btts_by_bin.get(b)
            if raw_row and cal_row:
                rg = cal_row['actual'] - raw_row['predicted']
                cg = cal_row['actual'] - cal_row['predicted']
                print(f"  {b:>12}  {raw_row['predicted']:>9.3f}  {rg:>+8.3f}  {cal_row['predicted']:>9.3f}  {cg:>+8.3f}  {cal_row['n']:>5}")

    print(f"\n{'='*70}\n")


# ── Internal ──────────────────────────────────────────────────────────────────

def _backtest_league(
    db: Session,
    league: str,
    train_seasons: list[int],
    test_season: int,
) -> LeagueReport | None:
    # ── Build training data ───────────────────────────────────────────────────
    train_df = build_training_dataset(db, leagues=[league])
    # Filter to training seasons only
    train_matches = (
        db.query(Match)
        .filter(Match.league == league, Match.season.in_(train_seasons), Match.status == MatchStatus.FINISHED)
        .all()
    )
    train_ids = {m.id for m in train_matches}
    train_df  = train_df[train_df["match_id"].isin(train_ids)]

    if len(train_df) < 100:
        logger.warning("%s — not enough training data (%d rows)", league, len(train_df))
        return None

    # ── Build test data ───────────────────────────────────────────────────────
    test_matches = (
        db.query(Match)
        .filter(Match.league == league, Match.season == test_season, Match.status == MatchStatus.FINISHED)
        .order_by(Match.utc_date)
        .all()
    )

    if not test_matches:
        logger.warning("%s — no test matches for season %d", league, test_season)
        return None

    # Build features for test matches — uses only data available before each match
    test_rows = []
    for m in test_matches:
        if m.result is None:
            continue
        feats = build_features(db, m)
        feats["match_id"]     = m.id
        feats["result_label"] = {"HOME": 0, "DRAW": 1, "AWAY": 2}[m.result.value]
        feats["btts_label"]   = int((m.home_score or 0) > 0 and (m.away_score or 0) > 0)
        feats["over25_label"] = int(((m.home_score or 0) + (m.away_score or 0)) > 2)
        test_rows.append(feats)

    if not test_rows:
        return None

    test_df = pd.DataFrame(test_rows)

    X_train = train_df[FEATURE_COLS]
    X_test  = test_df[FEATURE_COLS]
    y_result = test_df["result_label"].values
    y_btts   = test_df["btts_label"].values
    y_ou     = test_df["over25_label"].values

    # ── Recency weights (training set only) ──────────────────────────────────
    weights = _recency_weights(train_df["utc_date"])

    # ── Train: calibrated without weights vs calibrated with recency weights ──
    raw_result_model = _train_multiclass(X_train, train_df["result_label"], calibrate=False)
    cal_result_model = _train_multiclass(X_train, train_df["result_label"], calibrate=True, weights=weights)
    raw_btts_model   = _train_binary(X_train, train_df["btts_label"],   calibrate=False)
    cal_btts_model   = _train_binary(X_train, train_df["btts_label"],   calibrate=True, weights=weights)
    raw_ou_model     = _train_binary(X_train, train_df["over25_label"], calibrate=False)
    cal_ou_model     = _train_binary(X_train, train_df["over25_label"], calibrate=True, weights=weights)

    lr = LeagueReport(
        league     = league,
        train_rows = len(train_df),
        test_rows  = len(test_df),
        raw_result = _eval_multiclass(raw_result_model, X_test, y_result),
        cal_result = _eval_multiclass(cal_result_model, X_test, y_result),
        raw_btts   = _eval_binary(raw_btts_model, X_test, y_btts),
        cal_btts   = _eval_binary(cal_btts_model, X_test, y_btts),
        raw_ou     = _eval_binary(raw_ou_model,   X_test, y_ou),
        cal_ou     = _eval_binary(cal_ou_model,   X_test, y_ou),
    )

    # ── Confidence-stratified accuracy (calibrated model) ─────────────────────
    cal_proba = cal_result_model.predict_proba(X_test)
    cal_preds = cal_result_model.predict(X_test)
    max_proba = cal_proba.max(axis=1)
    for thresh in CONFIDENCE_THRESHOLDS:
        mask = max_proba >= thresh
        n    = int(mask.sum())
        if n > 0:
            acc = float(accuracy_score(y_result[mask], cal_preds[mask]))
            lr.confidence_accuracy[thresh] = (n, acc)

    return lr


def _eval_multiclass(model, X_test, y_true) -> ModelMetrics:
    proba = model.predict_proba(X_test)
    preds = model.predict(X_test)
    brier = float(np.mean([
        brier_score_loss((y_true == c).astype(int), proba[:, c]) for c in range(3)
    ]))
    predicted_class_proba = proba[np.arange(len(y_true)), preds]
    return ModelMetrics(
        accuracy    = float(accuracy_score(y_true, preds)),
        roc_auc     = float(roc_auc_score(y_true, proba, multi_class="ovr", average="macro")),
        brier       = brier,
        calibration = _calibration_bins(predicted_class_proba, (y_true == preds).astype(int)),
    )


def _eval_binary(model, X_test, y_true) -> ModelMetrics:
    proba = model.predict_proba(X_test)[:, 1]
    preds = model.predict(X_test)
    return ModelMetrics(
        accuracy    = float(accuracy_score(y_true, preds)),
        roc_auc     = float(roc_auc_score(y_true, proba)),
        brier       = float(brier_score_loss(y_true, proba)),
        calibration = _calibration_bins(proba, y_true),
    )


def _calibration_bins(proba: np.ndarray, actual: np.ndarray) -> list[dict]:
    rows = []
    for lo, hi in zip(CALIBRATION_BINS[:-1], CALIBRATION_BINS[1:]):
        mask = (proba >= lo) & (proba < hi)
        n    = int(mask.sum())
        if n == 0:
            continue
        rows.append({
            "bin":       f"{lo:.0%}–{hi:.0%}",
            "predicted": float(proba[mask].mean()),
            "actual":    float(actual[mask].mean()),
            "n":         n,
        })
    return rows


def _recency_weights(dates: pd.Series, half_life_days: int = 365) -> np.ndarray:
    dates_utc = pd.to_datetime(dates, utc=True)
    latest    = dates_utc.max()
    days_ago  = (latest - dates_utc).dt.total_seconds() / 86400
    lam       = np.log(2) / half_life_days
    return np.exp(-lam * days_ago.values).astype(np.float32)


def _train_multiclass(
    X: pd.DataFrame, y: pd.Series,
    calibrate: bool = True, weights: np.ndarray | None = None,
):
    idx = np.arange(len(X))
    idx_train, idx_cal = train_test_split(idx, test_size=0.25, random_state=42, stratify=y)
    X_tr, y_tr = X.iloc[idx_train], y.iloc[idx_train]
    X_cl, y_cl = X.iloc[idx_cal],   y.iloc[idx_cal]
    w_tr = weights[idx_train] if weights is not None else None
    w_cl = weights[idx_cal]   if weights is not None else None

    base = XGBClassifier(
        objective="multi:softprob", num_class=3, eval_metric="mlogloss",
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42, verbosity=0,
    )
    base.fit(X_tr, y_tr, sample_weight=w_tr)
    if not calibrate:
        return base
    cal = CalibratedClassifierCV(base, method="isotonic", cv="prefit")
    cal.fit(X_cl, y_cl, sample_weight=w_cl)
    return cal


def _train_binary(
    X: pd.DataFrame, y: pd.Series,
    calibrate: bool = True, weights: np.ndarray | None = None,
):
    idx = np.arange(len(X))
    idx_train, idx_cal = train_test_split(idx, test_size=0.25, random_state=42, stratify=y)
    X_tr, y_tr = X.iloc[idx_train], y.iloc[idx_train]
    X_cl, y_cl = X.iloc[idx_cal],   y.iloc[idx_cal]
    w_tr = weights[idx_train] if weights is not None else None
    w_cl = weights[idx_cal]   if weights is not None else None

    base = XGBClassifier(
        objective="binary:logistic", eval_metric="logloss",
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42, verbosity=0,
    )
    base.fit(X_tr, y_tr, sample_weight=w_tr)
    if not calibrate:
        return base
    cal = CalibratedClassifierCV(base, method="isotonic", cv="prefit")
    cal.fit(X_cl, y_cl, sample_weight=w_cl)
    return cal
