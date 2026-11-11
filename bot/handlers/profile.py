"""«حساب کاربری» — wallet balance, login status, panel accounts,
birthday registration, and the user's own order history («سفارش‌های من»)."""
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt
from bot.config import get_settings
from bot.db.models import User
from bot.db.repositories.order_repo import OrderRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.birthday import days_until_jalali_birthday, parse_and_validate_jalali_birthdate
from bot.services.formatting import format_date, format_datetime, now_tz, parse_iso
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient
from bot.states.profile import ProfileStates
from bot.web.cache import FastCache

router = Router(name="profile")


@router.callback_query(F.data == "menu:profile")
async def profile_view(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    remnawave: RemnawaveClient,
    state: FSMContext | None = None,
):
    if state:
        await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_profile(bot, user, user_repo, session, remnawave)
    await call.answer()


async def _render_profile(
    bot: Bot,
    user: User,
    user_repo: UserRepository,
    session: AsyncSession,
    remnawave: RemnawaveClient,
) -> None:
    lang = user.language or "fa"

    wallet = await WalletRepository(session).get_wallet(user.telegram_id)
    accounts = await remnawave.get_users_by_telegram_id(user.telegram_id) or []
    orders_count = len(await OrderRepository(session).list_for_user(user.telegram_id, limit=100))

    lines = [
        t(lang, "profile_title"),
        SEPARATOR,
        f"👛 {t(lang, 'user_balance')} : <b>{fmt(wallet.balance)}</b> {t(lang, 'svc_currency')}",
        f"🔐 {t(lang, 'profile_status')} : {'✅' if user.is_verified else '❌'}",
        f"🗂 {t(lang, 'user_panel_accounts')} : <b>{len(accounts)}</b>",
        f"🧾 {t(lang, 'orders_count')} : <b>{orders_count}</b>",
    ]

    # Birthday status
    bdate = getattr(user, "birth_date", None)
    if bdate and str(bdate).strip():
        tz = get_settings().TIMEZONE
        days_left = days_until_jalali_birthday(bdate, tz)
        if days_left == 0:
            bday_hint = "🎉 (امروز زادروز شماست!)" if lang == "fa" else "🎉 (Today is your birthday!)"
        elif days_left is not None:
            bday_hint = f"({days_left} روز تا زادروز)" if lang == "fa" else f"({days_left} days left)"
        else:
            bday_hint = ""
        bday_label = "🎂 تاریخ زادروز" if lang == "fa" else "🎂 Birthday"
        lines.append(f"{bday_label} : <b>{bdate}</b> {bday_hint}")
    else:
        bday_label = "🎂 تاریخ زادروز" if lang == "fa" else "🎂 Birthday"
        not_set = "ثبت نشده" if lang == "fa" else "Not set"
        lines.append(f"{bday_label} : {not_set}")

    if user.created_at is not None:
        lines.append(f"📅 {t(lang, 'profile_member_since')} : "
                     f"{format_datetime(user.created_at, lang)}")

    if accounts:
        lines.append("")
        now = now_tz(get_settings().TIMEZONE)
        for acc in accounts[:5]:
            uname = escape(str(acc.get("username", "—")))
            expire_at = parse_iso(acc.get("expireAt"))
            if expire_at is None:
                exp_text = t(lang, "stats_no_expire")
            else:
                date_str = format_date(expire_at.astimezone(now.tzinfo), lang)
                exp_text = date_str
            lines.append(f"   • <code>{uname}</code> — {exp_text}")

    kb = InlineKeyboardBuilder()
    # Row 1: My Orders | Referral
    kb.button(text=t(lang, "btn_my_orders"), callback_data="profile:orders")
    kb.button(text=t(lang, "btn_referral"), callback_data="menu:referral")

    # Row 2: Birthday registration / edit
    bday_btn_text = (
        ("🎂 ویرایش تاریخ تولد" if lang == "fa" else "🎂 Edit Birthday")
        if (bdate and str(bdate).strip())
        else ("🎂 ثبت تاریخ تولد" if lang == "fa" else "🎂 Set Birthday")
    )
    kb.button(text=bday_btn_text, callback_data="prof:birthday")

    sizes = [2, 1]
    if not user.is_verified:
        kb.button(text=t(lang, "btn_login"), callback_data="auth:login")
        sizes.append(1)
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    sizes.append(1)
    kb.adjust(*sizes)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "prof:birthday")
async def start_set_birthday(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    state: FSMContext,
):
    """Prompt user to enter their Jalali birth date."""
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    cur_bdate = getattr(user, "birth_date", None)
    if cur_bdate:
        await call.answer(
            "تاریخ تولد شما قبلاً ثبت شده و برای جلوگیری از سوءاستفاده قابل تغییر نیست."
            if lang == "fa"
            else "Your birth date is already registered and cannot be changed.",
            show_alert=True,
        )
        return

    await state.set_state(ProfileStates.waiting_for_birthday)

    cur_info = ""

    text = (
        "🎂 <b>ثبت تاریخ تولد و دریافت هدیه زادروز</b>\n"
        f"{SEPARATOR}\n"
        "با ثبت تاریخ زادروز خود، در روز تولدتان هدیه ویژه VIP (حجم اینترنت رایگان و کد تخفیف اختصاصی) "
        "به صورت خودکار برای شما ارسال خواهد شد! 🎁"
        f"{cur_info}\n\n"
        "لطفاً تاریخ تولد خود را به صورت شمسی ارسال کنید:\n"
        "نمونه: <code>1378/04/15</code> یا <code>04/15</code>"
        if lang == "fa"
        else (
            "🎂 <b>Birthday Registration</b>\n"
            f"{SEPARATOR}\n"
            "Register your birth date to receive automated VIP gifts (free traffic & discount coupons) on your birthday! 🎁"
            f"{cur_info}\n\n"
            "Please send your Jalali birth date (e.g. <code>1378/04/15</code> or <code>04/15</code>):"
        )
    )

    kb = InlineKeyboardBuilder()
    kb.button(
        text=t(lang, "btn_cancel"),
        callback_data="prof:birthday:cancel",
    )
    kb.adjust(1)

    await render_menu(bot, user, user_repo, text, kb.as_markup())
    await call.answer()


@router.callback_query(F.data == "prof:birthday:cancel")
async def cancel_set_birthday(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    remnawave: RemnawaveClient,
    state: FSMContext,
):
    """Cancel birthday input and return to profile."""
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_profile(bot, user, user_repo, session, remnawave)
    await call.answer()


@router.message(ProfileStates.waiting_for_birthday)
async def process_birthday_input(
    message: Message,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    cache: FastCache | None = None,
):
    """Validate and store user's birth date."""
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language or "fa"

    raw_text = (message.text or "").strip()
    is_valid, formatted_date, err_msg = parse_and_validate_jalali_birthdate(raw_text)

    if not is_valid:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="prof:birthday:cancel")
        kb.adjust(1)
        await message.reply(
            f"❌ {err_msg}\n\nلطفاً مجدداً به صورت صحیح ارسال کنید (مثال: <code>1378/04/15</code> یا <code>04/15</code>):",
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )
        return

    await state.clear()

    if getattr(user, "birth_date", None):
        kb = InlineKeyboardBuilder()
        kb.button(text="👤 بازگشت به حساب کاربری", callback_data="menu:profile")
        await message.reply(
            "⚠️ تاریخ تولد شما قبلاً ثبت شده و امکان تغییر مجدد آن وجود ندارد.",
            reply_markup=kb.as_markup(),
        )
        return

    user.birth_date = formatted_date
    await session.commit()

    if cache and hasattr(cache, "delete"):
        await cache.delete(f"tma:user:{user.telegram_id}")
        await cache.delete(f"tma:user:{user.telegram_id}:dashboard:default")
        await cache.delete(f"tma:user:{user.telegram_id}:dashboard")
        await cache.delete(f"tma:user:{user.telegram_id}:profile")

    tz = get_settings().TIMEZONE
    days_left = days_until_jalali_birthday(formatted_date, tz)
    if days_left == 0:
        congrats_hint = "\n🎉 <b>امروز سالروز تولد شماست! زادروزتان همایون باد!</b>"
    elif days_left is not None:
        congrats_hint = f"\n⏳ <b>{days_left} روز</b> تا سالروز تولد شما باقیمانده است."
    else:
        congrats_hint = ""

    success_text = (
        "✅ <b>تاریخ زادروز شما با موفقیت ثبت شد!</b>\n"
        f"{SEPARATOR}\n"
        f"📅 تاریخ ثبت شده: <code>{formatted_date}</code>"
        f"{congrats_hint}\n\n"
        "🎁 در روز تولدتان، بسته هدیه ویژه به صورت خودکار در همین ربات تقدیم شما خواهد شد."
        if lang == "fa"
        else (
            "✅ <b>Birth date successfully registered!</b>\n"
            f"{SEPARATOR}\n"
            f"📅 Registered date: <code>{formatted_date}</code>"
            f"{congrats_hint}\n\n"
            "🎁 On your birthday, your VIP gift package will be sent here automatically."
        )
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="👤 بازگشت به حساب کاربری", callback_data="menu:profile")
    kb.button(text="🏠 منوی اصلی", callback_data="nav:main_menu")
    kb.adjust(1)

    await message.reply(success_text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "profile:orders")
async def my_orders(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    orders = await OrderRepository(session).list_for_user(user.telegram_id, limit=10)

    lines = [t(lang, "orders_title"), SEPARATOR]
    if not orders:
        lines.append(t(lang, "orders_empty"))
    else:
        for i, order in enumerate(orders):
            mark = "✅" if order.status == "paid" else "↩️"
            when = format_datetime(order.created_at, lang)
            lines.append(
                f"{mark} #{order.id} · {escape(order.service_name)} · "
                f"<b>{fmt(order.amount)}</b> {t(lang, 'svc_currency')}\n"
                f"   🕒 {when}"
            )
            if i < len(orders) - 1:
                lines.append("")

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back"), callback_data="menu:profile")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()
