"""Service for reporting exceptions and system errors to the dedicated Error Logs topic."""
import asyncio
import contextvars
import html
import logging
import re
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

# Re-entrancy guard to 100% prevent recursive logging loops
_is_reporting_var: contextvars.ContextVar[bool] = contextvars.ContextVar("_is_reporting_var", default=False)

# In-memory resilient cache for topic_errors (persists across transient DB connection drops)
_cached_topic_errors: int | None = None
_last_topic_cached_epoch: float = 0.0


def update_cached_topic_errors(topic_id: int | None) -> None:
    """Updates the in-memory cached topic ID for error logs."""
    global _cached_topic_errors, _last_topic_cached_epoch
    if topic_id is not None:
        _cached_topic_errors = int(topic_id)
        _last_topic_cached_epoch = time.time()


def get_cached_topic_errors() -> int | None:
    """Returns the in-memory cached topic ID for error logs."""
    return _cached_topic_errors


def safe_html_truncate(html_text: str, max_chars: int = 3900) -> str:
    """Safely truncate HTML text ensuring that all opened tags are properly closed."""
    if len(html_text) <= max_chars:
        return html_text

    # Take slice allowing room for closing tags and ellipsis
    truncated = html_text[: max_chars - 30]

    # If cut mid-tag (e.g. "<pre" or "<b"), strip the incomplete tag
    last_open = truncated.rfind("<")
    last_close = truncated.rfind(">")
    if last_open > last_close:
        truncated = truncated[:last_open]

    # Supported formatting tags in Telegram HTML
    tag_pattern = re.compile(r"<\/?([a-zA-Z0-9]+)(?:\s+[^>]*)?>")
    open_tags: list[str] = []

    for match in tag_pattern.finditer(truncated):
        full_tag = match.group(0)
        tag_name = match.group(1).lower()
        if full_tag.startswith("</"):
            if open_tags and open_tags[-1] == tag_name:
                open_tags.pop()
        elif not full_tag.endswith("/>"):
            open_tags.append(tag_name)

    # Append ellipsis and close any dangling open tags in reverse order
    closing = "".join(f"</{t}>" for t in reversed(open_tags))
    return truncated + "..." + closing


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
    session_factory: async_sessionmaker | Any | None = None,
    exc: Exception | str = "",
    context: str = "",
    user_id: int | None = None,
    username: str | None = None,
    traceback_str: str | None = None,
    session: Any = None,
) -> None:
    """Dispatches a formatted error alert to the dedicated admin error topic."""
    settings = get_settings()
    if not settings.ADMIN_CHAT_ID and not settings.ADMIN_IDS:
        return

    # Error deduplication / throttle
    is_exc = isinstance(exc, Exception)
    exc_type = type(exc).__name__ if is_exc else "Error"
    exc_msg = str(exc) or "—"

    # Ignore client-side protocol/scanner noise
    if exc_type in (
        "BadHttpMessage",
        "HttpProcessingError",
        "PayloadEncodingError",
        "LineTooLong",
        "InvalidHeader",
        "ClientPayloadError",
        "ClientConnectionResetError",
        "ConnectionResetError",
        "BrokenPipeError",
    ) or "Pause on PRI/Upgrade" in exc_msg:
        return

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
        if session is not None:
            store = await get_store_settings(session)
            if store.topic_errors is not None:
                update_cached_topic_errors(store.topic_errors)
            topic_id = store.topic_errors if store.topic_errors is not None else settings.ADMIN_TOPIC_ERRORS
        elif session_factory is not None:
            if hasattr(session_factory, "execute") and not callable(session_factory):
                store = await get_store_settings(session_factory)
                if store.topic_errors is not None:
                    update_cached_topic_errors(store.topic_errors)
                topic_id = store.topic_errors if store.topic_errors is not None else settings.ADMIN_TOPIC_ERRORS
            else:
                async with session_factory() as sess:
                    store = await get_store_settings(sess)
                    if store.topic_errors is not None:
                        update_cached_topic_errors(store.topic_errors)
                    topic_id = store.topic_errors if store.topic_errors is not None else settings.ADMIN_TOPIC_ERRORS
        else:
            topic_id = _cached_topic_errors or settings.ADMIN_TOPIC_ERRORS
    except Exception as db_exc:
        logger.warning("Could not fetch topic_errors from DB, using cached fallback: %s", db_exc)
        topic_id = _cached_topic_errors or settings.ADMIN_TOPIC_ERRORS

    if topic_id is None:
        topic_id = _cached_topic_errors or settings.ADMIN_TOPIC_ERRORS

    # Format timestamp
    now = now_tz(settings.TIMEZONE)
    time_str = format_datetime(now, "fa")

    # Format traceback tail (keep safe under Telegram's 4096 char limit)
    if traceback_str:
        tb_str = traceback_str
    elif is_exc and getattr(exc, "__traceback__", None):
        try:
            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        except Exception as exc_fmt:
            logger.warning("Failed to format traceback: %s", exc_fmt)
            tb_str = ""
    else:
        tb_str = ""
    tb_tail = tb_str[-1800:] if len(tb_str) > 1800 else tb_str

    user_info = f"<code>{user_id}</code>" if user_id else "—"
    if username:
        user_info += f" (@{html.escape(username)})"

    context_info = html.escape(context[:150]) if context else "سیستم / پس‌زمینه"
    exc_msg_safe = html.escape(exc_msg[:400])

    traceback_section = (
        f"\n\n🔍 <b>ردیابی خطا (Traceback) :</b>\n<pre><code>{html.escape(tb_tail)}</code></pre>"
        if tb_tail
        else ""
    )

    raw_html = (
        "⚠️ <b>سیستم هشدار خطای ربات (Error Log)</b>\n"
        "──────────────────\n"
        f"⏰ <b>زمان :</b> {time_str}\n"
        f"📍 <b>محل وقوع :</b> {context_info}\n"
        f"👤 <b>کاربر :</b> {user_info}\n"
        f"💥 <b>کلاس خطا :</b> <code>{html.escape(exc_type)}</code>\n"
        f"📝 <b>پیام خطا :</b> <code>{exc_msg_safe}</code>"
        f"{traceback_section}"
    )

    text = safe_html_truncate(raw_html, 4000)

    plain_text = (
        "⚠️ سیستم هشدار خطای ربات (Error Log)\n"
        "──────────────────\n"
        f"⏰ زمان : {time_str}\n"
        f"📍 محل وقوع : {context[:150] or 'سیستم'}\n"
        f"👤 کاربر : {user_id or '—'}\n"
        f"💥 کلاس خطا : {exc_type}\n"
        f"📝 پیام خطا : {exc_msg[:400]}\n\n"
        f"🔍 Traceback:\n{tb_tail}"
    )[:3900]

    token = _is_reporting_var.set(True)
    try:
        thread_kwargs = admin_thread_kwargs(topic_id=topic_id)
        delivered = False

        if settings.ADMIN_CHAT_ID:
            try:
                await bot.send_message(settings.ADMIN_CHAT_ID, text, **thread_kwargs)
                delivered = True
            except Exception as send_exc:
                logger.warning(
                    "Failed sending HTML error alert to admin chat %s (topic %s): %s",
                    settings.ADMIN_CHAT_ID,
                    topic_id,
                    send_exc,
                )
                # Retry plain text with topic
                try:
                    await bot.send_message(settings.ADMIN_CHAT_ID, plain_text, parse_mode=None, **thread_kwargs)
                    delivered = True
                except Exception:
                    # Retry plain text without topic (in case topic ID is invalid)
                    try:
                        await bot.send_message(settings.ADMIN_CHAT_ID, plain_text, parse_mode=None)
                        delivered = True
                    except Exception as retry_exc:
                        logger.warning("Failed retry without thread: %s", retry_exc)

        if not delivered and settings.ADMIN_IDS:
            for aid in settings.ADMIN_IDS:
                try:
                    await bot.send_message(aid, text)
                    delivered = True
                except Exception:
                    try:
                        await bot.send_message(aid, plain_text, parse_mode=None)
                        delivered = True
                    except Exception as exc_fallback:
                        logger.warning("Failed to send error fallback to admin %s: %s", aid, exc_fallback)
    finally:
        _is_reporting_var.reset(token)


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
        self._recent_errors: dict[str, float] = {}
        self._active_tasks: set[asyncio.Task] = set()

    def emit(self, record: logging.LogRecord) -> None:
        # Check re-entrancy / infinite loop guard
        if _is_reporting_var.get():
            return

        # Prevent recursion and noise from error reporter itself or raw HTTP client
        if record.name.startswith((
            "bot.services.error_reporter",
            "aiogram.client",
            "aiohttp.access",
            "urllib3",
            "asyncio",
        )):
            return

        # Ignore shutdown / cancellation signals
        if record.exc_info and record.exc_info[0] in (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            return

        # Ignore client-side connection/parsing exceptions
        if record.exc_info and record.exc_info[0]:
            exc_name = record.exc_info[0].__name__
            if exc_name in (
                "BadHttpMessage",
                "HttpProcessingError",
                "PayloadEncodingError",
                "LineTooLong",
                "InvalidHeader",
                "ClientPayloadError",
                "ClientConnectionResetError",
                "ConnectionResetError",
                "BrokenPipeError",
            ):
                return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        if not loop.is_running():
            return

        # Throttle repetitive errors to prevent log storms
        now = time.monotonic()
        if len(self._recent_errors) > 100:
            self._recent_errors = {k: ts for k, ts in self._recent_errors.items() if now - ts < 60.0}

        dedup_key = f"{record.name}:{record.lineno}:{str(record.getMessage())[:80]}"
        last_seen = self._recent_errors.get(dedup_key)
        if last_seen and now - last_seen < 30.0:
            return
        self._recent_errors[dedup_key] = now

        # Limit concurrent alert tasks to at most 10, purging completed tasks
        self._active_tasks = {t for t in self._active_tasks if not t.done()}
        if len(self._active_tasks) >= 10:
            return

        tb_str = ""
        if record.exc_info and record.exc_info[1]:
            exc_obj: Exception | str = record.exc_info[1]
            try:
                tb_str = "".join(traceback.format_exception(*record.exc_info))
            except Exception as exc:
                logger.warning("Failed to format record exc_info: %s", exc)
                tb_str = ""
        else:
            exc_obj = record.getMessage()

        context = f"Logger: {record.name} ({record.filename}:{record.lineno})"
        task = loop.create_task(
            report_error(
                bot=self.bot,
                session_factory=self.session_factory,
                exc=exc_obj,
                context=context,
                traceback_str=tb_str,
            )
        )
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)


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
            if store.topic_errors is not None:
                update_cached_topic_errors(store.topic_errors)
            topic_id = store.topic_errors if store.topic_errors is not None else settings.ADMIN_TOPIC_ERRORS
        elif session_factory is not None:
            async with session_factory() as sess:
                store = await get_store_settings(sess)
                if store.topic_errors is not None:
                    update_cached_topic_errors(store.topic_errors)
                topic_id = store.topic_errors if store.topic_errors is not None else settings.ADMIN_TOPIC_ERRORS
        else:
            topic_id = _cached_topic_errors or settings.ADMIN_TOPIC_ERRORS
    except Exception as db_exc:
        logger.warning("Failed to fetch topic_errors from store, using cached fallback: %s", db_exc)
        topic_id = _cached_topic_errors or settings.ADMIN_TOPIC_ERRORS

    if not topic_id:
        topic_id = _cached_topic_errors or settings.ADMIN_TOPIC_ERRORS

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
        logger.warning("Failed to send test error report: %s", exc)
        return False, f"خطا در ارسال پیام به تاپیک {topic_id}: {exc}", topic_id
