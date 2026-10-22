"""Entry point:  python -m bot.main"""
import asyncio
import logging
import os
import tempfile
import time

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
from bot.services.auto_renew import auto_renew_sweep_loop
from bot.services.backup import auto_backup_loop
from bot.services.birthday import birthday_sweep_loop
from bot.services.crypto.nobitex import nobitex_rate_loop
from bot.services.crypto.ton import ton_watcher_loop
from bot.services.devices import devices_loop
from bot.services.expiry import expiry_loop
from bot.services.node_monitor import nodes_monitor_loop
from bot.services.reconcile import reconcile_loop
from bot.services.remnawave import RemnawaveClient
from bot.services.reports import (
    monthly_report_loop,
    nightly_report_loop,
    weekly_report_loop,
    wheel_reminder_loop,
)
from bot.services.retention import retention_loop
from bot.services.traffic_monitor import traffic_monitor_loop
from bot.web.cache import FastCache

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


def _write_heartbeat(path: str) -> None:
    with open(path, "w") as f:
        f.write(str(int(time.time())))


async def heartbeat_loop() -> None:
    """Touch a file every 60s so the Docker HEALTHCHECK can see liveness."""
    while True:
        try:
            await asyncio.to_thread(_write_heartbeat, HEARTBEAT_FILE)
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

        # --- users.last_active_at, phone_number, birth_date (new columns) #
        cols = await _table_columns(conn, "users")
        if cols:
            if "last_active_at" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN last_active_at TIMESTAMPTZ")
                )
                logger.info("added users.last_active_at")
            if "phone_number" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN phone_number VARCHAR(32)")
                )
                logger.info("added users.phone_number")
            if "birth_date" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN birth_date VARCHAR(32)")
                )
                logger.info("added users.birth_date")
            if "campaign_code" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN campaign_code VARCHAR(32)")
                )
                logger.info("added users.campaign_code")
            if "auto_renew" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN auto_renew BOOLEAN DEFAULT FALSE")
                )
                logger.info("added users.auto_renew")
            if "wheel_streak" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN wheel_streak INTEGER DEFAULT 0")
                )
                logger.info("added users.wheel_streak")
            if "wheel_last_spin_at" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN wheel_last_spin_at TIMESTAMPTZ")
                )
                logger.info("added users.wheel_last_spin_at")
            if "spin_tickets" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN spin_tickets INTEGER DEFAULT 0")
                )
                logger.info("added users.spin_tickets")

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
            if "badge" not in cols:
                await conn.execute(
                    text("ALTER TABLE services ADD COLUMN badge VARCHAR(32)")
                )
                logger.info("added services.badge")

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

        # --- report_settings columns (monthly, clean_reports, last_report_message_id, wheel_notify, wheel_notified, wheel_last_spin_at) --- #
        cols = await _table_columns(conn, "report_settings")
        if cols:
            if "monthly" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE report_settings ADD COLUMN monthly "
                        "BOOLEAN NOT NULL DEFAULT TRUE"
                    )
                )
                logger.info("added report_settings.monthly")
            if "clean_reports" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE report_settings ADD COLUMN clean_reports "
                        "BOOLEAN NOT NULL DEFAULT TRUE"
                    )
                )
                logger.info("added report_settings.clean_reports")
            if "last_report_message_id" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE report_settings ADD COLUMN last_report_message_id "
                        "BIGINT"
                    )
                )
                logger.info("added report_settings.last_report_message_id")
            if "wheel_notify" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE report_settings ADD COLUMN wheel_notify "
                        "BOOLEAN NOT NULL DEFAULT TRUE"
                    )
                )
                logger.info("added report_settings.wheel_notify")
            if "wheel_notified" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE report_settings ADD COLUMN wheel_notified "
                        "BOOLEAN NOT NULL DEFAULT FALSE"
                    )
                )
                logger.info("added report_settings.wheel_notified")
            if "wheel_last_spin_at" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE report_settings ADD COLUMN wheel_last_spin_at "
                        "TIMESTAMPTZ"
                    )
                )
                logger.info("added report_settings.wheel_last_spin_at")
            if "last_nightly_message_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE report_settings ADD COLUMN last_nightly_message_id BIGINT")
                )
                logger.info("added report_settings.last_nightly_message_id")
            if "last_weekly_message_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE report_settings ADD COLUMN last_weekly_message_id BIGINT")
                )
                logger.info("added report_settings.last_weekly_message_id")
            if "last_monthly_message_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE report_settings ADD COLUMN last_monthly_message_id BIGINT")
                )
                logger.info("added report_settings.last_monthly_message_id")
            if "last_wheel_message_id" not in cols:
                await conn.execute(
                    text("ALTER TABLE report_settings ADD COLUMN last_wheel_message_id BIGINT")
                )
                logger.info("added report_settings.last_wheel_message_id")

        # --- topups.receipt_hash (duplicate-receipt fingerprint) --------- #
        cols = await _table_columns(conn, "topups")
        if cols and "receipt_hash" not in cols:
            await conn.execute(
                text("ALTER TABLE topups ADD COLUMN receipt_hash VARCHAR(128)")
            )
            logger.info("added topups.receipt_hash")
        if cols and "receipt_photo_id" not in cols:
            await conn.execute(
                text("ALTER TABLE topups ADD COLUMN receipt_photo_id VARCHAR(256)")
            )
            logger.info("added topups.receipt_photo_id")
        if cols and "admin_message_id" not in cols:
            await conn.execute(
                text("ALTER TABLE topups ADD COLUMN admin_message_id BIGINT")
            )
            logger.info("added topups.admin_message_id")

        if cols:
            try:
                async with conn.begin_nested():
                    # Deduplicate existing non-null receipt_hashes before index creation
                    await conn.execute(
                        text(
                            "UPDATE topups "
                            "SET receipt_hash = receipt_hash || '_dup_' || CAST(id AS VARCHAR) "
                            "WHERE id NOT IN ("
                            "    SELECT min_id FROM ("
                            "        SELECT MIN(id) AS min_id FROM topups WHERE receipt_hash IS NOT NULL GROUP BY receipt_hash"
                            "    ) t"
                            ") AND receipt_hash IS NOT NULL"
                        )
                    )
                    await conn.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS uq_topups_receipt_hash "
                            "ON topups (receipt_hash) WHERE receipt_hash IS NOT NULL"
                        )
                    )
            except Exception as exc:
                logger.debug("Unique index on topups.receipt_hash check: %s", exc)

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
            if "full_name" not in cols:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN full_name VARCHAR(128)")
                )
                logger.info("added users.full_name")
            if "phone_number" in cols:
                try:
                    async with conn.begin_nested():
                        await conn.execute(
                            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone_number ON users (phone_number) WHERE phone_number IS NOT NULL")
                        )
                except Exception as exc:
                    logger.debug("Unique index on users.phone_number check: %s", exc)

        # --- orders: is_renewal column ----------------------------------------- #
        cols = await _table_columns(conn, "orders")
        if cols and "is_renewal" not in cols:
            await conn.execute(
                text("ALTER TABLE orders ADD COLUMN is_renewal BOOLEAN DEFAULT FALSE")
            )
            logger.info("added orders.is_renewal")

        # --- crypto_invoices: tx_hash index ------------------------------------ #
        cols = await _table_columns(conn, "crypto_invoices")
        if cols and "tx_hash" in cols:
            try:
                async with conn.begin_nested():
                    await conn.execute(
                        text("CREATE UNIQUE INDEX IF NOT EXISTS uq_crypto_invoices_tx_hash ON crypto_invoices (tx_hash) WHERE tx_hash IS NOT NULL")
                    )
                logger.info("ensured uq_crypto_invoices_tx_hash unique index")
            except Exception as exc:
                logger.debug("Unique index on crypto_invoices.tx_hash check: %s", exc)

        # --- node_costs: currency column --------------------------------------- #
        cols = await _table_columns(conn, "node_costs")
        if cols and "currency" not in cols:
            await conn.execute(
                text("ALTER TABLE node_costs ADD COLUMN currency VARCHAR(8) DEFAULT 'EUR'")
            )
            logger.info("added node_costs.currency")

        # --- admin_logs: target_user_id column --------------------------------- #
        cols = await _table_columns(conn, "admin_logs")
        if cols and "target_user_id" not in cols:
            await conn.execute(
                text("ALTER TABLE admin_logs ADD COLUMN target_user_id BIGINT")
            )
            logger.info("added admin_logs.target_user_id")

        # --- Scale composite indexes ------------------------------------------- #
        scale_indexes = [
            ("ix_orders_status_created_at", "orders", "(status, created_at)"),
            ("ix_topups_status", "topups", "(status)"),
            ("ix_crypto_invoices_status", "crypto_invoices", "(status)"),
            ("ix_users_auto_renew", "users", "(auto_renew)"),
            ("ix_admin_logs_target_user_id", "admin_logs", "(target_user_id)"),
            ("ix_admin_logs_action_created", "admin_logs", "(action, created_at)"),
        ]
        for idx_name, tbl, cols_spec in scale_indexes:
            try:
                await conn.execute(
                    text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} {cols_spec}")
                )
            except Exception as e:
                logger.debug("Scale index %s note: %s", idx_name, e)

        # --- campaigns table (idempotent creation for legacy databases) --------- #
        cols = await _table_columns(conn, "campaigns")
        if not cols:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(32) NOT NULL,
                    name VARCHAR(64) NOT NULL,
                    cost BIGINT NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_campaigns_code ON campaigns (code)"))
            logger.info("ensured campaigns table")


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
    from bot.services.error_reporter import setup_telegram_error_logging
    setup_telegram_error_logging(bot, session_factory)

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

    redis_client = getattr(dp.storage, "redis", None)
    fast_cache = FastCache(redis_client=redis_client)

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
            reconcile_loop(bot, session_factory, remnawave), name="reconcile-loop"
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
        asyncio.create_task(
            nodes_monitor_loop(bot, remnawave, session_factory=session_factory), name="nodes-monitor-loop"
        ),
        asyncio.create_task(
            traffic_monitor_loop(remnawave, session_factory), name="traffic-monitor-loop"
        ),
        asyncio.create_task(
            wheel_reminder_loop(bot, session_factory, remnawave), name="wheel-reminder-loop"
        ),
        asyncio.create_task(
            birthday_sweep_loop(bot, session_factory, remnawave, cache=fast_cache),
            name="birthday-sweep-loop",
        ),
        asyncio.create_task(
            auto_renew_sweep_loop(bot, session_factory, remnawave, cache=fast_cache),
            name="auto-renew-sweep-loop",
        ),
    ]

    web_runner = None
    if settings.WEB_ENABLED:
        try:
            from bot.web.server import create_web_app, start_web_server
            web_app = create_web_app(
                bot=bot,
                session_factory=session_factory,
                remnawave=remnawave,
                settings=settings,
                redis_client=redis_client,
            )
            web_runner = await start_web_server(
                web_app, host=settings.WEB_HOST, port=settings.WEB_PORT
            )
        except Exception:
            logger.exception("Failed to start TMA web server")

    try:
        logger.info("Bot started.")
        # Keep pending updates: dropping them would silently lose top-up
        # receipts / support messages sent while the bot was restarting.
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        for task in background_tasks:
            task.cancel()
        if web_runner:
            await web_runner.cleanup()
        await remnawave.close()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
