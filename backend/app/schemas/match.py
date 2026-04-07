from datetime import datetime
from pydantic import BaseModel
from app.schemas.team import TeamRead


class MatchRead(BaseModel):
    id: int
    api_id: int | None          # external ID from football-data.org; None for manually created matches
    league: str                 # e.g. "PL", "PD", "SA"
    matchday: int | None        # round number in the competition
    utc_date: datetime          # kickoff time in UTC
    status: str                 # SCHEDULED | LIVE | FINISHED | POSTPONED
    home_team: TeamRead         # eagerly loaded via joinedload in match_repo
    away_team: TeamRead
    home_score: int | None      # None until match is FINISHED
    away_score: int | None
    result: str | None          # HOME | DRAW | AWAY — None until FINISHED

    # from_attributes=True lets Pydantic serialize SQLAlchemy ORM objects directly
    model_config = {"from_attributes": True}


class MatchListResponse(BaseModel):
    """Wraps a list of matches with a total count — avoids a separate count query."""
    total: int
    items: list[MatchRead]
