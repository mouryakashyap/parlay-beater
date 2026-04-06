from datetime import datetime
from pydantic import BaseModel


class PredictionRead(BaseModel):
    id: int
    match_id: int
    model_version: str
    result_home: float | None
    result_draw: float | None
    result_away: float | None
    btts: float | None
    over_25: float | None
    confidence: float | None
    result_correct: bool | None
    btts_correct: bool | None
    over_25_correct: bool | None
    created_at: datetime

    model_config = {"from_attributes": True}
