from sqlalchemy.orm import Session
from app.repositories import team_repo
from app.models.team import Team


def get_all_teams(db: Session) -> list[Team]:
    return team_repo.get_all(db)


def get_teams_by_league(db: Session, league: str) -> list[Team]:
    return team_repo.get_by_league(db, league)


def get_team(db: Session, team_id: int) -> Team | None:
    return team_repo.get_by_id(db, team_id)
