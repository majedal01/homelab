"""add YNAB goal fields to categories

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-22

Adds six nullable columns to `categories` so the Goal Trajectory insight
generator can project completion dates and progress. Sync populates them
from YNAB's `/budgets/{id}/categories` response.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("goal_type", sa.String(), nullable=True))
    op.add_column("categories", sa.Column("goal_target_cents", sa.BigInteger(), nullable=True))
    op.add_column("categories", sa.Column("goal_target_month", sa.Date(), nullable=True))
    op.add_column(
        "categories", sa.Column("goal_percentage_complete", sa.Integer(), nullable=True)
    )
    op.add_column(
        "categories", sa.Column("goal_overall_left_cents", sa.BigInteger(), nullable=True)
    )
    op.add_column("categories", sa.Column("goal_months_to_budget", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("categories", "goal_months_to_budget")
    op.drop_column("categories", "goal_overall_left_cents")
    op.drop_column("categories", "goal_percentage_complete")
    op.drop_column("categories", "goal_target_month")
    op.drop_column("categories", "goal_target_cents")
    op.drop_column("categories", "goal_type")
