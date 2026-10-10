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
from bot.locales.texts import CHOOSE_LANGUAGE, INVITE_ONLY_NOTICE, MAINTENANCE_NOTICE, t
from bot.services.menu import render_menu, reset_menu

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message, bot: Bot, user_repo: UserRepository,
    session, state: FSMContext,
):
    await state.clear()

    # Maintenance mode & Access mode checks:
    existing = await user_repo.get_by_telegram_id(message.from_user.id)
    is_admin = message.from_user.id in get_settings().ADMIN_IDS

    if not is_admin:
        from bot.services.app_settings import get_store_settings, is_maintenance
        if await is_maintenance(session):
            await message.answer(MAINTENANCE_NOTICE)
            return

        store_settings = await get_store_settings(session)
        if getattr(store_settings, "access_mode", "open") == "invite_only" and existing is None:
            text_check = message.text or ""
            parts_check = text_check.split()
            has_invite = False
            if len(parts_check) > 1:
                param = parts_check[1]
                if param.startswith("ref_") or param.startswith("ad_") or param.startswith("inv_"):
                    has_invite = True
            if not has_invite:
                await message.answer(INVITE_ONLY_NOTICE)
                return

    user = await user_repo.get_or_create(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    # Referral & Campaign deep link extraction: /start ref_123456 or /start ad_mychannel
    text = message.text or ""
    parts = text.split()
    if len(parts) > 1:
        param = parts[1]
        if param.startswith("ref_"):
            ref_raw = param.removeprefix("ref_")
            if ref_raw.isdigit():
                inviter_id = int(ref_raw)
                if inviter_id != message.from_user.id and getattr(user, "referred_by_id", None) is None:
                    await user_repo.set_referrer(user, inviter_id)
        elif param.startswith("ad_"):
            ad_code = param.removeprefix("ad_").strip().lower()
            if ad_code and getattr(user, "campaign_code", None) is None:
                await user_repo.set_campaign(user, ad_code)

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
