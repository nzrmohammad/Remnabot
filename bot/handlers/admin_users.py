"""Admin panel: «مدیریت کاربران».

Features:
1. Panel Users List (`adm:ulist:{category}:{page}`) directly from Remnawave
   with filters:
   - All (همه)
   - Online (آنلاین - connected in the last 5 minutes)
   - Never connected (هرگز متصل نشده)
   - Offline (آفلاین)
   - Expiring soon (در آستانه انقضا - within 3 days)
   - Limit reached (پایان حجم)
   - Disabled (غیرفعال)
2. Panel User Details & Operations (`adm:puser:{user_id}:{category}:{page}`):
   - Toggle Active/Disabled status
   - Reset traffic consumption
   - View & remove connected HWID devices
   - Revoke & generate new subscription link
   - Wallet balance management (if linked to a Telegram user)
3. Panel User Creation Wizard (`adm:user:create`):
   - Guided FSM: username -> traffic (GB) -> duration (days) -> optional Telegram ID
   - Creates directly in Remnawave and displays subscription link
4. Search panel users by username, panel ID, or Telegram ID (`adm:user:search`)
5. Wallet balance manual adjustment (`adm:user:{telegram_id}` and `adm:ubal:...`)
"""
import re
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.formatting import format_date, format_datetime, human_bytes
from bot.services.menu import delete_message_silently, render_menu
from bot.common import SEPARATOR, fmt, get_limit_bytes, get_online_at, get_used_bytes, is_admin, parse_int
from bot.services.remnawave import RemnawaveClient
from bot.states.admin import UserManagementStates

router = Router(name="admin_users")

_is_admin = is_admin
_parse_int = parse_int
PAGE_SIZE = 15

PANEL_CATEGORIES = [
    ("all", "user_filter_all"),
    ("online", "user_filter_online"),
    ("never", "user_filter_never"),
    ("offline", "user_filter_offline"),
    ("expiring", "user_filter_expiring"),
    ("limited", "user_filter_limited"),
    ("disabled", "user_filter_disabled"),
]


_get_online_at = get_online_at
_get_used_bytes = get_used_bytes
_get_limit_bytes = get_limit_bytes
_format_gb = human_bytes


def _format_days_left(expire_at_str: Any, lang: str) -> str:
    if not expire_at_str:
        return "نامحدود" if lang == "fa" else "∞"
    try:
        now = datetime.now(timezone.utc)
        exp = datetime.fromisoformat(str(expire_at_str).replace("Z", "+00:00"))
        if exp < now:
            return "منقضی" if lang == "fa" else "Expired"
        days = (exp.date() - now.date()).days
        if days <= 0:
            return "امروز" if lang == "fa" else "Today"
        return f"{days} روز" if lang == "fa" else f"{days}d"
    except Exception:
        return "—"


def _user_status_emoji(u: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    status = str(u.get("status", "")).upper()
    if status == "DISABLED":
        return "⛔️"
    limit = _get_limit_bytes(u)
    used = _get_used_bytes(u)
    if status == "LIMITED" or (limit > 0 and used >= limit):
        return "⚠️"
    online_at = _get_online_at(u)
    if online_at is not None and (now - online_at) <= timedelta(minutes=5):
        return "🟢"
    if online_at is None and used == 0:
        return "⚪️"
    return "🔴"


def _filter_panel_users(users: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    if category == "all":
        return users
    filtered: list[dict[str, Any]] = []
    for u in users:
        status = str(u.get("status", "")).upper()
        online_at = _get_online_at(u)
        used = _get_used_bytes(u)
        limit = _get_limit_bytes(u)
        is_online = online_at is not None and (now - online_at) <= timedelta(minutes=5)

        if category == "online":
            if is_online:
                filtered.append(u)
        elif category == "never":
            if online_at is None and used == 0:
                filtered.append(u)
        elif category == "offline":
            if online_at is not None and not is_online:
                filtered.append(u)
        elif category == "disabled":
            if status == "DISABLED":
                filtered.append(u)
        elif category == "limited":
            if status == "LIMITED" or (limit > 0 and used >= limit):
                filtered.append(u)
        elif category == "expiring":
            expire_at_str = u.get("expireAt")
            if expire_at_str:
                try:
                    exp = datetime.fromisoformat(str(expire_at_str).replace("Z", "+00:00"))
                    diff_days = (exp - now).total_seconds() / 86400
                    if 0 <= diff_days <= 3:
                        filtered.append(u)
                except Exception:
                    pass
    return filtered


# --------------------------------------------------------------------- #
# User Management Entry Submenu
# --------------------------------------------------------------------- #
@router.callback_query(F.data == "adm:users")
async def users_menu(
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
        # Row 1: Left = Search User, Right = Add User
        kb.button(text=t(lang, "btn_user_search"), callback_data="adm:user:search")
        kb.button(text=t(lang, "btn_create_panel_user"), callback_data="adm:user:create")
        # Row 2: Left = Banned Users, Right = Users List
        kb.button(text=t(lang, "btn_banned_list"), callback_data="adm:banned")
        kb.button(text=t(lang, "btn_panel_users_list"), callback_data="adm:ulist:all:0")
    else:
        kb.button(text=t(lang, "btn_create_panel_user"), callback_data="adm:user:create")
        kb.button(text=t(lang, "btn_user_search"), callback_data="adm:user:search")
        kb.button(text=t(lang, "btn_panel_users_list"), callback_data="adm:ulist:all:0")
        kb.button(text=t(lang, "btn_banned_list"), callback_data="adm:banned")

    # Row 3: Back to Admin Panel
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(2, 2, 1)

    await render_menu(
        bot, user, user_repo,
        f"{t(lang, 'users_menu_title')}\n{SEPARATOR}\n{t(lang, 'users_menu_hint')}",
        kb.as_markup(),
    )
    await call.answer()


# --------------------------------------------------------------------- #
# Panel User Creation Wizard (Guided FSM) - delegated to admin_user_create
# --------------------------------------------------------------------- #
from bot.handlers.admin_user_create import (
    router as _user_create_router,
    user_create_start,
    user_create_username_step,
    user_create_traffic_step,
    user_create_duration_step,
    user_create_squad_step,
    user_create_hwid_step,
    _do_create_user,
    user_create_skip_tid,
    user_create_final_step,
)

router.include_router(_user_create_router)


# --------------------------------------------------------------------- #
# Search Panel Users
# --------------------------------------------------------------------- #
@router.callback_query(F.data == "adm:user:search")
async def user_search_start(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    await state.set_state(UserManagementStates.waiting_search)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:users")
    kb.adjust(1)
    await render_menu(bot, user, user_repo, t(lang, "user_search_prompt"), kb.as_markup())
    await call.answer()


@router.message(UserManagementStates.waiting_search, F.text)
async def user_search_exec(
    message: Message, bot: Bot, user_repo: UserRepository,
    state: FSMContext, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language or "fa"
    await delete_message_silently(bot, message.chat.id, message.message_id)

    query = (message.text or "").strip().lower()
    all_users = await remnawave.get_all_panel_users()
    if all_users is None:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_back"), callback_data="adm:users")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "acc_error"), kb.as_markup())
        return

    matches: list[dict[str, Any]] = []
    for u in all_users:
        uname = str(u.get("username", "")).lower()
        uid = str(u.get("id", ""))
        tid = str(u.get("telegramId", ""))
        if query in uname or query == uid or query == tid:
            matches.append(u)
            if len(matches) >= 10:
                break

    kb = InlineKeyboardBuilder()
    lines = [t(lang, "user_list_title"), SEPARATOR]
    if not matches:
        lines.append(t(lang, "user_search_empty"))
    else:
        for u in matches:
            emoji = _user_status_emoji(u)
            uname = str(u.get("username", "—"))
            uid = u.get("id")
            used = _format_gb(_get_used_bytes(u))
            limit = _format_gb(_get_limit_bytes(u)) if _get_limit_bytes(u) > 0 else "∞"
            lines.append(f"{emoji} <code>{uname}</code> — {used}/{limit}")
            kb.button(
                text=f"{emoji} {uname} ({used})",
                callback_data=f"adm:puser:{uid}:search:0",
            )
    kb.button(text=t(lang, "btn_user_search"), callback_data="adm:user:search")
    kb.button(text=t(lang, "btn_back"), callback_data="adm:users")
    kb.adjust(1)

    await state.clear()
    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


# --------------------------------------------------------------------- #
# Panel Users List (Paginated + 7 Categories)
# --------------------------------------------------------------------- #
async def _render_panel_users_list(
    bot: Bot, user, user_repo: UserRepository, remnawave: RemnawaveClient,
    category: str, page: int,
) -> None:
    lang = user.language or "fa"
    valid_cats = {c for c, _ in PANEL_CATEGORIES}
    if category not in valid_cats:
        category = "all"

    raw_users = await remnawave.get_all_panel_users()
    if raw_users is None:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_back"), callback_data="adm:users")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "acc_error"), kb.as_markup())
        return

    users = _filter_panel_users(raw_users, category)
    total = len(users)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))

    page_users = users[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    lines = [
        f"👥 {t(lang, 'user_list_title')}",
        SEPARATOR,
        f"📊 {t(lang, 'user_filter_' + category)} : <b>{total}</b>",
        "",
    ]
    if not page_users:
        lines.append(t(lang, "users_empty"))
    else:
        for u in page_users:
            emoji = _user_status_emoji(u)
            uname = str(u.get("username", "—"))
            used = _format_gb(_get_used_bytes(u))
            limit = _format_gb(_get_limit_bytes(u)) if _get_limit_bytes(u) > 0 else "∞"
            days_str = _format_days_left(u.get("expireAt"), lang)
            lines.append(f"{emoji} <code>{uname}</code> — {used}/{limit} ({days_str})")

    kb = InlineKeyboardBuilder()
    # 1. Filter Category Buttons (2 per row)
    if lang == "fa":
        # Persian RTL: first added is LEFT, second added is RIGHT
        # Row 1: Right = All, Left = Online
        # Row 2: Right = Never, Left = Offline
        # Row 3: Right = Expiring, Left = Limited
        # Row 4: Disabled (1)
        cat_order = [
            ("online", "user_filter_online"),
            ("all", "user_filter_all"),
            ("offline", "user_filter_offline"),
            ("never", "user_filter_never"),
            ("limited", "user_filter_limited"),
            ("expiring", "user_filter_expiring"),
            ("disabled", "user_filter_disabled"),
        ]
    else:
        cat_order = [
            ("all", "user_filter_all"),
            ("online", "user_filter_online"),
            ("never", "user_filter_never"),
            ("offline", "user_filter_offline"),
            ("expiring", "user_filter_expiring"),
            ("limited", "user_filter_limited"),
            ("disabled", "user_filter_disabled"),
        ]

    for cat, key in cat_order:
        label = t(lang, key)
        if cat == category:
            label = f"▪️ {label}"
        kb.button(text=label, callback_data=f"adm:ulist:{cat}:0")

    # 2. Pagination & navigation buttons
    nav_row = []
    if lang == "fa":
        # Persian RTL: Prev is on Right, Next is on Left
        if page < pages - 1:
            kb.button(text=t(lang, "btn_next"), callback_data=f"adm:ulist:{category}:{page + 1}")
            nav_row.append(1)
        if page > 0:
            kb.button(text=t(lang, "btn_prev"), callback_data=f"adm:ulist:{category}:{page - 1}")
            nav_row.append(1)
    else:
        if page > 0:
            kb.button(text=t(lang, "btn_prev"), callback_data=f"adm:ulist:{category}:{page - 1}")
            nav_row.append(1)
        if page < pages - 1:
            kb.button(text=t(lang, "btn_next"), callback_data=f"adm:ulist:{category}:{page + 1}")
            nav_row.append(1)

    kb.button(text=t(lang, "btn_back"), callback_data="adm:users")

    # Adjust layout: categories in pairs, nav row, back (1)
    cat_sizes = [2, 2, 2, 1]  # 7 categories -> 2, 2, 2, 1
    nav_sizes = [len(nav_row)] if nav_row else []
    kb.adjust(*(cat_sizes + nav_sizes + [1]))

    text = "\n".join(lines)
    if pages > 1:
        text += f"\n\n{t(lang, 'page_info', page=page + 1, pages=pages)}"

    await render_menu(bot, user, user_repo, text, kb.as_markup())


@router.callback_query(F.data.startswith("adm:ulist:"))
async def users_list_callback(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    parts = call.data.split(":")
    category = parts[2] if len(parts) > 2 else "all"
    try:
        page = int(parts[3]) if len(parts) > 3 else 0
    except (ValueError, TypeError):
        page = 0
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_panel_users_list(bot, user, user_repo, remnawave, category, page)
    await call.answer()


# --------------------------------------------------------------------- #
# Panel User Detail & Operations - delegated to bot.handlers.admin_user_detail
# --------------------------------------------------------------------- #
from bot.handlers.admin_user_detail import (
    _render_panel_user_detail,
    panel_user_callback_dispatch,
    puser_extend_days_step,
    puser_extend_traffic_step,
    puser_edit_tid_step,
    puser_edit_desc_step,
    router as _user_detail_router,
)

router.include_router(_user_detail_router)



# --------------------------------------------------------------------- #
# Telegram User Detail & Bans - delegated to bot.handlers.admin_user_bans
# --------------------------------------------------------------------- #
from bot.handlers.admin_user_bans import (
    telegram_user_detail,
    admin_ban_user,
    admin_unban_user,
    admin_banned_list,
    router as _user_bans_router,
)

router.include_router(_user_bans_router)


from bot.handlers.admin_user_wallet import (
    router as _user_wallet_router,
    balance_change_start,
    balance_change_save,
)

router.include_router(_user_wallet_router)



