"""Service for reporting exceptions and system errors to the dedicated Error Logs topic."""
import asyncio
import html
import logging
import time
import traceback
from typing import Any

from aiogram import Bot
from aiogram.types import ErrorEvent, Update
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.common import admin_thread_kwargs
from bot.config import get_settings
from bot.services.app_settings import get_store_settings
from bot.services.formatting import format_datetime, now_tz

logger = logging.getLogger(__name__)

# Error throttle: error_signature -> last_sent_epoch
_recent_errors: dict[str, float] = {}
THROTTLE_SECONDS = 30.0


def _clean_cache() -> None:
    now = time.time()
    for sig, ts in list(_recent_errors.items()):
        if now - ts > 300:
            _recent_errors.pop(sig, None)


async def report_error(
    bot: Bot,
    session_factory: async_sessionmaker,
    exc: Exception | str,
    context: str = "",
    user_id: int | None = None,
    username: str | None = None,
    traceback_str: str | None = None,
) -> None:
    """Dispatches a formatted error alert to the dedicated admin error topic."""
    settings = get_settings()
    if not settings.ADMIN_CHAT_ID:
        return

    # Error deduplication / throttle
    is_exc = isinstance(exc, Exception)
    exc_type = type(exc).__name__ if is_exc else "Error"
    exc_msg = str(exc) or "—"
    sig = f"{exc_type}:{exc_msg[:80]}:{context[:50]}"
    now_epoch = time.time()
    last_sent = _recent_errors.get(sig, 0.0)
    if now_epoch - last_sent < THROTTLE_SECONDS:
        logger.debug("Suppressing duplicate error report: %s", sig)
        return
    _recent_errors[sig] = now_epoch
    _clean_cache()

    topic_id = None
    try:
        async with session_factory() as session:
            store = await get_store_settings(session)
            topic_id = store.topic_errors if store.topic_errors is not None else settings.ADMIN_TOPIC_ERRORS
    except Exception as db_exc:
        logger.warning("Could not fetch topic_errors from DB: %s", db_exc)
        topic_id = settings.ADMIN_TOPIC_ERRORS

    # Format timestamp
    now = now_tz(settings.TIMEZONE)
    time_str = format_datetime(now, "fa")

    # Format traceback tail
    if traceback_str:
        tb_str = traceback_str
    elif is_exc and getattr(exc, "__traceback__", None):
        try:
            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        except Exception:
            tb_str = ""
    else:
        tb_str = ""
    tb_tail = tb_str[-1800:] if len(tb_str) > 1800 else tb_str

    user_info = f"<code>{user_id}</code>" if user_id else "—"
    if username:
        user_info += f" (@{html.escape(username)})"

    context_info = html.escape(context) if context else "سیستم / پس‌زمینه"
    traceback_section = (
        f"\n\n🔍 <b>ردیابی خطا (Traceback) :</b>\n<pre><code>{html.escape(tb_tail)}</code></pre>"
        if tb_tail
        else ""
    )

    text = (
        "⚠️ <b>سیستم هشدار خطای ربات (Error Log)</b>\n"
        "──────────────────\n"
        f"⏰ <b>زمان :</b> {time_str}\n"
        f"📍 <b>محل وقوع :</b> {context_info}\n"
        f"👤 <b>کاربر :</b> {user_info}\n"
        f"💥 <b>کلاس خطا :</b> <code>{html.escape(exc_type)}</code>\n"
        f"📝 <b>پیام خطا :</b> <code>{html.escape(exc_msg[:400])}</code>"
        f"{traceback_section}"
    )

    thread_kwargs = admin_thread_kwargs(topic_id=topic_id)
    delivered = False

    try:
        await bot.send_message(settings.ADMIN_CHAT_ID, text, **thread_kwargs)
        delivered = True
    except Exception as send_exc:
        logger.warning(
            "Failed sending error alert to admin chat %s (topic %s): %s",
            settings.ADMIN_CHAT_ID,
            topic_id,
            send_exc,
        )
        if thread_kwargs:
            try:
                await bot.send_message(settings.ADMIN_CHAT_ID, text)
                delivered = True
            except Exception as retry_exc:
                logger.warning("Failed retry without thread: %s", retry_exc)

    if not delivered and settings.ADMIN_IDS:
        for aid in settings.ADMIN_IDS:
            try:
                await bot.send_message(aid, text)
            except Exception:
                pass


async def report_error_event(
    bot: Bot,
    session_factory: async_sessionmaker,
    event: ErrorEvent,
) -> None:
    """Helper to report an unhandled aiogram ErrorEvent."""
    exc = event.exception
    update: Update | None = event.update
    user_id: int | None = None
    username: str | None = None
    context = "Unhandled Update"

    if update:
        if update.message:
            u = update.message.from_user
            if u:
                user_id = u.id
                username = u.username
            context = f"Message: {update.message.text[:40]}" if update.message.text else "Message"
        elif update.callback_query:
            u = update.callback_query.from_user
            if u:
                user_id = u.id
                username = u.username
            context = f"Callback: {update.callback_query.data}"
        elif update.inline_query:
            u = update.inline_query.from_user
            if u:
                user_id = u.id
                username = u.username
            context = "Inline Query"

    await report_error(
        bot=bot,
        session_factory=session_factory,
        exc=exc,
        context=context,
        user_id=user_id,
        username=username,
    )


class TelegramErrorLogHandler(logging.Handler):
    """Logging handler that forwards ERROR and CRITICAL logs directly to the Telegram error topic."""

    def __init__(self, bot: Bot, session_factory: async_sessionmaker) -> None:
        super().__init__(level=logging.ERROR)
        self.bot = bot
        self.session_factory = session_factory

    def emit(self, record: logging.LogRecord) -> None:
        # Prevent recursion and loop storms
        if record.name.startswith((
            "bot.services.error_reporter",
            "aiogram",
            "aiohttp.access",
            "urllib3",
            "asyncio",
        )):
            return

        # Ignore shutdown / cancellation signals
        if record.exc_info and record.exc_info[0] in (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        if not loop.is_running():
            return

        tb_str = ""
        if record.exc_info and record.exc_info[1]:
            exc_obj: Exception | str = record.exc_info[1]
            try:
                tb_str = "".join(traceback.format_exception(*record.exc_info))
            except Exception:
                tb_str = ""
        else:
            exc_obj = record.getMessage()

        context = f"Logger: {record.name} ({record.filename}:{record.lineno})"
        loop.create_task(
            report_error(
                bot=self.bot,
                session_factory=self.session_factory,
                exc=exc_obj,
                context=context,
                traceback_str=tb_str,
            )
        )


def setup_telegram_error_logging(bot: Bot, session_factory: async_sessionmaker) -> TelegramErrorLogHandler:
    """Attaches TelegramErrorLogHandler to the root logger to capture all system errors."""
    handler = TelegramErrorLogHandler(bot, session_factory)
    logging.getLogger().addHandler(handler)
    return handler


async def send_test_error_report(
    bot: Bot,
    session_factory: async_sessionmaker | None = None,
    session: Any = None,
) -> tuple[bool, str, int | None]:
    """Sends a test log message to verify topic configuration.
    Returns (success, message, topic_id).
    """
    settings = get_settings()
    if not settings.ADMIN_CHAT_ID:
        return False, "ADMIN_CHAT_ID در تنظیمات ربات خالی است.", None

    topic_id = None
    try:
        if session is not None:
            store = await get_store_settings(session)
            topic_id = store.topic_errors if store.topic_errors is not None else settings.ADMIN_TOPIC_ERRORS
        elif session_factory is not None:
            async with session_factory() as sess:
                store = await get_store_settings(sess)
                topic_id = store.topic_errors if store.topic_errors is not None else settings.ADMIN_TOPIC_ERRORS
        else:
            topic_id = settings.ADMIN_TOPIC_ERRORS
    except Exception as db_exc:
        topic_id = settings.ADMIN_TOPIC_ERRORS

    if not topic_id:
        return False, "شناسه تاپیک لاگ‌های ارور (topic_errors) هنوز تنظیم نشده است.", None

    now = now_tz(settings.TIMEZONE)
    time_str = format_datetime(now, "fa")

    text = (
        "🧪 <b>تست موفق اتصال به تاپیک لاگ‌های ارور</b>\n"
        "──────────────────\n"
        f"⏰ <b>زمان :</b> {time_str}\n"
        f"📌 <b>شناسه تاپیک :</b> <code>{topic_id}</code>\n"
        f"🤖 <b>وضعیت ربات :</b> دسترسی ارسال پیام در این تاپیک تایید شد ✅\n\n"
        "از این پس تمام خطاها، کرش‌ها و استثنائات سیستمی در این تاپیک ثبت خواهند شد."
    )

    thread_kwargs = admin_thread_kwargs(topic_id=topic_id)
    try:
        await bot.send_message(settings.ADMIN_CHAT_ID, text, **thread_kwargs)
        return True, f"پیام تست با موفقیت به تاپیک {topic_id} ارسال شد ✅", topic_id
    except Exception as exc:
        return False, f"خطا در ارسال پیام به تاپیک {topic_id}: {exc}", topic_id
