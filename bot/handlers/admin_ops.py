"""Admin panel: dashboard, sales report + refunds, top-up approvals,
broadcast, store settings (incl. maintenance mode), action log."""
import logging
import math
import re
import time
from datetime import datetime, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.models import Order, Wallet
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.order_repo import OrderRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.app_settings import (
    get_store_settings,
    is_maintenance,
    set_maintenance,
)
from bot.services.backup import create_database_backup
from bot.services.formatting import (
    country_flag,
    format_datetime,
    human_bytes,
)
from bot.services.menu import delete_message_silently, render_menu
from bot.common import SEPARATOR, fmt, is_admin, parse_int
from bot.services.remnawave import RemnawaveClient
from bot.services.topups import decide_topup
from bot.states.admin import (
    BroadcastStates,
    CouponManagementStates,
    OrderManagementStates,
    SettingsStates,
)

logger = logging.getLogger(__name__)
router = Router(name="admin_ops")

_is_admin = is_admin
_parse_int = parse_int

from bot.handlers.admin_settings import (
    SETTING_FIELDS,
    SETTING_DESCRIPTIONS,
)

# admin log actions -> locale keys for the label
LOG_ACTION_KEYS = {
    "balance_add": "log_balance_add",
    "balance_sub": "log_balance_sub",
    "refund": "log_refund",
    "topup_ok": "log_topup_ok",
    "topup_no": "log_topup_no",
    "setting": "log_setting",
    "maintenance": "log_maintenance",
    "broadcast": "log_broadcast",
}

BROADCAST_CONFIRM_KEY = "bcast:draft"

GB = 1024 ** 3



def _safe_int(value: str | int | None) -> int | None:
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return None


def _back_admin(lang: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1)
    return kb


# --------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------- #
@router.callback_query(F.data == "adm:dash")
async def dashboard(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    panel_users = await remnawave.get_all_panel_users() or []
    nodes = await remnawave.get_nodes() or []
    recap = await remnawave.get_system_recap() or {}

    total_users = len(panel_users)
    active_users = sum(1 for u in panel_users if str(u.get("status", "")).upper() == "ACTIVE")
    disabled_users = sum(1 for u in panel_users if str(u.get("status", "")).upper() == "DISABLED")
    limited_users = sum(1 for u in panel_users if str(u.get("status", "")).upper() == "LIMITED")
    expired_users = sum(1 for u in panel_users if str(u.get("status", "")).upper() == "EXPIRED")

    if isinstance(recap.get("users"), dict):
        ru = recap["users"]
        total_users = ru.get("total", total_users)
        active_users = ru.get("active", active_users)
        disabled_users = ru.get("disabled", disabled_users)
        limited_users = ru.get("limited", limited_users)
        expired_users = ru.get("expired", expired_users)

    total_nodes = len(nodes)
    online_nodes = sum(1 for n in nodes if n.get("isConnected") or str(n.get("status", "")).upper() == "CONNECTED")
    offline_nodes = total_nodes - online_nodes

    if isinstance(recap.get("nodes"), dict):
        rn = recap["nodes"]
        total_nodes = rn.get("total", total_nodes)
        online_nodes = rn.get("online", rn.get("connected", online_nodes))
        offline_nodes = total_nodes - online_nodes

    total_user_traffic = 0
    for u in panel_users:
        t_info = u.get("userTraffic") or {}
        val = t_info.get("usedTrafficBytes") or u.get("usedTrafficBytes") or 0
        try:
            total_user_traffic += int(val)
        except (ValueError, TypeError):
            pass

    total_node_traffic = 0
    for n in nodes:
        tb = (
            n.get("trafficUsedBytes")
            or n.get("todayTrafficBytes")
            or n.get("traffic")
            or (n.get("userTraffic") or {}).get("usedTrafficBytes")
            or 0
        )
        try:
            total_node_traffic += int(tb)
        except (ValueError, TypeError):
            pass

    rt = recap.get("traffic") if isinstance(recap.get("traffic"), dict) else {}
    traffic_total = rt.get("totalBytes") or rt.get("usedBytes") or max(total_user_traffic, total_node_traffic)
    download_bytes = rt.get("downloadBytes") or rt.get("down")
    upload_bytes = rt.get("uploadBytes") or rt.get("up")

    node_lines = []
    for n in nodes:
        name = escape(str(n.get("name") or "Node"))
        flag = country_flag(n.get("countryCode"))
        is_conn = n.get("isConnected")
        if is_conn is None:
            is_conn = str(n.get("status", "")).upper() == "CONNECTED"
        badge = "🟢" if is_conn else "🔴"
        tb = (
            n.get("trafficUsedBytes")
            or n.get("todayTrafficBytes")
            or n.get("traffic")
            or 0
        )
        try:
            val_tb = int(tb)
            t_str = f" ({human_bytes(val_tb)})" if val_tb > 0 else ""
        except (ValueError, TypeError):
            t_str = ""
        node_lines.append(f"   • {flag} {name} : {badge}{t_str}")

    version = recap.get("version") or recap.get("panelVersion") or recap.get("appVersion")
    if not version and isinstance(recap.get("system"), dict):
        version = recap["system"].get("version")

    if lang == "fa":
        lines = [
            "📊 <b>داشبورد پنل</b>",
            SEPARATOR,
            f"👥 <b>وضعیت کاربران ({total_users}) :</b>",
            f"   🟢 فعال : <b>{active_users}</b>",
            f"   🔴 غیرفعال : <b>{disabled_users}</b>",
            f"   🟡 محدود شده (اتمام حجم) : <b>{limited_users}</b>",
            f"   ⚪️ منقضی شده : <b>{expired_users}</b>",
            SEPARATOR,
            f"📡 <b>وضعیت نودها ({total_nodes}) :</b>",
            f"   🟢 آنلاین : <b>{online_nodes}</b>",
            f"   🔴 آفلاین : <b>{offline_nodes}</b>",
        ]
        if node_lines:
            lines.extend(node_lines[:8])
        lines.append(SEPARATOR)
        lines.append(f"📈 <b>مجموع مصرف ترافیک :</b> <b>{human_bytes(traffic_total)}</b>")
        if download_bytes and upload_bytes:
            lines.append(
                f"   • 📥 دانلود: {human_bytes(download_bytes)} | 📤 آپلود: {human_bytes(upload_bytes)}"
            )
        if version:
            v_clean = str(version).lstrip("v")
            lines.append(f"⚙️ <b>نسخه پنل :</b> v{v_clean}")
    else:
        lines = [
            "📊 <b>Panel Dashboard</b>",
            SEPARATOR,
            f"👥 <b>Users Overview ({total_users}) :</b>",
            f"   🟢 Active : <b>{active_users}</b>",
            f"   🔴 Disabled : <b>{disabled_users}</b>",
            f"   🟡 Limited : <b>{limited_users}</b>",
            f"   ⚪️ Expired : <b>{expired_users}</b>",
            SEPARATOR,
            f"📡 <b>Nodes Overview ({total_nodes}) :</b>",
            f"   🟢 Online : <b>{online_nodes}</b>",
            f"   🔴 Offline : <b>{offline_nodes}</b>",
        ]
        if node_lines:
            lines.extend(node_lines[:8])
        lines.append(SEPARATOR)
        lines.append(f"📈 <b>Total Traffic :</b> <b>{human_bytes(traffic_total)}</b>")
        if download_bytes and upload_bytes:
            lines.append(
                f"   • 📥 Down: {human_bytes(download_bytes)} | 📤 Up: {human_bytes(upload_bytes)}"
            )
        if version:
            v_clean = str(version).lstrip("v")
            lines.append(f"⚙️ <b>Panel Version :</b> v{v_clean}")

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_refresh"), callback_data="adm:dash")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()



# --------------------------------------------------------------------- #
# Sales report + refunds + filters + search - delegated to bot.handlers.admin_orders
# --------------------------------------------------------------------- #
from bot.handlers.admin_orders import (
    ORDERS_PER_PAGE,
    PLATFORM_EMOJI,
    _safe_int,
    _revert_panel_subscription,
    _render_order_detail,
    _render_orders_list,
    admin_noop,
    _render_reports_hub,
    trigger_admin_report_handler,
    _render_hwid_inspector,
    _render_srh_inspector,
    _render_sessions_explorer,
    reports_hub_entry,
    report_hwid_inspector_handler,
    report_srh_inspector_handler,
    report_sessions_explorer_handler,
    orders_search_prompt,
    orders_clear_search,
    orders_filtered_view,
    orders_search_submit,
    order_view_or_refund,
    router as _admin_orders_router,
)

router.include_router(_admin_orders_router)

# --------------------------------------------------------------------- #
# Top-up approvals - delegated to bot.handlers.admin_topups
# --------------------------------------------------------------------- #
from bot.handlers.admin_topups import (
    _render_topups,
    topups_list,
    topup_decide_from_panel,
    router as _admin_topups_router,
)

router.include_router(_admin_topups_router)


# --------------------------------------------------------------------- #
# Broadcast - delegated to bot.handlers.admin_broadcast
# --------------------------------------------------------------------- #
from bot.handlers.admin_broadcast import (
    BROADCAST_CONFIRM_KEY,
    _resolve_broadcast_recipients,
    broadcast_audience_select,
    broadcast_target_picked,
    broadcast_text,
    broadcast_send,
    router as _admin_broadcast_router,
)

router.include_router(_admin_broadcast_router)


# --------------------------------------------------------------------- #
# Action log
# --------------------------------------------------------------------- #
@router.callback_query(F.data == "adm:logs")
async def admin_logs(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    entries = await AdminLogRepository(session).recent(15)
    lines = [t(lang, "logs_title"), SEPARATOR]
    if not entries:
        lines.append(t(lang, "logs_empty"))
    else:
        for entry in entries:
            label = t(lang, LOG_ACTION_KEYS.get(entry.action, "logs_title"))
            when = format_datetime(entry.created_at, lang)
            detail = f" — {entry.detail}" if entry.detail else ""
            lines.append(f"• {label}{detail}\n  <code>{entry.admin_id}</code> · {when}")

    await render_menu(bot, user, user_repo, "\n".join(lines), _back_admin(lang).as_markup())
    await call.answer()


# --------------------------------------------------------------------- #
# Store settings (+ maintenance toggle) - delegated to bot.handlers.admin_settings
# --------------------------------------------------------------------- #
from bot.handlers.admin_settings import (
    _get_admin_group_title,
    _render_settings,
    _render_topics_settings,
    _render_crypto_settings,
    crypto_settings_view,
    toggle_crypto_enabled,
    crypto_nobitex_now,
    apply_nobitex_rate,
    store_settings_view,
    topics_settings_view,
    _render_trial_settings,
    _render_referral_settings,
    trial_settings_view,
    referral_settings_view,
    trial_ref_settings_view,
    setting_toggle_boolean,
    maintenance_toggle,
    _parse_remind_days_set,
    _render_remind_days_picker,
    remind_days_picker_entry,
    remind_days_toggle,
    _render_grace_days_picker,
    grace_days_picker_entry,
    grace_days_set,
    settings_edit_start,
    settings_set_squad,
    settings_value_save,
    router as _admin_settings_router,
)

router.include_router(_admin_settings_router)


# --------------------------------------------------------------------- #
# Node / Server Status Monitor - delegated to bot.handlers.admin_nodes
# --------------------------------------------------------------------- #
from bot.handlers.admin_nodes import (
    COUNTRY_FLAGS_MAP,
    _extract_versions,
    _extract_core_version,
    _format_node_title,
    admin_nodes_monitor,
    router as _admin_nodes_router,
)

router.include_router(_admin_nodes_router)


# --------------------------------------------------------------------- #
# Automatic / Manual Database Backup
# --------------------------------------------------------------------- #
@router.callback_query(F.data == "adm:backup")
async def admin_database_backup(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    await call.answer("در حال تهیه نسخه پشتیبان..." if lang == "fa" else "Creating backup...", show_alert=False)

    try:
        backup_path = await create_database_backup(session)
        doc = FSInputFile(backup_path, filename=backup_path.name)
        await bot.send_document(
            chat_id=call.from_user.id,
            document=doc,
            caption=t(lang, "backup_success"),
        )
        await AdminLogRepository(session).log(
            call.from_user.id, "setting", detail=f"database_backup={backup_path.name}"
        )
        await call.answer(t(lang, "backup_success"), show_alert=True)
    except Exception as e:
        logger.exception("failed to create database backup")
        await call.answer(f"Error: {e}", show_alert=True)


# --------------------------------------------------------------------- #
# Coupon Management (Admin) - delegated to bot.handlers.admin.coupons
# --------------------------------------------------------------------- #
from bot.handlers.admin_coupons import (
    router as _coupons_router,
    admin_coupons_list,
    admin_coupon_detail,
    admin_coupon_toggle,
    admin_coupon_delete,
    admin_coupon_add_start,
    admin_coupon_add_code,
    admin_coupon_add_discount,
    admin_coupon_add_max_uses,
)

router.include_router(_coupons_router)
