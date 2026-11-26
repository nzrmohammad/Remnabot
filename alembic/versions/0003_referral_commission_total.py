"""Add commission_toman column to referral_rewards to track earned affiliate cash.

Revision ID: 0003_referral_commission_total
Revises: 0002_support_chat_history
Create Date: 2026-11-26 17:45:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_referral_commission_total"
down_revision: str | Sequence[str] | None = "0002_support_chat_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("referral_rewards"):
        return
    cols = {col.get("name") for col in insp.get_columns("referral_rewards")}
    if "commission_toman" not in cols:
        with op.batch_alter_table("referral_rewards", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "commission_toman",
                    sa.BigInteger(),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("referral_rewards"):
        return
    cols = {col.get("name") for col in insp.get_columns("referral_rewards")}
    if "commission_toman" in cols:
        with op.batch_alter_table("referral_rewards", schema=None) as batch_op:
            batch_op.drop_column("commission_toman")
