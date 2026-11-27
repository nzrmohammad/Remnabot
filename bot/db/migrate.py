"""Automatic Alembic schema migration runner for container startup."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from bot.config import get_settings

logger = logging.getLogger(__name__)
_BASELINE_REV = "0001_baseline"
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _inspect_migration_state(sync_conn) -> tuple[bool, bool, bool, bool, bool]:
    """Return (has_alembic_version, has_legacy_users, has_support_chat_messages, has_ref_commission, has_engagement)."""
    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    has_ref_commission = False
    if "referral_rewards" in tables:
        ref_cols = {c.get("name") for c in inspector.get_columns("referral_rewards")}
        has_ref_commission = "commission_toman" in ref_cols
    has_engagement = False
    if "users" in tables and {"red_packets", "red_packet_claims", "wallet_transfers", "weekly_quest_progress"} <= tables:
        user_cols = {c.get("name") for c in inspector.get_columns("users")}
        has_engagement = "card_theme" in user_cols
    return (
        "alembic_version" in tables,
        "users" in tables,
        "support_chat_messages" in tables,
        has_ref_commission,
        has_engagement,
    )


async def ensure_schema_migrated(
    database_url: str | None = None,
    *,
    alembic_ini: str | Path = _ALEMBIC_INI,
) -> str:
    """Safely upgrade DB schema via Alembic, stamping pre-Alembic databases first.

    Returns 'stamped_head', 'stamped_and_upgraded', or 'upgraded'.
    """
    db_url = database_url or get_settings().DATABASE_URL
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", db_url)

    engine = create_async_engine(db_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            has_alembic, has_legacy_users, has_support_chat, has_ref_commission, has_engagement = await conn.run_sync(
                _inspect_migration_state
            )
    finally:
        await engine.dispose()

    if not has_alembic and has_legacy_users:
        if has_support_chat and has_ref_commission and has_engagement:
            logger.info("Existing database already matches current schema; stamping Alembic head directly.")
            await asyncio.to_thread(command.stamp, cfg, "head")
            return "stamped_head"
        if has_support_chat and has_ref_commission:
            stamp_rev = "0003_referral_commission_total"
        elif has_support_chat:
            stamp_rev = "0002_support_chat_history"
        else:
            stamp_rev = _BASELINE_REV
        logger.info("Existing database without alembic_version detected; stamping %s first.", stamp_rev)
        await asyncio.to_thread(command.stamp, cfg, stamp_rev)
        await asyncio.to_thread(command.upgrade, cfg, "head")
        return "stamped_and_upgraded"

    await asyncio.to_thread(command.upgrade, cfg, "head")
    return "upgraded"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    result = asyncio.run(ensure_schema_migrated())
    logger.info("Alembic startup check complete (%s).", result)
