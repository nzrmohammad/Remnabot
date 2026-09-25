"""Catch-all: any message that no other handler consumed gets deleted,
so the chat always stays clean and only the menu message remains.

IMPORTANT: this router must be registered LAST.
"""
from aiogram import Bot, Router
from aiogram.types import Message

from bot.services.menu import delete_message_silently

router = Router(name="cleanup")


@router.message()
async def delete_unhandled(message: Message, bot: Bot):
    await delete_message_silently(bot, message.chat.id, message.message_id)
