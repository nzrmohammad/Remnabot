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
from bot.services.app_settings import get_store_settings, is_maintenance
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
        elif param == "verify_phone":
            from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
            phone_kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 اشتراک‌گذاری شماره تماس من", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            )
            await message.answer(
                "🔒 <b>احراز هویت شماره همراه</b>\n\n"
                "جهت فعال‌سازی درگاه پرداخت کارت‌به‌کارت و جلوگیری از تخلفات بانکی (فیشینگ)، لطفاً با لمس دکمه زیر شماره همراه خود را تأیید نمایید:\n\n"
                "<i>(شماره شما صرفاً برای تأیید بانکی ذخیره شده و کاملاً محرمانه نزد ما محفوظ می‌ماند)</i>",
                reply_markup=phone_kb,
                parse_mode="HTML",
            )
            return

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


@router.message(F.contact)
async def handle_user_contact(
    message: Message, bot: Bot, user_repo: UserRepository, session
):
    from aiogram.types import ReplyKeyboardRemove
    if not message.contact:
        return

    # Anti-fraud verification: ensure contact belongs to this telegram user
    if message.contact.user_id != message.from_user.id:
        await message.answer(
            "⚠️ <b>خطای احراز هویت:</b> شماره تماس ارسالی باید متعلق به همین حساب تلگرام باشد و امکان ارسال شماره شخص دیگر وجود ندارد.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML",
        )
        return

    phone = message.contact.phone_number or ""
    phone = phone.strip()
    if phone and not phone.startswith("+"):
        phone = "+" + phone

    user = await user_repo.get_or_create(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    user.phone_number = phone
    await session.commit()

    await message.answer(
        f"✅ <b>شماره تماس شما با موفقیت تأیید و ثبت شد:</b>\n<code>{phone}</code>\n\n"
        "اکنون درگاه پرداخت کارت‌به‌کارت برای حساب شما فعال گردید. می‌توانید فرآیند پرداخت را در مینی‌اپ ادامه دهید.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )
