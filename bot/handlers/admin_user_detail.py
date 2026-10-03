"""Admin Remnawave Panel User Details, Operations, and FSM Actions."""
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import (
    SEPARATOR,
    fmt,
    get_limit_bytes,
    get_online_at,
    get_used_bytes,
    is_admin,
    parse_int,
    resolve_op,
)
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.user_repo import UserRepository
from bot.handlers.admin_user_devices import router as devices_router
from bot.handlers.admin_user_squads import router as squads_router
from bot.locales.texts import t
from bot.services.formatting import format_date, format_datetime, human_bytes
from bot.services.menu import delete_message_silently, render_menu
from bot.services.remnawave import RemnawaveClient
from bot.states.admin import UserManagementStates

logger = logging.getLogger(__name__)
router = Router(name="admin_user_detail")
router.include_router(squads_router)
router.include_router(devices_router)

_parse_int = parse_int
_is_admin = is_admin


async def _render_panel_user_detail(
    bot: Bot, user, user_repo: UserRepository, remnawave: RemnawaveClient,
    panel_user_id: int, category: str, page: int, toast: str | None = None,
) -> None:
    render_menu_fn = resolve_op("render_menu", render_menu)

    lang = user.language or "fa"
    puser = await remnawave.get_panel_user_by_id(panel_user_id)
    if puser is None:
        kb = InlineKeyboardBuilder()
        back_cb = "adm:user:search" if category == "search" else f"adm:ulist:{category}:{page}"
        kb.button(text=t(lang, "btn_back"), callback_data=back_cb)
        kb.adjust(1)
        await render_menu_fn(bot, user, user_repo, t(lang, "acc_error"), kb.as_markup())
        return

    uname = str(puser.get("username", "—"))
    status = str(puser.get("status", "")).upper()
    status_label = "✅" if status == "ACTIVE" else "⛔️"

    used_b = get_used_bytes(puser)
    limit_b = get_limit_bytes(puser)
    used_str = human_bytes(used_b)
    limit_str = human_bytes(limit_b) if limit_b > 0 else ("نامحدود" if lang == "fa" else "Unlimited")
    rem_str = human_bytes(max(0, limit_b - used_b)) if limit_b > 0 else "∞"

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
    online_at = get_online_at(puser)
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
        squads_display = "همه نودها (سراسری)" if lang == "fa" else "All Nodes (Global)"

    strat = str(puser.get("trafficLimitStrategy", "NO_RESET")).upper()
    strat_labels = {
        "NO_RESET": "بدون ریست" if lang == "fa" else "No reset",
        "DAY": "روزانه" if lang == "fa" else "Daily",
        "WEEK": "هفتگی" if lang == "fa" else "Weekly",
        "MONTH": "ماهانه" if lang == "fa" else "Monthly",
    }
    strat_str = strat_labels.get(strat, strat)
    desc = puser.get("description") or "—"

    lines = [
        f"👤 <b>{uname}</b>",
        SEPARATOR,
        f"🔘 {t(lang, 'puser_status')}: <b>{status} {status_label}</b>",
        f"📶 {t(lang, 'puser_online')}: {online_str}",
        f"📊 {t(lang, 'puser_traffic')}: <b>{used_str}</b> / <b>{limit_str}</b> (باقی‌مانده: {rem_str})",
        f"🔄 {t(lang, 'puser_strategy')}: <b>{strat_str}</b>",
        f"⏳ {t(lang, 'puser_expire')}: <b>{expire_str}</b>",
        f"🆔 {t(lang, 'puser_tid')}: {tid_str}",
        f"📱 {t(lang, 'puser_hwid')}: <b>{hwid_count}</b> / <b>{hwid_limit_str}</b>",
        f"🧩 {t(lang, 'puser_squads')}: <b>{squads_display}</b>",
        f"📝 {t(lang, 'puser_desc')}: <i>{desc}</i>",
        f"\n🔗 <code>{sub_url}</code>",
    ]

    kb = InlineKeyboardBuilder()
    row_adjust = []

    # Row 1: Status toggle + Revoke link
    toggle_text = t(lang, "btn_disable") if status == "ACTIVE" else t(lang, "btn_enable")
    if lang == "fa":
        kb.button(text=t(lang, "btn_revoke_sub"), callback_data=f"adm:puser:revoke:{panel_user_id}:{category}:{page}")
        kb.button(text=toggle_text, callback_data=f"adm:puser:toggle:{panel_user_id}:{category}:{page}")
    else:
        kb.button(text=toggle_text, callback_data=f"adm:puser:toggle:{panel_user_id}:{category}:{page}")
        kb.button(text=t(lang, "btn_revoke_sub"), callback_data=f"adm:puser:revoke:{panel_user_id}:{category}:{page}")
    row_adjust.append(2)

    # Row 2: Extend + Reset Traffic
    if lang == "fa":
        kb.button(text=t(lang, "btn_reset_traffic"), callback_data=f"adm:puser:reset:{panel_user_id}:{category}:{page}")
        kb.button(text=t(lang, "btn_quick_extend"), callback_data=f"adm:puser:ext:{panel_user_id}:{category}:{page}")
    else:
        kb.button(text=t(lang, "btn_quick_extend"), callback_data=f"adm:puser:ext:{panel_user_id}:{category}:{page}")
        kb.button(text=t(lang, "btn_reset_traffic"), callback_data=f"adm:puser:reset:{panel_user_id}:{category}:{page}")
    row_adjust.append(2)

    # Row 3: Squads + Strategy
    if lang == "fa":
        kb.button(text=t(lang, "btn_user_strat"), callback_data=f"adm:puser:strat:{panel_user_id}:{category}:{page}")
        kb.button(text=t(lang, "btn_user_squads"), callback_data=f"adm:puser:squads:{panel_user_id}:{category}:{page}")
    else:
        kb.button(text=t(lang, "btn_user_squads"), callback_data=f"adm:puser:squads:{panel_user_id}:{category}:{page}")
        kb.button(text=t(lang, "btn_user_strat"), callback_data=f"adm:puser:strat:{panel_user_id}:{category}:{page}")
    row_adjust.append(2)

    # Row 4: Devices/HWID list + HWID limit
    if lang == "fa":
        kb.button(text=t(lang, "btn_hwid_limit"), callback_data=f"adm:puser:hwidlim:{panel_user_id}:{category}:{page}")
        kb.button(text=t(lang, "btn_devices_list"), callback_data=f"adm:puser:hwid:{panel_user_id}:{category}:{page}")
    else:
        kb.button(text=t(lang, "btn_devices_list"), callback_data=f"adm:puser:hwid:{panel_user_id}:{category}:{page}")
        kb.button(text=t(lang, "btn_hwid_limit"), callback_data=f"adm:puser:hwidlim:{panel_user_id}:{category}:{page}")
    row_adjust.append(2)

    # Row 5: Edit Telegram ID + Edit Description
    if lang == "fa":
        kb.button(text=t(lang, "btn_edit_desc"), callback_data=f"adm:puser:desc:{panel_user_id}:{category}:{page}")
        kb.button(text=t(lang, "btn_edit_tid"), callback_data=f"adm:puser:edittid:{panel_user_id}:{category}:{page}")
    else:
        kb.button(text=t(lang, "btn_edit_tid"), callback_data=f"adm:puser:edittid:{panel_user_id}:{category}:{page}")
        kb.button(text=t(lang, "btn_edit_desc"), callback_data=f"adm:puser:desc:{panel_user_id}:{category}:{page}")
    row_adjust.append(2)

    # Row 6: Telegram user detail link if tid present
    if tid and int(tid) > 0:
        kb.button(text=f"👤 {t(lang, 'btn_view_tg_user')}", callback_data=f"adm:user:{tid}")
        row_adjust.append(1)

    # Row 7: Back
    back_cb = "adm:user:search" if category == "search" else f"adm:ulist:{category}:{page}"
    kb.button(text=t(lang, "btn_back"), callback_data=back_cb)
    row_adjust.append(1)

    kb.adjust(*row_adjust)

    text = "\n".join(lines)
    if toast:
        text = f"{toast}\n\n{text}"

    await render_menu_fn(bot, user, user_repo, text, kb.as_markup())


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

    render_detail_fn = resolve_op("_render_panel_user_detail", _render_panel_user_detail)
    render_menu_fn = resolve_op("render_menu", render_menu)

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
            await render_detail_fn(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_status_toggled"))
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
        await render_detail_fn(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_traffic_reset"))
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
        await render_detail_fn(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_sub_revoked"))
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
        await render_menu_fn(bot, user, user_repo, t(lang, "puser_extend_prompt_days"), kb.as_markup())
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
        await render_menu_fn(bot, user, user_repo, t(lang, "strat_title"), kb.as_markup())
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
        await render_detail_fn(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_strat_updated"))
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
        await render_menu_fn(bot, user, user_repo, t(lang, "puser_tid_prompt"), kb.as_markup())
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
        await render_menu_fn(bot, user, user_repo, t(lang, "puser_desc_prompt"), kb.as_markup())
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
    await render_detail_fn(bot, user, user_repo, remnawave, p_id, cat, page)
    await call.answer()


@router.message(UserManagementStates.waiting_extend_days, F.text)
async def puser_extend_days_step(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    render_menu_fn = resolve_op("render_menu", render_menu)

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
        await render_menu_fn(bot, user, user_repo, t(lang, "user_create_invalid_duration"), kb.as_markup())
        return

    await state.update_data(ext_days=parsed)
    await state.set_state(UserManagementStates.waiting_extend_traffic)

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:puser:{p_id}:{cat}:{page}")
    kb.adjust(1)
    await render_menu_fn(bot, user, user_repo, t(lang, "puser_extend_prompt_traffic"), kb.as_markup())


@router.message(UserManagementStates.waiting_extend_traffic, F.text)
async def puser_extend_traffic_step(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    render_menu_fn = resolve_op("render_menu", render_menu)
    render_detail_fn = resolve_op("_render_panel_user_detail", _render_panel_user_detail)
    import bot.handlers.admin_users as _users
    render_list_fn = resolve_op("_render_panel_users_list", _users._render_panel_users_list)

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
        await render_menu_fn(bot, user, user_repo, t(lang, "user_create_invalid_traffic"), kb.as_markup())
        return

    ext_gb = parsed
    puser = await remnawave.get_panel_user_by_id(p_id)
    if not puser:
        await state.clear()
        await render_list_fn(bot, user, user_repo, remnawave, cat, page)
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

    cur_limit = get_limit_bytes(puser)
    new_limit = cur_limit + (ext_gb * (1024 ** 3)) if ext_gb > 0 else cur_limit

    await remnawave.update_user_subscription(
        p_id, expire_at_iso=new_exp_iso, traffic_limit_bytes=new_limit, status="ACTIVE",
    )
    await AdminLogRepository(session).log(
        message.from_user.id, "quick_extend", detail=f"id={p_id} +days={ext_days} +gb={ext_gb}",
    )
    await state.clear()
    await render_detail_fn(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_user_extended"))


@router.message(UserManagementStates.waiting_edit_tid, F.text)
async def puser_edit_tid_step(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    render_menu_fn = resolve_op("render_menu", render_menu)
    render_detail_fn = resolve_op("_render_panel_user_detail", _render_panel_user_detail)

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
            await render_menu_fn(bot, user, user_repo, t(lang, "user_add_invalid"), kb.as_markup())
            return
        new_tid = parsed

    await remnawave.update_user_fields(p_id, telegramId=new_tid)
    await AdminLogRepository(session).log(
        message.from_user.id, "edit_telegram_id", detail=f"id={p_id} tid={new_tid}",
    )
    await state.clear()
    await render_detail_fn(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_tid_updated"))


@router.message(UserManagementStates.waiting_edit_desc, F.text)
async def puser_edit_desc_step(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    render_detail_fn = resolve_op("_render_panel_user_detail", _render_panel_user_detail)

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
    await render_detail_fn(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_desc_updated"))
