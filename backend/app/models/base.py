"""
Declarative base for all SQLAlchemy models.
All models must inherit from Base.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
