"""Entry point:  python -m bot.main"""
import asyncio
import logging
import os
import tempfile
import time
import uuid

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from bot.config import get_settings
from bot.db.base import create_engine_and_sessionmaker, init_db
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

log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)
log_handlers: list[logging.Handler] = [logging.StreamHandler()]

log_file_path = os.getenv("LOG_FILE", "").strip()
if log_file_path:
    try:
        from logging.handlers import RotatingFileHandler
        from pathlib import Path
        Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=20 * 1024 * 1024,  # 20 MB
            backupCount=5,
            encoding="utf-8",
        )
        log_handlers.append(file_handler)
    except Exception as exc:
        print(f"Failed setting up RotatingFileHandler for {log_file_path}: {exc}")

logging.basicConfig(
    level=log_level,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=log_handlers,
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
    engine, session_factory = create_engine_and_sessionmaker()

    # Automatic database initialization: create all tables on boot and apply migrations.
    await init_db(engine)

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
    redis_client = getattr(dp.storage, "redis", None)
    fast_cache = FastCache(redis_client=redis_client)

    # dependency injection
    dp["remnawave"] = remnawave
    dp["session_factory"] = session_factory
    dp["cache"] = fast_cache
    bot.session_factory = session_factory
    bot.cache = fast_cache
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

    # ── Startup Single-Instance Lock (Prevents TelegramConflictError) ──
    import hashlib
    token_hash = hashlib.sha256(settings.BOT_TOKEN.encode()).hexdigest()[:12]
    lock_key = f"remnabot:instance_lock:{token_hash}"
    lock_val = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
    lock_refresh_task = None

    # 1. OS Host File Lock (Prevents multiple processes on the same host)
    lock_dir = "/app/data" if os.path.isdir("/app/data") and os.access("/app/data", os.W_OK) else tempfile.gettempdir()
    file_lock_path = os.path.join(lock_dir, f"remnabot_{token_hash}.lock")
    file_lock_fd = None
    try:
        file_lock_fd = open(file_lock_path, "a+")
        if os.name == "posix":
            import fcntl
            fcntl.flock(file_lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif os.name == "nt":
            import msvcrt
            file_lock_fd.seek(0)
            msvcrt.locking(file_lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
        file_lock_fd.seek(0)
        file_lock_fd.truncate()
        file_lock_fd.write(f"pid={os.getpid()}\ntime={int(time.time())}\n")
        file_lock_fd.flush()
    except (BlockingIOError, OSError) as flock_err:
        logger.critical(
            "STARTUP ABORTED: Another bot instance is ALREADY running on this host with the same token! "
            "(Lock file: %s, Details: %s). Stop the previous instance before starting a new one to prevent TelegramConflictError.",
            file_lock_path,
            flock_err,
        )
        if file_lock_fd:
            try:
                file_lock_fd.close()
            except Exception:
                pass
        for task in background_tasks:
            task.cancel()
        if web_runner:
            await web_runner.cleanup()
        await remnawave.close()
        await bot.session.close()
        await engine.dispose()
        return

    # 2. Redis Distributed Lock (Prevents multiple containers/nodes with same token)
    if redis_client:
        try:
            acquired = await redis_client.set(lock_key, lock_val, nx=True, ex=30)
            if not acquired:
                holder = await redis_client.get(lock_key)
                logger.critical(
                    "STARTUP ABORTED: Another bot instance is holding the active polling lock (%s)! "
                    "Ensure only ONE bot instance is running to prevent TelegramConflictError and split updates.",
                    holder,
                )
                if file_lock_fd:
                    try:
                        file_lock_fd.close()
                    except Exception:
                        pass
                for task in background_tasks:
                    task.cancel()
                if web_runner:
                    await web_runner.cleanup()
                await remnawave.close()
                await bot.session.close()
                await engine.dispose()
                return

            async def _refresh_instance_lock():
                try:
                    while True:
                        await asyncio.sleep(10)
                        current_holder = await redis_client.get(lock_key)
                        if current_holder == lock_val:
                            await redis_client.expire(lock_key, 30)
                        else:
                            logger.warning("Instance lock lost or replaced: %s", current_holder)
                            break
                except asyncio.CancelledError:
                    pass
                except Exception as ex:
                    logger.debug("Instance lock refresh exception: %s", ex)

            lock_refresh_task = asyncio.create_task(_refresh_instance_lock(), name="instance-lock-refresh")
        except Exception as lock_err:
            logger.warning("Redis instance lock unavailable (falling back gracefully): %s", lock_err)

    try:
        logger.info("Bot started.")
        # Keep pending updates: dropping them would silently lose top-up
        # receipts / support messages sent while the bot was restarting.
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        if file_lock_fd:
            try:
                if os.name == "posix":
                    import fcntl
                    fcntl.flock(file_lock_fd.fileno(), fcntl.LOCK_UN)
                elif os.name == "nt":
                    import msvcrt
                    file_lock_fd.seek(0)
                    msvcrt.locking(file_lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                file_lock_fd.close()
            except Exception:
                pass
            try:
                if os.path.exists(file_lock_path):
                    os.remove(file_lock_path)
            except Exception:
                pass
        if lock_refresh_task:
            lock_refresh_task.cancel()
        if redis_client:
            try:
                current_holder = await redis_client.get(lock_key)
                if current_holder == lock_val:
                    await redis_client.delete(lock_key)
            except Exception:
                pass
        for task in background_tasks:
            task.cancel()
        if web_runner:
            await web_runner.cleanup()
        await remnawave.close()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
