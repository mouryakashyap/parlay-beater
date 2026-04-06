"""
Match service — business logic for match-related operations.
Sits between routes and repositories.
"""

from sqlalchemy.orm import Session
from app.repositories import match_repo
from app.models.match import Match


def get_upcoming_matches(db: Session, league: str | None = None, days: int = 7) -> list[Match]:
    return match_repo.get_upcoming(db, league=league, days=days)


def get_match(db: Session, match_id: int) -> Match | None:
    return match_repo.get_by_id(db, match_id)


def get_finished_matches(db: Session, days_back: int = 7) -> list[Match]:
    return match_repo.get_finished(db, days_back=days_back)
