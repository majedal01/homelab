"""initial ynab tables

Revision ID: 0001
Revises:
Create Date: 2026-05-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budgets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("last_modified_on", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("budget_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("balance_cents", sa.BigInteger(), nullable=False),
        sa.Column("on_budget", sa.Boolean(), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounts_budget_id", "accounts", ["budget_id"])

    op.create_table(
        "categories",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("budget_id", sa.String(), nullable=False),
        sa.Column("category_group_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_categories_budget_id", "categories", ["budget_id"])

    op.create_table(
        "payees",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("budget_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("transfer_account_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payees_budget_id", "payees", ["budget_id"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("budget_id", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("category_id", sa.String(), nullable=True),
        sa.Column("payee_id", sa.String(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("memo", sa.String(), nullable=True),
        sa.Column("cleared", sa.String(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["budget_id"], ["budgets.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["payee_id"], ["payees.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_budget_id", "transactions", ["budget_id"])
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"])
    op.create_index("ix_transactions_payee_id", "transactions", ["payee_id"])
    op.create_index("ix_transactions_date", "transactions", ["date"])


def downgrade() -> None:
    op.drop_index("ix_transactions_date", "transactions")
    op.drop_index("ix_transactions_payee_id", "transactions")
    op.drop_index("ix_transactions_category_id", "transactions")
    op.drop_index("ix_transactions_account_id", "transactions")
    op.drop_index("ix_transactions_budget_id", "transactions")
    op.drop_table("transactions")

    op.drop_index("ix_payees_budget_id", "payees")
    op.drop_table("payees")

    op.drop_index("ix_categories_budget_id", "categories")
    op.drop_table("categories")

    op.drop_index("ix_accounts_budget_id", "accounts")
    op.drop_table("accounts")

    op.drop_table("budgets")
