"""Admin panel user wallet balance adjustment handlers."""
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import fmt, is_admin, parse_int
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.menu import delete_message_silently, render_menu
from bot.states.admin import UserManagementStates

logger = logging.getLogger(__name__)
router = Router(name="admin_user_wallet")

_is_admin = is_admin
_parse_int = parse_int


@router.callback_query(F.data.startswith("adm:ubal:"))
async def balance_change_start(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        _, _, action, telegram_id_s = call.data.split(":")
        telegram_id = int(telegram_id_s)
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    await state.set_state(UserManagementStates.waiting_balance_amount)
    await state.update_data(balance_action=action, balance_tid=int(telegram_id))

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:user:{telegram_id}")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, t(lang, "user_balance_prompt"), kb.as_markup())
    await call.answer()


@router.message(UserManagementStates.waiting_balance_amount, F.text)
async def balance_change_save(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    data = await state.get_data()
    amount = _parse_int(message.text)
    telegram_id = int(data.get("balance_tid", 0))

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back"), callback_data=f"adm:user:{telegram_id}")
    kb.adjust(1)

    if amount is None or amount <= 0:
        await render_menu(bot, user, user_repo, t(lang, "user_balance_invalid"), kb.as_markup())
        return

    action = data.get("balance_action", "add")
    wallet_repo = WalletRepository(session)
    if action == "add":
        new_balance = await wallet_repo.adjust_balance_atomic(telegram_id, amount)
    else:
        new_balance = await wallet_repo.adjust_balance_atomic(telegram_id, -amount)

    await AdminLogRepository(session).log(
        message.from_user.id,
        "balance_add" if action == "add" else "balance_sub",
        detail=f"user={telegram_id} amount={amount}",
    )

    await state.clear()
    await render_menu(
        bot, user, user_repo,
        t(lang, "user_balance_ok", balance=fmt(new_balance)),
        kb.as_markup(),
    )
