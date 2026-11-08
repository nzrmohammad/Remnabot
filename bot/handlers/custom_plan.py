"""Custom Plan Builder Handler: Interactive volume & duration selection with tiered pricing."""
from __future__ import annotations

import logging
from html import escape
from types import SimpleNamespace

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, parse_int
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.app_settings import get_store_settings
from bot.services.formatting import ltr_frag
from bot.services.loyalty import apply_loyalty_discount, get_user_loyalty
from bot.services.menu import render_menu
from bot.services.purchases import execute_purchase, resolve_squad_name
from bot.services.remnawave import RemnawaveClient
from bot.states.custom_plan import CustomPlanStates
from bot.web.cache import FastCache
from bot.web.user_shop import compute_custom_plan_price

logger = logging.getLogger(__name__)
router = Router(name="custom_plan")

PRESET_GB = [15, 30, 50, 80, 100, 150, 200]
PRESET_DAYS = [(30, "۳۰ روز (۱ ماه)"), (60, "۶۰ روز (۲ ماه)"), (90, "۹۰ روز (۳ ماه)"), (180, "۱۸۰ روز (۶ ماه)")]


async def _prompt_traffic_gb(call: CallbackQuery, bot: Bot, user, user_repo, store_settings, lang: str):
    lines = [
        "🛠 <b>طراحی بسته دلخواه — انتخاب حجم</b>" if lang == "fa" else "🛠 <b>Custom Plan Builder — Select Traffic</b>",
        SEPARATOR,
        "در این بخش می‌توانید ترافیک و مدت زمان بسته خود را دقیقاً مطابق با مصرف خود انتخاب کنید.",
        "🔥 <b>تخفیف پلکانی حجم:</b> با انتخاب حجم‌های بالاتر، نرخ هر گیگابایت ارزان‌تر محاسبه می‌شود!",
        "",
        f"دامنه حجم مجاز: <b>{store_settings.custom_plan_min_gb} تا {store_settings.custom_plan_max_gb} گیگابایت</b>",
        "لطفاً حجم مورد نظر خود را انتخاب کنید:",
    ]

    kb = InlineKeyboardBuilder()
    for gb in PRESET_GB:
        if store_settings.custom_plan_min_gb <= gb <= store_settings.custom_plan_max_gb:
            kb.button(text=f"{gb} گیگابایت", callback_data=f"cplan:gb:{gb}")
    kb.button(text="✏️ حجم دلخواه", callback_data="cplan:gb:custom")
    kb.button(text="🏠 منوی اصلی", callback_data="nav:main_menu")

    kb.adjust(2, 2, 2, 1, 1, 1)
    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data.in_({"menu:custom_plan", "shop:custom_plan"}))
async def custom_plan_entry(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext | None = None,
    remnawave: RemnawaveClient | None = None,
):
    """Step 1: Choose Squad (or auto-select) and then Traffic (GB)."""
    if state:
        await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    store_settings = await get_store_settings(session)
    if not store_settings.custom_plan_enabled:
        await call.answer(
            "طراحی بسته اختصاصی در حال حاضر غیرفعال است." if lang == "fa" else "Custom plan builder is currently disabled.",
            show_alert=True,
        )
        return

    squads = []
    if remnawave:
        try:
            raw_sqs = await remnawave.get_internal_squads() or []
            for s in raw_sqs:
                if isinstance(s, dict):
                    uid = s.get("uuid") or s.get("id")
                    name = s.get("name") or uid
                    if uid:
                        squads.append({"uuid": str(uid), "name": str(name)})
        except Exception as exc:
            logger.debug("Failed fetching squads for custom plan: %s", exc)

    if len(squads) > 1:
        lines = [
            "🛠 <b>طراحی بسته دلخواه (مرحله ۱ از ۳)</b>" if lang == "fa" else "🛠 <b>Custom Plan Builder (Step 1 of 3)</b>",
            SEPARATOR,
            "لطفاً ابتدا دسته سرور (نوع سرویس) مورد نظر خود را انتخاب فرمایید:" if lang == "fa" else "Please select the server squad first:",
        ]
        kb = InlineKeyboardBuilder()
        for sq in squads:
            kb.button(text=f"🌐 {sq['name']}", callback_data=f"cplan:sq:{sq['uuid']}")
        kb.button(text="🏠 منوی اصلی" if lang == "fa" else "🏠 Main Menu", callback_data="nav:main_menu")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await call.answer()
        return

    default_sq = squads[0]["uuid"] if squads else store_settings.default_squad_uuid
    if state:
        await state.update_data(squad_uuid=default_sq)
    await _prompt_traffic_gb(call, bot, user, user_repo, store_settings, lang)
    await call.answer()


@router.callback_query(F.data.startswith("cplan:sq:"))
async def custom_plan_squad_selected(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    squad_uuid = call.data.split(":", 2)[2]
    await state.update_data(squad_uuid=squad_uuid)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    store_settings = await get_store_settings(session)
    await _prompt_traffic_gb(call, bot, user, user_repo, store_settings, lang)
    await call.answer()


@router.callback_query(F.data.startswith("cplan:gb:"))
async def custom_plan_gb_selected(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    """Store GB and prompt Step 2: Choose Duration Days."""
    val = call.data.split(":", 2)[2]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    store_settings = await get_store_settings(session)

    if val == "custom":
        await state.set_state(CustomPlanStates.waiting_for_custom_gb)
        lines = [
            "✏️ <b>ورود حجم دلخواه</b>",
            SEPARATOR,
            f"لطفاً حجم مورد نظر خود را به عدد (گیگابایت) وارد کنید (بین {store_settings.custom_plan_min_gb} تا {store_settings.custom_plan_max_gb}):",
            "نمونه: <code>75</code>",
        ]
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 بازگشت", callback_data="menu:custom_plan")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await call.answer()
        return

    gb = parse_int(val) or 0
    await state.update_data(traffic_gb=gb)
    await _prompt_duration_days(call, bot, user, user_repo, store_settings, gb, lang)


@router.message(CustomPlanStates.waiting_for_custom_gb)
async def custom_plan_custom_gb_input(
    message: Message,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    """Handle text input for custom GB."""
    await user_repo.get_or_create(message.from_user.id, message.from_user.username)

    store_settings = await get_store_settings(session)
    raw = (message.text or "").strip()
    p2e = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    clean = raw.translate(p2e)

    gb = parse_int(clean) or 0
    if gb < store_settings.custom_plan_min_gb or gb > store_settings.custom_plan_max_gb:
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 بازگشت", callback_data="menu:custom_plan")
        await message.reply(
            f"❌ حجم انتخابی باید بین {store_settings.custom_plan_min_gb} تا {store_settings.custom_plan_max_gb} گیگابایت باشد. لطفاً مجدداً وارد کنید:",
            reply_markup=kb.as_markup(),
        )
        return

    await state.update_data(traffic_gb=gb)

    # Render days choice via message reply
    lines = [
        f"✅ حجم انتخاب شده: <b>{gb} گیگابایت</b>",
        SEPARATOR,
        "🛠 <b>طراحی بسته دلخواه (مرحله ۲ از ۲)</b>",
        f"مدت زمان اعتبار بسته را انتخاب کنید (بین {store_settings.custom_plan_min_days} تا {store_settings.custom_plan_max_days} روز):",
    ]
    kb = InlineKeyboardBuilder()
    for d, label in PRESET_DAYS:
        if store_settings.custom_plan_min_days <= d <= store_settings.custom_plan_max_days:
            kb.button(text=label, callback_data=f"cplan:days:{gb}:{d}")
    kb.button(text="✏️ مدت دلخواه", callback_data=f"cplan:days:{gb}:custom")
    kb.button(text="🔙 تغییر حجم", callback_data="menu:custom_plan")
    kb.adjust(2, 2, 1, 1)

    await message.reply("\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML")


async def _prompt_duration_days(call: CallbackQuery, bot: Bot, user, user_repo, store_settings, gb: int, lang: str):
    lines = [
        f"✅ حجم انتخاب شده: <b>{gb} گیگابایت</b>",
        SEPARATOR,
        "🛠 <b>طراحی بسته دلخواه (مرحله ۲ از ۲)</b>",
        f"مدت زمان اعتبار بسته را انتخاب کنید (بین {store_settings.custom_plan_min_days} تا {store_settings.custom_plan_max_days} روز):",
    ]

    kb = InlineKeyboardBuilder()
    for d, label in PRESET_DAYS:
        if store_settings.custom_plan_min_days <= d <= store_settings.custom_plan_max_days:
            kb.button(text=label, callback_data=f"cplan:days:{gb}:{d}")
    kb.button(text="✏️ مدت دلخواه", callback_data=f"cplan:days:{gb}:custom")
    kb.button(text="🔙 تغییر حجم", callback_data="menu:custom_plan")
    kb.adjust(2, 2, 1, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("cplan:days:"))
async def custom_plan_days_selected(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    remnawave: RemnawaveClient | None = None,
    cache: FastCache | None = None,
):
    """Handle duration selection and show full live preview and breakdown."""
    parts = call.data.split(":")
    gb = parse_int(parts[2]) or 10
    val = parts[3]

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    store_settings = await get_store_settings(session)

    if val == "custom":
        await state.set_state(CustomPlanStates.waiting_for_custom_days)
        await state.update_data(traffic_gb=gb)
        lines = [
            "✏️ <b>ورود مدت زمان دلخواه</b>",
            SEPARATOR,
            f"لطفاً مدت زمان اعتبار بسته را به روز وارد کنید (بین {store_settings.custom_plan_min_days} تا {store_settings.custom_plan_max_days} روز):",
            "نمونه: <code>45</code>",
        ]
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 بازگشت", callback_data=f"cplan:gb:{gb}")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await call.answer()
        return

    days = parse_int(val) or 30
    st_data = await state.get_data() if state else {}
    squad_uuid = st_data.get("squad_uuid")
    squad_name = None
    if squad_uuid and remnawave:
        squad_name = await resolve_squad_name(remnawave, squad_uuid)
    await _render_custom_plan_preview(call, bot, user, user_repo, session, store_settings, gb, days, cache, lang, squad_name)


@router.message(CustomPlanStates.waiting_for_custom_days)
async def custom_plan_custom_days_input(
    message: Message,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    remnawave: RemnawaveClient | None = None,
    cache: FastCache | None = None,
):
    """Handle text input for custom Days."""
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language or "fa"

    data = await state.get_data()
    gb = int(data.get("traffic_gb", 10) or 10)
    squad_uuid = data.get("squad_uuid")
    squad_name = None
    if squad_uuid and remnawave:
        squad_name = await resolve_squad_name(remnawave, squad_uuid)

    store_settings = await get_store_settings(session)
    raw = (message.text or "").strip()
    p2e = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    clean = raw.translate(p2e)

    days = parse_int(clean) or 0
    if days < store_settings.custom_plan_min_days or days > store_settings.custom_plan_max_days:
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 بازگشت", callback_data=f"cplan:gb:{gb}")
        await message.reply(
            f"❌ مدت زمان انتخابی باید بین {store_settings.custom_plan_min_days} تا {store_settings.custom_plan_max_days} روز باشد. لطفاً مجدداً وارد کنید:",
            reply_markup=kb.as_markup(),
        )
        return

    await state.clear()
    if squad_uuid:
        await state.update_data(squad_uuid=squad_uuid)
    lines, kb = await _build_custom_plan_summary(user, session, store_settings, gb, days, cache, lang, squad_name)
    await message.reply("\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML")


async def _build_custom_plan_summary(user, session, store_settings, gb: int, days: int, cache, lang: str, squad_name: str | None = None):
    raw_base, volume_pct, base_price = compute_custom_plan_price(gb, days, store_settings)
    volume_discount_amount = max(0, raw_base - base_price)

    loyalty = await get_user_loyalty(session, user.telegram_id, cache=cache)
    loyalty_pct = loyalty.get("discount_percent", 0)
    loyalty_disc_amt, final_price = apply_loyalty_discount(base_price, loyalty_pct)

    wallet = await WalletRepository(session).get_wallet(user.telegram_id)
    balance = wallet.balance

    lines = [
        "🛠 <b>پیش‌نمایش بسته دلخواه شما</b>",
        SEPARATOR,
    ]
    if squad_name:
        lines.append(f"🌐 دسته سرور : <b>{escape(squad_name)}</b>")
    lines.extend([
        f"📦 حجم ترافیک : <b>{gb} گیگابایت</b>",
        f"⏳ مدت زمان اعتبار : <b>{days} روز</b>",
        "👥 کاربر همزمان مجاز : <b>۲ دستگاه</b>",
        SEPARATOR,
        f"💰 تعرفه بدون تخفیف : {fmt(raw_base)} تومان",
    ])

    if volume_pct > 0:
        lines.append(f"🔥 تخفیف پلکانی حجم : <b>{volume_pct}٪</b> ({fmt(volume_discount_amount)} تومان)")
    if loyalty_pct > 0:
        lines.append(f"💎 تخفیف سطح وفاداری : <b>{loyalty_pct}٪</b> ({fmt(loyalty_disc_amt)} تومان)")

    lines.extend([
        SEPARATOR,
        f"💳 مبلغ قابل پرداخت : <b>{fmt(final_price)} تومان</b>",
        f"👛 موجودی کیف پول شما : <b>{fmt(balance)} تومان</b>",
    ])

    kb = InlineKeyboardBuilder()
    if balance >= final_price:
        kb.button(
            text="✅ خرید و فعال‌سازی از کیف پول",
            callback_data=f"cplan:buy:{gb}:{days}",
        )
    else:
        shortage = final_price - balance
        lines.append(f"\n⚠️ موجودی کیف پول کافی نیست (کسری: {fmt(shortage)} تومان).")
        kb.button(text="👛 افزایش موجودی کیف پول", callback_data="wallet:topup")

    kb.button(text="🔄 تغییر مشخصات بسته", callback_data="menu:custom_plan")
    kb.button(text="🏠 منوی اصلی", callback_data="nav:main_menu")
    kb.adjust(1)

    return lines, kb


async def _render_custom_plan_preview(call: CallbackQuery, bot: Bot, user, user_repo, session, store_settings, gb: int, days: int, cache, lang: str, squad_name: str | None = None):
    lines, kb = await _build_custom_plan_summary(user, session, store_settings, gb, days, cache, lang, squad_name)
    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("cplan:buy:"))
async def custom_plan_execute_purchase(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    remnawave: RemnawaveClient,
    state: FSMContext | None = None,
    cache: FastCache | None = None,
):
    """Execute custom plan purchase atomically and deliver subscription."""
    parts = call.data.split(":")
    gb = parse_int(parts[2]) or 10
    days = parse_int(parts[3]) or 30

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    store_settings = await get_store_settings(session)

    if not store_settings.custom_plan_enabled:
        await call.answer("طراحی بسته دلخواه غیرفعال است.", show_alert=True)
        return

    raw_base, volume_pct, base_price = compute_custom_plan_price(gb, days, store_settings)
    loyalty = await get_user_loyalty(session, user.telegram_id, cache=cache)
    loyalty_pct = loyalty.get("discount_percent", 0)
    _, final_price = apply_loyalty_discount(base_price, loyalty_pct)

    wallet = await WalletRepository(session).get_wallet(user.telegram_id)
    if wallet.balance < final_price:
        await call.answer("موجودی کیف پول شما کافی نیست.", show_alert=True)
        return

    # Derive target squad from state or fallback
    target_squad = None
    if state:
        st_data = await state.get_data()
        target_squad = st_data.get("squad_uuid")
    if not target_squad:
        target_squad = store_settings.default_squad_uuid or None

    custom_svc = SimpleNamespace(
        id=None,
        name="بسته دلخواه",
        price=final_price,
        duration_days=days,
        traffic_gb=gb,
        hwid_limit=2,
        squad_uuid=target_squad,
        badge="custom",
        traffic_strategy="NO_RESET",
        max_purchases=None,
        purchases_count=0,
    )

    chosen_acc = None
    try:
        user_accounts = await remnawave.get_users_by_telegram_id(user.telegram_id) or []
        valid_accs = [a for a in user_accounts if str(a.get("status", "")).upper() not in ("DELETED",)]
        if len(valid_accs) == 1:
            chosen_acc = valid_accs[0]
    except Exception as acc_err:
        logger.debug("Failed checking existing account for custom plan: %s", acc_err)

    result = await execute_purchase(
        remnawave=remnawave,
        session=session,
        service=custom_svc,
        telegram_id=user.telegram_id,
        chosen_account=chosen_acc,
        create_new=(chosen_acc is None),
        bot=bot,
        cache=cache,
    )

    if not result.ok:
        err_msg = result.kind or "خطا در ثبت سفارش بسته دلخواه."
        await call.answer(err_msg, show_alert=True)
        return

    # Invalidate caches
    if cache and hasattr(cache, "delete"):
        await cache.delete(f"tma:user:{user.telegram_id}")
        await cache.delete(f"tma:user:{user.telegram_id}:dashboard:default")
        await cache.delete(f"tma:user:{user.telegram_id}:dashboard")

    acc_id = result.panel_user_id
    order_id = result.order_id
    sub_url = result.subscription_url or ""

    lines = [
        "🎉 <b>بسته دلخواه شما با موفقیت فعال گردید!</b>",
        SEPARATOR,
        f"🧾 شماره سفارش : <code>#{order_id}</code>",
        f"📦 بسته : <b>{gb} گیگابایت — {days} روز</b>",
        f"💳 مبلغ پرداخت شده : <b>{fmt(final_price)} تومان</b>",
    ]
    if getattr(result, "squad_changed", False):
        lines.extend([
            SEPARATOR,
            "⚡️ <b>نکته مهم به‌روزرسانی اتصال:</b>",
            "سرورهای اشتراک شما با موفقیت به دسته جدید تغییر یافت.",
            "لطفاً در نرم‌افزار فیلترشکن خود گزینه <b>Update Subscription (به‌روزرسانی اشتراک)</b> را بزنید تا سرورهای جدید بارگذاری شوند.",
        ])
    if sub_url:
        lines.extend([
            SEPARATOR,
            "🔗 <b>لینک اتصال سابسکریپشن شما:</b>",
            f"<code>{sub_url}</code>",
        ])

    kb = InlineKeyboardBuilder()
    if acc_id:
        kb.button(text="📱 دریافت کانفیگ‌ها", callback_data=f"cfg:acc:{acc_id}")
        kb.button(text="👤 مدیریت این اکانت", callback_data=f"acc:view:{acc_id}")
    kb.button(text="🏠 منوی اصلی", callback_data="nav:main_menu")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer("سفارش شما با موفقیت ثبت شد!", show_alert=False)
