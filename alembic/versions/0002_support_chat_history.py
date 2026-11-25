"""Add PostgreSQL support_chat_messages table for durable chat history.

Revision ID: 0002_support_chat_history
Revises: 0001_baseline
Create Date: 2026-11-25 11:15:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_support_chat_history"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("external_msg_id", sa.String(length=64), nullable=False),
        sa.Column("sender", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("support_chat_messages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_support_chat_messages_created_at"),
            ["created_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_support_chat_messages_telegram_id"),
            ["telegram_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("support_chat_messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_support_chat_messages_telegram_id"))
        batch_op.drop_index(batch_op.f("ix_support_chat_messages_created_at"))
    op.drop_table("support_chat_messages")
