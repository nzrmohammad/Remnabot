"""Core purchase flow, service view, new account checkout, and purchase helpers."""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, parse_int
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.handlers.shop_purchase_views import (
    ensure_can_buy as _ensure_can_buy,
    extract_coupon_from_state as _extract_coupon_from_state,
    finalize_purchase,
    maybe_reward_referrer as _maybe_reward_referrer,
    notify_admin as _notify_admin,
    render_buy_confirm as _render_buy_confirm,
    render_purchase_result as _render_purchase_result,
)
from bot.locales.texts import t
from bot.services.app_settings import is_maintenance
from bot.services.menu import render_menu
from bot.services.purchases import execute_purchase
from bot.services.remnawave import RemnawaveClient
from bot.services.service_display import service_block

logger = logging.getLogger(__name__)
router = Router(name="shop_purchase")

# In-memory per-user purchase lock: prevents double-tap double-charge.
_PURCHASE_LOCKS: set[int] = set()

_safe_int = parse_int


@router.callback_query(F.data.startswith("svc:buynew:"))
async def buy_new_account(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
    service_id: int | None = None,
):
    if service_id is None:
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

    coupon_code, discount_amount = await _extract_coupon_from_state(state)

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

        coupon_code, discount_amount = await _extract_coupon_from_state(state)

        result = await execute_purchase(
            remnawave, session, service, user.telegram_id,
            create_new=True, discount_amount=discount_amount,
            bot=bot,
        )
        await finalize_purchase(
            bot=bot,
            session=session,
            remnawave=remnawave,
            user=user,
            user_repo=user_repo,
            service=service,
            result=result,
            state=state,
            coupon_code=coupon_code,
            discount_amount=discount_amount,
            full_name=call.from_user.full_name,
            lang=lang,
        )
        await call.answer()
    finally:
        _PURCHASE_LOCKS.discard(call.from_user.id)


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
    service_id: int | None = None,
):
    if service_id is None:
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

    coupon_code, discount_amount = await _extract_coupon_from_state(state)

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

        coupon_code, discount_amount = await _extract_coupon_from_state(state)

        result = await execute_purchase(
            remnawave, session, service, user.telegram_id, discount_amount=discount_amount,
            bot=bot,
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

        await finalize_purchase(
            bot=bot,
            session=session,
            remnawave=remnawave,
            user=user,
            user_repo=user_repo,
            service=service,
            result=result,
            state=state,
            coupon_code=coupon_code,
            discount_amount=discount_amount,
            full_name=call.from_user.full_name,
            lang=lang,
        )
        await call.answer()
    finally:
        _PURCHASE_LOCKS.discard(call.from_user.id)
