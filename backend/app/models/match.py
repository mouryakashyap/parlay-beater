from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum

from app.models.base import Base


class MatchStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    LIVE      = "LIVE"
    FINISHED  = "FINISHED"
    POSTPONED = "POSTPONED"


class MatchResult(str, enum.Enum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"


class Match(Base):
    __tablename__ = "matches"

    id           = Column(Integer, primary_key=True, index=True)
    api_id       = Column(Integer, unique=True)         # ID from football-data.org
    league       = Column(String, nullable=False, index=True)
    matchday     = Column(Integer)
    utc_date     = Column(DateTime, nullable=False, index=True)
    status       = Column(Enum(MatchStatus), default=MatchStatus.SCHEDULED, index=True)

    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)

    # Filled in once match is FINISHED
    home_score   = Column(Integer)
    away_score   = Column(Integer)
    result       = Column(Enum(MatchResult))

    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    home_team    = relationship("Team", back_populates="home_matches", foreign_keys=[home_team_id])
    away_team    = relationship("Team", back_populates="away_matches", foreign_keys=[away_team_id])
    stats        = relationship("MatchStats", back_populates="match", uselist=False)
    odds         = relationship("Odds", back_populates="match")
    predictions  = relationship("Prediction", back_populates="match")

    def __repr__(self):
        return f"<Match {self.home_team_id} vs {self.away_team_id} on {self.utc_date}>"


class MatchStats(Base):
    """
    Per-match advanced stats — populated after the match is played.
    xG is the most predictive signal for future model training.
    """
    __tablename__ = "match_stats"

    id              = Column(Integer, primary_key=True)
    match_id        = Column(Integer, ForeignKey("matches.id"), nullable=False, unique=True)

    xg_home         = Column(Float)   # expected goals — home team
    xg_away         = Column(Float)   # expected goals — away team
    shots_home      = Column(Integer)
    shots_away      = Column(Integer)
    shots_on_target_home = Column(Integer)
    shots_on_target_away = Column(Integer)
    possession_home = Column(Float)   # 0–100
    possession_away = Column(Float)

    match = relationship("Match", back_populates="stats")


class Odds(Base):
    """
    Pre-match odds from a bookmaker. Stored for model training (odds = signal).
    Multiple rows per match if we source from multiple providers.
    """
    __tablename__ = "odds"

    id         = Column(Integer, primary_key=True)
    match_id   = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    provider   = Column(String, nullable=False)    # e.g. "bet365"

    home_win   = Column(Float)
    draw       = Column(Float)
    away_win   = Column(Float)
    btts_yes   = Column(Float)
    btts_no    = Column(Float)
    over_25    = Column(Float)
    under_25   = Column(Float)

    match = relationship("Match", back_populates="odds")
