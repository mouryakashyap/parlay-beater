"""add season column to matches

Revision ID: 002
Revises: 001
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("season", sa.Integer(), nullable=True))
    op.create_index("ix_matches_season", "matches", ["season"])


def downgrade() -> None:
    op.drop_index("ix_matches_season", table_name="matches")
    op.drop_column("matches", "season")
