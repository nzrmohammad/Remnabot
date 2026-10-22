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

    # Automatic database initialization: create all tables on boot.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
