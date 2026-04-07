"""
Team repository — all Team-related DB queries live here.
No business logic. Just SQL.
"""

from sqlalchemy.orm import Session
from app.models.team import Team
from app.schemas.team import TeamCreate


def get_by_id(db: Session, team_id: int) -> Team | None:
    return db.query(Team).filter(Team.id == team_id).first()


def get_by_api_id(db: Session, api_id: int) -> Team | None:
    return db.query(Team).filter(Team.api_id == api_id).first()


def get_by_league(db: Session, league: str) -> list[Team]:
    return db.query(Team).filter(Team.league == league).all()


def get_all(db: Session) -> list[Team]:
    return db.query(Team).order_by(Team.league, Team.name).all()


def create(db: Session, team_in: TeamCreate) -> Team:
    team = Team(**team_in.model_dump())
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


def upsert(db: Session, team_in: TeamCreate) -> Team:
    """Insert or update based on api_id. Used during data ingestion."""
    if team_in.api_id is None:
        return create(db, team_in)
    existing = get_by_api_id(db, team_in.api_id)
    if existing:
        for field, value in team_in.model_dump(exclude_unset=True).items():
            setattr(existing, field, value)
        db.commit()
        db.refresh(existing)
        return existing
    return create(db, team_in)
