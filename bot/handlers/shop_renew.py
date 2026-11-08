"""Shop renewal and account selection handlers."""
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
from bot.handlers.shop_purchase import (
    _PURCHASE_LOCKS,
    _ensure_can_buy,
    _render_buy_confirm,
    finalize_purchase,
)
from bot.locales.texts import t
from bot.services.app_settings import is_maintenance
from bot.services.menu import render_menu
from bot.services.purchases import execute_purchase, resolve_squad_name
from bot.services.remnawave import RemnawaveClient
from bot.services.render import render_services

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

    if not await _ensure_can_buy(bot, user, user_repo, remnawave):
        await call.answer()
        return

    panel_user_id = call.data.rsplit(":", 1)[1]
    chosen = await _verify_account(remnawave, user.telegram_id, panel_user_id)
    if chosen is None:
        await call.answer(t(lang, "acc_error"), show_alert=True)
        return

    await render_services(
        bot, user, user_repo, session, renew_account_id=str(chosen["id"]), remnawave=remnawave
    )
    await call.answer()


@router.callback_query(F.data.startswith("svc:buya:"))
async def buy_for_account(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
    service_id: int | None = None, panel_user_id: str | None = None,
):
    is_confirmed = False
    if call.data:
        parts = call.data.split(":")
        if len(parts) >= 5 and parts[4] == "ok":
            is_confirmed = True
        if service_id is None and len(parts) >= 3:
            service_id = _safe_int(parts[2])
        if panel_user_id is None and len(parts) >= 4:
            panel_user_id = parts[3]
    if service_id is None or panel_user_id is None:
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

    state_data = await state.get_data() if state else {}
    if state_data.get("coupon_code"):
        is_confirmed = True

    # Detect squad switch
    acc_squads = (
        chosen.get("activeInternalSquads")
        or chosen.get("internalSquads")
        or chosen.get("squads")
        or []
    )
    acc_squad_uuids: set[str] = set()
    for sq in acc_squads:
        if isinstance(sq, dict):
            u = sq.get("uuid") or sq.get("id")
            if u:
                acc_squad_uuids.add(str(u).strip().lower())
        elif isinstance(sq, str):
            acc_squad_uuids.add(sq.strip().lower())

    is_extra_traffic = bool(
        (service.duration_days == 0 and service.traffic_gb > 0)
        or (service.badge and service.badge.lower() == "traffic")
    )
    is_extra_time = bool(
        (service.traffic_gb == 0 and service.duration_days > 0)
        or (service.badge and service.badge.lower() == "time")
    )

    is_squad_switch = bool(
        chosen
        and not is_extra_traffic
        and not is_extra_time
        and service.squad_uuid
        and (not acc_squad_uuids or str(service.squad_uuid).strip().lower() not in acc_squad_uuids)
    )

    # If squad switch and user has not confirmed yet, show the warning modal/screen FIRST!
    if is_squad_switch and not is_confirmed:
        squad_name = await resolve_squad_name(remnawave, service.squad_uuid)
        username = escape(str(chosen.get("username", "—")))
        lines = [
            "⚠️ <b>هشدار مهم تغییر دسته سرور</b>" if lang == "fa" else "⚠️ <b>Server Squad Switch Warning</b>",
            SEPARATOR,
            f"کاربر گرامی، شما در حال تغییر سرویس اشتراک <b>{username}</b> به دسته سرور «<b>{escape(squad_name)}</b>» هستید." if lang == "fa" else f"You are switching subscription <b>{username}</b> to squad <b>{escape(squad_name)}</b>.",
            "",
            "📌 <b>نکات بسیار مهم پیش از مشاهده پیش‌فاکتور:</b>" if lang == "fa" else "📌 <b>Important notes before proceeding:</b>",
            "۱. با تغییر سرویس، <b>حجم و روزهای باقیمانده بسته قبلی شما جایگزین می‌شوند</b> (سقف حجم و روزها از نو برای این بسته آغاز می‌گردند)." if lang == "fa" else "1. Remaining traffic and days of your previous plan will be replaced starting fresh today.",
            "۲. <b>لینک اتصال اشتراک شما تغییری نمی‌کند</b> و تنها کافیست پس از پرداخت، گزینه <b>Update Subscription (بروزرسانی اشتراک)</b> را در برنامه بزنید." if lang == "fa" else "2. Your subscription link remains unchanged; simply tap Update Subscription in your VPN app.",
            "۳. هزینه کامل بسته جدید دریافت خواهد شد." if lang == "fa" else "3. Full price of the new plan will be charged.",
            "",
            "💡 <i>راهنما: چنانچه قصد تغییر دسته سرور اشتراک خود را ندارید، لطفاً از بسته‌های مربوط به دسته سرور فعلی جهت تمدید استفاده کرده و یا بسته افزایش حجم تهیه فرمایید.</i>" if lang == "fa" else "💡 <i>Tip: If you do not wish to switch server squads, please renew using plans from your current squad or purchase an extra traffic package.</i>",
            "",
            "آیا برای مشاهده پیش‌فاکتور و خرید این بسته موافقید؟" if lang == "fa" else "Do you agree to proceed to the invoice?",
        ]
        kb = InlineKeyboardBuilder()
        kb.button(
            text="✅ متوجه شدم، مشاهده پیش‌فاکتور" if lang == "fa" else "✅ I Understand, View Invoice",
            callback_data=f"svc:buya:{service.id}:{panel_user_id}:ok",
        )
        kb.button(
            text=t(lang, "btn_cancel"),
            callback_data=f"svc:buy:{service.id}",
        )
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await call.answer()
        return

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
        account=chosen,
        remnawave=remnawave,
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
            coupon_code=coupon_code,
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
            coupon_code=coupon_code,
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
