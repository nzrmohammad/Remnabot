"""Service for reporting exceptions and system errors to the dedicated Error Logs topic."""
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
    exc: Exception,
    context: str = "",
    user_id: int | None = None,
    username: str | None = None,
) -> None:
    """Dispatches a formatted error alert to the dedicated admin error topic."""
    settings = get_settings()
    if not settings.ADMIN_CHAT_ID:
        return

    # Error deduplication / throttle
    exc_type = type(exc).__name__
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
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    tb_tail = tb_str[-1800:] if len(tb_str) > 1800 else tb_str

    user_info = f"<code>{user_id}</code>" if user_id else "—"
    if username:
        user_info += f" (@{html.escape(username)})"

    context_info = html.escape(context) if context else "سیستم / پس‌زمینه"

    text = (
        "⚠️ <b>سیستم هشدار خطای ربات (Error Log)</b>\n"
        "──────────────────\n"
        f"⏰ <b>زمان :</b> {time_str}\n"
        f"📍 <b>محل وقوع :</b> {context_info}\n"
        f"👤 <b>کاربر :</b> {user_info}\n"
        f"💥 <b>کلاس خطا :</b> <code>{html.escape(exc_type)}</code>\n"
        f"📝 <b>پیام خطا :</b> <code>{html.escape(exc_msg[:300])}</code>\n\n"
        "🔍 <b>ردیابی خطا (Traceback) :</b>\n"
        f"<pre><code>{html.escape(tb_tail)}</code></pre>"
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
