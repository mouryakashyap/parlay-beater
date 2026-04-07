"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-06
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── teams ──────────────────────────────────────────────────────────────────
    op.create_table(
        "teams",
        sa.Column("id",         sa.Integer(), primary_key=True),
        sa.Column("name",       sa.String(),  nullable=False),
        sa.Column("short_name", sa.String()),
        sa.Column("league",     sa.String(),  nullable=False),
        sa.Column("country",    sa.String()),
        sa.Column("api_id",     sa.Integer(), unique=True),
    )
    op.create_index("ix_teams_id", "teams", ["id"])

    # ── matches ────────────────────────────────────────────────────────────────
    op.create_table(
        "matches",
        sa.Column("id",           sa.Integer(), primary_key=True),
        sa.Column("api_id",       sa.Integer(), unique=True),
        sa.Column("league",       sa.String(),  nullable=False),
        sa.Column("matchday",     sa.Integer()),
        sa.Column("utc_date",     sa.DateTime(), nullable=False),
        sa.Column("status",       sa.Enum("SCHEDULED", "LIVE", "FINISHED", "POSTPONED", name="matchstatus"),  default="SCHEDULED"),
        sa.Column("home_team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("away_team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("home_score",   sa.Integer()),
        sa.Column("away_score",   sa.Integer()),
        sa.Column("result",       sa.Enum("HOME", "DRAW", "AWAY", name="matchresult")),
        sa.Column("created_at",   sa.DateTime()),
        sa.Column("updated_at",   sa.DateTime()),
    )
    op.create_index("ix_matches_id",       "matches", ["id"])
    op.create_index("ix_matches_league",   "matches", ["league"])
    op.create_index("ix_matches_utc_date", "matches", ["utc_date"])
    op.create_index("ix_matches_status",   "matches", ["status"])

    # ── match_stats ────────────────────────────────────────────────────────────
    op.create_table(
        "match_stats",
        sa.Column("id",                      sa.Integer(), primary_key=True),
        sa.Column("match_id",                sa.Integer(), sa.ForeignKey("matches.id"), nullable=False, unique=True),
        sa.Column("xg_home",                 sa.Float()),
        sa.Column("xg_away",                 sa.Float()),
        sa.Column("shots_home",              sa.Integer()),
        sa.Column("shots_away",              sa.Integer()),
        sa.Column("shots_on_target_home",    sa.Integer()),
        sa.Column("shots_on_target_away",    sa.Integer()),
        sa.Column("possession_home",         sa.Float()),
        sa.Column("possession_away",         sa.Float()),
    )

    # ── odds ───────────────────────────────────────────────────────────────────
    op.create_table(
        "odds",
        sa.Column("id",       sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("provider", sa.String(),  nullable=False),
        sa.Column("home_win", sa.Float()),
        sa.Column("draw",     sa.Float()),
        sa.Column("away_win", sa.Float()),
        sa.Column("btts_yes", sa.Float()),
        sa.Column("btts_no",  sa.Float()),
        sa.Column("over_25",  sa.Float()),
        sa.Column("under_25", sa.Float()),
    )
    op.create_index("ix_odds_match_id", "odds", ["match_id"])

    # ── predictions ────────────────────────────────────────────────────────────
    op.create_table(
        "predictions",
        sa.Column("id",               sa.Integer(), primary_key=True),
        sa.Column("match_id",         sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("model_version",    sa.String(),  nullable=False),
        sa.Column("result_home",      sa.Float()),
        sa.Column("result_draw",      sa.Float()),
        sa.Column("result_away",      sa.Float()),
        sa.Column("btts",             sa.Float()),
        sa.Column("over_25",          sa.Float()),
        sa.Column("confidence",       sa.Float()),
        sa.Column("result_correct",   sa.Boolean()),
        sa.Column("btts_correct",     sa.Boolean()),
        sa.Column("over_25_correct",  sa.Boolean()),
        sa.Column("feature_snapshot", sa.JSON()),
        sa.Column("created_at",       sa.DateTime()),
    )
    op.create_index("ix_predictions_id",           "predictions", ["id"])
    op.create_index("ix_predictions_match_id",     "predictions", ["match_id"])
    op.create_index("ix_predictions_match_model",  "predictions", ["match_id", "model_version"])

    # ── model_registry ─────────────────────────────────────────────────────────
    op.create_table(
        "model_registry",
        sa.Column("id",            sa.Integer(), primary_key=True),
        sa.Column("model_name",    sa.String(),  nullable=False),
        sa.Column("version",       sa.String(),  nullable=False),
        sa.Column("mlflow_run_id", sa.String()),
        sa.Column("trained_at",    sa.DateTime()),
        sa.Column("is_active",     sa.Boolean(), default=False),
        sa.Column("metrics",       sa.JSON()),
    )


def downgrade() -> None:
    op.drop_table("model_registry")
    op.drop_table("predictions")
    op.drop_table("odds")
    op.drop_table("match_stats")
    op.drop_table("matches")
    op.drop_table("teams")
    sa.Enum(name="matchstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="matchresult").drop(op.get_bind(), checkfirst=True)
