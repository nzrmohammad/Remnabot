"""«Services» section with automatic purchase.

Buying flow:
1. «سرویس‌ها» → list of active services (admin-managed), each marked
   ✅/❌ based on the user's wallet balance.
2. Tap a service → details + «خرید» button.
3. Balance is checked; if enough → confirm screen → «پرداخت و فعال‌سازی».
4. The panel account is renewed (or created), the wallet is charged
   automatically and the subscription link is shown. No manual work.
   If the user owns more than one panel account, they choose which one.

Quick renewal: alert messages carry a «🔄 تمدید این اکانت» button
(`svc:renacc:{panelUserId}`) which opens the same purchase flow with the
account pre-selected — the user only picks a service and pays.

Order details are recorded in the `orders` table for the sales report.
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, CopyTextButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.referral_repo import ReferralRepository
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.support_repo import SupportMessageRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings, is_maintenance
from bot.services.formatting import format_datetime, now_tz
from bot.services.menu import delete_message_silently, render_menu
from bot.services.purchases import execute_purchase
from bot.services.remnawave import RemnawaveClient
from bot.services.service_display import fmt_price, fmt_traffic, service_block
from bot.states.service_request import ServiceRequestStates
from bot.common import SEPARATOR, fmt

logger = logging.getLogger(__name__)
router = Router(name="service_request")

# In-memory per-user purchase lock: prevents double-tap double-charge.
_PURCHASE_LOCKS: set[int] = set()

# Admin-chat service requests already notified (survives double-clicks;
# the button is also removed after the first press).
_REQUEST_DONE_NOTIFIED: set[int] = set()


def _safe_int(value: str | None) -> int | None:
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return None


async def _ensure_can_buy(bot: Bot, user, user_repo: UserRepository,
                          remnawave: RemnawaveClient) -> bool:
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


async def _render_services(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
    renew_account_id: str | None = None,
) -> None:
    """Service list. With `renew_account_id`, buttons buy FOR that account."""
    lang = user.language or "fa"
    services = await ServiceRepository(session).list_active()
    wallet = await WalletRepository(session).get_wallet(user.telegram_id)
    balance = wallet.balance

    lines = [t(lang, "services_title"), SEPARATOR]
    if not services:
        lines.append(t(lang, "services_active_empty"))
    else:
        for i, service in enumerate(services, start=1):
            indicator = "✅" if balance >= service.price else "❌"
            lines.append(f"{i}) {indicator} {service_block(service, lang)}")
            if i < len(services):
                lines.append("")
        lines.append(SEPARATOR)
        lines.append(t(lang, "services_policy_hint"))

    kb = InlineKeyboardBuilder()
    for service in services:
        indicator = "✅" if balance >= service.price else "❌"
        cb = (
            f"svc:buya:{service.id}:{renew_account_id}"
            if renew_account_id
            else f"svc:view:{service.id}"
        )
        traffic_str = fmt_traffic(service.traffic_gb, lang)
        price_str = f"{fmt_price(service.price)} {t(lang, 'svc_currency')}"
        kb.button(
            text=f"{indicator} {service.name} — {traffic_str} — {price_str}",
            callback_data=cb,
        )
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


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
    effective_price = max(0, service.price - discount_amount)
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

    price_lines = [f"💰 {t(lang, 'svc_field_price')} : <b>{fmt(service.price)}</b> {t(lang, 'svc_currency')}"]
    if coupon_code and discount_amount > 0:
        price_lines.append(
            f"🏷 {t(lang, 'retention_code_label')} (<code>{coupon_code}</code>) : <b>\u200e-{fmt(discount_amount)}</b> {t(lang, 'svc_currency')}"
        )
        price_lines.append(
            f"💵 {t(lang, 'receipt_amount')} : <b>{fmt(effective_price)}</b> {t(lang, 'svc_currency')}"
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
    inv_lang = (inviter_user.language if inviter_user else None) or "fa"
    try:
        await bot.send_message(
            user.referred_by_id,
            t(inv_lang, "referral_reward_notify", reward_gb=reward_gb),
        )
    except Exception:
        logger.exception("Failed to notify inviter %s of referral reward", user.referred_by_id)


from bot.handlers.shop_trial import (
    _request_done_kb,
    request_done_notify,
)



@router.callback_query(F.data == "menu:services")
async def services_entry(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_services(bot, user, user_repo, session)
    await call.answer()


# --------------------------------------------------------------------- #
# Free Trial & Service Requests - delegated to bot.handlers.shop_trial
# --------------------------------------------------------------------- #
from bot.handlers.shop_trial import (
    service_new_request,
    service_trial_username,
    service_new_forward,
    router as _shop_trial_router,
)

router.include_router(_shop_trial_router)


# --------------------------------------------------------------------- #
# Coupon handling in purchase flow - delegated to bot.handlers.shop_coupons
# --------------------------------------------------------------------- #
from bot.handlers.shop_coupons import (
    apply_coupon_prompt,
    remove_coupon,
    process_coupon_code,
    router as _shop_coupons_router,
)

router.include_router(_shop_coupons_router)



# --------------------------------------------------------------------- #
# Quick renewal from an alert message
# --------------------------------------------------------------------- #
async def _verify_account(
    remnawave: RemnawaveClient, telegram_id: int, panel_user_id: str
) -> dict | None:
    accounts = await remnawave.get_users_by_telegram_id(telegram_id)
    if accounts is None:
        return None
    return next(
        (a for a in accounts if str(a.get("id")) == str(panel_user_id)), None
    )


@router.callback_query(F.data.startswith("svc:renacc:"))
async def renew_pick_service(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    if await is_maintenance(session):
        await call.answer(t(lang, "maintenance_user"), show_alert=True)
        return

    if not await _ensure_can_buy(bot, user, user_repo, remnawave):
        await call.answer()
        return

    panel_user_id = call.data.rsplit(":", 1)[1]
    chosen = await _verify_account(remnawave, user.telegram_id, panel_user_id)
    if chosen is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    await _render_services(
        bot, user, user_repo, session, renew_account_id=str(chosen["id"])
    )
    await call.answer()


@router.callback_query(F.data.startswith("svc:buya:"))
async def buy_for_account(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
):
    try:
        _, _, service_id_s, panel_user_id = call.data.split(":")
        service_id = _safe_int(service_id_s)
    except ValueError:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if service_id is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    if await is_maintenance(session):
        await call.answer(t(lang, "maintenance_user"), show_alert=True)
        return

    if not await _ensure_can_buy(bot, user, user_repo, remnawave):
        await call.answer()
        return

    service = await ServiceRepository(session).get(int(service_id))
    if service is None or not service.is_active:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return
    chosen = await _verify_account(remnawave, user.telegram_id, panel_user_id)
    if chosen is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    state_data = await state.get_data()
    coupon_code = state_data.get("coupon_code")
    discount_amount = state_data.get("discount_amount", 0) if coupon_code else 0

    wallet = await WalletRepository(session).get_wallet(user.telegram_id)
    username = escape(str(chosen.get("username", "—")))
    await _render_buy_confirm(
        bot, user, user_repo, session, service, wallet.balance,
        confirm_callback=f"svc:confirma:{service.id}:{panel_user_id}",
        lang=lang,
        target_name=username,
        back_callback=f"svc:buy:{service.id}",
        flow_type="a",
        target_id=str(panel_user_id),
        coupon_code=coupon_code,
        discount_amount=discount_amount,
    )
    await call.answer(t(lang, "buy_for_account_toast", username=username))


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
            t(lang, "svc_days", days=service.duration_days)
            if service.duration_days and service.duration_days > 0
            else t(lang, "unlimited")
        )
        traf_text = (
            t(lang, "svc_gb", gb=service.traffic_gb)
            if service.traffic_gb and service.traffic_gb > 0
            else t(lang, "unlimited")
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

        effective_price = max(0, service.price - discount_amount)
        if coupon_code and discount_amount > 0:
            receipt_lines.append(
                f"💰 {t(lang, 'svc_field_price')} : <b>{fmt(service.price)} {t(lang, 'svc_currency')}</b>"
            )
            receipt_lines.append(
                f"🏷 {t(lang, 'retention_code_label')} (<code>{coupon_code}</code>) : <b>\u200e-{fmt(discount_amount)} {t(lang, 'svc_currency')}</b>"
            )
            receipt_lines.append(
                f"💵 {t(lang, 'receipt_amount')} : <b>{fmt(effective_price)} {t(lang, 'svc_currency')}</b>"
            )
        else:
            receipt_lines.append(
                f"💰 {t(lang, 'receipt_amount')} : <b>{fmt(service.price)} {t(lang, 'svc_currency')}</b>"
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
    else:  # failed
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_back"), callback_data="menu:services")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "buy_failed"), kb.as_markup())


@router.callback_query(F.data.startswith("svc:confirma:"))
async def confirm_for_account(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
):
    try:
        _, _, service_id_s, panel_user_id = call.data.split(":")
        service_id = _safe_int(service_id_s)
    except ValueError:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if service_id is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if call.from_user.id in _PURCHASE_LOCKS:
        await call.answer()
        return
    _PURCHASE_LOCKS.add(call.from_user.id)
    try:
        user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
        lang = user.language

        if not await _ensure_can_buy(bot, user, user_repo, remnawave):
            await call.answer()
            return

        service = await ServiceRepository(session).get(int(service_id))
        if service is None or not service.is_active:
            await call.answer(t(lang, "acc_error"), show_alert=True)
            return
        chosen = await _verify_account(remnawave, user.telegram_id, panel_user_id)
        if chosen is None:
            await call.answer(t(lang, "acc_error"), show_alert=True)
            return

        state_data = await state.get_data()
        coupon_code = state_data.get("coupon_code")
        discount_amount = state_data.get("discount_amount", 0) if coupon_code else 0

        result = await execute_purchase(
            remnawave, session, service, user.telegram_id,
            chosen_account=chosen, discount_amount=discount_amount,
        )
        if result.kind == "success":
            if coupon_code and result.order_id:
                c_repo = CouponRepository(session)
                cpn = await c_repo.get_by_code(coupon_code)
                if cpn:
                    await c_repo.record_usage(cpn.id, user.telegram_id, result.order_id, discount_amount)
            await _maybe_reward_referrer(bot, session, remnawave, user)
            await state.clear()
            await _notify_admin(
                bot, user, service, result, session,
                coupon_code=coupon_code, discount_amount=discount_amount,
                full_name=call.from_user.full_name,
            )
        await _render_purchase_result(
            bot, user, user_repo, session, result, service, lang,
            coupon_code=coupon_code, discount_amount=discount_amount,
        )
        await call.answer()
    finally:
        _PURCHASE_LOCKS.discard(call.from_user.id)


@router.callback_query(F.data.startswith("svc:buynew:"))
async def buy_new_account(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
):
    service_id = _safe_int(call.data.rsplit(":", 1)[1])
    if service_id is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    if await is_maintenance(session):
        await call.answer(t(lang, "maintenance_user"), show_alert=True)
        return

    if not await _ensure_can_buy(bot, user, user_repo, remnawave):
        await call.answer()
        return

    service = await ServiceRepository(session).get(service_id)
    if service is None or not service.is_active:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    state_data = await state.get_data()
    coupon_code = state_data.get("coupon_code")
    discount_amount = state_data.get("discount_amount", 0) if coupon_code else 0

    wallet = await WalletRepository(session).get_wallet(user.telegram_id)
    await _render_buy_confirm(
        bot, user, user_repo, session, service, wallet.balance,
        confirm_callback=f"svc:confirmn:{service.id}",
        lang=lang,
        target_name=t(lang, "buy_target_new"),
        back_callback=f"svc:buy:{service.id}",
        flow_type="n",
        target_id="0",
        coupon_code=coupon_code,
        discount_amount=discount_amount,
    )
    await call.answer()


@router.callback_query(F.data.startswith("svc:confirmn:"))
async def confirm_new_account(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
):
    service_id = _safe_int(call.data.rsplit(":", 1)[1])
    if service_id is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if call.from_user.id in _PURCHASE_LOCKS:
        await call.answer()
        return
    _PURCHASE_LOCKS.add(call.from_user.id)
    try:
        user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
        lang = user.language

        if not await _ensure_can_buy(bot, user, user_repo, remnawave):
            await call.answer()
            return

        service = await ServiceRepository(session).get(service_id)
        if service is None or not service.is_active:
            await call.answer(t(lang, "acc_error"), show_alert=True)
            return

        state_data = await state.get_data()
        coupon_code = state_data.get("coupon_code")
        discount_amount = state_data.get("discount_amount", 0) if coupon_code else 0

        result = await execute_purchase(
            remnawave, session, service, user.telegram_id,
            create_new=True, discount_amount=discount_amount,
        )
        if result.kind == "success":
            if coupon_code and result.order_id:
                c_repo = CouponRepository(session)
                cpn = await c_repo.get_by_code(coupon_code)
                if cpn:
                    await c_repo.record_usage(cpn.id, user.telegram_id, result.order_id, discount_amount)
            await _maybe_reward_referrer(bot, session, remnawave, user)
            await state.clear()
            await _notify_admin(
                bot, user, service, result, session,
                coupon_code=coupon_code, discount_amount=discount_amount,
                full_name=call.from_user.full_name,
            )
        await _render_purchase_result(
            bot, user, user_repo, session, result, service, lang,
            coupon_code=coupon_code, discount_amount=discount_amount,
        )
        await call.answer()
    finally:
        _PURCHASE_LOCKS.discard(call.from_user.id)



# --------------------------------------------------------------------- #
# Regular purchase flow
# --------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("svc:view:"))
async def service_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession
):
    service_id = _safe_int(call.data.rsplit(":", 1)[1])
    if service_id is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    service = await ServiceRepository(session).get(service_id)
    if service is None or not service.is_active:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_buy"), callback_data=f"svc:buy:{service.id}")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:services")
    kb.adjust(1)

    await render_menu(
        bot, user, user_repo,
        f"{t(lang, 'svc_view_title', name=escape(service.name))}\n"
        f"{SEPARATOR}\n{service_block(service, lang)}\n\n"
        f"{t(lang, 'services_policy_hint')}",
        kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("svc:buy:"))
async def service_buy(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
):
    service_id = _safe_int(call.data.rsplit(":", 1)[1])
    if service_id is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    if await is_maintenance(session):
        await call.answer(t(lang, "maintenance_user"), show_alert=True)
        return

    if not await _ensure_can_buy(bot, user, user_repo, remnawave):
        await call.answer()
        return

    service = await ServiceRepository(session).get(service_id)
    if service is None or not service.is_active:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    state_data = await state.get_data()
    coupon_code = state_data.get("coupon_code")
    discount_amount = state_data.get("discount_amount", 0) if coupon_code else 0

    wallet = await WalletRepository(session).get_wallet(user.telegram_id)

    # Check if the user already has panel accounts
    accounts = await remnawave.get_users_by_telegram_id(user.telegram_id)
    if accounts is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    valid_accounts = []
    seen = set()
    for a in accounts:
        aid = str(a.get("id"))
        if aid not in seen and str(a.get("status", "")).upper() not in ("DELETED",):
            seen.add(aid)
            valid_accounts.append(a)

    if valid_accounts:
        kb = InlineKeyboardBuilder()
        for a in valid_accounts:
            uname = escape(str(a.get("username", "—")))
            kb.button(
                text=t(lang, "btn_renew_account_item", username=uname),
                callback_data=f"svc:buya:{service.id}:{a.get('id')}",
            )
        kb.button(
            text=t(lang, "btn_buy_new_account"),
            callback_data=f"svc:buynew:{service.id}",
        )
        kb.button(text=t(lang, "btn_back"), callback_data=f"svc:view:{service.id}")
        kb.adjust(1)

        text = (
            f"🛍 <b>{t(lang, 'buy_choose_account_title', name=escape(service.name))}</b>\n"
            f"{SEPARATOR}\n"
            f"{service_block(service, lang)}\n\n"
            f"{t(lang, 'buy_choose_account_prompt')}"
        )
        await render_menu(bot, user, user_repo, text, kb.as_markup())
        await call.answer()
        return

    # First-time purchase without any existing accounts
    await _render_buy_confirm(
        bot, user, user_repo, session, service, wallet.balance,
        confirm_callback=f"svc:confirmn:{service.id}", lang=lang,
        target_name=t(lang, "buy_target_new"),
        back_callback=f"svc:view:{service.id}",
        flow_type="d",
        target_id="0",
        coupon_code=coupon_code,
        discount_amount=discount_amount,
    )
    await call.answer()


@router.callback_query(F.data.startswith("svc:confirm:"))
async def service_confirm(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
):
    service_id = _safe_int(call.data.rsplit(":", 1)[1])
    if service_id is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if call.from_user.id in _PURCHASE_LOCKS:
        await call.answer()
        return
    _PURCHASE_LOCKS.add(call.from_user.id)
    try:
        user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
        lang = user.language

        if not await _ensure_can_buy(bot, user, user_repo, remnawave):
            await call.answer()
            return

        service = await ServiceRepository(session).get(service_id)
        if service is None or not service.is_active:
            await call.answer(t(lang, "acc_error"), show_alert=True)
            return

        state_data = await state.get_data()
        coupon_code = state_data.get("coupon_code")
        discount_amount = state_data.get("discount_amount", 0) if coupon_code else 0

        result = await execute_purchase(
            remnawave, session, service, user.telegram_id, discount_amount=discount_amount
        )

        if result.kind == "needs_account":
            kb = InlineKeyboardBuilder()
            for acc in (result.accounts or []):
                username = escape(str(acc.get("username", "—")))
                status = str(acc.get("status", "")).upper()
                kb.button(
                    text=f"{username} — {status}",
                    callback_data=f"svc:acc:{service.id}:{acc.get('id')}",
                )
            kb.button(text=t(lang, "btn_back"), callback_data="menu:services")
            kb.adjust(1)
            await render_menu(
                bot, user, user_repo, t(lang, "buy_choose_account"), kb.as_markup()
            )
            await call.answer()
            return

        if result.kind == "success":
            if coupon_code and result.order_id:
                c_repo = CouponRepository(session)
                cpn = await c_repo.get_by_code(coupon_code)
                if cpn:
                    await c_repo.record_usage(cpn.id, user.telegram_id, result.order_id, discount_amount)
            await _maybe_reward_referrer(bot, session, remnawave, user)
            await state.clear()
            await _notify_admin(
                bot, user, service, result, session,
                coupon_code=coupon_code, discount_amount=discount_amount,
                full_name=call.from_user.full_name,
            )

        await _render_purchase_result(
            bot, user, user_repo, session, result, service, lang,
            coupon_code=coupon_code, discount_amount=discount_amount,
        )
        await call.answer()
    finally:
        _PURCHASE_LOCKS.discard(call.from_user.id)


@router.callback_query(F.data.startswith("svc:acc:"))
async def service_choose_account(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
):
    try:
        _, _, service_id_s, panel_user_id = call.data.split(":")
        service_id = _safe_int(service_id_s)
    except ValueError:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if service_id is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if call.from_user.id in _PURCHASE_LOCKS:
        await call.answer()
        return
    _PURCHASE_LOCKS.add(call.from_user.id)
    try:
        user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
        lang = user.language

        if not await _ensure_can_buy(bot, user, user_repo, remnawave):
            await call.answer()
            return

        service = await ServiceRepository(session).get(int(service_id))
        if service is None or not service.is_active:
            await call.answer(t(lang, "acc_error"), show_alert=True)
            return

        # The chosen account must really belong to this Telegram ID.
        chosen = await _verify_account(remnawave, user.telegram_id, panel_user_id)
        if chosen is None:
            await call.answer(t(lang, "acc_error"), show_alert=True)
            return

        state_data = await state.get_data()
        coupon_code = state_data.get("coupon_code")
        discount_amount = state_data.get("discount_amount", 0) if coupon_code else 0

        result = await execute_purchase(
            remnawave, session, service, user.telegram_id,
            chosen_account=chosen, discount_amount=discount_amount,
        )
        if result.kind == "success":
            if coupon_code and result.order_id:
                c_repo = CouponRepository(session)
                cpn = await c_repo.get_by_code(coupon_code)
                if cpn:
                    await c_repo.record_usage(cpn.id, user.telegram_id, result.order_id, discount_amount)
            await _maybe_reward_referrer(bot, session, remnawave, user)
            await state.clear()
            await _notify_admin(
                bot, user, service, result, session,
                coupon_code=coupon_code, discount_amount=discount_amount,
                full_name=call.from_user.full_name,
            )
        await _render_purchase_result(
            bot, user, user_repo, session, result, service, lang,
            coupon_code=coupon_code, discount_amount=discount_amount,
        )
        await call.answer()
    finally:
        _PURCHASE_LOCKS.discard(call.from_user.id)


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
    tg_username = f"@{user.username}" if user.username else "—"
    effective_price = max(0, service.price - discount_amount)
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
        f"🔗 {t('fa', 'svc_requested_username')} : {escape(tg_username)}\n"
        f"🔑 <code>{escape(str(result.panel_username or ''))}</code>\n\n"
        f"{t('fa', 'buy_remaining_balance', balance=fmt(result.new_balance), currency=t('fa', 'svc_currency'))}"
    )
    settings = get_settings()
    topic_id = settings.ADMIN_TOPIC_ORDERS
    if session is not None:
        from bot.services.app_settings import get_store_settings
        store = await get_store_settings(session)
        if store.topic_orders is not None:
            topic_id = store.topic_orders
    thread_kwargs = {"message_thread_id": topic_id} if topic_id else {}
    try:
        await bot.send_message(settings.ADMIN_CHAT_ID, text, **thread_kwargs)
    except Exception:
        logger.exception("failed to deliver purchase log to admin chat")
