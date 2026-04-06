from pydantic import BaseModel


class TeamBase(BaseModel):
    name: str
    short_name: str | None = None
    league: str
    country: str | None = None
    api_id: int | None = None


class TeamCreate(TeamBase):
    pass


class TeamRead(TeamBase):
    id: int

    model_config = {"from_attributes": True}
