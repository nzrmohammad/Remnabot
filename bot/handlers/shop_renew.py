"""Shop renewal and account selection handlers."""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import parse_int, resolve_op
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.app_settings import is_maintenance
from bot.services.purchases import execute_purchase
from bot.services.remnawave import RemnawaveClient
from bot.services.render import render_services
from bot.handlers.shop_purchase import (
    _PURCHASE_LOCKS,
    _ensure_can_buy,
    _maybe_reward_referrer,
    _notify_admin,
    _render_buy_confirm,
    _render_purchase_result,
)

logger = logging.getLogger(__name__)
router = Router(name="shop_renew")

_safe_int = parse_int


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

    ensure_can_buy_fn = resolve_op("_ensure_can_buy", _ensure_can_buy)
    if not await ensure_can_buy_fn(bot, user, user_repo, remnawave):
        await call.answer()
        return

    panel_user_id = call.data.rsplit(":", 1)[1]
    chosen = await _verify_account(remnawave, user.telegram_id, panel_user_id)
    if chosen is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    render_services_fn = resolve_op("_render_services", render_services)
    await render_services_fn(
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

    ensure_can_buy_fn = resolve_op("_ensure_can_buy", _ensure_can_buy)
    if not await ensure_can_buy_fn(bot, user, user_repo, remnawave):
        await call.answer()
        return

    s_repo_cls = resolve_op("ServiceRepository", ServiceRepository)
    service = await s_repo_cls(session).get(int(service_id))
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

    w_repo_cls = resolve_op("WalletRepository", WalletRepository)
    wallet = await w_repo_cls(session).get_wallet(user.telegram_id)
    username = escape(str(chosen.get("username", "—")))

    render_buy_confirm_fn = resolve_op("_render_buy_confirm", _render_buy_confirm)
    await render_buy_confirm_fn(
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

        ensure_can_buy_fn = resolve_op("_ensure_can_buy", _ensure_can_buy)
        if not await ensure_can_buy_fn(bot, user, user_repo, remnawave):
            await call.answer()
            return

        s_repo_cls = resolve_op("ServiceRepository", ServiceRepository)
        service = await s_repo_cls(session).get(int(service_id))
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
            reward_ref_fn = resolve_op("_maybe_reward_referrer", _maybe_reward_referrer)
            await reward_ref_fn(bot, session, remnawave, user)
            await state.clear()
            notify_admin_fn = resolve_op("_notify_admin", _notify_admin)
            await notify_admin_fn(
                bot, user, service, result, session,
                coupon_code=coupon_code, discount_amount=discount_amount,
                full_name=call.from_user.full_name,
            )
        render_purchase_result_fn = resolve_op("_render_purchase_result", _render_purchase_result)
        await render_purchase_result_fn(
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

        ensure_can_buy_fn = resolve_op("_ensure_can_buy", _ensure_can_buy)
        if not await ensure_can_buy_fn(bot, user, user_repo, remnawave):
            await call.answer()
            return

        s_repo_cls = resolve_op("ServiceRepository", ServiceRepository)
        service = await s_repo_cls(session).get(int(service_id))
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
            reward_ref_fn = resolve_op("_maybe_reward_referrer", _maybe_reward_referrer)
            await reward_ref_fn(bot, session, remnawave, user)
            await state.clear()
            notify_admin_fn = resolve_op("_notify_admin", _notify_admin)
            await notify_admin_fn(
                bot, user, service, result, session,
                coupon_code=coupon_code, discount_amount=discount_amount,
                full_name=call.from_user.full_name,
            )
        render_purchase_result_fn = resolve_op("_render_purchase_result", _render_purchase_result)
        await render_purchase_result_fn(
            bot, user, user_repo, session, result, service, lang,
            coupon_code=coupon_code, discount_amount=discount_amount,
        )
        await call.answer()
    finally:
        _PURCHASE_LOCKS.discard(call.from_user.id)
