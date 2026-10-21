from bot.web.user_common import db_session, require_user
"""Support chat message endpoints for Telegram Mini App."""
from html import escape
import logging
import time
from datetime import datetime

from aiohttp import web

from bot.common import admin_thread_kwargs
from bot.db.repositories.support_repo import SupportMessageRepository
from bot.services.app_settings import get_store_settings
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def get_user_support_messages(request: web.Request) -> web.Response:
    """Fetch existing chat messages for authenticated user from support Redis thread."""
    user_auth, err = require_user(request)
    if err or not user_auth:
        return err or web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    telegram_id = int(user_auth["id"])
    cache: FastCache = request.app["cache"]
    chat_key = f"support:chat:{telegram_id}"
    messages = await cache.get(chat_key) or []
    return web.json_response({"ok": True, "messages": messages})


async def post_user_support_message(request: web.Request) -> web.Response:
    """Send user message from TMA chat modal directly to Telegram support group/admin."""
    user_auth, err = require_user(request)
    if err or not user_auth:
        return err or web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    telegram_id = int(user_auth["id"])
    try:
        body = await request.json()
    except Exception:
        body = {}

    text = str(body.get("text") or "").strip()
    if not text:
        return web.json_response({"ok": False, "error": "متن پیام نمی‌تواند خالی باشد."}, status=400)

    now_ts = int(time.time())
    now_dt = datetime.fromtimestamp(now_ts)
    msg_id = f"user_{int(now_ts * 1000)}"

    user_msg = {
        "id": msg_id,
        "sender": "user",
        "text": text,
        "created_at": now_dt.strftime("%H:%M"),
        "timestamp": now_ts,
    }

    cache: FastCache = request.app["cache"]
    chat_key = f"support:chat:{telegram_id}"
    messages = await cache.get(chat_key) or []
    messages.append(user_msg)
    if len(messages) > 50:
        messages = messages[-50:]
    await cache.set(chat_key, messages, ttl_seconds=86400 * 30)

    active_ids = await cache.get("support:active_thread_ids") or []
    if telegram_id not in active_ids:
        active_ids.insert(0, telegram_id)
        if len(active_ids) > 100:
            active_ids = active_ids[:100]
        await cache.set("support:active_thread_ids", active_ids, ttl_seconds=86400 * 30)

    # Forward to Telegram admin chat
    bot = request.app.get("bot")
    settings = request.app.get("settings")
    if bot and settings and getattr(settings, "ADMIN_CHAT_ID", None):
        user_name = user_auth.get("first_name") or user_auth.get("username") or "کاربر"
        header = (
            f"💬 <b>پیام پشتیبانی از مینی‌اپ:</b>\n"
            f"👤 <b>کاربر:</b> {escape(user_name)} (<code>{telegram_id}</code>)\n\n"
            f"{escape(text)}"
        )
        try:
            async with db_session(request) as session:
                store = await get_store_settings(session)
                thread_kwargs = admin_thread_kwargs(store, settings, kind="support")
            sent_msg = await bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=header,
                parse_mode="HTML",
                **thread_kwargs,
            )
            async with db_session(request) as session:
                repo = SupportMessageRepository(session)
                await repo.map_message(sent_msg.message_id, telegram_id)
                await session.commit()
        except Exception as exc:
            logger.warning("Failed to forward support message to admin chat: %s", exc)

    return web.json_response({"ok": True, "message": user_msg})
