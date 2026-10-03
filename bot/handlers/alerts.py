"""Buttons under the automatic alert messages.

Tapping «کیف پول» or «سرویس‌ها» deletes the alert message and opens
that section in the user's clean menu message.
"""
import contextlib

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.keyboards.inline import back_to_menu_keyboard
from bot.locales.texts import t
from bot.services.menu import render_menu
from bot.services.render import render_services, render_wallet

router = Router(name="alerts")

SECTION_TITLES = {
    "wallet": "btn_wallet",
    "services": "btn_services",
}


@router.callback_query(F.data.startswith("alert:goto:"))
async def alert_goto(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session,
):
    section = call.data.rsplit(":", 1)[1]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)

    # remove the alert message itself
    with contextlib.suppress(TelegramBadRequest):
        await call.message.delete()

    if section == "services":
        await render_services(bot, user, user_repo, session)
    elif section == "wallet":
        await render_wallet(
            bot, user, user_repo, WalletRepository(session), user.language
        )
    else:
        title = t(user.language or "fa", SECTION_TITLES.get(section, "main_menu_title"))
        await render_menu(
            bot, user, user_repo,
            t(user.language or "fa", "section_placeholder", section=title),
            back_to_menu_keyboard(user.language or "fa"),
        )
    await call.answer()
