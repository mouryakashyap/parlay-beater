"""
Match service — business logic for match-related operations.
Sits between routes and repositories; routes never touch the DB directly.
"""

from sqlalchemy.orm import Session
from app.repositories import match_repo
from app.models.match import Match


def get_upcoming_matches(db: Session, league: str | None = None, days: int = 7) -> list[Match]:
    """Return SCHEDULED matches within the next N days, optionally filtered by league."""
    return match_repo.get_upcoming(db, league=league, days=days)


def get_match(db: Session, match_id: int) -> Match | None:
    """Return a single match by DB id, with home/away teams eagerly loaded."""
    return match_repo.get_by_id(db, match_id)


def get_finished_matches(db: Session, days_back: int = 7) -> list[Match]:
    """Return FINISHED matches from the last N days, newest first."""
    return match_repo.get_finished(db, days_back=days_back)
