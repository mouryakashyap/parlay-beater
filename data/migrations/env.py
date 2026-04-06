"""
Alembic environment — wires our SQLAlchemy models into the migration engine.

Key concept: by importing all models here, Alembic's autogenerate can
detect schema changes and generate migration files automatically.
"""

import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Import all models so Alembic can detect them ──────────────────────────────
from app.models.base import Base
from app.models.team import Team          # noqa: F401
from app.models.match import Match, MatchStats, Odds  # noqa: F401
from app.models.prediction import Prediction, ModelRegistry  # noqa: F401

config = context.config

# Override sqlalchemy.url with env var at runtime
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL only)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
