"""add insights and insight_runs tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-22

Creates the storage for the v2.4 Insights Feed: `insights` for the cards
themselves (with a JSON `structured_data` payload and a unique
`(budget_id, dedup_key)` constraint for idempotent generation) and
`insight_runs` for per-generator observability.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "insights",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("budget_id", sa.String(), nullable=False),
        sa.Column("card_type", sa.String(), nullable=False),
        sa.Column("dedup_key", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("structured_data", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("llm_enhanced", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("budget_id", "dedup_key", name="uq_insights_budget_dedup"),
    )
    op.create_index("ix_insights_budget_id", "insights", ["budget_id"])
    op.create_index("ix_insights_card_type", "insights", ["card_type"])
    op.create_index(
        "ix_insights_feed",
        "insights",
        ["budget_id", "dismissed_at", "refreshed_at"],
    )

    op.create_table(
        "insight_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("card_type", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("insights_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("insights_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_insight_runs_card_type_started",
        "insight_runs",
        ["card_type", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_insight_runs_card_type_started", "insight_runs")
    op.drop_table("insight_runs")

    op.drop_index("ix_insights_feed", "insights")
    op.drop_index("ix_insights_card_type", "insights")
    op.drop_index("ix_insights_budget_id", "insights")
    op.drop_table("insights")
