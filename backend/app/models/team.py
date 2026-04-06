from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class Team(Base):
    __tablename__ = "teams"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, nullable=False)
    short_name  = Column(String)               # e.g. "MCI"
    league      = Column(String, nullable=False)  # e.g. "PL"
    country     = Column(String)
    api_id      = Column(Integer, unique=True)    # ID from football-data.org

    # Relationships — back-populated from Match
    home_matches = relationship("Match", back_populates="home_team", foreign_keys="Match.home_team_id")
    away_matches = relationship("Match", back_populates="away_team", foreign_keys="Match.away_team_id")

    def __repr__(self):
        return f"<Team {self.name} ({self.league})>"
