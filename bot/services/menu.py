"""Single-message ("clean menu") helpers.

The bot keeps exactly ONE menu message per chat and always edits it.
Any message the user sends is deleted after processing.
"""
import contextlib
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

from bot.db.models import User
from bot.db.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)


async def delete_message_silently(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if message_id is None:
        return
    with contextlib.suppress(TelegramBadRequest):
        await bot.delete_message(chat_id=chat_id, message_id=message_id)


async def render_menu(
    bot: Bot,
    user: User,
    user_repo: UserRepository,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit the stored menu message; if it no longer exists, send a fresh one."""
    if user.menu_message_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=user.telegram_id,
                message_id=user.menu_message_id,
                text=text,
                reply_markup=reply_markup,
            )
            return
        except TelegramBadRequest as exc:
            # "message is not modified" → nothing to do
            if "message is not modified" in str(exc):
                return
            # message was deleted / too old → fall through and resend

    msg: Message = await bot.send_message(
        chat_id=user.telegram_id, text=text, reply_markup=reply_markup
    )
    await user_repo.set_menu_message_id(user, msg.message_id)


async def reset_menu(
    bot: Bot,
    user: User,
    user_repo: UserRepository,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Delete the old menu message (if any) and send a brand-new one.

    Used on /start so the menu is always the latest message in the chat.
    """
    await delete_message_silently(bot, user.telegram_id, user.menu_message_id)
    msg = await bot.send_message(
        chat_id=user.telegram_id, text=text, reply_markup=reply_markup
    )
    await user_repo.set_menu_message_id(user, msg.message_id)
