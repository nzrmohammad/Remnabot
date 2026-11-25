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


def _inspect_migration_state(sync_conn) -> tuple[bool, bool, bool]:
    """Return (has_alembic_version, has_legacy_users, has_support_chat_messages)."""
    tables = set(inspect(sync_conn).get_table_names())
    return ("alembic_version" in tables, "users" in tables, "support_chat_messages" in tables)


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
            has_alembic, has_legacy_users, has_support_chat = await conn.run_sync(_inspect_migration_state)
    finally:
        await engine.dispose()

    if not has_alembic and has_legacy_users:
        if has_support_chat:
            logger.info("Existing database already contains support_chat_messages; stamping Alembic head directly.")
            await asyncio.to_thread(command.stamp, cfg, "head")
            return "stamped_head"
        logger.info("Existing database without alembic_version detected; stamping %s first.", _BASELINE_REV)
        await asyncio.to_thread(command.stamp, cfg, _BASELINE_REV)
        await asyncio.to_thread(command.upgrade, cfg, "head")
        return "stamped_and_upgraded"

    await asyncio.to_thread(command.upgrade, cfg, "head")
    return "upgraded"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    result = asyncio.run(ensure_schema_migrated())
    logger.info("Alembic startup check complete (%s).", result)
