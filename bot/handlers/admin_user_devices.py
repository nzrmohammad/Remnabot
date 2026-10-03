"""Admin Remnawave Panel User HWID Devices and Limit Management."""
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, is_admin, resolve_op
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)
router = Router(name="admin_user_devices")

_is_admin = is_admin


@router.callback_query(F.data.startswith("adm:puser:hwidlim:"))
async def panel_user_hwid_limit_picker(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
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


@router.callback_query(F.data.startswith("adm:puser:sethwid:"))
async def panel_user_hwid_limit_set(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return

    from bot.handlers.admin_user_detail import _render_panel_user_detail
    render_detail_fn = resolve_op("_render_panel_user_detail", _render_panel_user_detail)

    parts = call.data.split(":")
    p_id = int(parts[3])
    val = int(parts[4])
    cat = parts[5]
    page = int(parts[6])

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    new_limit = val if val > 0 else None
    await remnawave.update_user_fields(p_id, hwidDeviceLimit=new_limit)
    await AdminLogRepository(session).log(
        call.from_user.id, "hwid_limit", detail=f"id={p_id} limit={new_limit}"
    )
    await render_detail_fn(bot, user, user_repo, remnawave, p_id, cat, page, toast=t(lang, "toast_hwid_updated"))
    await call.answer()


@router.callback_query(F.data.startswith("adm:puser:hwid:"))
async def panel_user_devices_list(
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


@router.callback_query(F.data.startswith("adm:puser:delhwid:"))
async def panel_user_device_delete(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return

    parts = call.data.split(":")
    p_id = int(parts[3])
    hwid = parts[4]
    cat = parts[5]
    page = int(parts[6])

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    await remnawave.delete_hwid_device(p_id, hwid)
    await AdminLogRepository(session).log(
        call.from_user.id, "delete_hwid", detail=f"id={p_id} hwid={hwid}"
    )
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
