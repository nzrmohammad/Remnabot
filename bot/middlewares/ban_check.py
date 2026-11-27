"""Middleware that blocks banned users from interacting with the bot."""
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineQuery, Message, TelegramObject, Update

from bot.config import get_settings
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t

logger = logging.getLogger(__name__)

BAN_MESSAGE = "⛔️ <b>حساب کاربری شما مسدود شده است.</b>\nجهت پیگیری با پشتیبانی در ارتباط باشید."
BAN_TOAST = "⛔️ حساب کاربری شما مسدود است."


def _extract_user_and_event(
    event: TelegramObject, data: dict[str, Any]
) -> tuple[Any, TelegramObject]:
    """Extract acting Telegram User and replyable inner event from Update or direct event."""
    inner = event
    if isinstance(event, Update):
        inner = (
            event.message
            or event.edited_message
            or event.callback_query
            or event.inline_query
            or event.chosen_inline_result
            or event.pre_checkout_query
            or event.shipping_query
            or event
        )
    user_obj = (
        getattr(inner, "from_user", None)
        or getattr(event, "from_user", None)
        or data.get("event_from_user")
    )
    return user_obj, inner


class BanCheckMiddleware(BaseMiddleware):
    @staticmethod
    async def _send_banned_reply(reply_event: TelegramObject, lang: str) -> None:
        ban_text = t(lang, "banned_user_notice")
        if isinstance(reply_event, CallbackQuery):
            try:
                await reply_event.answer(BAN_TOAST, show_alert=True)
            except Exception:
                pass
        elif isinstance(reply_event, Message):
            try:
                await reply_event.answer(ban_text)
            except Exception:
                pass
        elif isinstance(reply_event, InlineQuery):
            try:
                await reply_event.answer([], cache_time=30, is_personal=True)
            except Exception:
                pass

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_obj, reply_event = _extract_user_and_event(event, data)
        if user_obj is None:
            return await handler(event, data)

        uid = user_obj.id
        # Admins are never blocked
        if uid in get_settings().ADMIN_IDS:
            return await handler(event, data)

        cache = data.get("cache") or getattr(data.get("bot"), "cache", None)
        ban_cache_key = f"user:ban:{uid}"
        if cache and hasattr(cache, "get"):
            try:
                cached = await cache.get(ban_cache_key)
                if cached == "0" or cached == 0:
                    return await handler(event, data)
                if isinstance(cached, dict) and cached.get("b"):
                    await self._send_banned_reply(reply_event, cached.get("l") or "fa")
                    return None
                if cached in ("1", 1, True):
                    await self._send_banned_reply(reply_event, "fa")
                    return None
            except Exception:
                pass

        session = data.get("session")
        if session is not None:
            user = await UserRepository(session).get_by_telegram_id(uid)
            is_banned = bool(user and user.is_banned)
            lang = (user.language if user else None) or "fa"
            if cache and hasattr(cache, "set") and user is not None:
                try:
                    val: Any = {"b": True, "l": lang} if is_banned else "0"
                    await cache.set(ban_cache_key, val, ttl_seconds=60)
                except Exception:
                    pass
            if is_banned:
                logger.warning("Blocked action from banned user %s", uid)
                await self._send_banned_reply(reply_event, lang)
                return None

        return await handler(event, data)
