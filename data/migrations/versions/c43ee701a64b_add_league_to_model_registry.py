"""add_league_to_model_registry

Revision ID: c43ee701a64b
Revises: 002
Create Date: 2026-04-08 04:15:23.137571

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c43ee701a64b'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('model_registry', sa.Column('league', sa.String(), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('model_registry', 'league')
