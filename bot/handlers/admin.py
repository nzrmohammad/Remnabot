"""Admin panel: dashboard entry and admin navigation."""
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.common import SEPARATOR, is_admin, parse_int
from bot.config import get_settings
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.user_repo import UserRepository
from bot.handlers.admin_services_mgmt import (
    ADMIN_EMOJI,
    EDIT_FIELDS,
    FIELD_TO_COLUMN,
    STRATEGY_KEYS,
    _cancel_kb,
    _render_admin_services,
    _render_service_detail,
    add_service_start,
    admin_cancel,
    admin_services,
    create_description,
    create_duration,
    create_hwid,
    create_name,
    create_price,
    create_squad,
    create_strategy_pick,
    create_traffic,
    delete_service_confirm,
    delete_service_do,
    edit_service_field,
    edit_service_pick,
    edit_value_save,
    router as services_router,
    service_view_detail,
    toggle_service,
)
from bot.locales.texts import t
from bot.services.menu import render_menu

logger = logging.getLogger(__name__)

router = Router(name="admin")
router.include_router(services_router)

_is_admin = is_admin
_parse_int = parse_int


@router.callback_query(F.data == "menu:admin")
async def admin_panel(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext
):
    if not _is_admin(call.from_user.id):
        await call.answer(t(call.from_user.language_code, "not_authorized"), show_alert=True)
        return
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        # Persian RTL: first added button appears on LEFT, second on RIGHT
        # Row 1: Left = User Management, Right = Dashboard
        kb.button(text=t(lang, "btn_manage_users"), callback_data="adm:users")
        kb.button(text=t(lang, "btn_dashboard"), callback_data="adm:dash")
        # Row 2: Left = Manage Services, Right = Sales Report
        kb.button(text=t(lang, "btn_manage_services"), callback_data="adm:services")
        kb.button(text=t(lang, "btn_sales_report"), callback_data="adm:sales")
        # Row 3: Left = Broadcast, Right = Store Settings
        kb.button(text=t(lang, "btn_broadcast"), callback_data="adm:broadcast")
        kb.button(text=t(lang, "btn_store_settings"), callback_data="adm:settings")
        # Row 4: Left = Node Monitor, Right = Database Backup
        kb.button(text=t(lang, "btn_nodes_monitor"), callback_data="adm:nodes")
        kb.button(text=t(lang, "btn_backup_db"), callback_data="adm:backup")
    else:
        # LTR: Row 1: Left = Dashboard, Right = User Management
        kb.button(text=t(lang, "btn_dashboard"), callback_data="adm:dash")
        kb.button(text=t(lang, "btn_manage_users"), callback_data="adm:users")
        # Row 2: Left = Sales Report, Right = Manage Services
        kb.button(text=t(lang, "btn_sales_report"), callback_data="adm:sales")
        kb.button(text=t(lang, "btn_manage_services"), callback_data="adm:services")
        # Row 3: Left = Store Settings, Right = Broadcast
        kb.button(text=t(lang, "btn_store_settings"), callback_data="adm:settings")
        kb.button(text=t(lang, "btn_broadcast"), callback_data="adm:broadcast")
        # Row 4: Left = Database Backup, Right = Node Monitor
        kb.button(text=t(lang, "btn_backup_db"), callback_data="adm:backup")
        kb.button(text=t(lang, "btn_nodes_monitor"), callback_data="adm:nodes")

    # Row 5: Admin Mini App Panel
    settings = get_settings()
    web_app_url = getattr(settings, "WEB_APP_URL", "") or ""
    tma_btn_text = "📱 پنل مدیریت Mini App" if lang == "fa" else "📱 Admin Mini App Panel"

    if web_app_url and web_app_url.startswith("https://"):
        admin_tma_url = f"{web_app_url.rstrip('/')}/admin"
        kb.button(text=tma_btn_text, web_app=WebAppInfo(url=admin_tma_url))
    elif web_app_url and web_app_url.startswith("http://"):
        admin_tma_url = f"{web_app_url.rstrip('/')}/admin"
        kb.button(text=tma_btn_text, url=admin_tma_url)
    else:
        kb.button(text=tma_btn_text, callback_data="adm:tma:nourl")

    # Row 6: Main Menu
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    kb.adjust(2, 2, 2, 2, 1, 1)

    await render_menu(
        bot, user, user_repo,
        f"{t(lang, 'admin_panel_title')}\n{SEPARATOR}\n{t(lang, 'admin_panel_hint')}",
        kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "adm:tma:nourl")
async def admin_tma_nourl(call: CallbackQuery):
    """Notify admin if WEB_APP_URL is not yet configured in .env."""
    if not _is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer(
        "⚠️ لطفاً ابتدا آدرس اینترنتی WEB_APP_URL را با پروتکل https در فایل .env تنظیم فرمایید.",
        show_alert=True,
    )


__all__ = [
    "router",
    "_is_admin",
    "_parse_int",
    "EDIT_FIELDS",
    "FIELD_TO_COLUMN",
    "ADMIN_EMOJI",
    "STRATEGY_KEYS",
    "ServiceRepository",
    "render_menu",
    "_render_admin_services",
    "_render_service_detail",
    "_cancel_kb",
    "admin_panel",
    "admin_services",
    "service_view_detail",
    "admin_cancel",
    "add_service_start",
    "create_name",
    "create_price",
    "create_duration",
    "create_traffic",
    "create_strategy_pick",
    "create_hwid",
    "create_squad",
    "create_description",
    "edit_service_pick",
    "edit_service_field",
    "edit_value_save",
    "toggle_service",
    "delete_service_confirm",
    "delete_service_do",
    "admin_tma_nourl",
]
