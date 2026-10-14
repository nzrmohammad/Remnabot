"""Admin Service Management: CRUD, activation toggle, and FSM wizard."""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, is_admin, parse_int
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.user_repo import UserRepository
from bot.handlers.admin_services_wizard import (
    ADMIN_EMOJI,
    EDIT_FIELDS,
    FIELD_TO_COLUMN,
    STRATEGY_KEYS,
    _cancel_kb,
    add_service_start,
    create_description,
    create_duration,
    create_hwid,
    create_name,
    create_price,
    create_squad,
    create_strategy_pick,
    create_traffic,
    edit_service_field,
    edit_service_pick,
    edit_value_save,
    wizard_router,
)
from bot.locales.texts import t
from bot.services.menu import render_menu
from bot.services.service_display import service_block

logger = logging.getLogger(__name__)
router = Router(name="admin_services_mgmt")
router.include_router(wizard_router)

__all__ = [
    "ADMIN_EMOJI",
    "EDIT_FIELDS",
    "FIELD_TO_COLUMN",
    "STRATEGY_KEYS",
    "_cancel_kb",
    "add_service_start",
    "admin_cancel",
    "admin_services",
    "create_description",
    "create_duration",
    "create_hwid",
    "create_name",
    "create_price",
    "create_squad",
    "create_strategy_pick",
    "create_traffic",
    "delete_service_confirm",
    "delete_service_do",
    "edit_service_field",
    "edit_service_pick",
    "edit_value_save",
    "router",
    "service_view_detail",
    "toggle_service",
    "wizard_router",
]

_is_admin = is_admin
_parse_int = parse_int


async def _render_admin_services(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    toast: str | None = None,
) -> None:

    lang = user.language or "fa"
    services = await ServiceRepository(session).list_all()

    lines = [f"{t(lang, 'admin_services_title')}\n{SEPARATOR}"]
    if not services:
        lines.append(t(lang, "services_empty"))
    else:
        hint = (
            "برای مشاهده جزئیات، ویرایش یا فعال/غیرفعال‌سازی، سرویس مورد نظر را انتخاب کنید:"
            if lang == "fa"
            else "Select a service to view details, edit, or toggle status:"
        )
        lines.append(hint)

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        for i in range(0, len(services), 2):
            chunk = services[i : i + 2]
            if len(chunk) == 2:
                for s in reversed(chunk):
                    status_icon = "✅" if s.is_active else "❌"
                    kb.button(text=f"{status_icon} {s.name}", callback_data=f"adm:svc:view:{s.id}")
            else:
                s = chunk[0]
                status_icon = "✅" if s.is_active else "❌"
                kb.button(text=f"{status_icon} {s.name}", callback_data=f"adm:svc:view:{s.id}")
    else:
        for s in services:
            status_icon = "✅" if s.is_active else "❌"
            kb.button(text=f"{status_icon} {s.name}", callback_data=f"adm:svc:view:{s.id}")

    if lang == "fa":
        kb.button(text=t(lang, "btn_coupons_admin"), callback_data="adm:coupons")
        kb.button(text=t(lang, "btn_add_service"), callback_data="adm:svc:add")
    else:
        kb.button(text=t(lang, "btn_add_service"), callback_data="adm:svc:add")
        kb.button(text=t(lang, "btn_coupons_admin"), callback_data="adm:coupons")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")

    service_sizes = [2] * (len(services) // 2) + ([1] if len(services) % 2 else [])
    sizes = service_sizes + [2, 1]
    kb.adjust(*sizes)

    text = "\n".join(lines)
    if toast:
        text = f"{toast}\n\n{text}"
    await render_menu(bot, user, user_repo, text, kb.as_markup())


async def _render_service_detail(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    service_id: int,
    toast: str | None = None,
) -> None:

    lang = user.language or "fa"
    service = await ServiceRepository(session).get(service_id)
    if service is None:
        await _render_admin_services(bot, user, user_repo, session, toast=t(lang, "acc_error"))
        return

    lines = [
        f"📦 <b>{escape(service.name)}</b>\n{SEPARATOR}",
        service_block(service, lang, show_state=True),
    ]

    kb = InlineKeyboardBuilder()
    toggle_text = t(lang, "btn_disable") if service.is_active else t(lang, "btn_enable")
    edit_text = t(lang, "btn_edit")
    del_text = t(lang, "btn_delete")

    if lang == "fa":
        kb.button(text=toggle_text, callback_data=f"adm:svc:toggle:{service.id}")
        kb.button(text=edit_text, callback_data=f"adm:svc:edit:{service.id}")
    else:
        kb.button(text=edit_text, callback_data=f"adm:svc:edit:{service.id}")
        kb.button(text=toggle_text, callback_data=f"adm:svc:toggle:{service.id}")

    kb.button(text=del_text, callback_data=f"adm:svc:del:{service.id}")
    kb.button(text=t(lang, "btn_back"), callback_data="adm:services")
    kb.adjust(2, 1, 1)

    text = "\n".join(lines)
    if toast:
        text = f"{toast}\n\n{text}"
    await render_menu(bot, user, user_repo, text, kb.as_markup())




@router.callback_query(F.data == "adm:services")
async def admin_services(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_admin_services(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data.startswith("adm:svc:view:"))
async def service_view_detail(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    await state.clear()
    try:
        service_id = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_service_detail(bot, user, user_repo, session, service_id)
    await call.answer()


@router.callback_query(F.data == "adm:svc:cancel")
async def admin_cancel(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return

    data = await state.get_data()
    service_id = data.get("service_id")
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    if service_id:
        await _render_service_detail(bot, user, user_repo, session, int(service_id))
    else:
        await _render_admin_services(bot, user, user_repo, session)
    await call.answer()



@router.callback_query(F.data.startswith("adm:svc:toggle:"))
async def toggle_service(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        service_id = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    repo = ServiceRepository(session)
    service = await repo.get(service_id)
    if service is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    new_state = not service.is_active
    await repo.set_active(service_id, new_state)
    await _render_service_detail(bot, user, user_repo, session, service_id)
    toast_msg = "✅ سرویس فعال شد." if new_state else "⛔️ سرویس غیرفعال شد."
    await call.answer(toast_msg)


@router.callback_query(F.data.startswith("adm:svc:del:"))
async def delete_service_confirm(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        service_id = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    service = await ServiceRepository(session).get(service_id)
    if service is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.button(
        text=t(lang, "btn_yes_delete"),
        callback_data=f"adm:svc:del_yes:{service.id}",
    )
    kb.button(text=t(lang, "btn_cancel"), callback_data=f"adm:svc:view:{service.id}")
    kb.adjust(2)

    await render_menu(
        bot, user, user_repo,
        t(lang, "svc_delete_confirm", name=escape(service.name)),
        kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:svc:del_yes:"))
async def delete_service_do(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        service_id = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    repo = ServiceRepository(session)
    service = await repo.get(service_id)
    if service is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    await repo.delete(service_id)
    await _render_admin_services(
        bot, user, user_repo, session, toast=t(lang, "svc_deleted", name=service.name)
    )
    await call.answer()
