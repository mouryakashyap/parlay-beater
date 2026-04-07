from pydantic import BaseModel


class TeamBase(BaseModel):
    """Shared fields used for both creating and reading a team."""
    name: str
    short_name: str | None = None   # abbreviated name, e.g. "MCI" for Man City
    league: str                     # competition code, e.g. "PL"
    country: str | None = None
    api_id: int | None = None       # external ID from football-data.org


class TeamCreate(TeamBase):
    """Used by the ingestion pipeline when upserting teams from the API."""
    pass


class TeamRead(TeamBase):
    """Returned by the API — includes the internal DB id."""
    id: int

    # from_attributes=True lets Pydantic serialize SQLAlchemy ORM objects directly
    model_config = {"from_attributes": True}
