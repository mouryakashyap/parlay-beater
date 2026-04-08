"""
Understat xG ingestion — fetches expected goals data and links it to our match records.

Understat provides match-level xG for EPL, La Liga, Serie A, Bundesliga, Ligue 1
going back to the 2014/15 season. No API key required.

Public functions:
  fetch_xg_for_season(league, season) → list[XgMatchData]
  backfill_xg(db, leagues, seasons)   → int (rows upserted)
  update_recent_xg(db, leagues)       → int (rows upserted, last 30 days)

Matching strategy:
  Understat and football-data.org use different team names.
  We match on (date ± 1 day) + fuzzy team name to find the right DB record.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models.match import Match, MatchStatus, MatchStats

logger = logging.getLogger(__name__)

# Map our league codes → Understat league slugs
LEAGUE_MAP = {
    "PL":  "EPL",
    "PD":  "La_Liga",
    "SA":  "Serie_A",
    "BL1": "Bundesliga",
    "FL1": "Ligue_1",
}

FUZZY_THRESHOLD = 0.6  # min similarity to accept a team name match


@dataclass
class XgMatchData:
    understat_id: str
    league: str
    season: int
    utc_date: datetime
    home_team: str   # Understat name
    away_team: str   # Understat name
    xg_home: float
    xg_away: float


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_xg_for_season(league: str, season: int) -> list[XgMatchData]:
    """
    Fetch all finished match xG records from Understat for a given league/season.
    Returns empty list if the league is not supported or no data found.
    """
    understat_league = LEAGUE_MAP.get(league)
    if not understat_league:
        logger.warning("League %s not supported by Understat — skipping", league)
        return []

    try:
        from understatapi import UnderstatClient
        with UnderstatClient() as client:
            raw = client.league(understat_league).get_match_data(season=str(season))
    except Exception:
        logger.exception("Failed to fetch Understat data for %s %d", league, season)
        return []

    results = []
    for m in raw:
        try:
            # Only process finished matches (Understat marks these with isResult=True)
            if not m.get("isResult"):
                continue

            xg_h = float(m.get("xG", {}).get("h", 0) or 0)
            xg_a = float(m.get("xG", {}).get("a", 0) or 0)

            # Understat datetime is in Moscow time (UTC+3) — normalise to UTC
            raw_dt = m.get("datetime", "")
            utc_date = _parse_understat_datetime(raw_dt)
            if utc_date is None:
                continue

            results.append(XgMatchData(
                understat_id = str(m["id"]),
                league       = league,
                season       = season,
                utc_date     = utc_date,
                home_team    = m["h"]["title"],
                away_team    = m["a"]["title"],
                xg_home      = xg_h,
                xg_away      = xg_a,
            ))
        except Exception:
            logger.warning("Skipping malformed Understat record id=%s", m.get("id"))

    logger.info("Understat %s %d — %d xG records fetched", league, season, len(results))
    return results


def backfill_xg(
    db: Session,
    leagues: list[str],
    seasons: list[int],
) -> int:
    """Backfill xG for multiple leagues and seasons. Returns total rows upserted."""
    total = 0
    for season in seasons:
        for league in leagues:
            records = fetch_xg_for_season(league, season)
            upserted = _upsert_xg_records(db, records)
            total += upserted
            logger.info("  %s %d → %d xG rows upserted", league, season, upserted)
    return total


def update_recent_xg(db: Session, leagues: list[str], days_back: int = 30) -> int:
    """
    Refresh xG for recently finished matches (rolling update).
    Fetches the current season for each league and upserts.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    current_season = now.year if now.month >= 8 else now.year - 1
    return backfill_xg(db, leagues, [current_season])


# ── Internal helpers ──────────────────────────────────────────────────────────

def _parse_understat_datetime(raw: str) -> datetime | None:
    """
    Understat datetimes look like '2024-08-17 17:00:00'.
    They are in Moscow time (UTC+3). Convert to UTC.
    """
    if not raw:
        return None
    try:
        # Parse as naive, treat as Moscow time (UTC+3), convert to UTC
        from datetime import timezone as tz
        from zoneinfo import ZoneInfo
        moscow = ZoneInfo("Europe/Moscow")
        naive = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        return naive.replace(tzinfo=moscow).astimezone(timezone.utc)
    except Exception:
        logger.warning("Could not parse Understat datetime: %s", raw)
        return None


def _upsert_xg_records(db: Session, records: list[XgMatchData]) -> int:
    """
    Match each XgMatchData to a DB Match record and upsert MatchStats.
    Returns number of rows upserted.
    """
    upserted = 0
    for rec in records:
        match = _find_db_match(db, rec)
        if match is None:
            continue

        existing = db.query(MatchStats).filter(MatchStats.match_id == match.id).first()
        if existing:
            existing.xg_home = rec.xg_home
            existing.xg_away = rec.xg_away
        else:
            db.add(MatchStats(
                match_id = match.id,
                xg_home  = rec.xg_home,
                xg_away  = rec.xg_away,
            ))
        upserted += 1

    db.commit()
    return upserted


def _find_db_match(db: Session, rec: XgMatchData) -> Match | None:
    """
    Find the DB Match record that corresponds to an Understat record.
    Strategy: find all matches ±1 day in the same league, then pick the
    one with the highest combined fuzzy similarity on team names.
    """
    window_start = rec.utc_date - timedelta(hours=26)
    window_end   = rec.utc_date + timedelta(hours=26)

    candidates = (
        db.query(Match)
        .filter(Match.league == rec.league)
        .filter(Match.status == MatchStatus.FINISHED)
        .filter(Match.utc_date >= window_start)
        .filter(Match.utc_date <= window_end)
        .all()
    )

    if not candidates:
        return None

    best_match = None
    best_score = 0.0

    for m in candidates:
        home_name = m.home_team.name if m.home_team else ""
        away_name = m.away_team.name if m.away_team else ""

        score = (
            _similarity(rec.home_team, home_name) +
            _similarity(rec.away_team, away_name)
        ) / 2

        if score > best_score:
            best_score = score
            best_match = m

    if best_score < FUZZY_THRESHOLD:
        logger.debug(
            "No confident match for %s vs %s on %s (best=%.2f)",
            rec.home_team, rec.away_team, rec.utc_date.date(), best_score,
        )
        return None

    return best_match


def _similarity(a: str, b: str) -> float:
    """Case-insensitive fuzzy string similarity (0–1)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()
