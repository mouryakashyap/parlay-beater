"""
Match repository — all Match/MatchStats/Odds DB queries live here.
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session, joinedload
from app.models.match import Match, MatchStatus


def get_by_id(db: Session, match_id: int) -> Match | None:
    # joinedload fetches home_team and away_team in the same SQL query (avoids N+1)
    return (
        db.query(Match)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(Match.id == match_id)
        .first()
    )


def get_by_api_id(db: Session, api_id: int) -> Match | None:
    """Look up a match by the external football API id — used during ingestion."""
    return db.query(Match).filter(Match.api_id == api_id).first()


def get_upcoming(db: Session, league: str | None = None, days: int = 7) -> list[Match]:
    """Return SCHEDULED matches between now and N days from now."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    q = (
        db.query(Match)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(Match.status == MatchStatus.SCHEDULED)
        .filter(Match.utc_date >= now)
        .filter(Match.utc_date <= cutoff)
        .order_by(Match.utc_date)   # soonest first
    )
    if league:
        q = q.filter(Match.league == league)
    return q.all()


def get_finished(db: Session, days_back: int = 7) -> list[Match]:
    """Return FINISHED matches from the last N days, newest first."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    return (
        db.query(Match)
        .filter(Match.status == MatchStatus.FINISHED)
        .filter(Match.utc_date >= cutoff)
        .order_by(Match.utc_date.desc())
        .all()
    )


def upsert(db: Session, match_data: dict) -> Match:
    """
    Insert or update a match identified by api_id.
    Idempotent — safe to call multiple times with the same data.
    Used by the ingestion task so re-runs don't create duplicate rows.
    """
    existing = get_by_api_id(db, match_data["api_id"])
    if existing:
        for key, value in match_data.items():
            setattr(existing, key, value)
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing
    match = Match(**match_data)
    db.add(match)
    db.commit()
    db.refresh(match)
    return match
