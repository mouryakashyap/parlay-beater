"""
Team service — business logic for team-related operations.
Teams are read-only via the API; they're written by the ingestion pipeline.
"""

from sqlalchemy.orm import Session
from app.repositories import team_repo
from app.models.team import Team


def get_all_teams(db: Session) -> list[Team]:
    """Return all teams ordered by league then name."""
    return team_repo.get_all(db)


def get_teams_by_league(db: Session, league: str) -> list[Team]:
    """Return all teams in a specific league, e.g. 'PL'."""
    return team_repo.get_by_league(db, league)


def get_team(db: Session, team_id: int) -> Team | None:
    """Return a single team by DB id."""
    return team_repo.get_by_id(db, team_id)
