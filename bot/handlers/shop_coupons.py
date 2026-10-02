"""Coupon handling in user purchase and renewal flows."""
import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.menu import delete_message_silently, render_menu
from bot.services.remnawave import RemnawaveClient
from bot.states.service_request import ServiceRequestStates

logger = logging.getLogger(__name__)
router = Router(name="shop_coupons")


@router.callback_query(F.data.startswith("svc:cpn:"))
async def apply_coupon_prompt(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    import bot.handlers.service_request as _sr
    render_fn = getattr(_sr, "render_menu", render_menu)

    parts = call.data.split(":")
    service_id = int(parts[2])
    flow_type = parts[3]
    target_id = parts[4]

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    await state.update_data(service_id=service_id, flow_type=flow_type, target_id=target_id)
    await state.set_state(ServiceRequestStates.waiting_coupon)

    kb = InlineKeyboardBuilder()
    back_cb = (
        f"svc:buya:{service_id}:{target_id}" if flow_type == "a"
        else (f"svc:buynew:{service_id}" if flow_type == "n" else f"svc:buy:{service_id}")
    )
    kb.button(text=t(lang, "btn_cancel"), callback_data=back_cb)
    kb.adjust(1)

    await render_fn(bot, user, user_repo, t(lang, "coupon_prompt"), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("svc:rmcpn:"))
async def remove_coupon(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
):
    import bot.handlers.service_request as _sr

    parts = call.data.split(":")
    service_id = int(parts[2])
    flow_type = parts[3]
    target_id = parts[4]

    await state.update_data(coupon_code=None, discount_amount=0)

    if flow_type == "a":
        call.data = f"svc:buya:{service_id}:{target_id}"
        buy_for_account_fn = getattr(_sr, "buy_for_account")
        await buy_for_account_fn(call, bot, user_repo, session, remnawave, state)
    elif flow_type == "n":
        call.data = f"svc:buynew:{service_id}"
        buy_new_account_fn = getattr(_sr, "buy_new_account")
        await buy_new_account_fn(call, bot, user_repo, session, remnawave, state)
    else:
        call.data = f"svc:buy:{service_id}"
        service_buy_fn = getattr(_sr, "service_buy")
        await service_buy_fn(call, bot, user_repo, session, remnawave, state)


@router.message(ServiceRequestStates.waiting_coupon)
async def process_coupon_code(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
):
    import bot.handlers.service_request as _sr
    render_fn = getattr(_sr, "render_menu", render_menu)
    render_confirm_fn = getattr(_sr, "_render_buy_confirm")

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language or "fa"
    code = (message.text or "").strip().upper()
    await delete_message_silently(bot, message.chat.id, message.message_id)

    data = await state.get_data()
    service_id = data.get("service_id")
    flow_type = data.get("flow_type", "d")
    target_id = data.get("target_id", "0")

    if not service_id:
        await state.clear()
        return

    service = await ServiceRepository(session).get(service_id)
    if not service:
        await state.clear()
        return

    coupon_repo = CouponRepository(session)
    valid, err_key, discount_amount = await coupon_repo.validate_coupon(
        code, user.telegram_id, service.price
    )

    if not valid:
        kb = InlineKeyboardBuilder()
        back_cb = (
            f"svc:buya:{service_id}:{target_id}" if flow_type == "a"
            else (f"svc:buynew:{service_id}" if flow_type == "n" else f"svc:buy:{service_id}")
        )
        kb.button(text=t(lang, "btn_cancel"), callback_data=back_cb)
        kb.adjust(1)
        err_msg = t(lang, err_key or "coupon_not_found")
        await render_fn(
            bot, user, user_repo,
            f"{err_msg}\n\n{t(lang, 'coupon_prompt')}",
            kb.as_markup(),
        )
        return

    await state.update_data(coupon_code=code, discount_amount=discount_amount)

    wallet = await WalletRepository(session).get_wallet(user.telegram_id)
    target_name = None
    confirm_cb = f"svc:confirm:{service.id}"
    back_cb = "menu:services"

    if flow_type == "a":
        accounts = await remnawave.get_users_by_telegram_id(user.telegram_id) or []
        target_acc = next((a for a in accounts if str(a.get("id")) == str(target_id)), None)
        target_name = target_acc.get("username") if target_acc else None
        confirm_cb = f"svc:confirma:{service.id}:{target_id}"
        back_cb = f"svc:buy:{service.id}"
    elif flow_type == "n":
        target_name = t(lang, "buy_target_new")
        confirm_cb = f"svc:confirmn:{service.id}"
        back_cb = f"svc:buy:{service.id}"

    await render_confirm_fn(
        bot, user, user_repo, session, service, wallet.balance,
        confirm_callback=confirm_cb,
        lang=lang,
        target_name=target_name,
        back_callback=back_cb,
        flow_type=flow_type,
        target_id=target_id,
        coupon_code=code,
        discount_amount=discount_amount,
    )
