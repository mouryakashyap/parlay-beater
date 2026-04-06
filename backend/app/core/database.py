"""
Database engine + session factory.

Usage in route dependencies:
    def get_db():
        with SessionLocal() as db:
            yield db

Why context manager?
    SQLAlchemy 2.0 sessions auto-commit/rollback when used as context managers.
    No need to manually call db.close() or db.rollback().
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.core.config import settings

# connect_args only needed for SQLite (not Postgres) — kept here for reference
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,      # detect stale connections before use
    pool_size=10,            # max persistent connections in pool
    max_overflow=20,         # extra connections allowed above pool_size under load
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency — yields a DB session per request.
    Session is closed automatically after the request completes.

    Usage:
        @router.get("/matches")
        def list_matches(db: Session = Depends(get_db)):
            ...
    """
    with SessionLocal() as db:
        yield db
