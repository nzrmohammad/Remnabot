"""Middleware that blocks banned users from interacting with the bot."""
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import get_settings
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t

logger = logging.getLogger(__name__)

BAN_MESSAGE = "⛔️ <b>حساب کاربری شما مسدود شده است.</b>\nجهت پیگیری با پشتیبانی در ارتباط باشید."
BAN_TOAST = "⛔️ حساب کاربری شما مسدود است."


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_obj = getattr(event, "from_user", None)
        if user_obj is None:
            return await handler(event, data)

        uid = user_obj.id
        # Admins are never blocked
        if uid in get_settings().ADMIN_IDS:
            return await handler(event, data)

        session = data.get("session")
        if session is not None:
            user = await UserRepository(session).get_by_telegram_id(uid)
            if user and user.is_banned:
                logger.warning("Blocked action from banned user %s", uid)
                lang = (user.language if user else None) or "fa"
                ban_text = t(lang, "banned_user_notice")
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer(BAN_TOAST, show_alert=True)
                    except Exception:
                        pass
                elif isinstance(event, Message):
                    try:
                        await event.answer(ban_text)
                    except Exception:
                        pass
                return None

        return await handler(event, data)
