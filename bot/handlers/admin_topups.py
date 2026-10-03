"""Admin Top-up Approvals and Rejections."""
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, is_admin
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.menu import render_menu
from bot.services.topups import decide_topup

logger = logging.getLogger(__name__)
router = Router(name="admin_topups")

_is_admin = is_admin


async def _render_topups(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    lang = user.language or "fa"
    pending = await WalletRepository(session).list_pending_topups()

    lines = [t(lang, "topups_title"), SEPARATOR]
    if not pending:
        lines.append(t(lang, "topups_empty"))
    else:
        for tp in pending:
            lines.append(
                f"#{tp.id} — <code>{tp.telegram_id}</code> — "
                f"<b>{fmt(tp.amount)}</b> {t(lang, 'svc_currency')}"
            )

    kb = InlineKeyboardBuilder()
    for tp in pending:
        kb.button(text=t(lang, "btn_approve"), callback_data=f"adm:topup:ok:{tp.id}")
        kb.button(text=t(lang, "btn_reject"), callback_data=f"adm:topup:no:{tp.id}")
        kb.adjust(2)
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "adm:topups")
async def topups_list(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_topups(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data.startswith("adm:topup:"))
async def topup_decide_from_panel(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        _, _, action, topup_id_s = call.data.split(":")
        topup_id = int(topup_id_s)
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    changed, note = await decide_topup(
        bot, session, int(topup_id), approved=(action == "ok"),
        admin_id=call.from_user.id,
    )
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    if changed:
        await _render_topups(bot, user, user_repo, session)
    await call.answer(note, show_alert=not changed)
