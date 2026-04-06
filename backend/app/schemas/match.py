from datetime import datetime
from pydantic import BaseModel
from app.schemas.team import TeamRead


class MatchRead(BaseModel):
    id: int
    api_id: int | None
    league: str
    matchday: int | None
    utc_date: datetime
    status: str
    home_team: TeamRead
    away_team: TeamRead
    home_score: int | None
    away_score: int | None
    result: str | None

    model_config = {"from_attributes": True}


class MatchListResponse(BaseModel):
    total: int
    items: list[MatchRead]
