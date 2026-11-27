"""Custom Plan Builder Handler: Interactive volume & duration selection with tiered pricing."""
from __future__ import annotations

import logging
from contextlib import AsyncExitStack
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
from bot.handlers.shop_purchase import _PURCHASE_LOCKS
from bot.services.app_settings import get_store_settings
from bot.services.loyalty import apply_loyalty_discount, get_user_loyalty
from bot.services.menu import render_menu
from bot.services.purchases import (
    execute_purchase,
    filter_active_panel_users,
    maybe_reward_referrer,
    notify_admin,
    resolve_squad_name,
)
from bot.services.remnawave import RemnawaveClient
from bot.states.custom_plan import CustomPlanStates
from bot.web.cache import FastCache, invalidate_user_cache, user_action_lock
from bot.web.user_shop import compute_custom_plan_price, get_extra_device_rate

logger = logging.getLogger(__name__)
router = Router(name="custom_plan")

PRESET_GB = [15, 30, 50, 80, 100, 150, 200]
PRESET_DAYS = [(30, "30 روز (1 ماه)"), (60, "60 روز (2 ماه)"), (90, "90 روز (3 ماه)"), (180, "180 روز (6 ماه)")]


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
    """Step 1: Auto-select squad matching active sub (no squad picker) and prompt Traffic (GB)."""
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

    target_squad = None
    if remnawave:
        try:
            accounts = await remnawave.get_users_by_telegram_id(call.from_user.id) or []
            active_accs = filter_active_panel_users(accounts)
            if active_accs:
                chosen = active_accs[0]
                raw_sqs = chosen.get("activeInternalSquads") or chosen.get("internalSquads") or chosen.get("squads") or []
                for sq in raw_sqs:
                    if isinstance(sq, dict):
                        target_squad = sq.get("uuid") or sq.get("id")
                    elif isinstance(sq, str):
                        target_squad = sq
                    if target_squad:
                        break
        except Exception as exc:
            logger.debug("Failed resolving user squad for custom plan: %s", exc)

    if not target_squad:
        target_squad = store_settings.default_squad_uuid or None

    if state:
        await state.update_data(squad_uuid=str(target_squad) if target_squad else None)

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
    await state.set_state(None)
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
    await state.set_state(None)

    # Render days choice via message reply
    lines = [
        f"✅ حجم انتخاب شده: <b>{gb} گیگابایت</b>",
        SEPARATOR,
        "🛠 <b>طراحی بسته دلخواه (مرحله 2 از 3)</b>",
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
        "🛠 <b>طراحی بسته دلخواه (مرحله 2 از 3)</b>",
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


async def _prompt_devices(
    target: CallbackQuery | Message,
    bot: Bot,
    user,
    user_repo,
    store_settings,
    gb: int,
    days: int,
    lang: str,
):
    extra_rate = get_extra_device_rate(store_settings)
    lines = [
        f"✅ حجم: <b>{gb} گیگابایت</b> | مدت: <b>{days} روز</b>",
        SEPARATOR,
        "📱 <b>طراحی بسته دلخواه (مرحله 3 از 3) — تعداد کاربر</b>",
        f"تعداد کاربر / دستگاه همزمان مجاز برای اتصال به این اشتراک را انتخاب نمایید (به‌ازای هر کاربر اضافه، \u200e+{extra_rate}%\u200e به تعرفه اضافه می‌شود):",
    ]
    kb = InlineKeyboardBuilder()
    kb.button(text="📱 ۱ کاربره (پایه)", callback_data=f"cplan:hwid:{gb}:{days}:1")
    kb.button(text=f"📱 ۲ کاربره \u200e(+{extra_rate}%)\u200e", callback_data=f"cplan:hwid:{gb}:{days}:2")
    kb.button(text=f"📱 ۳ کاربره \u200e(+{extra_rate * 2}%)\u200e", callback_data=f"cplan:hwid:{gb}:{days}:3")
    kb.button(text=f"📱 ۴ کاربره \u200e(+{extra_rate * 3}%)\u200e", callback_data=f"cplan:hwid:{gb}:{days}:4")
    kb.button(text="🔙 تغییر مدت زمان", callback_data=f"cplan:gb:{gb}")
    kb.adjust(2, 2, 1)

    if isinstance(target, CallbackQuery):
        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await target.answer()
    else:
        await target.reply("\n".join(lines), reply_markup=kb.as_markup(), parse_mode="HTML")


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
    """Handle duration selection and prompt Step 3: Choose Device Count."""
    parts = call.data.split(":")
    gb = parse_int(parts[2])
    val = parts[3] if len(parts) > 3 else ""

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    store_settings = await get_store_settings(session)

    min_gb = max(1, int(store_settings.custom_plan_min_gb or 1))
    max_gb = max(min_gb, int(store_settings.custom_plan_max_gb or min_gb))
    if gb is None or gb < min_gb or gb > max_gb:
        await call.answer(f"حجم باید بین {min_gb} تا {max_gb} گیگابایت باشد.", show_alert=True)
        return

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

    days = parse_int(val)
    min_days = max(1, int(store_settings.custom_plan_min_days or 1))
    max_days = max(min_days, int(store_settings.custom_plan_max_days or min_days))
    if days is None or days < min_days or days > max_days:
        await call.answer(f"مدت زمان باید بین {min_days} تا {max_days} روز باشد.", show_alert=True)
        return

    if state:
        await state.update_data(traffic_gb=gb, duration_days=days)

    await _prompt_devices(call, bot, user, user_repo, store_settings, gb, days, lang)


@router.callback_query(F.data.startswith("cplan:hwid:"))
async def custom_plan_hwid_selected(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    remnawave: RemnawaveClient | None = None,
    cache: FastCache | None = None,
):
    """Handle device count selection and show full live preview and breakdown."""
    parts = call.data.split(":")
    if len(parts) < 5:
        await call.answer("دستور منقضی یا نامعتبر است.", show_alert=True)
        return
    gb = parse_int(parts[2])
    days = parse_int(parts[3])
    hwid = parse_int(parts[4]) or 1

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    store_settings = await get_store_settings(session)

    if state:
        await state.update_data(traffic_gb=gb, duration_days=days, hwid_limit=hwid)

    st_data = await state.get_data() if state else {}
    squad_uuid = st_data.get("squad_uuid")
    squad_name = None
    if squad_uuid and remnawave:
        squad_name = await resolve_squad_name(remnawave, squad_uuid)

    await _render_custom_plan_preview(call, bot, user, user_repo, session, store_settings, gb, days, hwid, cache, lang, squad_name)


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
        await state.update_data(squad_uuid=squad_uuid, traffic_gb=gb, duration_days=days)
    await _prompt_devices(message, bot, user, user_repo, store_settings, gb, days, lang)


async def _build_custom_plan_summary(
    user,
    session,
    store_settings,
    gb: int,
    days: int,
    hwid: int,
    cache,
    lang: str,
    squad_name: str | None = None,
):
    raw_base, volume_pct, base_price = compute_custom_plan_price(
        gb, days, store_settings, hwid_limit=hwid
    )
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
        sq_lower = squad_name.lower()
        if "ایران" in squad_name or "iran" in sq_lower:
            lines.append(
                "⚠️ <b>توجه مهم:</b> این بسته متصل به سرور ایران (🇮🇷) است و منحصراً برای دسترسی به سایت‌های بانکی و دولتی ایران از خارج کشور کاربرد دارد."
            )
        elif "تانل" in squad_name or "tunnel" in sq_lower:
            lines.append(
                "🚀 <b>سرویس تانل اختصاصی:</b> مجهز به تانل اختصاصی جهت پایداری بالا در تمامی اپراتورها."
            )

    lines.extend([
        f"📦 حجم ترافیک : <b>{gb} گیگابایت</b>",
        f"🗓 مدت زمان اعتبار : <b>{days} روز</b>",
        f"👥 کاربر همزمان مجاز : <b>{hwid} دستگاه</b>",
        SEPARATOR,
        f"💰 تعرفه بدون تخفیف : {fmt(raw_base)} تومان",
    ])

    if volume_pct > 0:
        lines.append(f"🔥 تخفیف پلکانی حجم : <b>\u200e{volume_pct}%\u200e</b> ({fmt(volume_discount_amount)} تومان)")
    if loyalty_pct > 0:
        lines.append(f"💎 تخفیف سطح وفاداری : <b>\u200e{loyalty_pct}%\u200e</b> ({fmt(loyalty_disc_amt)} تومان)")

    lines.extend([
        SEPARATOR,
        f"💳 مبلغ قابل پرداخت : <b>{fmt(final_price)} تومان</b>",
        f"👛 موجودی کیف پول شما : <b>{fmt(balance)} تومان</b>",
    ])

    kb = InlineKeyboardBuilder()
    if balance >= final_price:
        kb.button(
            text="✅ خرید و فعال‌سازی از کیف پول",
            callback_data=f"cplan:buy:{gb}:{days}:{hwid}",
        )
    else:
        shortage = final_price - balance
        lines.append(f"\n⚠️ موجودی کیف پول کافی نیست (کسری: {fmt(shortage)} تومان).")
        kb.button(text="👛 افزایش موجودی کیف پول", callback_data="wallet:topup")

    kb.button(text="🔄 تغییر مشخصات بسته", callback_data="menu:custom_plan")
    kb.button(text="🏠 منوی اصلی", callback_data="nav:main_menu")
    kb.adjust(1)

    return lines, kb


async def _render_custom_plan_preview(
    call: CallbackQuery,
    bot: Bot,
    user,
    user_repo,
    session,
    store_settings,
    gb: int,
    days: int,
    hwid: int,
    cache,
    lang: str,
    squad_name: str | None = None,
):
    lines, kb = await _build_custom_plan_summary(
        user, session, store_settings, gb, days, hwid, cache, lang, squad_name
    )
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
    gb = parse_int(parts[2]) if len(parts) > 2 else None
    days = parse_int(parts[3]) if len(parts) > 3 else None
    hwid = 1
    target_acc_spec = None
    if len(parts) > 4:
        if parts[4].isdigit():
            hwid = parse_int(parts[4]) or 1
            if len(parts) > 5:
                target_acc_spec = parts[5]
        else:
            target_acc_spec = parts[4]

    effective_cache = cache if cache is not None else getattr(bot, "cache", None)
    _lock_stack = AsyncExitStack()
    acquired = await _lock_stack.enter_async_context(
        user_action_lock(
            effective_cache, call.from_user.id, "purchase", ttl_seconds=45, local_locks=_PURCHASE_LOCKS
        )
    )
    if not acquired:
        await _lock_stack.aclose()
        await call.answer()
        return
    try:
        user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
        store_settings = await get_store_settings(session)

        if not store_settings.custom_plan_enabled:
            await call.answer("طراحی بسته دلخواه غیرفعال است.", show_alert=True)
            return

        min_gb = max(1, int(store_settings.custom_plan_min_gb or 1))
        max_gb = max(min_gb, int(store_settings.custom_plan_max_gb or min_gb))
        min_days = max(1, int(store_settings.custom_plan_min_days or 1))
        max_days = max(min_days, int(store_settings.custom_plan_max_days or min_days))

        if gb is None or gb < min_gb or gb > max_gb:
            await call.answer(f"حجم باید بین {min_gb} تا {max_gb} گیگابایت باشد.", show_alert=True)
            return
        if days is None or days < min_days or days > max_days:
            await call.answer(f"مدت زمان باید بین {min_days} تا {max_days} روز باشد.", show_alert=True)
            return

        if (
            store_settings.custom_plan_price_per_gb <= 0
            and store_settings.custom_plan_price_per_day <= 0
            and store_settings.custom_plan_base_price <= 0
        ):
            await call.answer("تعرفه بسته دلخواه هنوز توسط مدیریت تنظیم نشده است.", show_alert=True)
            return

        raw_base, volume_pct, base_price = compute_custom_plan_price(
            gb, days, store_settings, hwid_limit=hwid
        )
        if base_price <= 0:
            await call.answer("تعرفه محاسبه شده نامعتبر است.", show_alert=True)
            return

        loyalty = await get_user_loyalty(session, user.telegram_id, cache=cache)
        loyalty_pct = loyalty.get("discount_percent", 0)
        loyalty_disc_amt, final_price = apply_loyalty_discount(base_price, loyalty_pct)

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
            price=base_price,
            duration_days=days,
            traffic_gb=gb,
            hwid_limit=hwid,
            squad_uuid=target_squad,
            badge="custom",
            traffic_strategy="NO_RESET",
            max_purchases=None,
            purchases_count=0,
        )

        chosen_acc = None
        create_new = False
        user_accounts = await remnawave.get_users_by_telegram_id(user.telegram_id) or []
        valid_accs = filter_active_panel_users(user_accounts)
        if target_acc_spec == "new":
            create_new = True
        elif target_acc_spec:
            chosen_acc = next((a for a in valid_accs if str(a.get("id")) == str(target_acc_spec)), None)
            if chosen_acc is None:
                await call.answer("اکانت انتخابی یافت نشد.", show_alert=True)
                return
        elif len(valid_accs) == 1:
            chosen_acc = valid_accs[0]
        elif len(valid_accs) > 1:
            kb_pick = InlineKeyboardBuilder()
            for acc in valid_accs:
                uname = escape(str(acc.get("username", "—")))
                kb_pick.button(
                    text=f"👤 {uname}",
                    callback_data=f"cplan:buy:{gb}:{days}:{hwid}:{acc.get('id')}",
                )
            kb_pick.button(
                text="➕ ساخت اکانت جدید",
                callback_data=f"cplan:buy:{gb}:{days}:{hwid}:new",
            )
            kb_pick.button(text="🔙 بازگشت", callback_data="menu:custom_plan")
            kb_pick.adjust(1)
            await render_menu(
                bot,
                user,
                user_repo,
                "👤 <b>انتخاب اکانت برای بسته دلخواه</b>\n\nشما چند اشتراک دارید؛ لطفاً مشخص کنید بسته روی کدام اکانت اعمال شود:",
                kb_pick.as_markup(),
            )
            await call.answer()
            return
        else:
            create_new = True

        result = await execute_purchase(
            remnawave=remnawave,
            session=session,
            service=custom_svc,
            telegram_id=user.telegram_id,
            chosen_account=chosen_acc,
            create_new=create_new,
            discount_amount=loyalty_disc_amt,
            bot=bot,
            cache=cache,
        )

        if not result.ok:
            err_msg = result.message or result.kind or "خطا در ثبت سفارش بسته دلخواه."
            await call.answer(err_msg, show_alert=True)
            return

        await session.commit()
        try:
            await maybe_reward_referrer(bot, session, remnawave, user, paid_amount=final_price, cache=cache)
            await notify_admin(
                bot,
                user,
                custom_svc,
                result,
                session,
                loyalty_discount_amount=loyalty_disc_amt,
                full_name=call.from_user.full_name,
            )
        except Exception as post_err:
            logger.warning("Bot custom plan post-actions failed: %s", post_err)

        # Invalidate all user caches across accounts
        await invalidate_user_cache(cache, user.telegram_id)

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
    finally:
        await _lock_stack.aclose()
