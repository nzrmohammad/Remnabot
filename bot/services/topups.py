"""Shared logic for approving/rejecting a card-to-card top-up.

Used both by the inline buttons on the admin-chat receipt (wallet.py)
and by the «تایید شارژها» section of the admin panel (admin_ops.py).
"""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import fmt
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t

logger = logging.getLogger(__name__)


async def decide_topup(
    bot: Bot,
    session: AsyncSession,
    topup_id: int,
    approved: bool,
    admin_id: int | None = None,
) -> tuple[bool, str]:
    """Apply the decision; returns (changed, note_text_for_admin)."""
    wallet_repo = WalletRepository(session)
    # Atomic claim: only one concurrent approver wins, no double-credit.
    topup = await wallet_repo.claim_topup(topup_id, approved)
    if topup is None:
        return False, t("fa", "admin_topup_already")

    target = await UserRepository(session).get_by_telegram_id(topup.telegram_id)
    user_lang = (target.language if target else None) or "fa"
    kb = InlineKeyboardBuilder()

    if approved:
        new_balance = await wallet_repo.add_balance_atomic(topup.telegram_id, topup.amount)
        user_text = t(
            user_lang, "topup_approved_user",
            amount=fmt(topup.amount), balance=fmt(new_balance),
        )
        note = t("fa", "admin_topup_done")
        if user_lang == "fa":
            kb.button(text=t(user_lang, "btn_services"), callback_data="menu:services")
            kb.button(text=t(user_lang, "btn_wallet"), callback_data="menu:wallet")
        else:
            kb.button(text=t(user_lang, "btn_wallet"), callback_data="menu:wallet")
            kb.button(text=t(user_lang, "btn_services"), callback_data="menu:services")
        kb.adjust(2)
    else:
        user_text = t(user_lang, "topup_rejected_user", amount=fmt(topup.amount))
        note = t("fa", "admin_topup_rejected")
        kb.button(text=t(user_lang, "btn_support"), callback_data="menu:support")
        kb.adjust(1)

    if admin_id is not None:
        await AdminLogRepository(session).log(
            admin_id,
            "topup_ok" if approved else "topup_no",
            detail=f"topup={topup_id} user={topup.telegram_id} amount={topup.amount}",
        )

    try:
        await bot.send_message(topup.telegram_id, user_text, reply_markup=kb.as_markup())
    except TelegramAPIError:
        logger.warning("could not notify user %s about top-up", topup.telegram_id)

    return True, note
