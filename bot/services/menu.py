"""Single-message ("clean menu") helpers.

The bot keeps exactly ONE menu message per chat and always edits it.
Any message the user sends is deleted after processing.
"""
import asyncio
import contextlib
import logging
import re
from html.parser import HTMLParser

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup, Message

from bot.db.models import User
from bot.db.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)

_VOID_HTML_TAGS = frozenset({"br", "hr", "img"})


class _OpenHtmlTagTracker(HTMLParser):
    """Track unclosed formatting tags so truncated Telegram HTML never raises entity parse errors."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tl = tag.lower()
        if tl not in _VOID_HTML_TAGS:
            self.stack.append(tl)

    def handle_endtag(self, tag: str) -> None:
        tl = tag.lower()
        for idx in range(len(self.stack) - 1, -1, -1):
            if self.stack[idx] == tl:
                del self.stack[idx]
                break


def _truncate_telegram_html(text: str, limit: int = 4000) -> str:
    """Safely truncate HTML text without cutting tags/entities mid-token or leaving open tags."""
    if len(text) <= limit:
        return text
    cutoff = max(0, limit - 20)
    truncated = re.sub(r"<[^>]*$", "", text[:cutoff])
    truncated = re.sub(r"&[a-zA-Z0-9#]{0,8}$", "", truncated)
    tracker = _OpenHtmlTagTracker()
    try:
        tracker.feed(truncated)
    except Exception:
        tracker.stack.clear()
    closing = "".join(f"</{tag}>" for tag in reversed(tracker.stack))
    return f"{truncated}{closing}\n..."


async def delete_message_silently(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if message_id is None:
        return
    with contextlib.suppress(TelegramBadRequest, TelegramForbiddenError):
        await bot.delete_message(chat_id=chat_id, message_id=message_id)


async def render_menu(
    bot: Bot,
    user: User,
    user_repo: UserRepository,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit the stored menu message; if it no longer exists, send a fresh one."""
    text = _truncate_telegram_html(text, limit=4000)

    if user.menu_message_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=user.telegram_id,
                message_id=user.menu_message_id,
                text=text,
                reply_markup=reply_markup,
            )
            return
        except TelegramForbiddenError:
            logger.debug("Cannot edit menu for %s: user blocked bot", user.telegram_id)
            return
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            with contextlib.suppress(Exception):
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

    try:
        msg: Message = await bot.send_message(
            chat_id=user.telegram_id, text=text, reply_markup=reply_markup
        )
        await user_repo.set_menu_message_id(user, msg.message_id)
    except TelegramForbiddenError:
        logger.debug("Cannot send menu to %s: user blocked bot", user.telegram_id)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        try:
            msg = await bot.send_message(
                chat_id=user.telegram_id, text=text, reply_markup=reply_markup
            )
            await user_repo.set_menu_message_id(user, msg.message_id)
        except TelegramForbiddenError:
            logger.debug("Cannot send menu to %s after retry: user blocked bot", user.telegram_id)


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
    text = _truncate_telegram_html(text, limit=4000)
    await delete_message_silently(bot, user.telegram_id, user.menu_message_id)
    try:
        msg = await bot.send_message(
            chat_id=user.telegram_id, text=text, reply_markup=reply_markup
        )
        await user_repo.set_menu_message_id(user, msg.message_id)
    except TelegramForbiddenError:
        logger.debug("Cannot reset menu for %s: user blocked bot", user.telegram_id)


async def show(
    bot: Bot,
    user: User,
    user_repo: UserRepository,
    lines: str | list[str] | tuple[str, ...],
    kb: InlineKeyboardMarkup | None = None,
) -> None:
    """Convenience helper to render menu from a text string or list of lines joined by newline."""
    text = "\n".join(lines) if isinstance(lines, (list, tuple)) else str(lines)
    await render_menu(bot, user, user_repo, text, kb)

