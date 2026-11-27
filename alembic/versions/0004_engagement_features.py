"""Add engagement feature tables (red_packets, red_packet_claims, wallet_transfers, weekly_quest_progress) and users.card_theme.

Revision ID: 0004_engagement_features
Revises: 0003_referral_commission_total
Create Date: 2026-11-27 19:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_engagement_features"
down_revision: str | Sequence[str] | None = "0003_referral_commission_total"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())

    if insp.has_table("users"):
        user_cols = {col.get("name") for col in insp.get_columns("users")}
        if "card_theme" not in user_cols:
            with op.batch_alter_table("users", schema=None) as batch_op:
                batch_op.add_column(sa.Column("card_theme", sa.String(length=32), nullable=True))

    if not insp.has_table("red_packets"):
        op.create_table(
            "red_packets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=32), nullable=False, unique=True),
            sa.Column(
                "sender_telegram_id",
                sa.BigInteger(),
                sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("sender_name", sa.String(length=128), nullable=True),
            sa.Column("split_mode", sa.String(length=16), nullable=False, server_default="RANDOM"),
            sa.Column("total_amount", sa.BigInteger(), nullable=False),
            sa.Column("remaining_amount", sa.BigInteger(), nullable=False),
            sa.Column("max_claims", sa.Integer(), nullable=False),
            sa.Column("claimed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("message", sa.String(length=256), nullable=True),
            sa.Column("is_refunded", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_red_packets_code", "red_packets", ["code"], unique=True)
        op.create_index("ix_red_packets_sender_telegram_id", "red_packets", ["sender_telegram_id"])
        op.create_index("ix_red_packets_expires_at", "red_packets", ["expires_at"])

    if not insp.has_table("red_packet_claims"):
        op.create_table(
            "red_packet_claims",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "packet_id",
                sa.Integer(),
                sa.ForeignKey("red_packets.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "telegram_id",
                sa.BigInteger(),
                sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("claimer_name", sa.String(length=128), nullable=True),
            sa.Column("amount", sa.BigInteger(), nullable=False),
            sa.Column("claimed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("packet_id", "telegram_id", name="uq_red_packet_claim_user"),
        )
        op.create_index("ix_red_packet_claims_packet_id", "red_packet_claims", ["packet_id"])
        op.create_index("ix_red_packet_claims_telegram_id", "red_packet_claims", ["telegram_id"])

    if not insp.has_table("wallet_transfers"):
        op.create_table(
            "wallet_transfers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "sender_telegram_id",
                sa.BigInteger(),
                sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "receiver_telegram_id",
                sa.BigInteger(),
                sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("amount", sa.BigInteger(), nullable=False),
            sa.Column("note", sa.String(length=160), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_wallet_transfers_sender_telegram_id", "wallet_transfers", ["sender_telegram_id"])
        op.create_index("ix_wallet_transfers_receiver_telegram_id", "wallet_transfers", ["receiver_telegram_id"])
        op.create_index("ix_wallet_transfers_created_at", "wallet_transfers", ["created_at"])

    if not insp.has_table("weekly_quest_progress"):
        op.create_table(
            "weekly_quest_progress",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "telegram_id",
                sa.BigInteger(),
                sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("week_key", sa.String(length=16), nullable=False),
            sa.Column("quest_id", sa.String(length=32), nullable=False),
            sa.Column("progress", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("target", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("is_claimed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("telegram_id", "week_key", "quest_id", name="uq_weekly_quest_user_week"),
        )
        op.create_index("ix_weekly_quest_progress_telegram_id", "weekly_quest_progress", ["telegram_id"])
        op.create_index("ix_weekly_quest_progress_week_key", "weekly_quest_progress", ["week_key"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for tbl in ("weekly_quest_progress", "wallet_transfers", "red_packet_claims", "red_packets"):
        if insp.has_table(tbl):
            op.drop_table(tbl)
    if insp.has_table("users"):
        user_cols = {col.get("name") for col in insp.get_columns("users")}
        if "card_theme" in user_cols:
            with op.batch_alter_table("users", schema=None) as batch_op:
                batch_op.drop_column("card_theme")
