""" /start command + language selection + welcome screen navigation."""
import contextlib
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message, ReplyKeyboardRemove
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from bot.common.helpers import format_channel_link, matches_channel
from bot.config import get_settings
from bot.db.models import Campaign, GiftCard
from bot.db.repositories.user_repo import UserRepository
from bot.handlers.auth import try_auto_verify_from_panel
from bot.keyboards.inline import (
    language_keyboard,
    main_menu_keyboard,
    welcome_keyboard,
)
from bot.locales.texts import CHOOSE_LANGUAGE, INVITE_ONLY_NOTICE, MAINTENANCE_NOTICE, t
from bot.services.app_settings import get_store_settings, is_maintenance
from bot.services.menu import render_menu, reset_menu
from bot.web.user_common import format_support_link

router = Router(name="start")


async def _render_verified_or_welcome(
    bot: Bot,
    user,
    user_repo: UserRepository,
    is_admin: bool,
    remnawave=None,
    *,
    use_reset: bool = False,
) -> None:
    """Auto-verify against Remnawave in background and route straight to main menu when present."""
    verified = await try_auto_verify_from_panel(user, user_repo, remnawave)
    presenter = reset_menu if use_reset else render_menu
    if verified:
        await presenter(
            bot,
            user,
            user_repo,
            t(user.language, "main_menu_title"),
            main_menu_keyboard(user.language, is_admin),
        )
    else:
        await presenter(
            bot,
            user,
            user_repo,
            t(user.language, "welcome"),
            welcome_keyboard(user.language),
        )


@router.message(CommandStart())
async def cmd_start(
    message: Message, bot: Bot, user_repo: UserRepository,
    session, state: FSMContext, remnawave=None, cache=None,
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
                if param.startswith("ref_"):
                    ref_raw = param.removeprefix("ref_")
                    if ref_raw.isdigit() and int(ref_raw) != message.from_user.id:
                        inviter = await user_repo.get_by_telegram_id(int(ref_raw))
                        if inviter is not None and not getattr(inviter, "is_banned", False):
                            has_invite = True
                elif param.startswith("ad_"):
                    ad_code = param.removeprefix("ad_").strip().lower()
                    if ad_code:
                        camp_row = (
                            await session.execute(select(Campaign.id).where(Campaign.code == ad_code))
                        ).scalar_one_or_none()
                        if camp_row is not None:
                            has_invite = True
                elif param.startswith("gift_"):
                    gift_code = param.removeprefix("gift_").strip().upper()
                    if gift_code:
                        gift_row = (
                            await session.execute(
                                select(GiftCard).where(GiftCard.code == gift_code, GiftCard.is_claimed.is_(False))
                            )
                        ).scalar_one_or_none()
                        if gift_row is not None and gift_row.sender_telegram_id != message.from_user.id:
                            if gift_row.delivery_type != "DIRECT":
                                has_invite = True
                            elif gift_row.receiver_telegram_id and gift_row.receiver_telegram_id == message.from_user.id:
                                has_invite = True
                            elif (
                                not gift_row.receiver_telegram_id
                                and gift_row.receiver_username
                                and message.from_user.username
                                and gift_row.receiver_username.lstrip("@").strip().lower()
                                == message.from_user.username.lstrip("@").strip().lower()
                            ):
                                has_invite = True
            if not has_invite:
                from aiogram.utils.keyboard import InlineKeyboardBuilder
                kb = InlineKeyboardBuilder()
                raw_contact = (getattr(store_settings, "support_contact", "") or "").strip()
                support_url = format_support_link(raw_contact)
                if support_url:
                    kb.button(text="🎧 ارتباط با پشتیبانی", url=support_url)
                await message.answer(INVITE_ONLY_NOTICE, reply_markup=kb.as_markup() if support_url else None)
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
                    inviter_obj = await user_repo.get_by_telegram_id(inviter_id)
                    if inviter_obj is not None and not getattr(inviter_obj, "is_banned", False):
                        await user_repo.set_referrer(user, inviter_id)
        elif param.startswith("ad_"):
            ad_code = param.removeprefix("ad_").strip().lower()
            if ad_code and getattr(user, "campaign_code", None) is None:
                camp_exists = (
                    await session.execute(select(Campaign.id).where(Campaign.code == ad_code))
                ).scalar_one_or_none()
                if camp_exists is not None:
                    await user_repo.set_campaign(user, ad_code)
        elif param.startswith("gift_"):
            gift_code = param.removeprefix("gift_").strip().upper()
            from bot.services.gift_service import claim_gift
            session_factory = getattr(bot, "session_factory", None)
            cache_obj = cache or getattr(bot, "cache", None)
            res = await claim_gift(
                session=session,
                code=gift_code,
                claimer_telegram_id=message.from_user.id,
                claimer_username=message.from_user.username,
                remnawave=remnawave,
                bot=bot,
                session_factory=session_factory,
                cache=cache_obj,
            )
            if res.get("ok"):
                sub_url = res.get("subscription_url")
                kb = None
                if sub_url:
                    from aiogram.utils.keyboard import InlineKeyboardBuilder
                    builder = InlineKeyboardBuilder()
                    builder.button(text="🚀 اتصال به اشتراک / دریافت کانفیگ", url=sub_url)
                    kb = builder.as_markup()
                await message.answer(
                    f"🎁 <b>هدیه با موفقیت فعال شد!</b>\n\n"
                    f"👤 از طرف: <b>{escape(str(res.get('sender_name') or 'دوست شما'))}</b>\n"
                    f"✨ {res.get('message')}\n\n"
                    "از همراهی شما بسیار خوشحالیم! ❤️",
                    reply_markup=kb,
                    parse_mode="HTML",
                )
            else:
                await message.answer(
                    f"⚠️ <b>خطا در دریافت هدیه:</b>\n{escape(str(res.get('message', 'کارت هدیه نامعتبر است.')))}",
                    parse_mode="HTML"
                )
        elif param == "verify_phone":
            from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
            phone_kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 اشتراک‌گذاری شماره تماس من", request_contact=True)]],
                resize_keyboard=True,
                is_persistent=True,
                one_time_keyboard=False,
            )
            await message.answer(
                "🔒 <b>احراز هویت شماره همراه</b>\n\n"
                "جهت فعال‌سازی درگاه پرداخت کارت‌به‌کارت و جلوگیری از سوءاستفاده‌های بانکی (فیشینگ)، تأیید شماره تماس الزامی است.\n\n"
                "👇 <b>دکمه «📱 اشتراک‌گذاری شماره تماس من» در پایین صفحه (روی کیبورد تایپ پیام) نمایان شد:</b>\n"
                "لطفاً روی آن ضربه بزنید تا شماره شما فوراً تأیید گردد.\n\n"
                "(شماره شما صرفاً برای تأیید بانکی ذخیره شده و کاملاً محرمانه نزد ما محفوظ می‌ماند)",
                reply_markup=phone_kb,
                parse_mode="HTML",
            )
            return

    # Auto-dismiss any residual reply keyboard (e.g. phone share button)
    cleaner = await message.answer("🔄", reply_markup=ReplyKeyboardRemove())
    with contextlib.suppress(Exception):
        await cleaner.delete()

    # fresh menu message at the bottom of the chat
    is_admin = message.from_user.id in get_settings().ADMIN_IDS
    if not user.language:
        await reset_menu(bot, user, user_repo, CHOOSE_LANGUAGE, language_keyboard())
    else:
        await _render_verified_or_welcome(
            bot, user, user_repo, is_admin, remnawave=remnawave, use_reset=True,
        )


@router.callback_query(F.data.startswith("lang:"))
async def choose_language(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave=None,
):
    lang = call.data.split(":", 1)[1]
    if lang not in ("fa", "en"):
        await call.answer()
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    had_lang = bool(user.language)
    await user_repo.set_language(user, lang)

    is_admin = call.from_user.id in get_settings().ADMIN_IDS
    await _render_verified_or_welcome(
        bot, user, user_repo, is_admin, remnawave=remnawave, use_reset=False,
    )
    await call.answer(t(lang, "settings_saved") if had_lang else None)


@router.callback_query(F.data == "nav:welcome")
async def back_to_welcome(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    state: FSMContext,
    remnawave=None,
):
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    is_admin = call.from_user.id in get_settings().ADMIN_IDS
    await _render_verified_or_welcome(
        bot, user, user_repo, is_admin, remnawave=remnawave, use_reset=False,
    )
    await call.answer()


@router.chat_member()
async def on_channel_member_updated(
    event: ChatMemberUpdated, bot: Bot, user_repo: UserRepository, session,
):
    """Notify registered users if they leave the mandatory join-gate channel."""
    old_status = getattr(event.old_chat_member, "status", None)
    new_status = getattr(event.new_chat_member, "status", None)
    target_user = getattr(event.new_chat_member, "user", None)
    if target_user is None or getattr(target_user, "is_bot", False):
        return
    if old_status not in ("member", "administrator", "creator", "restricted"):
        return
    if new_status not in ("left", "kicked"):
        return

    tg_id = target_user.id
    if tg_id in get_settings().ADMIN_IDS:
        return

    store_settings = await get_store_settings(session)
    if not getattr(store_settings, "join_gate_enabled", False):
        return
    gate_channel = (getattr(store_settings, "join_gate_channel", "") or "").strip()
    if not gate_channel or not matches_channel(event.chat, gate_channel):
        return

    db_user = await user_repo.get_by_telegram_id(tg_id)
    if db_user is None or getattr(db_user, "is_banned", False):
        return

    # Clear cached TMA dashboard across all accounts so join gate blocks immediately
    from bot.web.cache import invalidate_user_cache

    bot_cache = getattr(bot, "cache", None)
    with contextlib.suppress(Exception):
        await invalidate_user_cache(bot_cache, tg_id)

    channel_url = format_channel_link(gate_channel)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    if channel_url:
        kb.button(text="📢 عضویت مجدد در کانال", url=channel_url)
    lang = db_user.language or "fa"
    text = (
        "⚠️ <b>خروج از کانال رسمی</b>\n\n"
        "شما از کانال اجباری ربات خارج شدید؛ بنابراین دسترسی به امکانات ربات و مینی‌اپ موقتاً متوقف شده است.\n"
        "برای فعال‌سازی مجدد دسترسی، لطفاً دوباره در کانال عضو شوید:"
        if lang == "fa"
        else "⚠️ <b>You left the required channel</b>\n\n"
        "Your access to bot and Mini App features has been paused until you rejoin our official channel:"
    )
    with contextlib.suppress(Exception):
        await bot.send_message(
            tg_id,
            text,
            reply_markup=kb.as_markup() if channel_url else None,
            parse_mode="HTML",
        )


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

    from bot.services.app_settings import get_store_settings
    store_settings = await get_store_settings(session)
    if store_settings.card_phone_iran_only:
        clean_p = phone.lstrip("+")
        if not (clean_p.startswith("98") or clean_p.startswith("09")):
            await message.answer(
                "⚠️ <b>خطای احراز هویت:</b>\n"
                "بر اساس قوانین بانکی و امنیتی، احراز هویت شماره تماس و پرداخت کارت‌به‌کارت تنها برای شماره‌های رسمی کشور ایران (<code>+98</code>) مجاز می‌باشد.",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="HTML",
            )
            return

    user = await user_repo.get_or_create(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    user.phone_number = phone
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        await message.answer(
            "⚠️ <b>خطای احراز هویت:</b> این شماره تماس قبلاً در سیستم ثبت شده است و امکان استفاده مجدد از آن روی حساب دیگر وجود ندارد.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML",
        )
        return

    from bot.web.cache import invalidate_user_cache

    with contextlib.suppress(Exception):
        await invalidate_user_cache(getattr(bot, "cache", None), message.from_user.id)

    await message.answer(
        f"✅ <b>شماره تماس شما با موفقیت تأیید و ثبت شد:</b>\n<code>{phone}</code>\n\n"
        "اکنون درگاه پرداخت کارت‌به‌کارت برای حساب شما فعال گردید. می‌توانید فرآیند پرداخت را در مینی‌اپ ادامه دهید.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )
