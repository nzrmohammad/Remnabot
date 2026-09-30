"""Entry point:  python -m bot.main"""
import asyncio
import logging
import os
import tempfile

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bot.config import get_settings
from bot.db.base import Base, create_engine_and_sessionmaker
from bot.handlers import get_main_router
from bot.middlewares.ban_check import BanCheckMiddleware
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.services.alerts import alerts_loop
from bot.services.backup import auto_backup_loop
from bot.services.crypto.nobitex import nobitex_rate_loop
from bot.services.crypto.ton import ton_watcher_loop
from bot.services.devices import devices_loop
from bot.services.expiry import expiry_loop
from bot.services.reconcile import reconcile_loop
from bot.services.remnawave import RemnawaveClient
from bot.services.reports import (
    monthly_report_loop,
    nightly_report_loop,
    weekly_report_loop,
)
from bot.services.retention import retention_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _build_storage(settings):
    """RedisStorage when REDIS_URL is set, else MemoryStorage (dev)."""
    if getattr(settings, "REDIS_URL", ""):
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            from redis.asyncio import Redis

            redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
            logger.info("Using RedisStorage for FSM.")
            return RedisStorage(redis)
        except Exception:
            logger.exception("Redis init failed, falling back to MemoryStorage")
    return MemoryStorage()


HEARTBEAT_FILE = os.path.join(tempfile.gettempdir(), "bot_heartbeat")


async def heartbeat_loop() -> None:
    """Touch a file every 60s so the Docker HEALTHCHECK can see liveness."""
    while True:
        try:
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(str(int(asyncio.get_event_loop().time())))
        except OSError:
            logger.exception("heartbeat write failed")
        await asyncio.sleep(60)


async def _table_columns(conn, table: str) -> set[str]:
    result = await conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :t"
        ),
        {"t": table},
    )
    return {row[0] for row in result}


async def _migrate_schema(engine: AsyncEngine) -> None:
    """Idempotent fixes for tables created by older versions.

    `create_all` never alters existing tables, so known renames / new
    columns are patched here manually. Safe to run on every start.
    """
    async with engine.begin() as conn:
        # --- alert_state.account_uuid -> account_id (schema rename) ---- #
        cols = await _table_columns(conn, "alert_state")
        if cols and "account_id" not in cols and "account_uuid" in cols:
            await conn.execute(
                text("ALTER TABLE alert_state RENAME COLUMN account_uuid TO account_id")
            )
            logger.info("migrated alert_state.account_uuid -> account_id")

        # --- users.last_active_at (new column) ------------------------- #
        cols = await _table_columns(conn, "users")
        if cols and "last_active_at" not in cols:
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN last_active_at TIMESTAMPTZ")
            )
            logger.info("added users.last_active_at")

        # --- services: strategy / hwid / squad (new columns) ----------- #
        cols = await _table_columns(conn, "services")
        if cols:
            if "traffic_strategy" not in cols:
                await conn.execute(text(
                    "ALTER TABLE services ADD COLUMN traffic_strategy "
                    "VARCHAR(16) NOT NULL DEFAULT 'NO_RESET'"
                ))
                logger.info("added services.traffic_strategy")
            if "hwid_limit" not in cols:
                await conn.execute(
                    text("ALTER TABLE services ADD COLUMN hwid_limit INTEGER")
                )
                logger.info("added services.hwid_limit")
            if "squad_uuid" not in cols:
                await conn.execute(
                    text("ALTER TABLE services ADD COLUMN squad_uuid VARCHAR(64)")
                )
                logger.info("added services.squad_uuid")

        # --- orders: status / refunded_at (new columns) ---------------- #
        cols = await _table_columns(conn, "orders")
        if cols:
            if "status" not in cols:
                await conn.execute(text(
                    "ALTER TABLE orders ADD COLUMN status "
                    "VARCHAR(10) NOT NULL DEFAULT 'paid'"
                ))
                logger.info("added orders.status")
            if "refunded_at" not in cols:
                await conn.execute(
                    text("ALTER TABLE orders ADD COLUMN refunded_at TIMESTAMPTZ")
                )
                logger.info("added orders.refunded_at")

        # --- report_settings.monthly (new column) ---------------------- #
        cols = await _table_columns(conn, "report_settings")
        if cols and "monthly" not in cols:
            await conn.execute(
                text(
                    "ALTER TABLE report_settings ADD COLUMN monthly "
                    "BOOLEAN NOT NULL DEFAULT TRUE"
                )
            )
            logger.info("added report_settings.monthly")

        # --- topups.receipt_hash (duplicate-receipt fingerprint) --------- #
        cols = await _table_columns(conn, "topups")
        if cols and "receipt_hash" not in cols:
            await conn.execute(
                text("ALTER TABLE topups ADD COLUMN receipt_hash VARCHAR(128)")
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_topups_receipt_hash "
                    "ON topups (receipt_hash)"
                )
            )
            logger.info("added topups.receipt_hash")

        # --- users: is_banned, has_claimed_trial, referred_by_id (new columns) --- #
        cols = await _table_columns(conn, "users")
        if cols:
            if "is_banned" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT FALSE")
                )
                logger.info("added users.is_banned")
            if "has_claimed_trial" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN has_claimed_trial BOOLEAN NOT NULL DEFAULT FALSE")
                )
                logger.info("added users.has_claimed_trial")
            if "referred_by_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN referred_by_id BIGINT")
                )
                await conn.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_users_referred_by_id ON users (referred_by_id)")
                )
                logger.info("added users.referred_by_id")


async def main() -> None:
    settings = get_settings()

    # Optional Sentry (no-op when SENTRY_DSN is empty).
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk

            sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)
            logger.info("Sentry enabled.")
        except Exception:
            logger.exception("Sentry init failed")

    engine, session_factory = create_engine_and_sessionmaker()

    # Automatic database initialization: create all tables and apply schema updates on boot.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_schema(engine)

    remnawave = RemnawaveClient(
        base_url=settings.REMNAWAVE_BASE_URL,
        token=settings.REMNAWAVE_TOKEN,
    )

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # NOTE: MemoryStorage loses all FSM states (top-up flow, admin wizards,
    # broadcast drafts) on every restart. For production, switch to
    # aiogram.fsm.storage.redis.RedisStorage(redis) — no code changes
    # needed beyond this line.
    dp = Dispatcher(storage=_build_storage(settings))

    # dependency injection
    dp["remnawave"] = remnawave
    # Rate-limit first (drops floods before DB sessions are opened).
    dp.update.outer_middleware(RateLimitMiddleware())
    dp.update.outer_middleware(DbSessionMiddleware(session_factory))
    dp.update.outer_middleware(BanCheckMiddleware())

    dp.include_router(get_main_router())

    @dp.error()
    async def global_error_handler(event: ErrorEvent):
        logger.exception("Global unhandled error: %s", event.exception)
        try:
            from bot.services.error_reporter import report_error_event
            await report_error_event(bot, session_factory, event)
        except Exception as exc:
            logger.warning("Failed to dispatch error report: %s", exc)

    background_tasks = [
        asyncio.create_task(
            alerts_loop(bot, session_factory, remnawave), name="alerts-loop"
        ),
        asyncio.create_task(
            devices_loop(bot, session_factory, remnawave), name="devices-loop"
        ),
        asyncio.create_task(
            expiry_loop(bot, session_factory, remnawave), name="expiry-loop"
        ),
        asyncio.create_task(
            reconcile_loop(bot, session_factory), name="reconcile-loop"
        ),
        asyncio.create_task(heartbeat_loop(), name="heartbeat"),
        asyncio.create_task(
            nightly_report_loop(bot, session_factory, remnawave), name="nightly-report"
        ),
        asyncio.create_task(
            weekly_report_loop(bot, session_factory, remnawave), name="weekly-report"
        ),
        asyncio.create_task(
            monthly_report_loop(bot, session_factory, remnawave), name="monthly-report"
        ),
        asyncio.create_task(
            retention_loop(bot, session_factory, remnawave), name="retention-loop"
        ),
        asyncio.create_task(
            auto_backup_loop(bot, session_factory), name="auto-backup-loop"
        ),
        asyncio.create_task(
            nobitex_rate_loop(bot, session_factory), name="nobitex-rate-loop"
        ),
        asyncio.create_task(
            ton_watcher_loop(bot, session_factory), name="ton-watcher-loop"
        ),
    ]

    try:
        logger.info("Bot started.")
        # Keep pending updates: dropping them would silently lose top-up
        # receipts / support messages sent while the bot was restarting.
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        for task in background_tasks:
            task.cancel()
        await remnawave.close()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
