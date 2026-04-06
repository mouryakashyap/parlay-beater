"""
Central config — all env vars live here.
Access anywhere via: from app.core.config import settings
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://parlay:parlay@localhost:5432/parlay_beater"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Football APIs ─────────────────────────────────────────────────────────
    FOOTBALL_DATA_API_KEY: str = ""
    API_FOOTBALL_KEY: str = ""

    # ── App ───────────────────────────────────────────────────────────────────
    ENV: str = "development"
    USE_MOCK_DATA: bool = True
    TARGET_LEAGUES: str = "PL,PD,SA"  # comma-separated

    # ── Cache ─────────────────────────────────────────────────────────────────
    PREDICTION_CACHE_TTL: int = 3600  # seconds

    # ── MLflow ────────────────────────────────────────────────────────────────
    MLFLOW_TRACKING_URI: str = "sqlite:///data/mlflow.db"

    @property
    def target_leagues_list(self) -> list[str]:
        return [l.strip() for l in self.TARGET_LEAGUES.split(",")]


settings = Settings()
