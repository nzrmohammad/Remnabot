"""Main menu + section navigation.

Every section currently shows a placeholder that you can replace with
real logic later — each one is a separate handler, so extending the
bot means editing exactly one function (or moving it to its own module).
"""
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.config import get_settings
from bot.db.repositories.user_repo import UserRepository
from bot.keyboards.inline import back_to_menu_keyboard, main_menu_keyboard
from bot.locales.texts import t
from bot.services.menu import render_menu

router = Router(name="main_menu")

# callback suffix -> locale key of the section title
# "stats" is handled by handlers/stats.py (registered before this router)
SECTIONS = {
    "account": "btn_account_mgmt",
    "wallet": "btn_wallet",
    "services": "btn_services",
    "guide": "btn_connection_guide",
    "settings": "btn_settings",
    "support": "btn_support",
    "profile": "btn_profile",
}


@router.callback_query(F.data == "nav:main_menu")
async def show_main_menu(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language
    is_admin = call.from_user.id in get_settings().ADMIN_IDS
    await render_menu(
        bot, user, user_repo,
        t(lang, "main_menu_title"),
        main_menu_keyboard(lang, is_admin),
    )
    await call.answer()


@router.callback_query(F.data.startswith("menu:"))
async def open_section(call: CallbackQuery, bot: Bot, user_repo: UserRepository):
    section = call.data.split(":", 1)[1]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    if section == "admin":
        if call.from_user.id not in get_settings().ADMIN_IDS:
            await call.answer(t(lang, "not_authorized"), show_alert=True)
            return
        title = t(lang, "btn_admin_panel")
    else:
        title = t(lang, SECTIONS.get(section, "main_menu_title"))

    await render_menu(
        bot, user, user_repo,
        t(lang, "section_placeholder", section=title),
        back_to_menu_keyboard(lang),
    )
    await call.answer()
