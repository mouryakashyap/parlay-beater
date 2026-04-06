from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import team_service
from app.schemas.team import TeamRead

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/", response_model=list[TeamRead])
def get_teams(
    league: str | None = Query(None, description="Filter by league code"),
    db: Session = Depends(get_db),
):
    if league:
        return team_service.get_teams_by_league(db, league)
    return team_service.get_all_teams(db)


@router.get("/{team_id}", response_model=TeamRead)
def get_team(team_id: int, db: Session = Depends(get_db)):
    team = team_service.get_team(db, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team
