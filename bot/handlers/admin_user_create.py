"""Admin Panel User Creation Wizard (Guided FSM)."""
from datetime import datetime, timedelta, timezone
from html import escape
import logging
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import is_admin, parse_int
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.menu import delete_message_silently, render_menu
from bot.services.remnawave import RemnawaveClient
from bot.states.admin import UserManagementStates

logger = logging.getLogger(__name__)
router = Router(name="admin_user_create")

_is_admin = is_admin
_parse_int = parse_int


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
