"""Admin Telegram User Details, Ban, Unban, and Banned List."""
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, is_admin, resolve_op
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.formatting import format_datetime
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)
router = Router(name="admin_user_bans")


_is_admin = is_admin


@router.callback_query(F.data.startswith("adm:user:"))
async def telegram_user_detail(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient,
):
    if call.data in ("adm:user:search", "adm:user:create"):
        return
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        telegram_id = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    user_repo_cls = resolve_op("UserRepository", UserRepository)
    wallet_repo_cls = resolve_op("WalletRepository", WalletRepository)
    render_menu_fn = resolve_op("render_menu", render_menu)

    target = await user_repo_cls(session).get_by_telegram_id(telegram_id)
    if target is None:
        target = await user_repo_cls(session).get_or_create(telegram_id, username=None)

    wallet = await wallet_repo_cls(session).get_wallet(telegram_id)
    accounts = await remnawave.get_users_by_telegram_id(telegram_id) or []

    ban_badge = "⛔️ مسدود" if target.is_banned else "✅ فعال" if lang == "fa" else ("⛔️ Banned" if target.is_banned else "✅ Active")

    lines = [
        t(lang, "user_detail_title"),
        SEPARATOR,
        f"👤 {target.username or '—'}",
        f"🆔 <code>{target.telegram_id}</code>",
        f"🔘 وضعیت دسترسی: <b>{ban_badge}</b>" if lang == "fa" else f"🔘 Status: <b>{ban_badge}</b>",
        f"👛 {t(lang, 'user_balance')} : <b>{fmt(wallet.balance)}</b> {t(lang, 'svc_currency')}",
        f"{t(lang, 'user_panel_accounts')} : {len(accounts)}",
    ]
    if target.last_active_at is not None:
        lines.append(
            f"🕒 {t(lang, 'user_last_active')} : "
            f"{format_datetime(target.last_active_at, lang)}"
        )
    if accounts:
        for acc in accounts[:5]:
            uname = str(acc.get("username", "—"))
            status = str(acc.get("status", "")).upper()
            lines.append(f"   • <code>{uname}</code> — {status}")

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_add_balance"), callback_data=f"adm:ubal:add:{telegram_id}")
    kb.button(text=t(lang, "btn_sub_balance"), callback_data=f"adm:ubal:sub:{telegram_id}")
    if target.is_banned:
        kb.button(text=t(lang, "btn_unban_user"), callback_data=f"adm:uban:{telegram_id}")
    else:
        kb.button(text=t(lang, "btn_ban_user"), callback_data=f"adm:ban:{telegram_id}")
    kb.button(text=t(lang, "btn_back"), callback_data="adm:ulist:all:0")
    kb.adjust(2, 1, 1)

    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("adm:ban:"))
async def admin_ban_user(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    admin_log_repo_cls = resolve_op("AdminLogRepository", AdminLogRepository)

    telegram_id = int(call.data.rsplit(":", 1)[1])
    await user_repo.set_banned(telegram_id, True)
    await admin_log_repo_cls(session).log(
        call.from_user.id, "setting", detail=f"ban_user={telegram_id}"
    )
    call.data = f"adm:user:{telegram_id}"
    await telegram_user_detail(call, bot, user_repo, session, remnawave)
    await call.answer(t(call.from_user.language_code, "user_banned_toast"))


@router.callback_query(F.data.startswith("adm:uban:"))
async def admin_unban_user(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    admin_log_repo_cls = resolve_op("AdminLogRepository", AdminLogRepository)

    telegram_id = int(call.data.rsplit(":", 1)[1])
    await user_repo.set_banned(telegram_id, False)
    await admin_log_repo_cls(session).log(
        call.from_user.id, "setting", detail=f"unban_user={telegram_id}"
    )
    call.data = f"adm:user:{telegram_id}"
    await telegram_user_detail(call, bot, user_repo, session, remnawave)
    await call.answer(t(call.from_user.language_code, "user_unbanned_toast"))


@router.callback_query(F.data == "adm:banned")
async def admin_banned_list(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_menu_fn = resolve_op("render_menu", render_menu)

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    banned_users = await user_repo.list_banned()
    lines = [
        f"{t(lang, 'banned_list_title')}\n{SEPARATOR}",
    ]
    if not banned_users:
        lines.append(t(lang, "banned_list_empty"))
    else:
        for u in banned_users:
            uname = f"@{u.username}" if u.username else "بدون نام کاربری"
            lines.append(f"⛔️ <b>{uname}</b> (<code>{u.telegram_id}</code>)")

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        for i in range(0, len(banned_users), 2):
            chunk = banned_users[i : i + 2]
            if len(chunk) == 2:
                for u in reversed(chunk):
                    uname = f"@{u.username}" if u.username else str(u.telegram_id)
                    kb.button(text=f"⛔️ {uname}", callback_data=f"adm:user:{u.telegram_id}")
            else:
                u = chunk[0]
                uname = f"@{u.username}" if u.username else str(u.telegram_id)
                kb.button(text=f"⛔️ {uname}", callback_data=f"adm:user:{u.telegram_id}")
    else:
        for u in banned_users:
            uname = f"@{u.username}" if u.username else str(u.telegram_id)
            kb.button(text=f"⛔️ {uname}", callback_data=f"adm:user:{u.telegram_id}")
    kb.button(text=t(lang, "btn_back"), callback_data="adm:users")
    sizes = [2] * (len(banned_users) // 2) + ([1] if len(banned_users) % 2 else []) + [1]
    kb.adjust(*sizes)

    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()
