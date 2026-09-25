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
from bot.services.formatting import format_date, format_datetime
from bot.services.menu import delete_message_silently, render_menu
from bot.services.remnawave import RemnawaveClient
from bot.services.topups import fmt
from bot.states.admin import UserManagementStates

router = Router(name="admin_users")

SEPARATOR = "─" * 18
PAGE_SIZE = 15

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

PANEL_CATEGORIES = [
    ("all", "user_filter_all"),
    ("online", "user_filter_online"),
    ("never", "user_filter_never"),
    ("offline", "user_filter_offline"),
    ("expiring", "user_filter_expiring"),
    ("limited", "user_filter_limited"),
    ("disabled", "user_filter_disabled"),
]


def _is_admin(user_id: int) -> bool:
    return user_id in get_settings().ADMIN_IDS


def _parse_int(text: str) -> int | None:
    cleaned = text.translate(_DIGIT_MAP).replace(",", "").replace("،", "").strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def _get_online_at(u: dict[str, Any]) -> datetime | None:
    online_str = None
    if isinstance(u.get("userTraffic"), dict):
        online_str = u["userTraffic"].get("onlineAt")
    if not online_str:
        online_str = u.get("onlineAt")
    if not online_str:
        return None
    try:
        return datetime.fromisoformat(str(online_str).replace("Z", "+00:00"))
    except Exception:
        return None


def _get_used_bytes(u: dict[str, Any]) -> int:
    if isinstance(u.get("userTraffic"), dict):
        try:
            return int(u["userTraffic"].get("usedTrafficBytes") or 0)
        except (ValueError, TypeError):
            pass
    try:
        return int(u.get("usedTrafficBytes") or 0)
    except (ValueError, TypeError):
        return 0


def _get_limit_bytes(u: dict[str, Any]) -> int:
    try:
        return int(u.get("trafficLimitBytes") or 0)
    except (ValueError, TypeError):
        return 0


def _format_gb(bytes_val: int) -> str:
    gb = bytes_val / (1024 ** 3)
    if gb >= 10:
        return f"{gb:.0f} GB"
    elif gb >= 1:
        return f"{gb:.1f} GB"
    mb = bytes_val / (1024 ** 2)
    return f"{mb:.0f} MB"


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
# Panel User Creation Wizard (Guided FSM)
# --------------------------------------------------------------------- #
@router.callback_query(F.data == "adm:user:create")
async def user_create_start(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    await state.set_state(UserManagementStates.create_username)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:users")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, t(lang, "user_create_prompt_username"), kb.as_markup())
    await call.answer()


@router.message(UserManagementStates.create_username, F.text)
async def user_create_username_step(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    raw_username = message.text.strip()
    # Username: English alphanumeric, underscores, hyphens, length 2-32
    if not re.match(r"^[a-zA-Z0-9_\-]{2,32}$", raw_username):
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="adm:users")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "user_create_invalid_username"), kb.as_markup())
        return

    await state.update_data(c_username=raw_username)
    await state.set_state(UserManagementStates.create_traffic)

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:users")
    kb.adjust(1)
    await render_menu(bot, user, user_repo, t(lang, "user_create_prompt_traffic"), kb.as_markup())


@router.message(UserManagementStates.create_traffic, F.text)
async def user_create_traffic_step(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    parsed = _parse_int(message.text)
    if parsed is None or parsed < 0:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="adm:users")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "user_create_invalid_traffic"), kb.as_markup())
        return

    await state.update_data(c_traffic=parsed)
    await state.set_state(UserManagementStates.create_duration)

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:users")
    kb.adjust(1)
    await render_menu(bot, user, user_repo, t(lang, "user_create_prompt_duration"), kb.as_markup())


@router.message(UserManagementStates.create_duration, F.text)
async def user_create_duration_step(
    message: Message, bot: Bot, user_repo: UserRepository,
    state: FSMContext, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    parsed = _parse_int(message.text)
    if parsed is None or parsed < 0:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="adm:users")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "user_create_invalid_duration"), kb.as_markup())
        return

    await state.update_data(c_duration=parsed)
    await state.set_state(UserManagementStates.create_squad)

    squads = await remnawave.get_internal_squads()
    kb = InlineKeyboardBuilder()
    for sq in squads:
        sq_name = sq.get("name") or "Squad"
        sq_uuid = sq.get("uuid")
        kb.button(text=f"🧩 {sq_name}", callback_data=f"adm:csq:{sq_uuid}")
    kb.button(text=t(lang, "user_create_all_squads"), callback_data="adm:csq:all")
    kb.button(text=t(lang, "user_create_default_squad"), callback_data="adm:csq:default")
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:users")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, t(lang, "user_create_prompt_squad"), kb.as_markup())


@router.callback_query(UserManagementStates.create_squad, F.data.startswith("adm:csq:"))
async def user_create_squad_step(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    state: FSMContext, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    choice = call.data.rsplit(":", 1)[1]
    if choice == "all":
        squads = await remnawave.get_internal_squads()
        selected = [s["uuid"] for s in squads if "uuid" in s]
    elif choice == "default":
        selected = []
    else:
        selected = [choice]

    await state.update_data(c_squads=selected)
    await state.set_state(UserManagementStates.create_hwid)

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "hwid_n_devices", n=1), callback_data="adm:chwid:1")
    kb.button(text=t(lang, "hwid_n_devices", n=2), callback_data="adm:chwid:2")
    kb.button(text=t(lang, "hwid_n_devices", n=3), callback_data="adm:chwid:3")
    kb.button(text=t(lang, "hwid_unlimited"), callback_data="adm:chwid:0")
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:users")
    kb.adjust(2, 2, 1)

    await render_menu(bot, user, user_repo, t(lang, "user_create_prompt_hwid"), kb.as_markup())
    await call.answer()


@router.callback_query(UserManagementStates.create_hwid, F.data.startswith("adm:chwid:"))
async def user_create_hwid_step(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    hwid_val = call.data.rsplit(":", 1)[1]
    hwid_limit = int(hwid_val) if hwid_val != "0" else None

    await state.update_data(c_hwid=hwid_limit)
    await state.set_state(UserManagementStates.create_telegram_id)

    kb = InlineKeyboardBuilder()
    kb.button(
        text="⏭ " + ("رد کردن (بدون اتصال تلگرام)" if lang == "fa" else "Skip (No Telegram)"),
        callback_data="adm:cskip:tid",
    )
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:users")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, t(lang, "user_create_prompt_telegram_id"), kb.as_markup())
    await call.answer()


async def _do_create_user(
    bot: Bot, user, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
    telegram_id: int,
) -> None:
    lang = user.language
    data = await state.get_data()
    username = str(data.get("c_username", ""))
    traffic_gb = int(data.get("c_traffic", 0))
    duration_days = int(data.get("c_duration", 0))
    squads = data.get("c_squads") or []
    hwid = data.get("c_hwid")

    if not squads:
        from bot.services.app_settings import get_store_settings
        store = await get_store_settings(session)
        if store.default_squad_uuid:
            squads = [store.default_squad_uuid]

    if duration_days > 0:
        expire_dt = datetime.now(timezone.utc) + timedelta(days=duration_days)
        expire_at_iso = expire_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        expire_dt = datetime.now(timezone.utc) + timedelta(days=36500)
        expire_at_iso = expire_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    traffic_limit_bytes = traffic_gb * (1024 ** 3) if traffic_gb > 0 else 0

    created = await remnawave.create_user(
        username=username,
        expire_at_iso=expire_at_iso,
        traffic_limit_bytes=traffic_limit_bytes,
        telegram_id=telegram_id,
        hwid_device_limit=hwid,
        internal_squads=squads if squads else None,
    )

    await state.clear()
    kb = InlineKeyboardBuilder()

    if created:
        sub_url = created.get("subscriptionUrl") or "—"
        await AdminLogRepository(session).log(
            user.telegram_id, "create_panel_user",
            detail=f"username={username} traffic={traffic_gb}GB days={duration_days} squads={len(squads)}",
        )
        traffic_label = f"{traffic_gb} GB" if traffic_gb > 0 else ("نامحدود" if lang == "fa" else "Unlimited")
        duration_label = f"{duration_days} روز" if duration_days > 0 else ("نامحدود" if lang == "fa" else "Unlimited")

        text = t(
            lang, "user_create_success",
            username=escape(username),
            traffic=traffic_label,
            duration=duration_label,
            sub_url=escape(sub_url),
        )
        kb.button(text=t(lang, "btn_back"), callback_data="adm:users")
        kb.adjust(1)
    else:
        text = t(lang, "user_create_error")
        kb.button(text=t(lang, "btn_back"), callback_data="adm:users")
        kb.adjust(1)

    await render_menu(bot, user, user_repo, text, kb.as_markup())


@router.callback_query(UserManagementStates.create_telegram_id, F.data == "adm:cskip:tid")
async def user_create_skip_tid(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _do_create_user(bot, user, user_repo, session, state, remnawave, telegram_id=0)
    await call.answer()


@router.message(UserManagementStates.create_telegram_id, F.text)
async def user_create_final_step(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    raw = message.text.strip()
    telegram_id = 0
    SKIP_WORDS = ("/skip", "-", "—", "0")
    if raw not in SKIP_WORDS:
        parsed_tid = _parse_int(raw)
        if parsed_tid is None or parsed_tid <= 0:
            kb = InlineKeyboardBuilder()
            kb.button(text=t(lang, "btn_cancel"), callback_data="adm:users")
            kb.adjust(1)
            await render_menu(bot, user, user_repo, t(lang, "user_add_invalid"), kb.as_markup())
            return
        telegram_id = parsed_tid

    await _do_create_user(bot, user, user_repo, session, state, remnawave, telegram_id=telegram_id)


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
# Panel User Detail & Operations
# --------------------------------------------------------------------- #
async def _render_panel_user_detail(
    bot: Bot, user, user_repo: UserRepository, remnawave: RemnawaveClient,
    panel_user_id: int, category: str, page: int, toast: str | None = None,
) -> None:
    lang = user.language or "fa"
    puser = await remnawave.get_panel_user_by_id(panel_user_id)
    if puser is None:
        kb = InlineKeyboardBuilder()
        back_cb = "adm:user:search" if category == "search" else f"adm:ulist:{category}:{page}"
        kb.button(text=t(lang, "btn_back"), callback_data=back_cb)
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "acc_error"), kb.as_markup())
        return

    uname = str(puser.get("username", "—"))
    status = str(puser.get("status", "")).upper()
    status_label = "✅" if status == "ACTIVE" else "⛔️"

    used_b = _get_used_bytes(puser)
    limit_b = _get_limit_bytes(puser)
    used_str = _format_gb(used_b)
    limit_str = _format_gb(limit_b) if limit_b > 0 else ("نامحدود" if lang == "fa" else "Unlimited")
    rem_str = _format_gb(max(0, limit_b - used_b)) if limit_b > 0 else "∞"

    # Expiry
    expire_str = "—"
    expire_iso = puser.get("expireAt")
    if expire_iso:
        try:
            exp = datetime.fromisoformat(str(expire_iso).replace("Z", "+00:00"))
            expire_str = format_date(exp, lang)
            now = datetime.now(timezone.utc)
            days_left = (exp - now).days
            if days_left > 0:
                expire_str += f" ({days_left} " + ("روز دیگر" if lang == "fa" else "days left") + ")"
            elif days_left == 0:
                expire_str += " (" + ("امروز" if lang == "fa" else "today") + ")"
            else:
                expire_str += " (" + ("منقضی شده" if lang == "fa" else "expired") + ")"
        except Exception:
            pass

    # Online
    online_str = "⚪️"
    online_at = _get_online_at(puser)
    if online_at:
        now = datetime.now(timezone.utc)
        if (now - online_at) <= timedelta(minutes=5):
            online_str = "🟢"
        else:
            online_str = f"🔴 ({format_datetime(online_at, lang)})"

    tid = puser.get("telegramId")
    tid_str = f"<code>{tid}</code>" if (tid and int(tid) > 0) else ("ثبت نشده" if lang == "fa" else "Unlinked")
    sub_url = str(puser.get("subscriptionUrl") or "—")

    hwid_devices = await remnawave.get_user_hwid_devices(panel_user_id)
    hwid_count = len(hwid_devices)
    hwid_limit = puser.get("hwidDeviceLimit")
    hwid_limit_str = str(hwid_limit) if hwid_limit else ("نامحدود" if lang == "fa" else "Unlimited")

    raw_squads = puser.get("activeInternalSquads") or []
    all_squads = await remnawave.get_internal_squads()
    squad_map = {sq["uuid"]: sq.get("name", "Squad") for sq in all_squads if "uuid" in sq}
    squad_names = []
    for item in raw_squads:
        if isinstance(item, dict):
            u_id = str(item.get("uuid") or item.get("id") or "")
            s_name = item.get("name") or squad_map.get(u_id, u_id[:8] if len(u_id) >= 8 else u_id)
        else:
            u_id = str(item)
            s_name = squad_map.get(u_id, u_id[:8] if len(u_id) >= 8 else u_id)
        if s_name:
            squad_names.append(s_name)

    if squad_names:
        squads_display = ", ".join(squad_names)
    else:
        squads_display = "پیش‌فرض" if lang == "fa" else "Default"

    traffic_strat = str(puser.get("trafficLimitStrategy") or "NO_RESET").upper()
    strat_labels = {
        "NO_RESET": t(lang, "strat_no_reset"),
        "DAY": t(lang, "strat_day"),
        "WEEK": t(lang, "strat_week"),
        "MONTH": t(lang, "strat_month"),
    }
    strat_name = strat_labels.get(traffic_strat, traffic_strat)

    desc = str(puser.get("description") or "").strip()
    desc_display = desc if desc else ("ثبت نشده" if lang == "fa" else "None")
    short_desc = (desc[:10] + "...") if len(desc) > 10 else (desc or ("—" if lang == "fa" else "None"))

    lines = [
        f"{t(lang, 'puser_title')}: <b>{escape(uname)}</b>",
        SEPARATOR,
        f"🆔 شناسه پنل: <code>{panel_user_id}</code>",
        f"📱 شناسه تلگرام: {tid_str}",
        f"📊 وضعیت: {status_label}",
        f"📈 {t(lang, 'puser_traffic')}: <b>{used_str}</b> / {limit_str} (باقی‌مانده: {rem_str})",
        f"🔁 دوره ریست: <b>{strat_name}</b>",
        f"📅 {t(lang, 'puser_expire')}: {expire_str}",
        f"🕒 {t(lang, 'puser_last_online')}: {online_str}",
        f"📱 {t(lang, 'puser_devices')}: <b>{hwid_count}</b> از {hwid_limit_str}",
        f"🧩 اسکوادها: <b>{escape(squads_display)}</b>",
        f"📝 یادداشت: {escape(desc_display)}",
        f"🔗 {t(lang, 'puser_sub_url')}:\n<code>{escape(sub_url)}</code>",
    ]

    kb = InlineKeyboardBuilder()

    btn_status = (
        t(lang, "btn_toggle_disable")
        if status == "ACTIVE"
        else t(lang, "btn_toggle_enable")
    )
    cb_status = f"adm:puser:toggle:{panel_user_id}:{category}:{page}"
    btn_ext = t(lang, "btn_quick_extend")
    cb_ext = f"adm:puser:ext:{panel_user_id}:{category}:{page}"

    btn_reset = t(lang, "btn_reset_traffic")
    cb_reset = f"adm:puser:reset:{panel_user_id}:{category}:{page}"
    btn_strat = t(lang, "btn_traffic_strategy", strategy=strat_name)
    cb_strat = f"adm:puser:strat:{panel_user_id}:{category}:{page}"

    btn_squads = t(lang, "btn_edit_squads")
    cb_squads = f"adm:puser:squads:{panel_user_id}:{category}:{page}"
    btn_devices = t(lang, "btn_view_devices")
    cb_devices = f"adm:puser:hwid:{panel_user_id}:{category}:{page}"

    btn_hwid_lim = t(lang, "btn_hwid_limit", limit=hwid_limit_str)
    cb_hwid_lim = f"adm:puser:hwidlim:{panel_user_id}:{category}:{page}"
    btn_tid = t(lang, "btn_edit_tid", tid=str(tid or ("—" if lang == "fa" else "None")))
    cb_tid = f"adm:puser:edittid:{panel_user_id}:{category}:{page}"

    btn_desc = t(lang, "btn_edit_desc", desc=short_desc)
    cb_desc = f"adm:puser:desc:{panel_user_id}:{category}:{page}"
    btn_revoke = t(lang, "btn_revoke_sub")
    cb_revoke = f"adm:puser:revoke:{panel_user_id}:{category}:{page}"

    if lang == "fa":
        # Persian RTL: first added is LEFT, second added is RIGHT
        # Row 1: Right = Quick Extend, Left = Toggle Status
        kb.button(text=btn_status, callback_data=cb_status)
        kb.button(text=btn_ext, callback_data=cb_ext)

        # Row 2: Right = Reset Traffic, Left = Reset Strategy
        kb.button(text=btn_strat, callback_data=cb_strat)
        kb.button(text=btn_reset, callback_data=cb_reset)

        # Row 3: Right = Squads, Left = View Devices
        kb.button(text=btn_devices, callback_data=cb_devices)
        kb.button(text=btn_squads, callback_data=cb_squads)

        # Row 4: Right = HWID Limit, Left = Edit Telegram ID
        kb.button(text=btn_tid, callback_data=cb_tid)
        kb.button(text=btn_hwid_lim, callback_data=cb_hwid_lim)

        # Row 5: Right = Revoke Sub, Left = Edit Note
        kb.button(text=btn_desc, callback_data=cb_desc)
        kb.button(text=btn_revoke, callback_data=cb_revoke)
    else:
        # LTR: first added is LEFT, second added is RIGHT
        kb.button(text=btn_ext, callback_data=cb_ext)
        kb.button(text=btn_status, callback_data=cb_status)

        kb.button(text=btn_reset, callback_data=cb_reset)
        kb.button(text=btn_strat, callback_data=cb_strat)

        kb.button(text=btn_squads, callback_data=cb_squads)
        kb.button(text=btn_devices, callback_data=cb_devices)

        kb.button(text=btn_hwid_lim, callback_data=cb_hwid_lim)
        kb.button(text=btn_tid, callback_data=cb_tid)

        kb.button(text=btn_revoke, callback_data=cb_revoke)
        kb.button(text=btn_desc, callback_data=cb_desc)

    row_adjust = [2, 2, 2, 2, 2]
    if tid and int(tid) > 0:
        kb.button(text=t(lang, "btn_wallet_manage"), callback_data=f"adm:user:{tid}")
        row_adjust.append(1)

    back_cb = "adm:user:search" if category == "search" else f"adm:ulist:{category}:{page}"
    kb.button(text=t(lang, "btn_back"), callback_data=back_cb)
    row_adjust.append(1)

    kb.adjust(*row_adjust)

    text = "\n".join(lines)
    if toast:
        text = f"{toast}\n\n{text}"

    await render_menu(bot, user, user_repo, text, kb.as_markup())


@router.callback_query(F.data.startswith("adm:puser:"))
async def panel_user_callback_dispatch(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return

    parts = call.data.split(":")
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    sub_action = parts[2]
    if sub_action == "toggle":
        p_id = int(parts[3])
        cat = parts[4]
        page = int(parts[5])
        puser = await remnawave.get_panel_user_by_id(p_id)
        if puser:
            cur_status = str(puser.get("status", "")).upper()
            new_status = "DISABLED" if cur_status == "ACTIVE" else "ACTIVE"
            await remnawave.set_user_status(p_id, new_status)
            await AdminLogRepository(session).log(
                call.from_user.id, "toggle_user_status", detail=f"id={p_id} status={new_status}"
            )
            await _render_panel_user_detail(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_status_toggled"))
        await call.answer()
        return

    if sub_action == "reset":
        p_id = int(parts[3])
        cat = parts[4]
        page = int(parts[5])
        await remnawave.reset_user_traffic(p_id)
        await AdminLogRepository(session).log(
            call.from_user.id, "reset_user_traffic", detail=f"id={p_id}"
        )
        await _render_panel_user_detail(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_traffic_reset"))
        await call.answer()
        return

    if sub_action == "revoke":
        p_id = int(parts[3])
        cat = parts[4]
        page = int(parts[5])
        await remnawave.revoke_user_sub(p_id)
        await AdminLogRepository(session).log(
            call.from_user.id, "revoke_user_sub", detail=f"id={p_id}"
        )
        await _render_panel_user_detail(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_sub_revoked"))
        await call.answer()
        return

    if sub_action == "ext":
        p_id = int(parts[3])
        cat = parts[4]
        page = int(parts[5])
        await state.set_state(UserManagementStates.waiting_extend_days)
        await state.update_data(ext_p_id=p_id, ext_cat=cat, ext_page=page)
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "puser_extend_prompt_days"), kb.as_markup())
        await call.answer()
        return

    if sub_action == "strat":
        p_id = int(parts[3])
        cat = parts[4]
        page = int(parts[5])
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "strat_no_reset"), callback_data=f"adm:puser:setstrat:{p_id}:NO_RESET:{cat}:{page}")
        kb.button(text=t(lang, "strat_day"), callback_data=f"adm:puser:setstrat:{p_id}:DAY:{cat}:{page}")
        kb.button(text=t(lang, "strat_week"), callback_data=f"adm:puser:setstrat:{p_id}:WEEK:{cat}:{page}")
        kb.button(text=t(lang, "strat_month"), callback_data=f"adm:puser:setstrat:{p_id}:MONTH:{cat}:{page}")
        kb.button(text=t(lang, "btn_back"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "strat_title"), kb.as_markup())
        await call.answer()
        return

    if sub_action == "setstrat":
        p_id = int(parts[3])
        strat = parts[4]
        cat = parts[5]
        page = int(parts[6])
        await remnawave.update_user_fields(p_id, trafficLimitStrategy=strat)
        await AdminLogRepository(session).log(
            call.from_user.id, "traffic_strategy", detail=f"id={p_id} strat={strat}"
        )
        await _render_panel_user_detail(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_strat_updated"))
        await call.answer()
        return

    if sub_action == "hwidlim":
        p_id = int(parts[3])
        cat = parts[4]
        page = int(parts[5])
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "hwid_n_devices", n=1), callback_data=f"adm:puser:sethwid:{p_id}:1:{cat}:{page}")
        kb.button(text=t(lang, "hwid_n_devices", n=2), callback_data=f"adm:puser:sethwid:{p_id}:2:{cat}:{page}")
        kb.button(text=t(lang, "hwid_n_devices", n=3), callback_data=f"adm:puser:sethwid:{p_id}:3:{cat}:{page}")
        kb.button(text=t(lang, "hwid_n_devices", n=5), callback_data=f"adm:puser:sethwid:{p_id}:5:{cat}:{page}")
        kb.button(text=t(lang, "hwid_unlimited"), callback_data=f"adm:puser:sethwid:{p_id}:0:{cat}:{page}")
        kb.button(text=t(lang, "btn_back"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
        kb.adjust(2, 2, 1, 1)
        await render_menu(bot, user, user_repo, t(lang, "hwid_limit_title"), kb.as_markup())
        await call.answer()
        return

    if sub_action == "sethwid":
        p_id = int(parts[3])
        val = int(parts[4])
        cat = parts[5]
        page = int(parts[6])
        new_limit = val if val > 0 else None
        await remnawave.update_user_fields(p_id, hwidDeviceLimit=new_limit)
        await AdminLogRepository(session).log(
            call.from_user.id, "hwid_limit", detail=f"id={p_id} limit={new_limit}"
        )
        await _render_panel_user_detail(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_hwid_updated"))
        await call.answer()
        return

    if sub_action == "edittid":
        p_id = int(parts[3])
        cat = parts[4]
        page = int(parts[5])
        await state.set_state(UserManagementStates.waiting_edit_tid)
        await state.update_data(edit_p_id=p_id, edit_cat=cat, edit_page=page)
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "puser_tid_prompt"), kb.as_markup())
        await call.answer()
        return

    if sub_action == "desc":
        p_id = int(parts[3])
        cat = parts[4]
        page = int(parts[5])
        await state.set_state(UserManagementStates.waiting_edit_desc)
        await state.update_data(edit_p_id=p_id, edit_cat=cat, edit_page=page)
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "puser_desc_prompt"), kb.as_markup())
        await call.answer()
        return

    if sub_action == "squads":
        p_id = int(parts[3])
        cat = parts[4]
        page = int(parts[5])
        puser = await remnawave.get_panel_user_by_id(p_id)
        if not puser:
            await call.answer(t("fa", "acc_error"), show_alert=True)
        active_uuids = set()
        for item in (puser.get("activeInternalSquads") or []):
            if isinstance(item, dict):
                uid = item.get("uuid") or item.get("id")
                if uid:
                    active_uuids.add(str(uid))
            elif item:
                active_uuids.add(str(item))

        all_squads = await remnawave.get_internal_squads()
        lines = [t(lang, "puser_squads_title"), SEPARATOR, t(lang, "puser_squads_hint")]
        kb = InlineKeyboardBuilder()
        for sq in all_squads:
            u_id = sq.get("uuid")
            s_name = sq.get("name", "Squad")
            is_active = u_id in active_uuids
            icon = "✅" if is_active else "⬜️"
            kb.button(
                text=f"{icon} {s_name}",
                callback_data=f"adm:puser:tgsq:{p_id}:{u_id}:{cat}:{page}",
            )
        kb.button(text=t(lang, "btn_back"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await call.answer()
        return

    if sub_action == "tgsq":
        p_id = int(parts[3])
        target_uuid = parts[4]
        cat = parts[5]
        page = int(parts[6])
        puser = await remnawave.get_panel_user_by_id(p_id)
        if not puser:
            await call.answer(t("fa", "acc_error"), show_alert=True)
            return
        active_uuids = set()
        for item in (puser.get("activeInternalSquads") or []):
            if isinstance(item, dict):
                uid = item.get("uuid") or item.get("id")
                if uid:
                    active_uuids.add(str(uid))
            elif item:
                active_uuids.add(str(item))

        if target_uuid in active_uuids:
            active_uuids.remove(target_uuid)
        else:
            active_uuids.add(target_uuid)
        await remnawave.set_user_squads(p_id, list(active_uuids))
        await AdminLogRepository(session).log(
            call.from_user.id, "update_user_squads", detail=f"id={p_id} squads={len(active_uuids)}"
        )
        all_squads = await remnawave.get_internal_squads()
        lines = [t(lang, "toast_squads_updated"), "", t(lang, "puser_squads_title"), SEPARATOR, t(lang, "puser_squads_hint")]
        kb = InlineKeyboardBuilder()
        for sq in all_squads:
            u_id = sq.get("uuid")
            s_name = sq.get("name", "Squad")
            is_active = u_id in active_uuids
            icon = "✅" if is_active else "⬜️"
            kb.button(
                text=f"{icon} {s_name}",
                callback_data=f"adm:puser:tgsq:{p_id}:{u_id}:{cat}:{page}",
            )
        kb.button(text=t(lang, "btn_back"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await call.answer()
        return

    if sub_action == "hwid":
        p_id = int(parts[3])
        cat = parts[4]
        page = int(parts[5])
        devices = await remnawave.get_user_hwid_devices(p_id)
        kb = InlineKeyboardBuilder()
        lines = [f"📱 {t(lang, 'puser_devices')}:", SEPARATOR]
        if not devices:
            lines.append(t(lang, "puser_no_devices"))
        else:
            for dev in devices:
                hwid = dev.get("hwid", "—")
                dev_name = dev.get("deviceName") or dev.get("platform") or "Device"
                lines.append(f"• <b>{dev_name}</b>\n  <code>{hwid}</code>")
                kb.button(
                    text=f"🗑 {dev_name[:16]}",
                    callback_data=f"adm:puser:delhwid:{p_id}:{hwid}:{cat}:{page}",
                )
        kb.button(text=t(lang, "btn_back"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await call.answer()
        return

    if sub_action == "delhwid":
        p_id = int(parts[3])
        hwid = parts[4]
        cat = parts[5]
        page = int(parts[6])
        await remnawave.delete_hwid_device(p_id, hwid)
        await AdminLogRepository(session).log(
            call.from_user.id, "delete_hwid", detail=f"id={p_id} hwid={hwid}"
        )
        # return to devices list
        devices = await remnawave.get_user_hwid_devices(p_id)
        kb = InlineKeyboardBuilder()
        lines = [t(lang, "puser_device_removed"), "", f"📱 {t(lang, 'puser_devices')}:", SEPARATOR]
        if not devices:
            lines.append(t(lang, "puser_no_devices"))
        else:
            for dev in devices:
                dev_hwid = dev.get("hwid", "—")
                dev_name = dev.get("deviceName") or dev.get("platform") or "Device"
                lines.append(f"• <b>{dev_name}</b>\n  <code>{dev_hwid}</code>")
                kb.button(
                    text=f"🗑 {dev_name[:16]}",
                    callback_data=f"adm:puser:delhwid:{p_id}:{dev_hwid}:{cat}:{page}",
                )
        kb.button(text=t(lang, "btn_back"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await call.answer()
        return

    # Default: view user detail: adm:puser:{id}:{category}:{page}
    try:
        p_id = int(parts[2])
        cat = parts[3] if len(parts) > 3 else "all"
        page = int(parts[4]) if len(parts) > 4 else 0
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    await state.clear()
    await _render_panel_user_detail(bot, user, user_repo, remnawave, p_id, cat, page)
    await call.answer()


# --------------------------------------------------------------------- #
# Telegram User Detail (Wallet Balance Adjustment)
# --------------------------------------------------------------------- #
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

    target = await UserRepository(session).get_by_telegram_id(telegram_id)
    if target is None:
        target = await UserRepository(session).get_or_create(telegram_id, username=None)

    wallet = await WalletRepository(session).get_wallet(telegram_id)
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

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("adm:ban:"))
async def admin_ban_user(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    telegram_id = int(call.data.rsplit(":", 1)[1])
    await user_repo.set_banned(telegram_id, True)
    await AdminLogRepository(session).log(
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
    telegram_id = int(call.data.rsplit(":", 1)[1])
    await user_repo.set_banned(telegram_id, False)
    await AdminLogRepository(session).log(
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

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


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


# --------------------------------------------------------------------- #
# FSM Handlers: Quick Extend, Telegram ID, Admin Note
# --------------------------------------------------------------------- #
@router.message(UserManagementStates.waiting_extend_days, F.text)
async def puser_extend_days_step(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    data = await state.get_data()
    p_id = int(data.get("ext_p_id", 0))
    cat = data.get("ext_cat", "all")
    page = int(data.get("ext_page", 0))

    parsed = _parse_int(message.text)
    if parsed is None or parsed < 0:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "user_create_invalid_duration"), kb.as_markup())
        return

    await state.update_data(ext_days=parsed)
    await state.set_state(UserManagementStates.waiting_extend_traffic)

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
    kb.adjust(1)
    await render_menu(bot, user, user_repo, t(lang, "puser_extend_prompt_traffic"), kb.as_markup())


@router.message(UserManagementStates.waiting_extend_traffic, F.text)
async def puser_extend_traffic_step(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    data = await state.get_data()
    p_id = int(data.get("ext_p_id", 0))
    cat = data.get("ext_cat", "all")
    page = int(data.get("ext_page", 0))
    ext_days = int(data.get("ext_days", 0))

    parsed = _parse_int(message.text)
    if parsed is None or parsed < 0:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "user_create_invalid_traffic"), kb.as_markup())
        return

    ext_gb = parsed
    puser = await remnawave.get_panel_user_by_id(p_id)
    if not puser:
        await state.clear()
        await _render_panel_users_list(bot, user, user_repo, remnawave, cat, page)
        return

    cur_exp_str = puser.get("expireAt")
    now = datetime.now(timezone.utc)
    if ext_days > 0:
        base_dt = now
        if cur_exp_str:
            try:
                dt = datetime.fromisoformat(str(cur_exp_str).replace("Z", "+00:00"))
                if dt > now:
                    base_dt = dt
            except Exception:
                pass
        new_exp_iso = (base_dt + timedelta(days=ext_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        new_exp_iso = cur_exp_str or (now + timedelta(days=36500)).strftime("%Y-%m-%dT%H:%M:%SZ")

    cur_limit = _get_limit_bytes(puser)
    new_limit = cur_limit + (ext_gb * (1024 ** 3)) if ext_gb > 0 else cur_limit

    await remnawave.update_user_subscription(
        p_id, expire_at_iso=new_exp_iso, traffic_limit_bytes=new_limit, status="ACTIVE",
    )
    await AdminLogRepository(session).log(
        message.from_user.id, "quick_extend", detail=f"id={p_id} +days={ext_days} +gb={ext_gb}",
    )
    await state.clear()
    await _render_panel_user_detail(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_user_extended"))


@router.message(UserManagementStates.waiting_edit_tid, F.text)
async def puser_edit_tid_step(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    data = await state.get_data()
    p_id = int(data.get("edit_p_id", 0))
    cat = data.get("edit_cat", "all")
    page = int(data.get("edit_page", 0))

    raw = message.text.strip()
    new_tid: int | None = 0
    SKIP_WORDS = ("/skip", "-", "—", "0")
    if raw not in SKIP_WORDS:
        parsed = _parse_int(raw)
        if parsed is None or parsed < 0:
            kb = InlineKeyboardBuilder()
            kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
            kb.adjust(1)
            await render_menu(bot, user, user_repo, t(lang, "user_add_invalid"), kb.as_markup())
            return
        new_tid = parsed

    await remnawave.update_user_fields(p_id, telegramId=new_tid)
    await AdminLogRepository(session).log(
        message.from_user.id, "edit_telegram_id", detail=f"id={p_id} tid={new_tid}",
    )
    await state.clear()
    await _render_panel_user_detail(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_tid_updated"))


@router.message(UserManagementStates.waiting_edit_desc, F.text)
async def puser_edit_desc_step(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    data = await state.get_data()
    p_id = int(data.get("edit_p_id", 0))
    cat = data.get("edit_cat", "all")
    page = int(data.get("edit_page", 0))

    raw = message.text.strip()
    SKIP_WORDS = ("/skip", "-", "—")
    new_desc = "" if raw in SKIP_WORDS else raw

    await remnawave.update_user_fields(p_id, description=new_desc)
    await AdminLogRepository(session).log(
        message.from_user.id, "edit_description", detail=f"id={p_id} desc={new_desc[:30]}",
    )
    await state.clear()
    await _render_panel_user_detail(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_desc_updated"))
