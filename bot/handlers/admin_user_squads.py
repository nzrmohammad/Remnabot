"""Admin Remnawave Panel User Squad Assignment."""
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, is_admin
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)
router = Router(name="admin_user_squads")

_is_admin = is_admin


@router.callback_query(F.data.startswith("adm:puser:squads:"))
async def panel_user_squads_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return

    parts = call.data.split(":")
    p_id = int(parts[3])
    cat = parts[4]
    page = int(parts[5])

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

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


@router.callback_query(F.data.startswith("adm:puser:tgsq:"))
async def panel_user_squad_toggle(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return

    parts = call.data.split(":")
    p_id = int(parts[3])
    target_uuid = parts[4]
    cat = parts[5]
    page = int(parts[6])

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

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
