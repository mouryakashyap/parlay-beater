# Import all models here so SQLAlchemy's mapper registry is fully populated
# before any relationship string references are resolved.
from app.models.team import Team
from app.models.match import Match, MatchStats, Odds, MatchStatus, MatchResult
from app.models.prediction import Prediction, ModelRegistry

__all__ = [
    "Team",
    "Match", "MatchStats", "Odds", "MatchStatus", "MatchResult",
    "Prediction", "ModelRegistry",
]
