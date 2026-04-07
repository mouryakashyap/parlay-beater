from datetime import datetime
from pydantic import BaseModel


class PredictionRead(BaseModel):
    id: int
    match_id: int
    model_version: str          # e.g. "xgb-v1.2" — identifies which trained model generated this

    # Probabilities (0.0–1.0) for each outcome — all three should sum to ~1.0
    result_home: float | None
    result_draw: float | None
    result_away: float | None

    btts: float | None          # probability that both teams score
    over_25: float | None       # probability of more than 2.5 total goals

    confidence: float | None    # composite model confidence (0–1); higher = more certain

    # Accuracy fields — None until the match finishes and results are resolved
    result_correct: bool | None
    btts_correct: bool | None
    over_25_correct: bool | None

    created_at: datetime

    # from_attributes=True lets Pydantic serialize SQLAlchemy ORM objects directly
    model_config = {"from_attributes": True}
