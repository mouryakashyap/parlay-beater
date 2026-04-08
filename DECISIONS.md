# Prediction Model Decisions

Running log of design decisions made during model development.
Each entry captures what was decided, why, and what was explicitly left open.

---

## D1 — Rolling window: last 5 matches, scoped to same competition

**Decision:** Form features (points, goals scored/conceded, BTTS rate, over-2.5 rate) use
the last 5 finished matches for each team **within the same competition** as the match being predicted.
H2H features remain cross-competition (last 5 meetings between the two teams, any venue).

**Why:**
- Cup/rotation matches don't reflect league form — a team fielding reserves in a cup pollutes
  their league form signal if not scoped.
- Scoring patterns differ between competitions (Serie A league vs Coppa Italia, for example).
- Architecturally clean for future league expansion: each league's features stay independent.

**Trade-off accepted:**
- Early-season matches (matchday 1–5) will have fewer available league matches.
  The builder defaults to `0.0` for all features when no prior matches exist. The model
  learns this cold-start pattern from training data.
- H2H kept cross-competition intentionally — two newly promoted teams may have only
  met in other competitions historically.

**Status:** Implemented in `ml/features/builder.py` — `_recent_matches()` accepts a `league`
parameter. Model needs retraining after this change.

---

## D2 — Additional signals: xG first, odds next, injuries later

**Decision:** Integrate signals in this order:
1. **xG** — low effort, meaningful signal, free via Understat
2. **Odds** — highest predictive value; The Odds API preferred over Kalshi (Kalshi lacks PL/PD/SA coverage)
3. **Injuries** — API-Football free tier (100 req/day); pursue after odds

**Kalshi ruled out** for odds — their market coverage is US-focused and doesn't include matchday fixtures for PL/PD/SA.

**xG source:** Understat.com via `understatapi` (no key required). Covers EPL, La Liga, Serie A, Bundesliga, Ligue 1 from 2014/15 onward. Matched to DB records by date ± 1 day + fuzzy team name (threshold 0.6).

**xG impact on model:**
- match_result ROC AUC: 0.643 → 0.655 (+0.012)
- btts/over_under: slight regression (xG less relevant when actual goals are available)

**Status:** xG implemented. `data/ingestion/understat.py` + `app/workers/tasks/xg.py`. Odds and injuries pending.

---

## D3 — Per-league models, no global model fallback

**Decision:** Train separate models per league. Cross-league matches (e.g. Champions League) are not predicted — no global model is maintained.

**Why:**
- PL, La Liga, Serie A have measurably different scoring patterns (SA is low-scoring, PL high-tempo).
- Global model collapses these differences into a single `league_code` feature — too blunt.
- Architecturally clean for expansion: adding BL1/FL1 = backfill data + retrain, no other changes.

**Trade-off accepted:**
- ~1,000 rows per league vs 3,000 rows global. Accepted — league-specific signal outweighs sample size.
- BL1/FL1 produce no predictions until match data is backfilled for those leagues.

**Model version format:** `v{date}-{time}:{league}` (e.g. `v20260408-0415:PL`)

**Status:** Implemented. `ModelRegistry` has `league` column (migration `c43ee701a64b`).
Trainer loops per league. Predictor loads league-specific models and skips unrecognised leagues.

---

## D4 — Probability calibration: isotonic regression (implemented)

**Decision:** Wrap each XGBoost model with a `CalibratedClassifierCV(method='isotonic', cv='prefit')` calibrator trained on a held-out 20% calibration split. The calibrated model is what gets saved to MLflow and served.

**Why isotonic over Platt scaling:** Platt scaling assumes an S-shaped miscalibration curve — isotonic regression makes no shape assumption and fits the actual data directly. More flexible for our small dataset.

**Backtest results (train=2023-24, test=2025):**
- Brier score improved on every model in every league (lower = better)
- PD match result at confidence ≥ 50%: 71.0% accuracy (vs 45.8% baseline)
- SA match result at confidence ≥ 60%: 68.2% accuracy
- BTTS overconfidence corrected: Atlético vs Celta went from 79.7% → 57.4%

**Data split:** 60% train XGBoost / 20% fit calibrator / 20% validate

**Status:** Implemented. All served predictions now pass through the calibrator.

---

## D5 — Recency weighting: exponential decay, half-life 365 days (implemented)

**Decision:** Weight training samples by exponential decay based on match date.
Most recent match gets weight 1.0; a match 365 days ago gets weight 0.5; 2023 matches
get ~15–16% of the weight of today's matches.

Formula: `weight = exp(-ln(2) / 365 × days_ago)`

Applied to both XGBoost `.fit(sample_weight=w_train)` and calibrator `.fit(sample_weight=w_cal)`.

**Why:**
- Football evolves — squad changes, managerial shifts, tactical shifts between seasons.
- 2023 data is useful context but should not override 2025 form signals.
- A half-life of 365 days keeps a full season of prior history meaningfully weighted
  while still down-weighting older data.

**Backtest results (train=2023–2024, test=2025 matches, confidence-stratified):**
- PL: at ≥60% confidence → 61.3% accuracy (vs 43.1% overall)
- PD: at ≥60% confidence → 72.7% accuracy (vs 48.2% overall)
- SA: at ≥60% confidence → 76.2% accuracy (vs 46.0% overall)

Brier scores improved across all leagues vs the raw unweighted baseline.

**Trade-off accepted:**
- Half-life is a hyperparameter — 365 days was chosen as a reasonable default
  (one full season). Could be tuned per league if data volume supports it.

**Status:** Implemented in `ml/training/trainer.py` — `_recency_weights()` + `RECENCY_HALF_LIFE_DAYS = 365`.
All 223 current predictions regenerated with the new models.
