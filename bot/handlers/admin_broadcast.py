"""Admin broadcast messaging with audience targeting."""
import asyncio
import logging
from datetime import datetime, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import is_admin
from bot.db.models import Order, Wallet
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.menu import delete_message_silently, render_menu
from bot.services.remnawave import RemnawaveClient
from bot.states.admin import BroadcastStates

logger = logging.getLogger(__name__)
router = Router(name="admin_broadcast")

def _is_admin(user_id: int) -> bool:
    import bot.handlers.admin_ops as _ops
    fn = getattr(_ops, "_is_admin", is_admin)
    return fn(user_id)

BROADCAST_CONFIRM_KEY = "bcast:draft"


def _back_admin(lang: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1)
    return kb


async def _resolve_broadcast_recipients(
    session: AsyncSession,
    remnawave: RemnawaveClient,
    target: str,
) -> list[int]:
    """Return a list of Telegram IDs matching the audience filter."""
    import bot.handlers.admin_ops as _ops
    u_repo_cls = getattr(_ops, "UserRepository", UserRepository)

    if target == "all":
        users = await u_repo_cls(session).all_users()
        return [u.telegram_id for u in users]

    if target == "balance":
        stmt = select(Wallet.telegram_id).where(Wallet.balance > 0)
        res = await session.execute(stmt)
        return [row[0] for row in res.fetchall()]

    if target == "buyers":
        stmt = select(distinct(Order.telegram_id)).where(Order.status == "paid")
        res = await session.execute(stmt)
        return [row[0] for row in res.fetchall()]

    # Targets requiring Remnawave
    panel_users = await remnawave.get_all_panel_users() or []
    now = datetime.now(timezone.utc)
    active_tids: set[int] = set()
    for pu in panel_users:
        if str(pu.get("status", "")).upper() == "ACTIVE":
            exp_str = pu.get("expireAt")
            if exp_str:
                try:
                    exp = datetime.fromisoformat(str(exp_str).replace("Z", "+00:00"))
                    if exp > now:
                        tid = pu.get("telegramId")
                        if tid and int(tid) > 0:
                            active_tids.add(int(tid))
                except Exception:
                    pass

    if target == "active":
        return list(active_tids)

    if target == "expired":
        all_users = await u_repo_cls(session).all_users()
        all_tids = {u.telegram_id for u in all_users}
        return list(all_tids - active_tids)

    users = await u_repo_cls(session).all_users()
    return [u.telegram_id for u in users]


@router.callback_query(F.data == "adm:broadcast")
async def broadcast_audience_select(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        # Persian RTL: first added is LEFT, second added is RIGHT
        # Row 1: Right = All, Left = Active
        kb.button(text=t(lang, "bcast_target_active"), callback_data="adm:bcast:target:active")
        kb.button(text=t(lang, "bcast_target_all"), callback_data="adm:bcast:target:all")
        # Row 2: Right = Expired, Left = Balance
        kb.button(text=t(lang, "bcast_target_balance"), callback_data="adm:bcast:target:balance")
        kb.button(text=t(lang, "bcast_target_expired"), callback_data="adm:bcast:target:expired")
    else:
        kb.button(text=t(lang, "bcast_target_all"), callback_data="adm:bcast:target:all")
        kb.button(text=t(lang, "bcast_target_active"), callback_data="adm:bcast:target:active")
        kb.button(text=t(lang, "bcast_target_expired"), callback_data="adm:bcast:target:expired")
        kb.button(text=t(lang, "bcast_target_balance"), callback_data="adm:bcast:target:balance")

    # Row 3: Buyers
    kb.button(text=t(lang, "bcast_target_buyers"), callback_data="adm:bcast:target:buyers")
    # Row 4: Back
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(2, 2, 1, 1)

    await render_menu(bot, user, user_repo, t(lang, "bcast_target_title"), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("adm:bcast:target:"))
async def broadcast_target_picked(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    target = call.data.rsplit(":", 1)[1]
    await state.set_state(BroadcastStates.waiting_text)
    await state.update_data(bcast_target=target)

    target_label = t(lang, f"bcast_target_{target}")
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:broadcast")
    kb.adjust(1)

    prompt = f"🎯 <b>{target_label}</b>\n\n{t(lang, 'broadcast_prompt')}"
    await render_menu(bot, user, user_repo, prompt, kb.as_markup())
    await call.answer()


@router.message(BroadcastStates.waiting_text, F.text)
async def broadcast_text(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    draft = message.text.strip()
    data = await state.get_data()
    target = str(data.get("bcast_target", "all"))
    target_label = t(lang, f"bcast_target_{target}")

    if not draft:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="adm:broadcast")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "broadcast_prompt"), kb.as_markup())
        return

    recipients = await _resolve_broadcast_recipients(session, remnawave, target)
    await state.update_data(draft=draft, recipient_ids=recipients)

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_send"), callback_data=BROADCAST_CONFIRM_KEY)
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:broadcast")
    kb.adjust(1)

    preview_text = t(
        lang, "bcast_preview_target",
        target=target_label,
        count=len(recipients),
        text=escape(draft),
    )
    await render_menu(bot, user, user_repo, preview_text, kb.as_markup())


@router.callback_query(F.data == BROADCAST_CONFIRM_KEY)
async def broadcast_send(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    data = await state.get_data()
    draft = data.get("draft", "")
    recipient_ids = data.get("recipient_ids") or []
    target = data.get("bcast_target", "all")
    await state.clear()

    if not draft:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    import bot.handlers.admin_ops as _ops
    log_repo_cls = getattr(_ops, "AdminLogRepository", AdminLogRepository)

    ok = fail = 0
    safe_text = escape(draft)
    for tid in recipient_ids:
        try:
            await bot.send_message(tid, safe_text)
            ok += 1
        except Exception as exc:
            from aiogram.exceptions import TelegramRetryAfter

            if isinstance(exc, TelegramRetryAfter):
                try:
                    await asyncio.sleep(exc.retry_after + 1)
                except Exception:
                    pass
                try:
                    await bot.send_message(tid, safe_text)
                    ok += 1
                    continue
                except Exception:
                    pass
            fail += 1
        if (ok + fail) % 20 == 0:
            await asyncio.sleep(1)

    await log_repo_cls(session).log(
        call.from_user.id, "broadcast", detail=f"target={target} ok={ok} fail={fail}"
    )
    await render_menu(
        bot, user, user_repo,
        t(lang, "broadcast_sent", ok=ok, fail=fail),
        _back_admin(lang).as_markup(),
    )
    await call.answer()
