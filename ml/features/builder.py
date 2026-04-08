"""
Feature builder — computes per-match ML features from historical match data.

All features are computed using only matches played BEFORE the target match date
so there is no data leakage between train and test.

Main entry points:
  build_features(db, match)          → dict  (single match, for serving)
  build_training_dataset(db, league) → pd.DataFrame  (all finished matches)
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.models.match import Match, MatchStatus, MatchStats

WINDOW = 5          # rolling window: last N matches used for form features
LEAGUE_CODES = {"PL": 0, "PD": 1, "SA": 2, "BL1": 3, "FL1": 4}

# Canonical feature column order — used by both trainer and predictor
FEATURE_COLS = [
    "home_form_pts", "away_form_pts",
    "home_goals_scored_avg", "away_goals_scored_avg",
    "home_goals_conceded_avg", "away_goals_conceded_avg",
    "home_venue_goals_scored_avg", "away_venue_goals_scored_avg",
    "home_venue_goals_conceded_avg", "away_venue_goals_conceded_avg",
    "h2h_home_win_rate", "h2h_draw_rate", "h2h_away_win_rate",
    "home_btts_rate", "away_btts_rate",
    "home_over25_rate", "away_over25_rate",
    "home_xg_scored_avg", "away_xg_scored_avg",
    "home_xg_conceded_avg", "away_xg_conceded_avg",
    "matchday", "league_code",
    "home_matches_available", "away_matches_available",
]


# ── Public API ────────────────────────────────────────────────────────────────

def build_features(db: Session, match: Match) -> dict:
    """
    Build a flat feature dict for a single match.
    Works for both upcoming (status=SCHEDULED) and finished matches.
    Uses only matches played strictly before match.utc_date.
    Form features are scoped to the same competition (match.league) so that
    cup/other-league matches don't pollute league form signals.
    """
    cutoff = match.utc_date
    home_id = match.home_team_id
    away_id = match.away_team_id
    league = match.league

    home_recent   = _recent_matches(db, home_id, cutoff, n=WINDOW, league=league)
    away_recent   = _recent_matches(db, away_id, cutoff, n=WINDOW, league=league)
    home_at_home  = _recent_matches(db, home_id, cutoff, n=WINDOW, venue="home", league=league)
    away_at_away  = _recent_matches(db, away_id, cutoff, n=WINDOW, venue="away", league=league)
    h2h           = _h2h_matches(db, home_id, away_id, cutoff, n=WINDOW)

    features = {
        # ── Overall form ──────────────────────────────────────────────────────
        "home_form_pts":           _avg_points(home_recent, home_id),
        "away_form_pts":           _avg_points(away_recent, away_id),
        "home_goals_scored_avg":   _avg_goals_scored(home_recent, home_id),
        "away_goals_scored_avg":   _avg_goals_scored(away_recent, away_id),
        "home_goals_conceded_avg": _avg_goals_conceded(home_recent, home_id),
        "away_goals_conceded_avg": _avg_goals_conceded(away_recent, away_id),

        # ── Venue-split form ──────────────────────────────────────────────────
        "home_venue_goals_scored_avg":   _avg_goals_scored(home_at_home, home_id),
        "away_venue_goals_scored_avg":   _avg_goals_scored(away_at_away, away_id),
        "home_venue_goals_conceded_avg": _avg_goals_conceded(home_at_home, home_id),
        "away_venue_goals_conceded_avg": _avg_goals_conceded(away_at_away, away_id),

        # ── Head-to-head ──────────────────────────────────────────────────────
        "h2h_home_win_rate": _h2h_win_rate(h2h, home_id),
        "h2h_draw_rate":     _h2h_draw_rate(h2h),
        "h2h_away_win_rate": _h2h_win_rate(h2h, away_id),

        # ── BTTS & over 2.5 rates ─────────────────────────────────────────────
        "home_btts_rate":    _btts_rate(home_recent),
        "away_btts_rate":    _btts_rate(away_recent),
        "home_over25_rate":  _over25_rate(home_recent),
        "away_over25_rate":  _over25_rate(away_recent),

        # ── xG form (last 5 league matches, None → 0.0 if no stats available) ──
        "home_xg_scored_avg":   _avg_xg_scored(db, home_recent, home_id),
        "away_xg_scored_avg":   _avg_xg_scored(db, away_recent, away_id),
        "home_xg_conceded_avg": _avg_xg_conceded(db, home_recent, home_id),
        "away_xg_conceded_avg": _avg_xg_conceded(db, away_recent, away_id),

        # ── Match context ─────────────────────────────────────────────────────
        "matchday":          match.matchday or 0,
        "league_code":       LEAGUE_CODES.get(match.league, -1),

        # ── Sample sizes (used as model reliability signal) ───────────────────
        "home_matches_available": len(home_recent),
        "away_matches_available": len(away_recent),
    }

    return features


def build_training_dataset(db: Session, leagues: list[str] | None = None) -> pd.DataFrame:
    """
    Build a DataFrame of features + labels for all finished matches.
    One row per match. Suitable for direct use with sklearn / XGBoost.

    Labels:
      result_label  — 0=HOME, 1=DRAW, 2=AWAY
      btts_label    — 1 if both teams scored
      over25_label  — 1 if total goals > 2
    """
    q = db.query(Match).filter(Match.status == MatchStatus.FINISHED)
    if leagues:
        q = q.filter(Match.league.in_(leagues))
    matches = q.order_by(Match.utc_date).all()

    rows = []
    for m in matches:
        if m.home_score is None or m.away_score is None or m.result is None:
            continue

        feats = build_features(db, m)

        feats["match_id"]     = m.id
        feats["utc_date"]     = m.utc_date          # kept for recency weighting in trainer
        feats["result_label"] = {"HOME": 0, "DRAW": 1, "AWAY": 2}[m.result.value]
        feats["btts_label"]   = int(m.home_score > 0 and m.away_score > 0)
        feats["over25_label"] = int((m.home_score + m.away_score) > 2)

        rows.append(feats)

    return pd.DataFrame(rows)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _recent_matches(
    db: Session,
    team_id: int,
    before: object,
    n: int,
    venue: str | None = None,   # "home" | "away" | None (both)
    league: str | None = None,  # scope to a specific competition
) -> list[Match]:
    """Return the N most recent FINISHED matches for a team before a given date."""
    q = (
        db.query(Match)
        .filter(Match.status == MatchStatus.FINISHED)
        .filter(Match.utc_date < before)
    )
    if league:
        q = q.filter(Match.league == league)
    if venue == "home":
        q = q.filter(Match.home_team_id == team_id)
    elif venue == "away":
        q = q.filter(Match.away_team_id == team_id)
    else:
        q = q.filter(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    return q.order_by(Match.utc_date.desc()).limit(n).all()


def _h2h_matches(
    db: Session, home_id: int, away_id: int, before: object, n: int
) -> list[Match]:
    """Return the N most recent finished H2H matches between two teams (either venue)."""
    return (
        db.query(Match)
        .filter(Match.status == MatchStatus.FINISHED)
        .filter(Match.utc_date < before)
        .filter(
            or_(
                and_(Match.home_team_id == home_id, Match.away_team_id == away_id),
                and_(Match.home_team_id == away_id, Match.away_team_id == home_id),
            )
        )
        .order_by(Match.utc_date.desc())
        .limit(n)
        .all()
    )


def _avg_points(matches: list[Match], team_id: int) -> float:
    """Average points per game (3=win, 1=draw, 0=loss). 0.0 if no matches."""
    if not matches:
        return 0.0
    pts = []
    for m in matches:
        if m.result is None:
            continue
        r = m.result.value
        if m.home_team_id == team_id:
            pts.append(3 if r == "HOME" else (1 if r == "DRAW" else 0))
        else:
            pts.append(3 if r == "AWAY" else (1 if r == "DRAW" else 0))
    return sum(pts) / len(pts) if pts else 0.0


def _avg_goals_scored(matches: list[Match], team_id: int) -> float:
    if not matches:
        return 0.0
    goals = []
    for m in matches:
        if m.home_score is None:
            continue
        goals.append(m.home_score if m.home_team_id == team_id else m.away_score)
    return sum(goals) / len(goals) if goals else 0.0


def _avg_goals_conceded(matches: list[Match], team_id: int) -> float:
    if not matches:
        return 0.0
    goals = []
    for m in matches:
        if m.home_score is None:
            continue
        goals.append(m.away_score if m.home_team_id == team_id else m.home_score)
    return sum(goals) / len(goals) if goals else 0.0


def _h2h_win_rate(matches: list[Match], team_id: int) -> float:
    if not matches:
        return 0.0
    wins = sum(
        1 for m in matches
        if m.result is not None and (
            (m.home_team_id == team_id and m.result.value == "HOME") or
            (m.away_team_id == team_id and m.result.value == "AWAY")
        )
    )
    return wins / len(matches)


def _h2h_draw_rate(matches: list[Match]) -> float:
    if not matches:
        return 0.0
    return sum(1 for m in matches if m.result is not None and m.result.value == "DRAW") / len(matches)


def _btts_rate(matches: list[Match]) -> float:
    """Fraction of matches where both teams scored."""
    finished = [m for m in matches if m.home_score is not None and m.away_score is not None]
    if not finished:
        return 0.0
    return sum(1 for m in finished if m.home_score > 0 and m.away_score > 0) / len(finished)


def _over25_rate(matches: list[Match]) -> float:
    """Fraction of matches with more than 2 total goals."""
    finished = [m for m in matches if m.home_score is not None and m.away_score is not None]
    if not finished:
        return 0.0
    return sum(1 for m in finished if (m.home_score + m.away_score) > 2) / len(finished)


def _avg_xg_scored(db: Session, matches: list[Match], team_id: int) -> float:
    """Average xG scored per game from MatchStats. Falls back to 0.0 if no stats."""
    if not matches:
        return 0.0
    values = []
    for m in matches:
        stats = db.query(MatchStats).filter(MatchStats.match_id == m.id).first()
        if stats is None:
            continue
        xg = stats.xg_home if m.home_team_id == team_id else stats.xg_away
        if xg is not None:
            values.append(xg)
    return sum(values) / len(values) if values else 0.0


def _avg_xg_conceded(db: Session, matches: list[Match], team_id: int) -> float:
    """Average xG conceded per game from MatchStats. Falls back to 0.0 if no stats."""
    if not matches:
        return 0.0
    values = []
    for m in matches:
        stats = db.query(MatchStats).filter(MatchStats.match_id == m.id).first()
        if stats is None:
            continue
        xg = stats.xg_away if m.home_team_id == team_id else stats.xg_home
        if xg is not None:
            values.append(xg)
    return sum(values) / len(values) if values else 0.0
