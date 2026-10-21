"""UI rendering, receipts, and admin notification helpers for shop purchase flows."""
from __future__ import annotations

import logging
from html import escape
from typing import Any

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CopyTextButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, admin_thread_kwargs, fmt
from bot.config import get_settings
from bot.db.repositories.referral_repo import ReferralRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.formatting import format_datetime, now_tz
from bot.services.purchases import calc_price, receipt_price_lines, record_coupon_usage_if_any
from bot.services.remnawave import RemnawaveClient
from bot.services.service_display import service_block

logger = logging.getLogger(__name__)


async def render_menu(*args, **kwargs):
    import bot.handlers.shop_purchase as sp_module
    return await sp_module.render_menu(*args, **kwargs)

async def _ensure_can_buy(
    bot: Bot, user, user_repo: UserRepository, remnawave: RemnawaveClient
) -> bool:
    """Guests may buy their FIRST service (it creates the panel account).

    Users who already own panel account(s) but are not verified must log
    in first — otherwise anyone could renew someone else's flow. Returns
    True when the purchase may proceed (renders the gate message itself).
    """
    if user.is_verified:
        return True
    accounts = await remnawave.get_users_by_telegram_id(user.telegram_id)
    if accounts is None:
        await render_menu(
            bot, user, user_repo, t(user.language, "stats_error"),
            InlineKeyboardBuilder()
            .button(text=t(user.language, "btn_back_to_menu"),
                    callback_data="nav:main_menu").as_markup(),
        )
        return False
    if not accounts:
        return True  # first purchase — allowed, creates the account
    from bot.keyboards.inline import welcome_keyboard
    await render_menu(
        bot, user, user_repo, t(user.language, "not_verified"),
        welcome_keyboard(user.language),
    )
    return False


async def _extract_coupon_from_state(state: FSMContext) -> tuple[str | None, int]:
    data = await state.get_data()
    code = data.get("coupon_code")
    amt = int(data.get("discount_amount", 0) or 0) if code else 0
    return code, amt


async def _render_buy_confirm(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
    service, balance: int, confirm_callback: str, lang: str,
    target_name: str | None = None,
    back_callback: str = "menu:services",
    flow_type: str = "d",
    target_id: str = "0",
    coupon_code: str | None = None,
    discount_amount: int = 0,
) -> None:
    effective_price, discount_amount = calc_price(service.price, discount_amount)
    kb = InlineKeyboardBuilder()

    if balance >= effective_price:
        kb.button(text=t(lang, "btn_confirm_pay"), callback_data=confirm_callback)
    else:
        kb.button(text=t(lang, "btn_topup"), callback_data="wallet:topup")

    if coupon_code:
        kb.button(
            text=f"❌ {coupon_code}",
            callback_data=f"svc:rmcpn:{service.id}:{flow_type}:{target_id}",
        )
    else:
        kb.button(
            text=t(lang, "btn_apply_coupon"),
            callback_data=f"svc:cpn:{service.id}:{flow_type}:{target_id}",
        )

    kb.button(text=t(lang, "btn_back"), callback_data=back_callback)
    kb.adjust(1)

    target_line = (
        f"👤 {t(lang, 'buy_target_account')} : <b>{escape(target_name)}</b>\n"
        if target_name
        else ""
    )

    price_lines = receipt_price_lines(
        lang, service.price, effective_price, discount_amount, coupon_code, t(lang, "svc_currency"), is_confirm_card=True
    )

    if balance < effective_price:
        shortage = effective_price - balance
        balance_note = (
            f"\n\n⚠️ موجودی شما کافی نیست (کسری: <b>{fmt(shortage)}</b> {t(lang, 'svc_currency')}).\n"
            f"می‌توانید کیف پول خود را شارژ کنید یا در صورت داشتن کد تخفیف، آن را ثبت نمایید."
        ) if lang == "fa" else (
            f"\n\n⚠️ Insufficient balance (need <b>{fmt(shortage)}</b> {t(lang, 'svc_currency')}).\n"
            f"You can top up your wallet or apply a discount coupon."
        )
    else:
        balance_note = ""

    await render_menu(
        bot, user, user_repo,
        f"{t(lang, 'buy_confirm_title')}\n{SEPARATOR}\n"
        f"{service_block(service, lang)}\n\n"
        f"{target_line}"
        f"{chr(10).join(price_lines)}\n"
        f"👛 {t(lang, 'buy_current_balance')} : <b>{fmt(balance)}</b> {t(lang, 'svc_currency')}"
        f"{balance_note}",
        kb.as_markup(),
    )


async def _maybe_reward_referrer(
    bot: Bot, session: AsyncSession, remnawave: RemnawaveClient, user,
) -> None:
    if not getattr(user, "referred_by_id", None):
        return
    store = await get_store_settings(session)
    if not store.referral_enabled or store.referral_reward_gb <= 0:
        return
    referral_repo = ReferralRepository(session)
    if await referral_repo.has_rewarded(user.telegram_id):
        return

    reward_gb = store.referral_reward_gb
    inviter_accs = await remnawave.get_users_by_telegram_id(user.referred_by_id)
    if inviter_accs:
        inv_acc = inviter_accs[0]
        cur_limit = int(inv_acc.get("trafficLimitBytes") or 0)
        if cur_limit > 0:
            new_limit = cur_limit + reward_gb * (1024 ** 3)
            try:
                await remnawave.update_user_subscription(
                    int(inv_acc["id"]), inv_acc.get("expireAt"), new_limit
                )
            except Exception:
                logger.exception("Failed to add referral traffic to panel user %s", inv_acc.get("id"))

    await referral_repo.record_reward(user.referred_by_id, user.telegram_id, reward_gb)

    inviter_user = await UserRepository(session).get_by_telegram_id(user.referred_by_id)
    if inviter_user:
        inviter_user.spin_tickets = (getattr(inviter_user, "spin_tickets", 0) or 0) + 1
    inv_lang = (inviter_user.language if inviter_user else None) or "fa"
    try:
        ticket_note = (
            "\n\n🎫 <b>+۱ شانس چرخش گردونه (تیکت اسپین)</b> نیز به حساب شما اضافه شد!"
            if inv_lang == "fa"
            else "\n\n🎫 <b>+1 Lucky Wheel spin ticket</b> has also been credited to your account!"
        )
        await bot.send_message(
            user.referred_by_id,
            t(inv_lang, "referral_reward_notify", reward_gb=reward_gb) + ticket_note,
        )
    except Exception:
        logger.exception("Failed to notify inviter %s of referral reward", user.referred_by_id)


async def _render_purchase_result(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
    result, service, lang: str,
    coupon_code: str | None = None,
    discount_amount: int = 0,
) -> None:
    if result.kind == "success":
        await user_repo.set_verified(user)
        kb = InlineKeyboardBuilder()

        # Row 1: Copy subscription link button (if available)
        if result.subscription_url:
            kb.button(
                text=t(lang, "btn_copy_sub_link"),
                copy_text=CopyTextButton(text=result.subscription_url),
            )

        # Row 2: Get single configs + Connection guide
        cfg_cb = f"cfg:acc:{result.panel_user_id}" if result.panel_user_id else "cfg:root"
        if lang == "fa":
            kb.button(text=t(lang, "btn_connection_guide"), callback_data="menu:guide")
            kb.button(text=t(lang, "btn_get_configs"), callback_data=cfg_cb)
        else:
            kb.button(text=t(lang, "btn_get_configs"), callback_data=cfg_cb)
            kb.button(text=t(lang, "btn_connection_guide"), callback_data="menu:guide")

        # Row 3: Account management + Main menu
        if lang == "fa":
            kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
            kb.button(text=t(lang, "btn_account_mgmt"), callback_data="menu:account")
        else:
            kb.button(text=t(lang, "btn_account_mgmt"), callback_data="menu:account")
            kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")

        if result.subscription_url:
            kb.adjust(1, 2, 2)
        else:
            kb.adjust(2, 2)

        tz = get_settings().TIMEZONE
        dt_str = format_datetime(now_tz(tz), lang)

        dur_text = (
            ("هم‌گام با انقضای فعلی (بدون تغییر)" if lang == "fa" else "Preserved current expiry")
            if service.duration_days == 0 and service.traffic_gb > 0
            else (
                t(lang, "svc_days", days=service.duration_days)
                if service.duration_days and service.duration_days > 0
                else t(lang, "unlimited")
            )
        )
        traf_text = (
            ("بدون تغییر حجم فعلی" if lang == "fa" else "Preserved current traffic")
            if service.traffic_gb == 0 and service.duration_days > 0
            else (
                t(lang, "svc_gb", gb=service.traffic_gb)
                if service.traffic_gb and service.traffic_gb > 0
                else t(lang, "unlimited")
            )
        )

        receipt_lines = [
            f"🧾 <b>{t(lang, 'receipt_title')}</b>",
            SEPARATOR,
            f"📅 {t(lang, 'receipt_date')} : <code>{dt_str}</code>",
            f"💳 {t(lang, 'receipt_status')} : <b>{t(lang, 'receipt_status_paid')}</b>",
            f"📦 {t(lang, 'receipt_service')} : <b>\u200e{escape(service.name)}\u200e</b>",
        ]
        if result.panel_username:
            receipt_lines.append(
                f"{t(lang, 'stats_account')} : <code>{escape(result.panel_username)}</code>"
            )
        receipt_lines.extend([
            f"⏳ {t(lang, 'receipt_duration')} : <b>{dur_text}</b>",
            f"🌐 {t(lang, 'receipt_traffic')} : <b>{traf_text}</b>",
        ])

        effective_price, discount_amount = calc_price(service.price, discount_amount)
        receipt_lines.extend(
            receipt_price_lines(
                lang, service.price, effective_price, discount_amount, coupon_code, t(lang, "svc_currency")
            )
        )
        receipt_lines.append(
            f"👛 {t(lang, 'receipt_balance')} : <b>{fmt(result.new_balance)} {t(lang, 'svc_currency')}</b>"
        )
        if result.subscription_url:
            receipt_lines.append(SEPARATOR)
            receipt_lines.append(
                t(lang, "buy_success_link", url=escape(result.subscription_url))
            )
        receipt_lines.append(f"\n💡 {t(lang, 'receipt_footer_hint')}")

        await render_menu(
            bot, user, user_repo,
            "\n".join(receipt_lines),
            kb.as_markup(),
        )
    elif result.kind == "insufficient":
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_topup"), callback_data="wallet:topup")
        kb.button(text=t(lang, "btn_back"), callback_data="menu:services")
        kb.adjust(1)
        await render_menu(
            bot, user, user_repo,
            t(
                lang, "buy_insufficient",
                balance=fmt(result.new_balance),
                price=fmt(service.price),
                currency=t(lang, "svc_currency"),
            ),
            kb.as_markup(),
        )
    elif result.kind == "maintenance":
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_back"), callback_data="menu:services")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "maintenance_user"), kb.as_markup())
    elif result.kind == "needs_active_sub":
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_back"), callback_data="menu:services")
        kb.adjust(1)
        msg = (
            "⚠️ <b>اشتراک فعالی یافت نشد!</b>\n\n"
            "بسته‌های افزایش حجم و افزایش زمان صرفاً به سرویس‌های فعال اضافه می‌شوند.\n"
            "جهت استفاده، لطفاً ابتدا یک سرویس کامل خریداری فرمایید."
            if lang == "fa"
            else "⚠️ <b>No active subscription found!</b>\n\nAdd-on packages can only be applied to active services."
        )
        await render_menu(bot, user, user_repo, msg, kb.as_markup())
    else:  # failed
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_back"), callback_data="menu:services")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "buy_failed"), kb.as_markup())


async def _notify_admin(
    bot: Bot,
    user,
    service,
    result,
    session: AsyncSession | None = None,
    coupon_code: str | None = None,
    discount_amount: int = 0,
    full_name: str | None = None,
) -> None:
    tg_username = f"\u200e@{escape(user.username)}\u200e" if user.username else "—"
    effective_price, discount_amount = calc_price(service.price, discount_amount)
    display_name = escape(full_name or user.username or str(user.telegram_id))

    price_lines = []
    if coupon_code and discount_amount > 0:
        price_lines.append(f"💰 {t('fa', 'svc_field_price')} : <b>{fmt(service.price)}</b> {t('fa', 'svc_currency')}")
        price_lines.append(f"🏷 {t('fa', 'retention_code_label')} (<code>{coupon_code}</code>) : <b>\u200e-{fmt(discount_amount)}</b> {t('fa', 'svc_currency')}")
        price_lines.append(f"💵 پرداختی از کیف پول : <b>{fmt(effective_price)}</b> {t('fa', 'svc_currency')}")
    else:
        price_lines.append(f"💰 مبلغ کل : <b>{fmt(service.price)}</b> {t('fa', 'svc_currency')}")
        price_lines.append(f"💵 پرداختی از کیف پول : <b>{fmt(service.price)}</b> {t('fa', 'svc_currency')}")

    prices_str = "\n".join(price_lines)

    text = (
        f"🛒 <b>{t('fa', 'buy_admin_log')}</b>\n\n"
        f"📦 <b>\u200e{escape(service.name)}\u200e</b>\n"
        f"{prices_str}\n\n"
        f"👤 {display_name} — <code>{user.telegram_id}</code>\n"
        f"🔗 {t('fa', 'svc_requested_username')} : {tg_username}\n"
        f"🔑 <code>{escape(str(result.panel_username or ''))}</code>\n\n"
        f"{t('fa', 'buy_remaining_balance', balance=fmt(result.new_balance), currency=t('fa', 'svc_currency'))}"
    )
    settings = get_settings()
    topic_id = settings.ADMIN_TOPIC_ORDERS
    if session is not None:
        store = await get_store_settings(session)
        if store.topic_orders is not None:
            topic_id = store.topic_orders
    thread_kwargs = admin_thread_kwargs(topic_id=topic_id)
    try:
        await bot.send_message(settings.ADMIN_CHAT_ID, text, **thread_kwargs)
    except Exception:
        logger.exception("failed to deliver purchase log to admin chat")


ensure_can_buy = _ensure_can_buy
extract_coupon_from_state = _extract_coupon_from_state
render_buy_confirm = _render_buy_confirm
maybe_reward_referrer = _maybe_reward_referrer
render_purchase_result = _render_purchase_result
notify_admin = _notify_admin


async def finalize_purchase(
    bot: Bot,
    session: AsyncSession,
    remnawave: RemnawaveClient,
    user: Any,
    user_repo: UserRepository,
    service: Any,
    result: Any,
    state: FSMContext,
    coupon_code: str | None = None,
    discount_amount: int = 0,
    full_name: str | None = None,
    lang: str = "fa",
) -> None:
    """Unified pipeline executed after successful purchase/renewal (SSOT)."""
    if result.kind == "success":
        await record_coupon_usage_if_any(
            session, coupon_code, user.telegram_id, result.order_id, discount_amount
        )
        await _maybe_reward_referrer(bot, session, remnawave, user)
        await state.clear()
        await _notify_admin(
            bot,
            user,
            service,
            result,
            session,
            coupon_code=coupon_code,
            discount_amount=discount_amount,
            full_name=full_name,
        )
    await _render_purchase_result(
        bot,
        user,
        user_repo,
        session,
        result,
        service,
        lang,
        coupon_code=coupon_code,
        discount_amount=discount_amount,
    )
