"""Gift Cards and Voucher Handler: Send wallet balance or service plans to friends."""
from __future__ import annotations

import logging
import urllib.parse
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, parse_int
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.formatting import format_datetime
from bot.services.gift_service import create_gift, get_user_gifts
from bot.services.menu import render_menu
from bot.states.gift import GiftStates
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)
router = Router(name="gift")

PRESET_AMOUNTS = [50_000, 100_000, 200_000, 500_000]


@router.callback_query(F.data == "menu:gift")
async def gift_hub(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext | None = None,
):
    """Main gift hub: send gifts or view past sent gifts."""
    if state:
        await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    wallet = await WalletRepository(session).get_wallet(user.telegram_id)

    lines = [
        "🎁 <b>ارسال هدیه به دوستان</b>" if lang == "fa" else "🎁 <b>Send Gifts to Friends</b>",
        SEPARATOR,
        f"👛 موجودی کیف پول شما : <b>{fmt(wallet.balance)}</b> {t(lang, 'svc_currency')}"
        if lang == "fa"
        else f"👛 Your Wallet Balance : <b>{fmt(wallet.balance)}</b> {t(lang, 'svc_currency')}",
        "",
        "شما می‌توانید با موجودی کیف پول خود، اعتبار یا بسته اشتراک را به عنوان هدیه برای دوستانتان ارسال کنید."
        if lang == "fa"
        else "You can gift wallet credit or subscription plans to your friends using your wallet balance.",
        "هدیه می‌تواند به صورت لینک اشتراک‌گذاری یا مستقیماً به نام کاربری دوستتان ارسال گردد."
        if lang == "fa"
        else "Gifts can be sent as shareable links or delivered directly to their Telegram username.",
    ]

    kb = InlineKeyboardBuilder()
    # Row 1: Balance Gift | Service Gift
    btn_bal = "👛 هدیه اعتبار کیف پول" if lang == "fa" else "👛 Gift Wallet Balance"
    btn_svc = "📦 هدیه بسته اشتراک" if lang == "fa" else "📦 Gift Service Plan"
    kb.button(text=btn_bal, callback_data="gift:type:balance")
    kb.button(text=btn_svc, callback_data="gift:type:service")

    # Row 2: My Sent Gifts
    btn_sent = "📜 هدیه‌های ارسالی من" if lang == "fa" else "📜 My Sent Gifts"
    kb.button(text=btn_sent, callback_data="gift:my_sent")

    # Row 3: Main Menu
    btn_back = "🏠 منوی اصلی" if lang == "fa" else "🏠 Main Menu"
    kb.button(text=btn_back, callback_data="nav:main_menu")

    kb.adjust(2, 1, 1)
    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data == "gift:type:balance")
async def gift_choose_balance(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    """Step 1 (Balance): Choose preset amount or enter custom amount."""
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    await state.set_state(GiftStates.waiting_for_balance_amount)
    await state.update_data(gift_type="BALANCE")

    wallet = await WalletRepository(session).get_wallet(user.telegram_id)

    lines = [
        "👛 <b>انتخاب مبلغ هدیه اعتبار</b>" if lang == "fa" else "👛 <b>Select Gift Credit Amount</b>",
        SEPARATOR,
        f"موجودی کیف پول شما: <b>{fmt(wallet.balance)}</b> تومان"
        if lang == "fa"
        else f"Your wallet balance: <b>{fmt(wallet.balance)}</b> Toman",
        "",
        "لطفاً یکی از مبالغ پیشنهادی را انتخاب کنید یا گزینه مبلغ دلخواه را بزنید:"
        if lang == "fa"
        else "Please select a preset amount or tap custom amount:",
    ]

    kb = InlineKeyboardBuilder()
    for amt in PRESET_AMOUNTS:
        kb.button(text=f"{fmt(amt)} تومان", callback_data=f"gift:amt:{amt}")
    kb.button(text="✏️ مبلغ دلخواه", callback_data="gift:amt:custom")
    kb.button(text="🔙 بازگشت", callback_data="menu:gift")
    kb.adjust(2, 2, 1, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("gift:amt:"))
async def gift_balance_amount_selected(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    state: FSMContext,
):
    """Handle preset amount button or prompt for custom number."""
    val = call.data.split(":", 2)[2]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    if val == "custom":
        lines = [
            "✏️ <b>ورود مبلغ دلخواه هدیه</b>",
            SEPARATOR,
            "لطفاً مبلغ مورد نظر خود را به تومان ارسال کنید (حداقل ۱۰,۰۰۰ تومان):",
            "نمونه: <code>75000</code>",
        ]
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 بازگشت", callback_data="gift:type:balance")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await call.answer()
        return

    amount = parse_int(val) or 0
    if amount < 10_000:
        await call.answer("مبلغ باید حداقل ۱۰,۰۰۰ تومان باشد.", show_alert=True)
        return

    await state.update_data(amount=amount)
    await _prompt_recipient(call, bot, user, user_repo, state, lang)


@router.message(GiftStates.waiting_for_balance_amount)
async def gift_custom_amount_input(
    message: Message,
    bot: Bot,
    user_repo: UserRepository,
    state: FSMContext,
):
    """Handle text input for custom balance amount."""
    await user_repo.get_or_create(message.from_user.id, message.from_user.username)

    raw = (message.text or "").strip().replace(",", "").replace("،", "")
    # Persian to English digits
    p2e = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    clean = raw.translate(p2e)

    amount = parse_int(clean) or 0
    if amount < 10_000:
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 بازگشت", callback_data="gift:type:balance")
        await message.reply(
            "❌ حداقل مبلغ هدیه اعتبار ۱۰,۰۰۰ تومان است. لطفاً مبلغ معتبری وارد کنید:",
            reply_markup=kb.as_markup(),
        )
        return

    await state.update_data(amount=amount)

    # Prompt delivery method
    lines = [
        f"✅ مبلغ انتخاب شده: <b>{fmt(amount)} تومان</b>",
        SEPARATOR,
        "نحوه ارسال هدیه را انتخاب کنید:",
        "• <b>لینک و کد هدیه:</b> یک کد و لینک اختصاصی ساخته می‌شود که می‌توانید برای هر کسی فوروارد کنید.",
        "• <b>ارسال به آیدی دوست:</b> هدیه مستقیماً به نام کاربری یا شناسه تلگرام دوستتان ارسال می‌شود.",
    ]
    kb = InlineKeyboardBuilder()
    kb.button(text="🔗 ساخت لینک و کد هدیه", callback_data="gift:deliv:link")
    kb.button(text="👤 ارسال به آیدی تلگرام", callback_data="gift:deliv:direct")
    kb.button(text="🔙 تغییر مبلغ", callback_data="gift:type:balance")
    kb.adjust(1)

    await message.reply("\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "gift:type:service")
async def gift_choose_service(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    """Step 1 (Service): Select service plan to gift."""
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    services = await ServiceRepository(session).list_active()
    if not services:
        await call.answer("در حال حاضر سرویسی برای هدیه موجود نیست.", show_alert=True)
        return

    await state.set_state(GiftStates.waiting_for_receiver)
    await state.update_data(gift_type="SERVICE")

    lines = [
        "📦 <b>انتخاب بسته اشتراک جهت هدیه</b>" if lang == "fa" else "📦 <b>Select Service Plan to Gift</b>",
        SEPARATOR,
        "لطفاً بسته مورد نظر را جهت هدیه به دوستتان انتخاب کنید:"
        if lang == "fa"
        else "Please select the service plan to gift:",
    ]

    kb = InlineKeyboardBuilder()
    for svc in services:
        kb.button(
            text=f"🎁 {svc.name} — {fmt(svc.price)} تومان",
            callback_data=f"gift:svc:{svc.id}",
        )
    kb.button(text="🔙 بازگشت", callback_data="menu:gift")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("gift:svc:"))
async def gift_service_selected(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    """Store selected service ID and prompt for recipient."""
    svc_id = parse_int(call.data.split(":", 2)[2])
    if not svc_id:
        await call.answer("سرویس نامعتبر است.", show_alert=True)
        return

    svc = await ServiceRepository(session).get_by_id(svc_id)
    if not svc:
        await call.answer("سرویس یافت نشد.", show_alert=True)
        return

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    await state.update_data(service_id=svc.id, service_name=svc.name, service_price=svc.price)
    await _prompt_recipient(call, bot, user, user_repo, state, lang)


async def _prompt_recipient(call: CallbackQuery, bot: Bot, user, user_repo, state: FSMContext, lang: str):
    data = await state.get_data()
    gift_type = data.get("gift_type", "BALANCE")

    if gift_type == "BALANCE":
        summary = f"مبلغ: <b>{fmt(data.get('amount', 0))} تومان</b>"
    else:
        summary = f"سرویس: <b>{escape(data.get('service_name', ''))}</b>"

    lines = [
        f"🎁 {summary}",
        SEPARATOR,
        "نحوه تحویل هدیه را انتخاب کنید:",
        "• <b>🔗 لینک عمومی هدیه:</b> یک لینک و کد اختصاصی ساخته می‌شود که می‌توانید آن را برای هر کسی بفرستید.",
        "• <b>👤 ارسال مستقیم به آیدی:</b> هدیه به صورت مستقیم در ربات به آیدی دوستتان تحویل داده می‌شود.",
    ]

    kb = InlineKeyboardBuilder()
    kb.button(text="🔗 ساخت لینک و کد هدیه", callback_data="gift:deliv:link")
    kb.button(text="👤 ارسال به آیدی تلگرام", callback_data="gift:deliv:direct")
    kb.button(text="🔙 انصراف", callback_data="menu:gift")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data == "gift:deliv:link")
async def gift_delivery_link(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    cache: FastCache | None = None,
):
    """Delivery via public shareable link."""
    await state.update_data(delivery_type="LINK", receiver_target=None)
    await _prompt_message_or_confirm(call, bot, user_repo, session, state, cache)


@router.callback_query(F.data == "gift:deliv:direct")
async def gift_delivery_direct(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    state: FSMContext,
):
    """Prompt user for recipient's @username or Telegram ID."""
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)

    await state.set_state(GiftStates.waiting_for_receiver)
    await state.update_data(delivery_type="DIRECT")

    lines = [
        "👤 <b>دریافت‌کننده هدیه</b>",
        SEPARATOR,
        "لطفاً نام کاربری (با علامت @) یا شناسه عددی تلگرام دوستتان را ارسال کنید:",
        "نمونه: <code>@username</code> یا <code>123456789</code>",
    ]

    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 انصراف", callback_data="menu:gift")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.message(GiftStates.waiting_for_receiver)
async def gift_receiver_input(
    message: Message,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    cache: FastCache | None = None,
):
    """Store receiver target and proceed to message or confirmation."""
    target = (message.text or "").strip()
    if not target:
        await message.reply("لطفاً آیدی تلگرام را وارد کنید:")
        return

    # Clean username - ensure standard representation
    clean_target = target.lstrip("@").strip()
    if not clean_target:
        await message.reply("نام کاربری وارد شده نامعتبر است.")
        return

    formatted_target = f"@{clean_target}" if not clean_target.isdigit() else clean_target
    await state.update_data(receiver_target=formatted_target)

    # Proceed to optional greeting message prompt
    await state.set_state(GiftStates.waiting_for_message)

    lines = [
        f"👤 دریافت‌کننده: <b>\u200e{formatted_target}\u200e</b>",
        SEPARATOR,
        "آیا مایلید یک متن تبریک یا پیام دلخواه همراه با هدیه ارسال شود؟",
        "می‌توانید پیام خود را ارسال کنید یا دکمه «رد کردن و تأیید نهایی» را بزنید:",
    ]
    kb = InlineKeyboardBuilder()
    kb.button(text="⏭ رد کردن پیام و تأیید نهایی", callback_data="gift:msg:skip")
    kb.button(text="🔙 انصراف", callback_data="menu:gift")
    kb.adjust(1)

    await message.reply("\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "gift:msg:skip")
async def gift_message_skip(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    cache: FastCache | None = None,
):
    """Skip personal message and render checkout confirmation."""
    await state.update_data(greeting_message=None)
    await _render_gift_checkout(call, bot, user_repo, session, state, cache)


@router.message(GiftStates.waiting_for_message)
async def gift_message_input(
    message: Message,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    cache: FastCache | None = None,
):
    """Store greeting message and render checkout confirmation."""
    msg = (message.text or "").strip()[:200]
    await state.update_data(greeting_message=msg)

    # Render summary via message reply
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language or "fa"

    data = await state.get_data()
    lines, kb = await _build_checkout_payload(user, session, data, cache, lang)
    await message.reply("\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML")


async def _prompt_message_or_confirm(
    call: CallbackQuery, bot: Bot, user_repo, session, state: FSMContext, cache
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)

    await state.set_state(GiftStates.waiting_for_message)

    lines = [
        "📝 <b>متن تبریک و یادداشت هدیه</b>",
        SEPARATOR,
        "آیا مایلید متن تبریک یا یادداشت دلخواهی همراه با هدیه باشد؟",
        "می‌توانید متن پیام را تایپ و ارسال کنید یا دکمه «رد کردن و تأیید نهایی» را بزنید:",
    ]
    kb = InlineKeyboardBuilder()
    kb.button(text="⏭ رد کردن و تأیید نهایی", callback_data="gift:msg:skip")
    kb.button(text="🔙 انصراف", callback_data="menu:gift")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


async def _build_checkout_payload(user, session, data, cache, lang):
    gift_type = data.get("gift_type", "BALANCE")
    delivery_type = data.get("delivery_type", "LINK")
    target = data.get("receiver_target")
    custom_msg = data.get("greeting_message")

    wallet = await WalletRepository(session).get_wallet(user.telegram_id)
    balance = wallet.balance

    if gift_type == "BALANCE":
        cost = int(data.get("amount", 0) or 0)
        gift_desc = f"<b>{fmt(cost)} تومان</b> اعتبار کیف پول"
    else:
        cost = int(data.get("service_price", 0) or 0)
        svc_name = escape(str(data.get("service_name", "")))
        gift_desc = f"اشتراک <b>{svc_name}</b>"

    delivery_desc = (
        f"ارسال مستقیم به \u200e{escape(str(target))}\u200e" if (delivery_type == "DIRECT" and target) else "لینک و کد عمومی هدیه"
    )

    lines = [
        "🎁 <b>پیش‌فاکتور ارسال هدیه</b>",
        SEPARATOR,
        f"📦 نوع هدیه: {gift_desc}",
        f"🎯 نحوه تحویل: <b>{delivery_desc}</b>",
    ]
    if custom_msg:
        lines.append(f"💬 پیام همراه هدیه: <i>«{escape(custom_msg)}»</i>")

    lines.extend([
        SEPARATOR,
        f"💰 مبلغ کسر از کیف پول شما: <b>{fmt(cost)}</b> تومان",
        f"👛 موجودی فعلی کیف پول: <b>{fmt(balance)}</b> تومان",
    ])

    kb = InlineKeyboardBuilder()
    if balance >= cost and cost > 0:
        kb.button(text="✅ تأیید و پرداخت از کیف پول", callback_data="gift:checkout:confirm")
        kb.button(text="❌ انصراف", callback_data="menu:gift")
    else:
        shortage = cost - balance
        lines.append(f"⚠️ موجودی کیف پول شما کافی نیست (کسری: {fmt(shortage)} تومان).")
        kb.button(text="👛 افزایش موجودی کیف پول", callback_data="wallet:topup")
        kb.button(text="❌ انصراف", callback_data="menu:gift")

    kb.adjust(1)
    return lines, kb


async def _render_gift_checkout(call: CallbackQuery, bot: Bot, user_repo, session, state: FSMContext, cache):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    data = await state.get_data()
    lines, kb = await _build_checkout_payload(user, session, data, cache, lang)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data == "gift:checkout:confirm")
async def gift_checkout_confirm(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    cache: FastCache | None = None,
):
    """Execute gift creation, atomically deduct wallet balance, and issue gift card."""
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)

    data = await state.get_data()
    await state.clear()

    gift_type = data.get("gift_type", "BALANCE")
    delivery_type = data.get("delivery_type", "LINK")
    amount = int(data.get("amount", 0) or 0)
    service_id = parse_int(data.get("service_id"))
    receiver_target = data.get("receiver_target")
    custom_message = data.get("greeting_message")

    bot_user = getattr(getattr(bot, "_me", None), "username", "")
    if not bot_user:
        try:
            me = await bot.get_me()
            bot_user = me.username or ""
        except Exception:
            bot_user = ""

    sender_name = user.full_name or user.username or "یک دوست"

    res = await create_gift(
        session=session,
        sender_telegram_id=user.telegram_id,
        sender_name=sender_name,
        delivery_type=delivery_type,
        gift_type=gift_type,
        amount=amount,
        service_id=service_id,
        receiver_target=receiver_target,
        message=custom_message,
        bot=bot,
        bot_username=bot_user,
        cache=cache,
    )

    if not res.get("ok"):
        await call.answer(res.get("message", "خطا در صدور هدیه"), show_alert=True)
        return

    code = res.get("code", "")
    share_url = res.get("share_url", "")
    direct_notified = res.get("direct_notified", False)

    lines = [
        "🎉 <b>کارت هدیه شما با موفقیت صادر شد!</b>",
        SEPARATOR,
        f"🔑 <b>کد هدیه:</b> \u2066<code>{escape(code)}</code>\u2069 (جهت کپی لمس کنید)",
        f"🔗 <b>لینک فعال‌سازی:</b> <code>{escape(share_url)}</code>",
    ]

    if direct_notified:
        lines.append("\n✅ <i>این هدیه به صورت خودکار برای دریافت‌کننده ارسال گردید.</i>")
    elif delivery_type == "DIRECT" and receiver_target:
        lines.append(f"\nℹ️ <i>دریافت‌کننده (\u200e{escape(str(receiver_target))}\u200e) پس از ورود به ربات می‌تواند با کلیک روی لینک، هدیه خود را تحویل بگیرد.</i>")
    else:
        lines.append("\n💡 <i>می‌توانید پیام یا لینک بالا را برای دوست خود ارسال کنید تا هدیه برایش فعال شود.</i>")

    kb = InlineKeyboardBuilder()

    # Share via Telegram button
    tg_share_link = f"https://t.me/share/url?url={urllib.parse.quote(share_url)}&text={urllib.parse.quote('🎁 یک کارت هدیه برای شما ارسال شد!')}"
    kb.button(text="📤 ارسال مستقیم در تلگرام", url=tg_share_link)

    kb.button(text="🎁 ارسال هدیه دیگر", callback_data="menu:gift")
    kb.button(text="📜 هدیه‌های ارسالی من", callback_data="gift:my_sent")
    kb.button(text="🏠 منوی اصلی", callback_data="nav:main_menu")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data == "gift:my_sent")
async def gift_my_sent(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
):
    """List sent gifts and their claim status."""
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    bot_user = getattr(getattr(bot, "_me", None), "username", "")
    gifts_data = await get_user_gifts(session, user.telegram_id, bot_username=bot_user)
    gifts = gifts_data.get("sent", []) if isinstance(gifts_data, dict) else gifts_data

    lines = [
        "📜 <b>هدیه‌های ارسالی شما</b>",
        SEPARATOR,
    ]

    if not gifts:
        lines.append("شما تاکنون هدیه‌ای ارسال نکرده‌اید.")
    else:
        for i, g in enumerate(gifts[:10], start=1):
            is_claimed = g.get("is_claimed")
            status_emoji = "✅ باز شده" if is_claimed else "⏳ منتظر فعال‌سازی"
            code = g.get("code")
            desc = g.get("gift_desc")
            receiver = g.get("receiver_username") or "عمومی"
            when = format_datetime(g.get("created_at"), lang)

            lines.append(
                f"{i}) {status_emoji} · <b>{escape(str(desc))}</b>\n"
                f"   🔑 کد: \u2066<code>{escape(str(code))}</code>\u2069\n"
                f"   👤 گیرنده: \u200e@{escape(str(receiver).lstrip('@'))}\u200e · 🕒 {when}"
            )
            if i < len(gifts[:10]):
                lines.append("")

    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 ارسال هدیه جدید", callback_data="menu:gift")
    kb.button(text="🏠 منوی اصلی", callback_data="nav:main_menu")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()
