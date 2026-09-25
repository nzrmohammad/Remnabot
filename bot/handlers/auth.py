"""Login flow: verify the user's Telegram ID against the Remnawave panel."""
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from bot.config import get_settings
from bot.db.repositories.user_repo import UserRepository
from bot.keyboards.inline import back_keyboard, main_menu_keyboard
from bot.locales.texts import t
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient

router = Router(name="auth")


@router.callback_query(F.data == "auth:login")
async def login(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    exists = await remnawave.telegram_id_exists(call.from_user.id)

    if exists is None:
        # Panel is down — don't touch is_verified, just show retry message.
        await render_menu(
            bot, user, user_repo,
            t(lang, "stats_error"),
            back_keyboard(lang, target="nav:welcome"),
        )
    elif exists:
        await user_repo.set_verified(user, True)
        is_admin = call.from_user.id in get_settings().ADMIN_IDS
        await render_menu(
            bot, user, user_repo,
            t(lang, "main_menu_title"),
            main_menu_keyboard(lang, is_admin),
        )
    else:
        # edit the SAME message: error + back button
        await render_menu(
            bot, user, user_repo,
            t(lang, "login_failed"),
            back_keyboard(lang, target="nav:welcome"),
        )
    await call.answer()
