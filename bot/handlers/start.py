""" /start command + language selection + welcome screen navigation."""
from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import get_settings
from bot.db.repositories.user_repo import UserRepository
from bot.keyboards.inline import (
    language_keyboard,
    main_menu_keyboard,
    welcome_keyboard,
)
from bot.locales.texts import CHOOSE_LANGUAGE, MAINTENANCE_NOTICE, t
from bot.services.menu import render_menu, reset_menu

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message, bot: Bot, user_repo: UserRepository,
    session, state: FSMContext,
):
    await state.clear()

    # Maintenance mode: new users cannot register.
    existing = await user_repo.get_by_telegram_id(message.from_user.id)
    if existing is None:
        from bot.services.app_settings import is_maintenance
        if await is_maintenance(session):
            await message.answer(MAINTENANCE_NOTICE)
            return

    user = await user_repo.get_or_create(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
    )

    # Referral link extraction: /start ref_123456 (do not delete the /start message)
    text = message.text or ""
    parts = text.split()
    if len(parts) > 1 and parts[1].startswith("ref_"):
        ref_raw = parts[1].removeprefix("ref_")
        if ref_raw.isdigit():
            inviter_id = int(ref_raw)
            if inviter_id != message.from_user.id and getattr(user, "referred_by_id", None) is None:
                await user_repo.set_referrer(user, inviter_id)

    # fresh menu message at the bottom of the chat
    if not user.language:
        await reset_menu(bot, user, user_repo, CHOOSE_LANGUAGE, language_keyboard())
    elif user.is_verified:
        is_admin = message.from_user.id in get_settings().ADMIN_IDS
        await reset_menu(
            bot, user, user_repo,
            t(user.language, "main_menu_title"),
            main_menu_keyboard(user.language, is_admin),
        )
    else:
        await reset_menu(
            bot, user, user_repo,
            t(user.language, "welcome"),
            welcome_keyboard(user.language),
        )


@router.callback_query(F.data.startswith("lang:"))
async def choose_language(call: CallbackQuery, bot: Bot, user_repo: UserRepository):
    lang = call.data.split(":", 1)[1]
    if lang not in ("fa", "en"):
        await call.answer()
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    had_lang = bool(user.language)
    was_verified = bool(user.is_verified)
    await user_repo.set_language(user, lang)

    if had_lang:
        # Language switch from settings → back to main menu, not welcome.
        is_admin = call.from_user.id in get_settings().ADMIN_IDS
        if was_verified:
            await render_menu(
                bot, user, user_repo,
                t(lang, "main_menu_title"),
                main_menu_keyboard(lang, is_admin),
            )
        else:
            await render_menu(bot, user, user_repo, t(lang, "welcome"), welcome_keyboard(lang))
        await call.answer(t(lang, "settings_saved"))
        return

    await render_menu(bot, user, user_repo, t(lang, "welcome"), welcome_keyboard(lang))
    await call.answer()


@router.callback_query(F.data == "nav:welcome")
async def back_to_welcome(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language
    if user.is_verified:
        is_admin = call.from_user.id in get_settings().ADMIN_IDS
        await render_menu(
            bot, user, user_repo,
            t(lang, "main_menu_title"),
            main_menu_keyboard(lang, is_admin),
        )
    else:
        await render_menu(bot, user, user_repo, t(lang, "welcome"), welcome_keyboard(lang))
    await call.answer()
