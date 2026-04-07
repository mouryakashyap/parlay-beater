"""
Football data ingestion client — wraps football-data.org API v4.

Public functions:
  fetch_upcoming(leagues, days_ahead)      → list[FixtureData]
  fetch_finished(leagues, days_back)       → list[FixtureData]
  fetch_season(league, season)             → list[FixtureData]  ← historical backfill

When USE_MOCK_DATA=true, all functions return deterministic fake data.

football-data.org docs: https://www.football-data.org/documentation/quickstart
Rate limit: 10 req/min on free tier.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

_BASE_URL  = "https://api.football-data.org/v4"
_RATE_PAUSE = 7  # seconds between requests to stay safely within 10 req/min

# Status strings as returned by the football-data.org API → our MatchStatus
_STATUS_MAP = {
    "SCHEDULED": "SCHEDULED",
    "TIMED":     "SCHEDULED",
    "IN_PLAY":   "LIVE",
    "PAUSED":    "LIVE",
    "FINISHED":  "FINISHED",
    "POSTPONED": "POSTPONED",
    "CANCELLED": "POSTPONED",
    "SUSPENDED": "POSTPONED",
}


@dataclass
class TeamData:
    api_id: int
    name: str
    short_name: str | None
    league: str
    country: str | None


@dataclass
class FixtureData:
    api_id: int
    league: str
    season: int | None        # year the season started, e.g. 2024 for 2024-25
    matchday: int | None
    utc_date: datetime
    status: str               # normalised to our MatchStatus strings
    home_team: TeamData
    away_team: TeamData
    home_score: int | None
    away_score: int | None
    result: str | None        # HOME | DRAW | AWAY — None until FINISHED


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_upcoming(leagues: list[str], days_ahead: int = 7) -> list[FixtureData]:
    """Return SCHEDULED matches across all target leagues for the next N days."""
    from app.core.config import settings

    if settings.USE_MOCK_DATA:
        return _mock_upcoming(leagues, days_ahead)

    fixtures: list[FixtureData] = []
    date_from = datetime.now(timezone.utc).date()
    date_to   = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).date()

    for i, league in enumerate(leagues):
        if i > 0:
            time.sleep(_RATE_PAUSE)
        try:
            data = _get(
                f"/competitions/{league}/matches",
                params={"status": "SCHEDULED,TIMED", "dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()},
                api_key=settings.FOOTBALL_DATA_API_KEY,
            )
            season = _extract_season(data)
            fixtures.extend(_parse_matches(data.get("matches", []), league, season))
        except Exception:
            logger.exception("Failed to fetch upcoming fixtures for league %s", league)

    return fixtures


def fetch_finished(leagues: list[str], days_back: int = 3) -> list[FixtureData]:
    """Return FINISHED matches across all target leagues for the last N days."""
    from app.core.config import settings

    if settings.USE_MOCK_DATA:
        return _mock_finished(leagues)

    fixtures: list[FixtureData] = []
    date_from = (datetime.now(timezone.utc) - timedelta(days=days_back)).date()
    date_to   = datetime.now(timezone.utc).date()

    for i, league in enumerate(leagues):
        if i > 0:
            time.sleep(_RATE_PAUSE)
        try:
            data = _get(
                f"/competitions/{league}/matches",
                params={"status": "FINISHED", "dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()},
                api_key=settings.FOOTBALL_DATA_API_KEY,
            )
            season = _extract_season(data)
            fixtures.extend(_parse_matches(data.get("matches", []), league, season))
        except Exception:
            logger.exception("Failed to fetch finished matches for league %s", league)

    return fixtures


def fetch_season(league: str, season: int) -> list[FixtureData]:
    """
    Fetch all matches for a completed season.
    Used by the historical backfill task.

    season = year the season started (e.g. 2023 for the 2023-24 season).
    Returns all matches regardless of status so partially-played seasons work too.
    """
    from app.core.config import settings

    if settings.USE_MOCK_DATA:
        return _mock_season(league, season)

    try:
        data = _get(
            f"/competitions/{league}/matches",
            params={"season": season},
            api_key=settings.FOOTBALL_DATA_API_KEY,
        )
        return _parse_matches(data.get("matches", []), league, season)
    except Exception:
        logger.exception("Failed to fetch season %d for league %s", season, league)
        return []


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get(path: str, params: dict, api_key: str) -> dict:
    with httpx.Client(base_url=_BASE_URL, timeout=15) as client:
        resp = client.get(path, params=params, headers={"X-Auth-Token": api_key})
        if resp.status_code == 429:
            logger.warning("Rate limited — sleeping 65s then retrying")
            time.sleep(65)
            resp = client.get(path, params=params, headers={"X-Auth-Token": api_key})
        resp.raise_for_status()
        return resp.json()


def _extract_season(data: dict) -> int | None:
    """Pull the season year out of a competition response envelope."""
    filters = data.get("filters", {})
    season = filters.get("season")
    if season is not None:
        return int(season)
    # fallback: infer from current date
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 8 else now.year - 1


def _parse_matches(raw_matches: list[dict], league: str, season: int | None) -> list[FixtureData]:
    fixtures = []
    for m in raw_matches:
        try:
            fixtures.append(_parse_match(m, league, season))
        except Exception:
            logger.warning("Skipping malformed match payload: %s", m.get("id"))
    return fixtures


def _parse_match(m: dict, league: str, season: int | None) -> FixtureData:
    raw_status = m.get("status", "SCHEDULED")
    status = _STATUS_MAP.get(raw_status, "SCHEDULED")

    score = m.get("score", {}).get("fullTime", {})
    home_score = score.get("home")
    away_score = score.get("away")
    result = _derive_result(home_score, away_score) if status == "FINISHED" else None

    home = m["homeTeam"]
    away = m["awayTeam"]
    area_name = m.get("area", {}).get("name")

    return FixtureData(
        api_id    = m["id"],
        league    = league,
        season    = season,
        matchday  = m.get("matchday"),
        utc_date  = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")),
        status    = status,
        home_team = TeamData(
            api_id     = home["id"],
            name       = home["name"],
            short_name = home.get("shortName") or home.get("tla"),
            league     = league,
            country    = area_name,
        ),
        away_team = TeamData(
            api_id     = away["id"],
            name       = away["name"],
            short_name = away.get("shortName") or away.get("tla"),
            league     = league,
            country    = area_name,
        ),
        home_score = home_score,
        away_score = away_score,
        result     = result,
    )


def _derive_result(home: int | None, away: int | None) -> str | None:
    if home is None or away is None:
        return None
    if home > away:
        return "HOME"
    if away > home:
        return "AWAY"
    return "DRAW"


# ── Mock data ─────────────────────────────────────────────────────────────────

_MOCK_TEAMS: dict[str, list[tuple[int, str, str]]] = {
    "PL": [
        (65,  "Manchester City FC",     "Man City"),
        (66,  "Manchester United FC",   "Man Utd"),
        (73,  "Tottenham Hotspur FC",   "Spurs"),
        (57,  "Arsenal FC",             "Arsenal"),
        (61,  "Chelsea FC",             "Chelsea"),
        (64,  "Liverpool FC",           "Liverpool"),
    ],
    "PD": [
        (86,  "Real Madrid CF",         "Real Madrid"),
        (81,  "FC Barcelona",           "Barcelona"),
        (78,  "Club Atlético de Madrid","Atlético"),
        (558, "RC Celta de Vigo",       "Celta Vigo"),
    ],
    "SA": [
        (108, "FC Internazionale Milano","Inter"),
        (109, "Juventus FC",             "Juventus"),
        (113, "AC Milan",                "AC Milan"),
        (107, "AS Roma",                 "Roma"),
    ],
    "BL1": [
        (5,   "FC Bayern München",       "Bayern"),
        (4,   "Borussia Dortmund",       "Dortmund"),
        (3,   "Bayer 04 Leverkusen",     "Leverkusen"),
        (11,  "VfL Wolfsburg",           "Wolfsburg"),
    ],
    "FL1": [
        (524, "Paris Saint-Germain FC",  "PSG"),
        (516, "Olympique de Marseille",  "Marseille"),
        (521, "Olympique Lyonnais",      "Lyon"),
        (519, "Stade Rennais FC",        "Rennes"),
    ],
}

_COUNTRY_MAP = {"PL": "England", "PD": "Spain", "SA": "Italy", "BL1": "Germany", "FL1": "France"}


def _mock_upcoming(leagues: list[str], days_ahead: int) -> list[FixtureData]:
    now = datetime.now(timezone.utc)
    current_season = now.year if now.month >= 8 else now.year - 1
    fixtures = []
    match_id_offset = 90000

    for league in leagues:
        teams = _MOCK_TEAMS.get(league, [])
        country = _COUNTRY_MAP.get(league)
        for i in range(0, len(teams) - 1, 2):
            kickoff = now + timedelta(days=(i // 2) + 1)
            fixtures.append(FixtureData(
                api_id    = match_id_offset + i,
                league    = league,
                season    = current_season,
                matchday  = 30 + i,
                utc_date  = kickoff.replace(hour=15, minute=0, second=0, microsecond=0),
                status    = "SCHEDULED",
                home_team = TeamData(api_id=teams[i][0],   name=teams[i][1],   short_name=teams[i][2],   league=league, country=country),
                away_team = TeamData(api_id=teams[i+1][0], name=teams[i+1][1], short_name=teams[i+1][2], league=league, country=country),
                home_score = None,
                away_score = None,
                result     = None,
            ))
        match_id_offset += 100

    return fixtures


def _mock_finished(leagues: list[str]) -> list[FixtureData]:
    """Uses the same api_ids as _mock_upcoming so resolve_finished_matches can update them."""
    now = datetime.now(timezone.utc)
    current_season = now.year if now.month >= 8 else now.year - 1

    _RESULTS: dict[str, list[tuple]] = {
        "PL": [
            (90000, 65, "Manchester City FC", "Man City",  66, "Manchester United FC", "Man Utd", 3, 1),
            (90002, 73, "Tottenham Hotspur FC", "Spurs",   57, "Arsenal FC",           "Arsenal", 1, 1),
        ],
        "PD": [
            (90100, 86, "Real Madrid CF", "Real Madrid",  81, "FC Barcelona",          "Barcelona", 2, 0),
        ],
        "SA": [
            (90200, 108, "FC Internazionale Milano", "Inter", 109, "Juventus FC",       "Juventus",  2, 1),
        ],
    }

    fixtures = []
    for league in leagues:
        country = _COUNTRY_MAP.get(league)
        for row in _RESULTS.get(league, []):
            mid, h_id, h_name, h_short, a_id, a_name, a_short, hs, as_ = row
            fixtures.append(FixtureData(
                api_id    = mid,
                league    = league,
                season    = current_season,
                matchday  = 30,
                utc_date  = (now - timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0),
                status    = "FINISHED",
                home_team = TeamData(api_id=h_id, name=h_name, short_name=h_short, league=league, country=country),
                away_team = TeamData(api_id=a_id, name=a_name, short_name=a_short, league=league, country=country),
                home_score = hs,
                away_score = as_,
                result     = _derive_result(hs, as_),
            ))

    return fixtures


def _mock_season(league: str, season: int) -> list[FixtureData]:
    """
    Generate a plausible set of finished matches for a historical season.
    Produces round-robin fixtures for all teams in the league with
    deterministic (but varied) scorelines.
    """
    teams = _MOCK_TEAMS.get(league, [])
    country = _COUNTRY_MAP.get(league)
    if not teams:
        return []

    fixtures = []
    # Stable base api_id per league+season so re-runs don't create duplicates
    league_offset = {"PL": 0, "PD": 50000, "SA": 100000}.get(league, 200000)
    season_offset = (season - 2020) * 10000
    base_id = 300000 + league_offset + season_offset

    # Season starts in August of the season year
    season_start = datetime(season, 8, 1, 15, 0, tzinfo=timezone.utc)

    match_num = 0
    for home_i, home in enumerate(teams):
        for away_i, away in enumerate(teams):
            if home_i == away_i:
                continue
            # Deterministic scoreline based on team indices and season
            h_score = (home_i + season) % 4
            a_score = (away_i + season + 1) % 3
            kickoff = season_start + timedelta(weeks=match_num % 38)

            fixtures.append(FixtureData(
                api_id    = base_id + match_num,
                league    = league,
                season    = season,
                matchday  = (match_num % 38) + 1,
                utc_date  = kickoff,
                status    = "FINISHED",
                home_team = TeamData(api_id=home[0], name=home[1], short_name=home[2], league=league, country=country),
                away_team = TeamData(api_id=away[0], name=away[1], short_name=away[2], league=league, country=country),
                home_score = h_score,
                away_score = a_score,
                result     = _derive_result(h_score, a_score),
            ))
            match_num += 1

    return fixtures
