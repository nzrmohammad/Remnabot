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
from bot.services.remnawave import RemnawaveClient
from bot.services.topups import decide_topup, fmt
from bot.states.admin import (
    BroadcastStates,
    CouponManagementStates,
    OrderManagementStates,
    SettingsStates,
)

logger = logging.getLogger(__name__)
router = Router(name="admin_ops")

SEPARATOR = "─" * 18

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# settings field key -> (text key, is_numeric)
SETTING_FIELDS = {
    "card_number": ("settings_card", False),
    "card_holder": ("settings_holder", False),
    "topup_min_amount": ("settings_min", True),
    "default_squad_uuid": ("settings_squad", False),
    "expiry_grace_days": ("settings_grace_days", True),
    "expiry_remind_days": ("settings_remind_days", False),
    "topic_topups": ("settings_topic_topups", True),
    "topic_orders": ("settings_topic_orders", True),
    "topic_support": ("settings_topic_support", True),
    "topic_alerts": ("settings_topic_alerts", True),
    "support_contact": ("settings_support_contact", False),
    "trial_enabled": ("settings_trial_enabled", True),
    "trial_traffic_gb": ("settings_trial_traffic", True),
    "trial_duration_days": ("settings_trial_duration", True),
    "referral_enabled": ("settings_referral_enabled", True),
    "referral_reward_gb": ("settings_referral_reward", True),
    "topic_crypto": ("settings_topic_crypto", True),
    "ton_wallet_address": ("settings_ton_wallet", False),
    "ton_rate_toman": ("settings_ton_rate", True),
    "usdt_rate_toman": ("settings_usdt_rate", True),
}

SETTING_DESCRIPTIONS = {
    "fa": {
        "card_number": "شماره کارت بانکی جهت دریافت مبالغ شارژ کیف پول توسط کاربران.",
        "card_holder": "نام و نام خانوادگی صاحب کارت بانکی جهت نمایش به کاربران در زمان شارژ.",
        "topup_min_amount": "حداقل مبلغ مجاز برای هر بار شارژ کیف پول به تومان.",
        "support_contact": "آیدی یا لینک پشتیبانی که در بخش ارتباط با پشتیبانی نمایش داده می‌شود.",
        "expiry_grace_days": "تعداد روزهایی که پس از پایان اشتراک، اکانت در پنل حفظ می‌شود تا کاربر فرصت تمدید داشته باشد.",
        "expiry_remind_days": "روزهای مانده به انقضا (مانند 3,1) که پیام هشدار تمدید برای کاربر ارسال می‌شود.",
        "topic_topups": "شناسه تاپیک تایید شارژها در سوپرگروه مدیریت تلگرام جهت ارسال فیش‌های کاربران.",
        "topic_orders": "شناسه تاپیک سفارشات در سوپرگروه مدیریت تلگرام جهت ارسال لاگ خرید بسته‌ها.",
        "topic_support": "شناسه تاپیک پشتیبانی در سوپرگروه مدیریت تلگرام جهت فوروارد پیام‌های کاربران.",
        "topic_alerts": "شناسه تاپیک هشدارهای سیستم و ارسال خودکار فایل پشتیبان دیتابیس در سوپرگروه مدیریت.",
        "topic_crypto": "شناسه تاپیک کریپتو در سوپرگروه مدیریت جهت ارسال استعلام نرخ نوبیتکس و لاگ پرداخت‌های تون.",
        "ton_wallet_address": "آدرس عمومی کیف پول تون (مانند UQ... یا EQ...) جهت دریافت وجه از کاربران.",
        "ton_rate_toman": "نرخ تبدیل هر یک تون به تومان جهت صدور فاکتور شارژ کیف پول.",
        "usdt_rate_toman": "نرخ هر تتر (USDT) به تومان جهت تبدیل قیمت دلاری تون در صرافی‌های جهانی.",
        "trial_enabled": "فعال (1) یا غیرفعال (0) بودن امکان دریافت اکانت تست رایگان توسط کاربران جدید.",
        "trial_traffic_gb": "حجم ترافیک اختصاص داده شده به اکانت تست رایگان به گیگابایت.",
        "trial_duration_days": "مدت زمان اعتبار اکانت تست رایگان به روز.",
        "referral_enabled": "فعال (1) یا غیرفعال (0) بودن سیستم دعوت از دوستان و دریافت ترافیک رایگان.",
        "referral_reward_gb": "حجم ترافیک هدیه (GB) که با هر دعوت موفق به کاربر معرف اهدا می‌شود.",
    },
    "en": {
        "card_number": "Bank card number for wallet top-ups.",
        "card_holder": "Bank card holder name shown to users.",
        "topup_min_amount": "Minimum top-up amount in Toman.",
        "support_contact": "Support contact username or link.",
        "expiry_grace_days": "Days an account is preserved in panel after expiry before deletion.",
        "expiry_remind_days": "Days before expiry (e.g. 3,1) to send renewal reminders.",
        "topic_topups": "Telegram topic ID for top-up receipts in admin supergroup.",
        "topic_orders": "Telegram topic ID for order purchase notifications.",
        "topic_support": "Telegram topic ID for support message forwarding.",
        "topic_alerts": "Telegram topic ID for system alerts and auto database backups.",
        "topic_crypto": "Telegram topic ID for crypto rates and TON payment logs.",
        "ton_wallet_address": "Public TON wallet address for receiving user payments.",
        "ton_rate_toman": "Conversion rate of 1 TON in Toman for invoices.",
        "usdt_rate_toman": "Benchmark USDT rate in Toman for global crypto price conversion.",
        "trial_enabled": "Enable (1) or disable (0) free trial accounts.",
        "trial_traffic_gb": "Free trial traffic volume in GB.",
        "trial_duration_days": "Free trial duration in days.",
        "referral_enabled": "Enable (1) or disable (0) referral system.",
        "referral_reward_gb": "Traffic reward in GB given to referrer per invite.",
    },
}

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


async def _revert_panel_subscription(remnawave, order) -> None:
    """Roll back what the purchase granted: subtract duration/traffic.

    Best-effort: if the panel is down or the account is gone, the wallet
    refund already happened, so we only log.
    """
    from datetime import datetime, timezone

    accounts = await remnawave.get_users_by_telegram_id(order.telegram_id)
    if not accounts:
        return
    acc = next(
        (a for a in accounts if str(a.get("id")) == str(order.panel_user_id)), None
    )
    if acc is None:
        return
    try:
        current_limit = int(acc.get("trafficLimitBytes") or 0)
    except (ValueError, TypeError):
        current_limit = 0
    new_limit = current_limit
    if (order.traffic_gb or 0) > 0 and current_limit > 0:
        new_limit = max(0, current_limit - int(order.traffic_gb) * GB)
    # Roll back expiry by the purchased duration.
    expire_iso = acc.get("expireAt")
    new_expire_iso = expire_iso
    if (order.duration_days or 0) > 0 and expire_iso:
        try:
            from datetime import timedelta
            cur = datetime.fromisoformat(str(expire_iso).replace("Z", "+00:00"))
            new_expire_iso = (cur - timedelta(days=int(order.duration_days))).astimezone(
                timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError):
            new_expire_iso = expire_iso
    await remnawave.update_user_subscription(
        int(order.panel_user_id), str(new_expire_iso), int(new_limit)
    )


def _is_admin(user_id: int) -> bool:
    return user_id in get_settings().ADMIN_IDS


def _parse_int(text: str) -> int | None:
    cleaned = text.translate(_DIGIT_MAP).replace(",", "").replace("،", "").strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


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
# Sales report + refunds + filters + search
# --------------------------------------------------------------------- #
ORDERS_PER_PAGE = 8


async def _render_order_detail(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    order_id: int,
    toast: str | None = None,
    status: str = "all",
    page: int = 0,
) -> None:
    lang = user.language or "fa"
    order = await OrderRepository(session).get(order_id)
    if order is None:
        await render_menu(
            bot,
            user,
            user_repo,
            t(lang, "acc_error"),
            _back_admin(lang).as_markup(),
        )
        return

    status_key = "ord_status_paid" if order.status == "paid" else "ord_status_refunded"
    lines = [
        f"🧾 <b>{t(lang, 'ord_title')} #{order.id}</b>",
        SEPARATOR,
        f"📦 {escape(order.service_name)}",
        f"💰 {fmt(order.amount)} {t(lang, 'svc_currency')}",
        f"📌 {t(lang, 'ord_status')} : <b>{t(lang, status_key)}</b>",
        f"👤 <code>{order.telegram_id}</code>",
        f"🔑 <code>{escape(str(order.panel_username or '—'))}</code>",
        f"🕒 {format_datetime(order.created_at, lang)}",
    ]
    if order.subscription_url:
        lines.append(f"\n🔗 <code>{escape(order.subscription_url)}</code>")
    if toast:
        lines.insert(2, toast)

    kb = InlineKeyboardBuilder()
    if order.status == "paid":
        kb.button(
            text=t(lang, "btn_refund"),
            callback_data=f"adm:ord:ref:{order.id}:{status}:{page}",
        )
        kb.adjust(1)
    kb.button(text=t(lang, "btn_back"), callback_data=f"adm:orders:{status}:{page}")
    kb.adjust(1)
    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


async def _render_orders_list(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    status: str = "all",
    page: int = 0,
    query: str | None = None,
) -> None:
    lang = user.language or "fa"
    order_repo = OrderRepository(session)
    total_rev = await order_repo.total_revenue()
    total_cnt = await order_repo.count()
    counts = await order_repo.status_counts(query=query)
    matching_count = counts.get(status, 0) if status != "all" else counts.get("all", 0)
    total_pages = max(1, (matching_count + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    orders = await order_repo.list_filtered(
        status=status, query=query, offset=page * ORDERS_PER_PAGE, limit=ORDERS_PER_PAGE
    )

    filter_title_map = {
        "all": "همه" if lang == "fa" else "All",
        "paid": "موفق" if lang == "fa" else "Paid",
        "pending": "در انتظار" if lang == "fa" else "Pending",
        "failed": "ناموفق" if lang == "fa" else "Failed",
        "refunded": "مرجوعی" if lang == "fa" else "Refunded",
    }
    curr_filter_title = filter_title_map.get(status, status)

    lines = [
        t(lang, "sales_title"),
        SEPARATOR,
        f"{t(lang, 'sales_total')} : <b>{fmt(total_rev)}</b> {t(lang, 'svc_currency')}",
        f"{t(lang, 'sales_count')} : <b>{total_cnt}</b>",
        SEPARATOR,
    ]
    if query:
        lines.append(t(lang, "ord_search_active", query=escape(query)))
    lines.append(t(lang, "ord_active_filter", filter=curr_filter_title, count=matching_count))
    if matching_count > 0:
        lines.append(t(lang, "ord_page_info", page=page + 1, pages=total_pages))
    lines.append(SEPARATOR)

    if not orders:
        if query or status != "all":
            lines.append(t(lang, "ord_empty_filtered"))
        else:
            lines.append(t(lang, "sales_empty"))

    kb = InlineKeyboardBuilder()

    def _fmt_filter_btn(st: str) -> str:
        c = counts.get(st, 0)
        label = t(lang, f"ord_filter_{st}", n=c)
        return f"• {label} •" if st == status else label

    if lang == "fa":
        # Row 1 (RTL: pending, paid, all)
        kb.button(text=_fmt_filter_btn("pending"), callback_data="adm:orders:pending:0")
        kb.button(text=_fmt_filter_btn("paid"), callback_data="adm:orders:paid:0")
        kb.button(text=_fmt_filter_btn("all"), callback_data="adm:orders:all:0")
        # Row 2 (RTL: refunded, failed)
        kb.button(text=_fmt_filter_btn("refunded"), callback_data="adm:orders:refunded:0")
        kb.button(text=_fmt_filter_btn("failed"), callback_data="adm:orders:failed:0")
    else:
        # LTR
        kb.button(text=_fmt_filter_btn("all"), callback_data="adm:orders:all:0")
        kb.button(text=_fmt_filter_btn("paid"), callback_data="adm:orders:paid:0")
        kb.button(text=_fmt_filter_btn("pending"), callback_data="adm:orders:pending:0")
        kb.button(text=_fmt_filter_btn("failed"), callback_data="adm:orders:failed:0")
        kb.button(text=_fmt_filter_btn("refunded"), callback_data="adm:orders:refunded:0")
    kb.adjust(3, 2)

    # Search Row
    if query:
        if lang == "fa":
            kb.button(text=t(lang, "btn_order_clear_search"), callback_data=f"adm:orders:clear:{status}")
            kb.button(text=t(lang, "btn_order_search"), callback_data="adm:orders:search")
        else:
            kb.button(text=t(lang, "btn_order_search"), callback_data="adm:orders:search")
            kb.button(text=t(lang, "btn_order_clear_search"), callback_data=f"adm:orders:clear:{status}")
        kb.adjust(2)
    else:
        kb.button(text=t(lang, "btn_order_search"), callback_data="adm:orders:search")
        kb.adjust(1)

    # Order item buttons
    for order in orders:
        badge = {
            "paid": "✅",
            "pending": "⏳",
            "failed": "❌",
            "refunded": "🔄",
        }.get(order.status, "📦")
        btn_title = f"{badge} #{order.id} — {order.service_name} — {fmt(order.amount)}"
        kb.button(
            text=btn_title,
            callback_data=f"adm:ord:{order.id}:{status}:{page}",
        )
        kb.adjust(1)

    # Pagination controls
    if total_pages > 1:
        if lang == "fa":
            if page < total_pages - 1:
                kb.button(text="بعدی ➡️", callback_data=f"adm:orders:{status}:{page + 1}")
            else:
                kb.button(text=" ", callback_data="adm:noop")

            kb.button(text=f"📄 {page + 1}/{total_pages}", callback_data="adm:noop")

            if page > 0:
                kb.button(text="⬅️ قبلی", callback_data=f"adm:orders:{status}:{page - 1}")
            else:
                kb.button(text=" ", callback_data="adm:noop")
        else:
            if page > 0:
                kb.button(text="⬅️ Prev", callback_data=f"adm:orders:{status}:{page - 1}")
            else:
                kb.button(text=" ", callback_data="adm:noop")

            kb.button(text=f"📄 {page + 1}/{total_pages}", callback_data="adm:noop")

            if page < total_pages - 1:
                kb.button(text="Next ➡️", callback_data=f"adm:orders:{status}:{page + 1}")
            else:
                kb.button(text=" ", callback_data="adm:noop")
        kb.adjust(3)

    kb.button(text="🔙 بازگشت به گزارشات" if lang == "fa" else "🔙 Back to Reports", callback_data="adm:sales")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "adm:noop")
async def admin_noop(call: CallbackQuery):
    await call.answer()


PLATFORM_EMOJI = {
    "android": "🤖",
    "ios": "🍏",
    "windows": "🖥",
    "macos": "💻",
    "linux": "🐧",
}


async def _render_reports_hub(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    remnawave: RemnawaveClient,
) -> None:
    lang = user.language or "fa"

    # Panel users & Nodes count
    panel_users = await remnawave.get_all_panel_users() or []
    total_users = len(panel_users)
    active_users = sum(1 for u in panel_users if str(u.get("status", "")).upper() == "ACTIVE")

    nodes = await remnawave.get_nodes() or []
    online_nodes = sum(1 for n in nodes if n.get("isConnected") or str(n.get("status", "")).upper() == "CONNECTED")

    lines = [
        f"{t(lang, 'reports_hub_title')}\n{SEPARATOR}",
        f"👥 <b>کاربران پنل:</b> {active_users} فعال / {total_users} کل"
        if lang == "fa"
        else f"👥 <b>Panel Users:</b> {active_users} active / {total_users} total",
        f"📡 <b>وضعیت نودها:</b> {online_nodes} متصل از {len(nodes)} نود"
        if lang == "fa"
        else f"📡 <b>Nodes Status:</b> {online_nodes} connected of {len(nodes)}",
        "",
        "جهت بررسی دقیق هر بخش، گزینه مورد نظر را انتخاب کنید:"
        if lang == "fa"
        else "Select a section below for detailed reports & diagnostics:",
    ]

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        # Persian RTL: first added button appears on LEFT, second on RIGHT
        # Row 1: Left = SRH Inspector, Right = HWID Inspector
        kb.button(text="🌐 SRH Inspector", callback_data="adm:rep:srh")
        kb.button(text="🔍 HWID Inspector", callback_data="adm:rep:hwid")
        # Row 2: Sessions Explorer (Full width)
        kb.button(text="⚡ Sessions Explorer", callback_data="adm:rep:sessions:0")
    else:
        kb.button(text="🔍 HWID Inspector", callback_data="adm:rep:hwid")
        kb.button(text="🌐 SRH Inspector", callback_data="adm:rep:srh")
        kb.button(text="⚡ Sessions Explorer", callback_data="adm:rep:sessions:0")

    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(2, 1, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


async def _render_hwid_inspector(
    bot: Bot, user, user_repo: UserRepository, remnawave: RemnawaveClient
) -> None:
    lang = user.language or "fa"
    stats_data = await remnawave.get_hwid_stats() or {}

    stats = stats_data.get("stats") or {}
    total_unique = stats.get("totalUniqueDevices") or stats_data.get("totalUniqueDevices") or 0
    total_hwid = stats.get("totalHwidDevices") or stats_data.get("totalHwidDevices") or 0
    avg_per_user = stats.get("averageHwidDevicesPerUser") or stats_data.get("averageHwidDevicesPerUser") or 0
    by_platform = stats_data.get("byPlatform") or []

    # If byPlatform not in stats_data, fallback to querying devices
    if not by_platform:
        devices = await remnawave.get_all_hwid_devices(size=500) or []
        if devices:
            total_hwid = total_hwid or len(devices)
            plat_map: dict[str, list] = {}
            for d in devices:
                p = d.get("platform") or "Other"
                plat_map.setdefault(p, []).append(d)
            by_platform = []
            for p, d_list in plat_map.items():
                app_map: dict[str, int] = {}
                for d in d_list:
                    app = d.get("deviceModel") or d.get("userAgent") or "App"
                    app_map[app] = app_map.get(app, 0) + 1
                by_platform.append({
                    "platform": p,
                    "count": len(d_list),
                    "byApp": [{"app": a, "count": c} for a, c in app_map.items()],
                })

    if isinstance(avg_per_user, (int, float)):
        avg_str = f"{round(avg_per_user)}" if avg_per_user == round(avg_per_user) else f"{round(avg_per_user)} ({avg_per_user:.2f})"
    else:
        avg_str = str(avg_per_user)

    lines = [
        "🔍 <b>HWID Inspector (آمار دستگاه‌ها)</b>" if lang == "fa" else "🔍 <b>HWID Inspector</b>",
        SEPARATOR,
        f"📱 <b>Total unique devices:</b> {total_unique}",
        f"💻 <b>Total HWID devices:</b> {total_hwid}",
        f"⚖️ <b>Avg devices per user:</b> {avg_str}",
        "",
        "📊 <b>Platform distribution:</b>",
        "",
    ]

    if by_platform:
        for p in by_platform:
            plat_name = p.get("platform") or "Other"
            plat_count = p.get("count") or 0
            pct = (plat_count / total_hwid * 100) if total_hwid else 0

            p_lower = str(plat_name).lower()
            if "android" in p_lower:
                emoji = "🤖"
            elif "ios" in p_lower or "iphone" in p_lower or "ipad" in p_lower or "apple" in p_lower:
                emoji = "🍏"
            elif "windows" in p_lower:
                emoji = "🪟"
            elif "mac" in p_lower:
                emoji = "💻"
            elif "linux" in p_lower:
                emoji = "🐧"
            else:
                emoji = "📱"

            lines.append(f"{emoji} <b>{escape(str(plat_name))}</b> : {plat_count} ({pct:.1f}%)")
            by_app = p.get("byApp") or []
            if by_app:
                for a in by_app:
                    app_name = a.get("app") or "Unknown"
                    app_count = a.get("count") or 0
                    lines.append(f"  ▫️ {escape(str(app_name))}: {app_count}")
            lines.append("")
    else:
        lines.append("<i>هیچ اطلاعاتی از دستگاه‌ها یافت نشد.</i>" if lang == "fa" else "<i>No device data found.</i>")

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 بروزرسانی", callback_data="adm:rep:hwid")
    kb.button(text="🔙 بازگشت به گزارشات", callback_data="adm:sales")
    kb.adjust(1, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


async def _render_srh_inspector(
    bot: Bot, user, user_repo: UserRepository, remnawave: RemnawaveClient
) -> None:
    lang = user.language or "fa"
    srh_data = await remnawave.get_srh_stats() or {}

    by_parsed_app = srh_data.get("byParsedApp") or []
    hourly_stats = srh_data.get("hourlyRequestStats") or []

    total_app_reqs = sum(item.get("count", 0) for item in by_parsed_app)

    lines = [
        "🌐 <b>SRH Inspector (درخواست‌های سابسکریپشن)</b>" if lang == "fa" else "🌐 <b>SRH Inspector</b>",
        SEPARATOR,
        f"📥 <b>مجموع درخواست‌های ثبت‌شده:</b> {fmt(total_app_reqs)}",
        "",
        "📱 <b>توزیع نرم‌افزارها:</b>" if lang == "fa" else "📱 <b>App Distribution:</b>",
    ]

    if by_parsed_app:
        for item in by_parsed_app:
            app_name = item.get("app") or "Unknown"
            count = item.get("count") or 0
            pct = (count / total_app_reqs * 100) if total_app_reqs else 0
            lines.append(f"  ▫️ <b>{escape(str(app_name))}</b>: {count} ({pct:.1f}%)")
    else:
        lines.append("  <i>آماری از توزیع کلاینت‌ها یافت نشد.</i>" if lang == "fa" else "  <i>No app distribution data.</i>")

    lines.append("")

    if hourly_stats:
        lines.append("⏱ <b>آمار ساعتی درخواست‌ها:</b>" if lang == "fa" else "⏱ <b>Hourly Request Statistics:</b>")
        total_24h = sum(h.get("requestCount", 0) for h in hourly_stats)
        peak_entry = max(hourly_stats, key=lambda x: x.get("requestCount", 0))
        peak_cnt = peak_entry.get("requestCount", 0)

        lines.append(
            f"📈 <b>مجموع کل ثبت‌شده:</b> {total_24h} درخواست"
            if lang == "fa"
            else f"📈 <b>Total 24h Requests:</b> {total_24h}"
        )
        lines.append(
            f"⚡ <b>اوج ترافیک ساعتی (Peak):</b> {peak_cnt} درخواست"
            if lang == "fa"
            else f"⚡ <b>Peak Hourly Traffic:</b> {peak_cnt} requests"
        )
        lines.append("")
        lines.append("📊 <b>ساعات اخیر:</b>" if lang == "fa" else "📊 <b>Recent Hours:</b>")
        for h in hourly_stats[-6:]:
            dt_raw = str(h.get("dateTime", ""))
            hour_str = dt_raw[11:16] if len(dt_raw) >= 16 else dt_raw
            cnt = h.get("requestCount", 0)
            lines.append(
                f"  • {hour_str} : {cnt} درخواست"
                if lang == "fa"
                else f"  • {hour_str} : {cnt} requests"
            )

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 بروزرسانی", callback_data="adm:rep:srh")
    kb.button(text="🔙 بازگشت به گزارشات", callback_data="adm:sales")
    kb.adjust(1, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


async def _render_sessions_explorer(
    bot: Bot,
    user,
    user_repo: UserRepository,
    remnawave: RemnawaveClient,
    page: int = 0,
) -> None:
    lang = user.language or "fa"
    data = await remnawave.get_live_sessions_explorer()

    total_online = data["total_users_online"]
    total_conns = data["total_connections"]
    multi_users = data["multi_ip_users"]
    nodes_scanned = data["nodes_scanned"]
    total_nodes = data["total_nodes"]

    lines = [
        "⚡ <b>Sessions Explorer</b>",
        SEPARATOR,
        f"🟢 <b>کاربران آنلاین:</b> <code>{total_online}</code>"
        if lang == "fa"
        else f"🟢 <b>Online Users:</b> <code>{total_online}</code>",
        f"🌐 <b>کل اتصالات فعال:</b> <code>{total_conns}</code>"
        if lang == "fa"
        else f"🌐 <b>Total Active Connections:</b> <code>{total_conns}</code>",
        f"⚠️ <b>کاربران با چند IP:</b> <code>{len(multi_users)}</code>"
        if lang == "fa"
        else f"⚠️ <b>Multi-IP Users:</b> <code>{len(multi_users)}</code>",
        f"📡 <b>نودهای اسکن‌شده:</b> <code>{nodes_scanned}</code> از <code>{total_nodes}</code> نود"
        if lang == "fa"
        else f"📡 <b>Nodes Scanned:</b> <code>{nodes_scanned}</code> of <code>{total_nodes}</code>",
        "",
    ]

    PER_PAGE = 5
    total_pages = max(1, math.ceil(len(multi_users) / PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    current_batch = multi_users[page * PER_PAGE : (page + 1) * PER_PAGE]

    if current_batch:
        lines.append(
            f"📋 <b>کاربران متصل با بیش از یک IP (صفحه {page + 1} از {total_pages}):</b>"
            if lang == "fa"
            else f"📋 <b>Multi-IP Users List (Page {page + 1}/{total_pages}):</b>"
        )
        lines.append("")
        for idx, u in enumerate(current_batch, start=page * PER_PAGE + 1):
            uname = escape(str(u["username"]))
            ip_cnt = len(u["uniqueIps"])
            lines.append(f" {idx}) 👤 <b>{uname}</b> — <code>{ip_cnt} IP</code>")
            for nc in u["nodeConnections"]:
                flag = country_flag(nc.get("countryCode"))
                n_name = escape(str(nc.get("nodeName") or "Node"))
                for ip in nc.get("ips", []):
                    lines.append(f"     ▫️ {flag} {n_name} : <code>{escape(str(ip))}</code>")
            lines.append("")
    else:
        lines.append(
            "✅ <i>در حال حاضر هیچ کاربری با بیش از یک IP متصل نیست (تمامی اتصالات تک-IP هستند).</i>"
            if lang == "fa"
            else "✅ <i>No multi-IP users detected (all users have a single IP).</i>"
        )

    kb = InlineKeyboardBuilder()
    nav_row = []
    if page > 0:
        nav_row.append(("⬅️ قبلی", f"adm:rep:sessions:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(("بعدی ➡️", f"adm:rep:sessions:{page + 1}"))

    if nav_row:
        if lang == "fa" and len(nav_row) == 2:
            kb.button(text=nav_row[0][0], callback_data=nav_row[0][1])  # Left: قبلی
            kb.button(text=nav_row[1][0], callback_data=nav_row[1][1])  # Right: بعدی
            kb.adjust(2)
        else:
            for text, cb in nav_row:
                kb.button(text=text, callback_data=cb)
            kb.adjust(len(nav_row))

    kb.button(text="🔄 بروزرسانی", callback_data=f"adm:rep:sessions:{page}")
    kb.button(text="🔙 بازگشت به گزارشات", callback_data="adm:sales")
    kb.adjust(len(nav_row) if nav_row else 1, 1, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())



@router.callback_query(F.data == "adm:sales")
async def reports_hub_entry(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await state.clear()
    await _render_reports_hub(bot, user, user_repo, session, remnawave)
    await call.answer()


@router.callback_query(F.data == "adm:rep:hwid")
async def report_hwid_inspector_handler(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_hwid_inspector(bot, user, user_repo, remnawave)
    await call.answer()


@router.callback_query(F.data == "adm:rep:srh")
async def report_srh_inspector_handler(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_srh_inspector(bot, user, user_repo, remnawave)
    await call.answer()


@router.callback_query(F.data.startswith("adm:rep:sessions"))
async def report_sessions_explorer_handler(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    page = 0
    parts = call.data.split(":")
    if len(parts) >= 4 and parts[3].isdigit():
        page = int(parts[3])
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_sessions_explorer(bot, user, user_repo, remnawave, page=page)
    await call.answer()


@router.callback_query(F.data == "adm:orders:search")
async def orders_search_prompt(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    await state.set_state(OrderManagementStates.waiting_search)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:orders:all:0")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, t(lang, "ord_search_prompt"), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("adm:orders:clear:"))
async def orders_clear_search(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    status = call.data.rsplit(":", 1)[1]
    await state.update_data(order_search_query=None)
    await _render_orders_list(bot, user, user_repo, session, status=status, page=0, query=None)
    await call.answer()


@router.callback_query(F.data.startswith("adm:orders:"))
async def orders_filtered_view(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)

    parts = call.data.split(":")
    status = parts[2] if len(parts) > 2 else "all"
    page = _safe_int(parts[3]) if len(parts) > 3 else 0
    if page is None:
        page = 0

    data = await state.get_data()
    query = data.get("order_search_query")
    await _render_orders_list(bot, user, user_repo, session, status=status, page=page, query=query)
    await call.answer()


@router.message(OrderManagementStates.waiting_search)
async def orders_search_submit(
    message: Message,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    if not _is_admin(message.from_user.id):
        return
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    query = (message.text or "").strip()
    await delete_message_silently(bot, message.chat.id, message.message_id)

    if not query:
        return

    await state.update_data(order_search_query=query)
    await state.set_state(None)
    await _render_orders_list(bot, user, user_repo, session, status="all", page=0, query=query)


@router.callback_query(F.data.startswith("adm:ord:"))
async def order_view_or_refund(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    remnawave: RemnawaveClient | None = None,
):
    """Dispatches: adm:ord:{id} | adm:ord:ref:{id} | adm:ord:refyes:{id}."""
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    parts = call.data.split(":")
    if len(parts) >= 3 and parts[2] in ("ref", "refyes"):
        action = parts[2]
        order_id = _safe_int(parts[3])
        status = parts[4] if len(parts) > 4 else "all"
        page = _safe_int(parts[5]) if len(parts) > 5 else 0
    else:
        action = "view"
        order_id = _safe_int(parts[2])
        status = parts[3] if len(parts) > 3 else "all"
        page = _safe_int(parts[4]) if len(parts) > 4 else 0

    if order_id is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if page is None:
        page = 0

    order_repo = OrderRepository(session)
    order = await order_repo.get(order_id)
    if order is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    if action == "refyes":
        # Atomic claim first: concurrent clicks can't double-refund.
        claimed = await order_repo.claim_refund(order_id)
        if claimed is None:
            await call.answer(t("fa", "acc_error"), show_alert=True)
            return
        order = claimed
        new_balance = await WalletRepository(session).add_balance_atomic(
            order.telegram_id, order.amount
        )
        # Revert the panel subscription: roll back what the purchase added.
        if order.panel_user_id is not None and remnawave is not None:
            try:
                await _revert_panel_subscription(remnawave, order)
            except Exception:
                pass
        await AdminLogRepository(session).log(
            call.from_user.id,
            "refund",
            detail=f"#{order.id} user={order.telegram_id} amount={order.amount}",
        )
        target = await UserRepository(session).get_by_telegram_id(order.telegram_id)
        user_lang = (target.language if target else None) or "fa"
        try:
            await bot.send_message(
                order.telegram_id,
                t(
                    user_lang,
                    "refund_notice_user",
                    id=order.id,
                    amount=fmt(order.amount),
                ),
            )
        except Exception:
            pass
        await _render_order_detail(
            bot,
            user,
            user_repo,
            session,
            order_id,
            toast=t(
                lang,
                "ord_refunded",
                amount=fmt(order.amount),
                balance=fmt(new_balance),
            ),
            status=status,
            page=page,
        )
        await call.answer()
        return

    if action == "ref":
        kb = InlineKeyboardBuilder()
        kb.button(
            text=t(lang, "btn_yes_delete"),
            callback_data=f"adm:ord:refyes:{order.id}:{status}:{page}",
        )
        kb.button(
            text=t(lang, "btn_cancel"),
            callback_data=f"adm:ord:{order.id}:{status}:{page}",
        )
        kb.adjust(2)
        await render_menu(
            bot,
            user,
            user_repo,
            t(
                lang,
                "ord_refund_confirm",
                id=order.id,
                name=escape(order.service_name),
                amount=fmt(order.amount),
            ),
            kb.as_markup(),
        )
        await call.answer()
        return

    # plain detail view
    await state.clear()
    await _render_order_detail(bot, user, user_repo, session, order_id, status=status, page=page)
    await call.answer()


# --------------------------------------------------------------------- #
# Top-up approvals
# --------------------------------------------------------------------- #
async def _render_topups(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    lang = user.language or "fa"
    pending = await WalletRepository(session).list_pending_topups()

    lines = [t(lang, "topups_title"), SEPARATOR]
    if not pending:
        lines.append(t(lang, "topups_empty"))
    else:
        for tp in pending:
            lines.append(
                f"#{tp.id} — <code>{tp.telegram_id}</code> — "
                f"<b>{fmt(tp.amount)}</b> {t(lang, 'svc_currency')}"
            )

    kb = InlineKeyboardBuilder()
    for tp in pending:
        kb.button(text=t(lang, "btn_approve"), callback_data=f"adm:topup:ok:{tp.id}")
        kb.button(text=t(lang, "btn_reject"), callback_data=f"adm:topup:no:{tp.id}")
        kb.adjust(2)
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "adm:topups")
async def topups_list(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_topups(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data.startswith("adm:topup:"))
async def topup_decide_from_panel(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        _, _, action, topup_id_s = call.data.split(":")
        topup_id = int(topup_id_s)
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    changed, note = await decide_topup(
        bot, session, int(topup_id), approved=(action == "ok"),
        admin_id=call.from_user.id,
    )
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    if changed:
        await _render_topups(bot, user, user_repo, session)
    await call.answer(note, show_alert=not changed)


# --------------------------------------------------------------------- #
# Broadcast
# --------------------------------------------------------------------- #
# --------------------------------------------------------------------- #
# Broadcast with Audience Filtering
# --------------------------------------------------------------------- #
async def _resolve_broadcast_recipients(
    session: AsyncSession,
    remnawave: RemnawaveClient,
    target: str,
) -> list[int]:
    """Return a list of Telegram IDs matching the audience filter."""
    if target == "all":
        users = await UserRepository(session).all_users()
        return [u.telegram_id for u in users]

    if target == "balance":
        stmt = select(Wallet.telegram_id).where(Wallet.balance > 0)
        res = await session.execute(stmt)
        return [row[0] for row in res.fetchall()]

    if target == "buyers":
        stmt = select(distinct(Order.telegram_id)).where(Order.status == "paid")
        res = await session.execute(stmt)
        return [row[0] for row in res.fetchall()]

    # Targets requiring Remnawave
    panel_users = await remnawave.get_all_panel_users() or []
    now = datetime.now(timezone.utc)
    active_tids: set[int] = set()
    for pu in panel_users:
        if str(pu.get("status", "")).upper() == "ACTIVE":
            exp_str = pu.get("expireAt")
            if exp_str:
                try:
                    exp = datetime.fromisoformat(str(exp_str).replace("Z", "+00:00"))
                    if exp > now:
                        tid = pu.get("telegramId")
                        if tid and int(tid) > 0:
                            active_tids.add(int(tid))
                except Exception:
                    pass

    if target == "active":
        return list(active_tids)

    if target == "expired":
        all_users = await UserRepository(session).all_users()
        all_tids = {u.telegram_id for u in all_users}
        return list(all_tids - active_tids)

    users = await UserRepository(session).all_users()
    return [u.telegram_id for u in users]


@router.callback_query(F.data == "adm:broadcast")
async def broadcast_audience_select(
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
        # Row 1: Right = All, Left = Active
        kb.button(text=t(lang, "bcast_target_active"), callback_data="adm:bcast:target:active")
        kb.button(text=t(lang, "bcast_target_all"), callback_data="adm:bcast:target:all")
        # Row 2: Right = Expired, Left = Balance
        kb.button(text=t(lang, "bcast_target_balance"), callback_data="adm:bcast:target:balance")
        kb.button(text=t(lang, "bcast_target_expired"), callback_data="adm:bcast:target:expired")
    else:
        kb.button(text=t(lang, "bcast_target_all"), callback_data="adm:bcast:target:all")
        kb.button(text=t(lang, "bcast_target_active"), callback_data="adm:bcast:target:active")
        kb.button(text=t(lang, "bcast_target_expired"), callback_data="adm:bcast:target:expired")
        kb.button(text=t(lang, "bcast_target_balance"), callback_data="adm:bcast:target:balance")

    # Row 3: Buyers
    kb.button(text=t(lang, "bcast_target_buyers"), callback_data="adm:bcast:target:buyers")
    # Row 4: Back
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(2, 2, 1, 1)

    await render_menu(bot, user, user_repo, t(lang, "bcast_target_title"), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("adm:bcast:target:"))
async def broadcast_target_picked(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    target = call.data.rsplit(":", 1)[1]
    await state.set_state(BroadcastStates.waiting_text)
    await state.update_data(bcast_target=target)

    target_label = t(lang, f"bcast_target_{target}")
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:broadcast")
    kb.adjust(1)

    prompt = f"🎯 <b>{target_label}</b>\n\n{t(lang, 'broadcast_prompt')}"
    await render_menu(bot, user, user_repo, prompt, kb.as_markup())
    await call.answer()


@router.message(BroadcastStates.waiting_text, F.text)
async def broadcast_text(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    draft = message.text.strip()
    data = await state.get_data()
    target = str(data.get("bcast_target", "all"))
    target_label = t(lang, f"bcast_target_{target}")

    if not draft:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="adm:broadcast")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, t(lang, "broadcast_prompt"), kb.as_markup())
        return

    recipients = await _resolve_broadcast_recipients(session, remnawave, target)
    await state.update_data(draft=draft, recipient_ids=recipients)

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_send"), callback_data=BROADCAST_CONFIRM_KEY)
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:broadcast")
    kb.adjust(1)

    preview_text = t(
        lang, "bcast_preview_target",
        target=target_label,
        count=len(recipients),
        text=escape(draft),
    )
    await render_menu(bot, user, user_repo, preview_text, kb.as_markup())


@router.callback_query(F.data == BROADCAST_CONFIRM_KEY)
async def broadcast_send(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    data = await state.get_data()
    draft = data.get("draft", "")
    recipient_ids = data.get("recipient_ids") or []
    target = data.get("bcast_target", "all")
    await state.clear()

    if not draft:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    import asyncio as _asyncio

    ok = fail = 0
    safe_text = escape(draft)
    for tid in recipient_ids:
        try:
            await bot.send_message(tid, safe_text)
            ok += 1
        except Exception as exc:
            from aiogram.exceptions import TelegramRetryAfter

            if isinstance(exc, TelegramRetryAfter):
                try:
                    await _asyncio.sleep(exc.retry_after + 1)
                except Exception:
                    pass
                try:
                    await bot.send_message(tid, safe_text)
                    ok += 1
                    continue
                except Exception:
                    pass
            fail += 1
        if (ok + fail) % 20 == 0:
            await _asyncio.sleep(1)

    await AdminLogRepository(session).log(
        call.from_user.id, "broadcast", detail=f"target={target} ok={ok} fail={fail}"
    )
    await render_menu(
        bot, user, user_repo,
        t(lang, "broadcast_sent", ok=ok, fail=fail),
        _back_admin(lang).as_markup(),
    )
    await call.answer()


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
# Store settings (+ maintenance toggle)
# --------------------------------------------------------------------- #
_cached_admin_group_title: str | None = None
_cached_admin_group_title_time: float = 0


async def _get_admin_group_title(bot: Bot) -> str | None:
    global _cached_admin_group_title, _cached_admin_group_title_time
    now = time.time()
    if _cached_admin_group_title is not None and (now - _cached_admin_group_title_time) < 300:
        return _cached_admin_group_title
    cfg = get_settings()
    chat_id = getattr(cfg, "ADMIN_CHAT_ID", None)
    if not chat_id:
        return None
    try:
        chat = await bot.get_chat(chat_id)
        _cached_admin_group_title = chat.title or None
        _cached_admin_group_title_time = now
        return _cached_admin_group_title
    except Exception:
        return _cached_admin_group_title


async def _render_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    lang = user.language or "fa"
    store = await get_store_settings(session)
    maint_on = await is_maintenance(session)
    kb = InlineKeyboardBuilder()
    maint_label = t(lang, "btn_maintenance", state=t(lang, "toggle_on" if maint_on else "toggle_off"))
    kb.button(text=maint_label, callback_data="adm:maint")

    has_contact = bool(
        store.support_contact
        and store.support_contact.strip()
        and store.support_contact.strip() not in ("—", "-")
    )

    if lang == "fa":
        # Persian RTL: first added is LEFT, second added is RIGHT
        # Row 2: Right = Card Number, Left = Name
        kb.button(text=t(lang, "settings_holder"), callback_data="adm:set:card_holder")
        kb.button(text=t(lang, "settings_card"), callback_data="adm:set:card_number")
        # Row 3: Right = Min Topup, Left = Support Contact
        kb.button(text=t(lang, "settings_support_contact"), callback_data="adm:set:support_contact")
        kb.button(text=t(lang, "settings_min"), callback_data="adm:set:topup_min_amount")
        # Row 4: Support Direct Toggle
        if has_contact:
            sup_toggle_text = f"📞 پشتیبانی مستقیم: {'✅' if store.support_direct_enabled else '❌'}"
        else:
            sup_toggle_text = "📞 پشتیبانی مستقیم: ❌"
        kb.button(text=sup_toggle_text, callback_data="adm:settings:toggle:support_direct_enabled")
        # Row 5: Right = Grace Days, Left = Reminder Days
        kb.button(text=t(lang, "settings_remind_days"), callback_data="adm:set:expiry_remind_days")
        kb.button(text=t(lang, "settings_grace_days"), callback_data="adm:set:expiry_grace_days")
        # Row 6: Right = Squad UUID, Left = Topics
        kb.button(text=t(lang, "settings_topics_btn"), callback_data="adm:settings:topics")
        kb.button(text=t(lang, "settings_squad"), callback_data="adm:set:default_squad_uuid")
        # Row 7: Invite Settings & Test Settings (2 columns RTL: Left = Invite, Right = Test)
        kb.button(text="🤝 تنظیمات دعوت", callback_data="adm:settings:referral")
        kb.button(text="🎁 تنظیمات تست", callback_data="adm:settings:trial")
        # Row 8: Crypto Settings
        kb.button(text="💎 تنظیمات پرداخت کریپتو", callback_data="adm:settings:crypto")
    else:
        kb.button(text=t(lang, "settings_card"), callback_data="adm:set:card_number")
        kb.button(text=t(lang, "settings_holder"), callback_data="adm:set:card_holder")
        kb.button(text=t(lang, "settings_min"), callback_data="adm:set:topup_min_amount")
        kb.button(text=t(lang, "settings_support_contact"), callback_data="adm:set:support_contact")
        if has_contact:
            sup_toggle_text = f"📞 Direct Support: {'✅' if store.support_direct_enabled else '❌'}"
        else:
            sup_toggle_text = "📞 Direct Support: ❌"
        kb.button(text=sup_toggle_text, callback_data="adm:settings:toggle:support_direct_enabled")
        kb.button(text=t(lang, "settings_grace_days"), callback_data="adm:set:expiry_grace_days")
        kb.button(text=t(lang, "settings_remind_days"), callback_data="adm:set:expiry_remind_days")
        kb.button(text=t(lang, "settings_squad"), callback_data="adm:set:default_squad_uuid")
        kb.button(text=t(lang, "settings_topics_btn"), callback_data="adm:settings:topics")
        kb.button(text="🎁 Trial Settings", callback_data="adm:settings:trial")
        kb.button(text="🤝 Invite Settings", callback_data="adm:settings:referral")
        kb.button(text="💎 Crypto Payment Settings", callback_data="adm:settings:crypto")

    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1, 2, 2, 1, 2, 2, 2, 1, 1)

    squad_show = store.default_squad_uuid or "—"

    if has_contact:
        sup_status = "✅" if store.support_direct_enabled else "❌"
        support_block = (
            f"📞 پشتیبانی مستقیم : {sup_status}\n"
            f"📞 {t(lang, 'settings_support_contact')} : \u200e{escape(store.support_contact)}"
        )
    else:
        support_block = f"📞 {t(lang, 'settings_support_contact')} : —"

    trial_desc = (
        f"✅\n   حجم : \u200e{store.trial_traffic_gb} GB\n   زمان : {store.trial_duration_days} روز"
        if store.trial_enabled
        else "❌"
    )

    ref_desc = (
        f"✅\n   حجم : \u200e{store.referral_reward_gb} GB"
        if store.referral_enabled
        else "❌"
    )

    grp_title = await _get_admin_group_title(bot)
    topics_header = f"🎧 تاپیک‌ها ({escape(grp_title)}) :" if grp_title else "🎧 تاپیک‌ها :"
    topics_header_en = f"🎧 Topics ({escape(grp_title)}) :" if grp_title else "🎧 Topics :"

    t_topups = f"شارژ ({store.topic_topups}) : Topups" if store.topic_topups is not None else "شارژ : — (Topups)"
    t_orders = f"سفارش ({store.topic_orders}) : Orders" if store.topic_orders is not None else "سفارش : — (Orders)"
    t_support = f"پشتیبانی ({store.topic_support}) : Support" if store.topic_support is not None else "پشتیبانی : — (Support)"
    t_alerts = f"هشدار ({store.topic_alerts}) : Alerts" if store.topic_alerts is not None else "هشدار : — (Alerts)"
    t_crypto = f"کریپتو ({store.topic_crypto}) : Crypto" if store.topic_crypto is not None else "کریپتو : — (Crypto)"

    crypto_status_fa = "✅" if store.crypto_enabled else "❌"
    rate_fa = f"{store.ton_rate_toman:,} تومان" if store.ton_rate_toman > 0 else "—"

    maint_badge = "✅" if maint_on else "❌"

    if lang == "fa":
        lines = [
            f"{t(lang, 'store_settings_title')}\n{SEPARATOR}",
            f"💳 {t(lang, 'settings_card')} : <code>{escape(store.card_number or '—')}</code>",
            f"👤 {t(lang, 'settings_holder')} : {escape(store.card_holder or '—')}",
            f"💰 {t(lang, 'settings_min')} : {fmt(store.topup_min_amount)} {t(lang, 'svc_currency')}",
            "",
            support_block,
            "",
            f"🎁 سرویس تست : {trial_desc}",
            f"🤝 سیستم دعوت : {ref_desc}",
            f"💎 پرداخت کریپتو : {crypto_status_fa}",
            f"   قیمت تبدیل : {rate_fa}",
            "",
            f"⏳ {t(lang, 'settings_grace_days')} : {store.expiry_grace_days} روز",
            f"🔔 {t(lang, 'settings_remind_days')} : {escape(store.expiry_remind_days)}",
            f"🧩 {t(lang, 'settings_squad')} : {escape(squad_show[:24])}",
            "",
            topics_header,
            f"   {t_topups}",
            f"   {t_orders}",
            f"   {t_support}",
            f"   {t_alerts}",
            f"   {t_crypto}",
            "",
            f"🚧 {t(lang, 'settings_maintenance')} : {maint_badge}",
        ]
    else:
        trial_en = (
            f"✅\n   Traffic : {store.trial_traffic_gb} GB\n   Duration : {store.trial_duration_days}d"
            if store.trial_enabled
            else "❌"
        )
        ref_en = (
            f"✅\n   Traffic : {store.referral_reward_gb} GB"
            if store.referral_enabled
            else "❌"
        )
        sup_status_en = "✅" if store.support_direct_enabled else "❌"
        if has_contact:
            sup_block_en = (
                f"📞 Direct Support : {sup_status_en}\n"
                f"📞 {t(lang, 'settings_support_contact')} : \u200e{escape(store.support_contact)}"
            )
        else:
            sup_block_en = f"📞 {t(lang, 'settings_support_contact')} : —"

        topup_en = f"   Top-ups ({store.topic_topups}) : Topups" if store.topic_topups is not None else "   Top-ups : — (Topups)"
        orders_en = f"   Orders ({store.topic_orders}) : Orders" if store.topic_orders is not None else "   Orders : — (Orders)"
        support_en = f"   Support ({store.topic_support}) : Support" if store.topic_support is not None else "   Support : — (Support)"
        alerts_en = f"   Alerts ({store.topic_alerts}) : Alerts" if store.topic_alerts is not None else "   Alerts : — (Alerts)"
        crypto_en = f"   Crypto ({store.topic_crypto}) : Crypto" if store.topic_crypto is not None else "   Crypto : — (Crypto)"

        crypto_status_en = "✅" if store.crypto_enabled else "❌"
        rate_en = f"{store.ton_rate_toman:,} Toman" if store.ton_rate_toman > 0 else "—"

        lines = [
            f"{t(lang, 'store_settings_title')}\n{SEPARATOR}",
            f"💳 {t(lang, 'settings_card')} : <code>{escape(store.card_number or '—')}</code>",
            f"👤 {t(lang, 'settings_holder')} : {escape(store.card_holder or '—')}",
            f"💰 {t(lang, 'settings_min')} : <b>{fmt(store.topup_min_amount)}</b> {t(lang, 'svc_currency')}",
            "",
            sup_block_en,
            "",
            f"🎁 Free Trial : {trial_en}",
            f"🤝 Referral : {ref_en}",
            f"💎 Crypto Payment : {crypto_status_en}",
            f"   Exchange Rate : {rate_en}",
            "",
            f"⏳ {t(lang, 'settings_grace_days')} : {store.expiry_grace_days}d",
            f"🔔 {t(lang, 'settings_remind_days')} : {escape(store.expiry_remind_days)}",
            f"🧩 {t(lang, 'settings_squad')} : {escape(squad_show[:24])}",
            "",
            topics_header_en,
            topup_en,
            orders_en,
            support_en,
            alerts_en,
            crypto_en,
            "",
            f"🚧 {t(lang, 'settings_maintenance')} : {maint_badge}",
        ]
    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


async def _render_topics_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    lang = user.language or "fa"
    store = await get_store_settings(session)
    kb = InlineKeyboardBuilder()

    t_topups = f"{store.topic_topups} (Topups)" if store.topic_topups is not None else "— (Topups)"
    t_orders = f"{store.topic_orders} (Orders)" if store.topic_orders is not None else "— (Orders)"
    t_support = f"{store.topic_support} (Support)" if store.topic_support is not None else "— (Support)"
    t_alerts = f"{store.topic_alerts} (Alerts)" if store.topic_alerts is not None else "— (Alerts)"
    t_crypto = f"{store.topic_crypto} (Crypto)" if store.topic_crypto is not None else "— (Crypto)"

    if lang == "fa":
        # Persian RTL: first added is LEFT, second added is RIGHT
        # Row 1: Right = تاپیک شارژها, Left = تاپیک سفارشات
        kb.button(text="🛒 تاپیک سفارشات", callback_data="adm:set:topic_orders")
        kb.button(text="💳 تاپیک شارژها", callback_data="adm:set:topic_topups")
        # Row 2: Right = تاپیک پشتیبانی, Left = تاپیک هشدار و بکاپ
        kb.button(text="🚨 تاپیک هشدار و بکاپ", callback_data="adm:set:topic_alerts")
        kb.button(text="\u200f🎧 تاپیک پشتیبانی", callback_data="adm:set:topic_support")
        # Row 3: تاپیک کریپتو و نرخ
        kb.button(text="💎 تاپیک کریپتو و نرخ", callback_data="adm:set:topic_crypto")
    else:
        kb.button(text="💳 Top-ups Topic", callback_data="adm:set:topic_topups")
        kb.button(text="🛒 Orders Topic", callback_data="adm:set:topic_orders")
        kb.button(text="🎧 Support Topic", callback_data="adm:set:topic_support")
        kb.button(text="🚨 Alerts & Backup", callback_data="adm:set:topic_alerts")
        kb.button(text="💎 Crypto & Rates Topic", callback_data="adm:set:topic_crypto")

    kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    kb.adjust(2, 2, 1, 1)

    grp_title = await _get_admin_group_title(bot)
    topics_title = f"{t(lang, 'settings_topics_title')} ({escape(grp_title)})" if grp_title else t(lang, 'settings_topics_title')

    text = (
        f"{topics_title}\n{SEPARATOR}\n"
        f"💳 <b>تاپیک تایید شارژها :</b> {t_topups}\n"
        f"🛒 <b>تاپیک ثبت سفارشات :</b> {t_orders}\n"
        f"🎧 <b>تاپیک پیام‌های پشتیبانی :</b> {t_support}\n"
        f"🚨 <b>تاپیک هشدارهای سیستم و بکاپ :</b> {t_alerts}\n"
        f"💎 <b>تاپیک کریپتو و نرخ ارز :</b> {t_crypto}\n\n"
        f"💡 جهت اتصال هر بخش به تاپیک، روی دکمه مربوطه کلیک کنید و شناسه عددی (Topic ID) آن را ارسال نمایید.\n"
        f"(برای غیرفعال‌سازی هر تاپیک مقدار 0 یا /skip ارسال کنید)"
    ) if lang == "fa" else (
        f"{topics_title}\n{SEPARATOR}\n"
        f"💳 <b>Top-ups Topic :</b> {t_topups}\n"
        f"🛒 <b>Orders Topic :</b> {t_orders}\n"
        f"🎧 <b>Support Topic :</b> {t_support}\n"
        f"🚨 <b>System Alerts & Backup :</b> {t_alerts}\n"
        f"💎 <b>Crypto & Rates Topic :</b> {t_crypto}\n\n"
        f"<i>(Send 0 or /skip to disable any topic)</i>"
    )
    await render_menu(bot, user, user_repo, text, kb.as_markup())


async def _render_crypto_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    lang = user.language or "fa"
    store = await get_store_settings(session)
    kb = InlineKeyboardBuilder()

    status_badge = "✅" if store.crypto_enabled else "❌"
    rate_str = f"{store.ton_rate_toman:,} تومان" if store.ton_rate_toman > 0 else "— (تنظیم‌نشده)"
    wallet_str = store.ton_wallet_address or "— (تنظیم‌نشده)"

    if lang == "fa":
        kb.button(
            text=f"⚡️ وضعیت درگاه : {status_badge}",
            callback_data="adm:settings:toggle:crypto_enabled",
        )
        kb.button(text="📬 تنظیم آدرس والت", callback_data="adm:set:ton_wallet_address")
        kb.button(text="💰 تنظیم نرخ تبدیل", callback_data="adm:set:ton_rate_toman")
        kb.button(text="💵 تنظیم نرخ مبنای تتر", callback_data="adm:set:usdt_rate_toman")
        kb.button(text="📊 استعلام آنی نرخ ارز", callback_data="adm:crypto:nobitex_now")
    else:
        kb.button(
            text=f"⚡️ Status: {status_badge}",
            callback_data="adm:settings:toggle:crypto_enabled",
        )
        kb.button(text="📬 Set Wallet Address", callback_data="adm:set:ton_wallet_address")
        kb.button(text="💰 Set Exchange Rate", callback_data="adm:set:ton_rate_toman")
        kb.button(text="💵 Set USDT Rate", callback_data="adm:set:usdt_rate_toman")
        kb.button(text="📊 Check Market Price", callback_data="adm:crypto:nobitex_now")

    kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    kb.adjust(1, 2, 1, 1, 1)

    lines = [
        "💎 <b>تنظیمات پرداخت کریپتو</b>\n" + SEPARATOR,
        f"⚡️ وضعیت درگاه : <b>{status_badge}</b>",
        f"📬 آدرس والت مقصد : <code>{escape(wallet_str)}</code>",
        f"💰 نرخ تبدیل (۱ تون) : <b>{rate_str}</b>",
        f"💵 نرخ مبنای تتر : <b>{store.usdt_rate_toman:,} تومان</b>\n",
        "💡 ربات روزانه ۴ بار (ساعت‌های ۱۰:۰۰، ۱۴:۰۰، ۱۸:۰۰ و ۲۲:۰۰) قیمت لحظه‌ای را در تاپیک کریپتو ارسال می‌کند تا با یک کلیک بتوانید نرخ فروشگاه را آپدیت فرمایید.",
    ] if lang == "fa" else [
        "💎 <b>Crypto Payment Settings</b>\n" + SEPARATOR,
        f"⚡️ Status : <b>{status_badge}</b>",
        f"📬 Wallet : <code>{escape(wallet_str)}</code>",
        f"💰 Rate : <b>{rate_str}</b>",
        f"💵 USDT Rate : <b>{store.usdt_rate_toman:,} Toman</b>",
    ]

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "adm:settings:crypto")
async def crypto_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_crypto_settings(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:settings:toggle:crypto_enabled")
async def toggle_crypto_enabled(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    store = await get_store_settings(session)
    new_val = not store.crypto_enabled
    await AppSettingRepository(session).set("crypto_enabled", "1" if new_val else "0")
    await AdminLogRepository(session).log(
        call.from_user.id, "setting", detail=f"crypto_enabled={'1' if new_val else '0'}"
    )
    await _render_crypto_settings(bot, user, user_repo, session)
    await call.answer("✅ وضعیت پرداخت کریپتو تغییر یافت.")


@router.callback_query(F.data == "adm:crypto:nobitex_now")
async def crypto_nobitex_now(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    from bot.services.crypto.nobitex import fetch_ton_market_price, format_rate_alert
    store = await get_store_settings(session)
    price, source = await fetch_ton_market_price(usdt_rate=store.usdt_rate_toman)
    if price is None:
        await call.answer(
            "❌ خطا در استعلام از صرافی‌ها (احتمال مسدود بودن دسترسی از خارج کشور). لطفاً نرخ را به‌صورت دستی تنظیم فرمایید.",
            show_alert=True,
        )
        return

    src_title = source or "نوبیتکس"
    text, kb = format_rate_alert(price, store.ton_rate_toman, source_name=src_title)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_menu(bot, user, user_repo, text, kb)
    await call.answer(f"قیمت {src_title}: {price:,} تومان")


@router.callback_query(F.data.startswith("adm:rate:apply:"))
async def apply_nobitex_rate(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        price_s = call.data.split(":", 3)[3]
        price = int(price_s)
    except (ValueError, IndexError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    await AppSettingRepository(session).set("ton_rate_toman", str(price))
    await AdminLogRepository(session).log(
        call.from_user.id, "setting", detail=f"ton_rate_toman={price}"
    )
    await session.commit()

    await call.answer(f"✅ نرخ فروشگاه روی {price:,} تومان تنظیم شد.", show_alert=True)
    try:
        await call.message.edit_text(
            f"{call.message.html_text}\n\n✅ <b>نرخ فروشگاه با موفقیت روی {price:,} تومان تنظیم شد.</b>"
        )
    except Exception:
        pass


@router.callback_query(F.data == "adm:settings")
async def store_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_settings(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:settings:topics")
async def topics_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_topics_settings(bot, user, user_repo, session)
    await call.answer()


async def _render_trial_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    lang = user.language or "fa"
    store = await get_store_settings(session)
    kb = InlineKeyboardBuilder()

    trial_badge = "✅" if store.trial_enabled else "❌"
    trial_btn_text = f"وضعیت: {'✅' if store.trial_enabled else '❌'}"

    if lang == "fa":
        # Row 1 (RTL): Left = Duration, Right = Traffic
        kb.button(text=f"⏳ زمان: {store.trial_duration_days} روز", callback_data="adm:set:trial_duration_days")
        kb.button(text=f"📊 حجم: {store.trial_traffic_gb} GB", callback_data="adm:set:trial_traffic_gb")
        # Row 2: Toggle
        kb.button(text=trial_btn_text, callback_data="adm:settings:toggle:trial_enabled")
    else:
        kb.button(text=f"📊 Traffic: {store.trial_traffic_gb} GB", callback_data="adm:set:trial_traffic_gb")
        kb.button(text=f"⏳ Days: {store.trial_duration_days}", callback_data="adm:set:trial_duration_days")
        kb.button(text=f"Status: {'✅' if store.trial_enabled else '❌'}", callback_data="adm:settings:toggle:trial_enabled")

    kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    kb.adjust(2, 1, 1)

    text = (
        f"🎁 <b>تنظیمات اکانت تست</b>\n{SEPARATOR}\n"
        f"🎁 <b>وضعیت تست :</b> {trial_badge}\n"
        f"📊 <b>حجم :</b> {store.trial_traffic_gb} GB\n"
        f"⏳ <b>زمان :</b> {store.trial_duration_days} روز\n\n"
        f"💡 جهت فعال یا غیرفعال‌سازی، روی دکمه وضعیت کلیک کنید. برای تغییر حجم یا زمان، دکمه مربوطه را انتخاب کنید."
    ) if lang == "fa" else (
        f"🎁 <b>Free Trial Settings</b>\n{SEPARATOR}\n"
        f"🎁 <b>Trial Status :</b> {trial_badge}\n"
        f"📊 <b>Traffic :</b> {store.trial_traffic_gb} GB\n"
        f"⏳ <b>Days :</b> {store.trial_duration_days} Days\n\n"
        f"Tap the status button to enable/disable, or tap traffic/days to edit."
    )
    await render_menu(bot, user, user_repo, text, kb.as_markup())


async def _render_referral_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    lang = user.language or "fa"
    store = await get_store_settings(session)
    kb = InlineKeyboardBuilder()

    ref_badge = "✅" if store.referral_enabled else "❌"
    ref_btn_text = f"وضعیت: {'✅' if store.referral_enabled else '❌'}"

    if lang == "fa":
        kb.button(text=f"📊 حجم: {store.referral_reward_gb} GB", callback_data="adm:set:referral_reward_gb")
        kb.button(text=ref_btn_text, callback_data="adm:settings:toggle:referral_enabled")
    else:
        kb.button(text=f"📊 Traffic: {store.referral_reward_gb} GB", callback_data="adm:set:referral_reward_gb")
        kb.button(text=f"Status: {'✅' if store.referral_enabled else '❌'}", callback_data="adm:settings:toggle:referral_enabled")

    kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    kb.adjust(1, 1, 1)

    text = (
        f"🤝 <b>تنظیمات سیستم دعوت</b>\n{SEPARATOR}\n"
        f"🤝 <b>وضعیت سیستم دعوت :</b> {ref_badge}\n"
        f"🎁 <b>حجم :</b> {store.referral_reward_gb} GB\n\n"
        f"💡 جهت فعال یا غیرفعال‌سازی، روی دکمه وضعیت کلیک کنید. برای تغییر مقدار هدیه، دکمه حجم را انتخاب کنید."
    ) if lang == "fa" else (
        f"🤝 <b>Invite System Settings</b>\n{SEPARATOR}\n"
        f"🤝 <b>Invite Status :</b> {ref_badge}\n"
        f"🎁 <b>Traffic :</b> {store.referral_reward_gb} GB\n\n"
        f"Tap the status button to enable/disable, or tap traffic to edit."
    )
    await render_menu(bot, user, user_repo, text, kb.as_markup())


@router.callback_query(F.data == "adm:settings:trial")
async def trial_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_trial_settings(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:settings:referral")
async def referral_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_referral_settings(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:settings:trial_ref")
async def trial_ref_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_trial_settings(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data.startswith("adm:settings:toggle:"))
async def setting_toggle_boolean(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    field = call.data.rsplit(":", 1)[1]
    if field not in ("trial_enabled", "referral_enabled", "support_direct_enabled"):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    store = await get_store_settings(session)

    if field == "support_direct_enabled":
        has_contact = bool(
            store.support_contact
            and store.support_contact.strip()
            and store.support_contact.strip() not in ("—", "-")
        )
        if not has_contact:
            alert_text = (
                "⚠️ ابتدا باید آیدی پشتیبانی را در تنظیمات وارد کنید."
                if lang == "fa"
                else "⚠️ Please set the support contact ID first."
            )
            await call.answer(alert_text, show_alert=True)
            return

    curr_val = getattr(store, field, False)
    new_val = not curr_val
    new_str = "1" if new_val else "0"

    await AppSettingRepository(session).set(field, new_str)
    await AdminLogRepository(session).log(
        call.from_user.id, "setting", detail=f"{field}={new_str}"
    )

    if field == "trial_enabled":
        await _render_trial_settings(bot, user, user_repo, session)
        label = "سرویس تست" if lang == "fa" else "Free Trial"
    elif field == "referral_enabled":
        await _render_referral_settings(bot, user, user_repo, session)
        label = "سیستم دعوت" if lang == "fa" else "Referral"
    else:
        await _render_settings(bot, user, user_repo, session)
        label = "پشتیبانی مستقیم" if lang == "fa" else "Direct Support"
    status_text = (
        ("فعال شد" if new_val else "غیرفعال شد")
        if lang == "fa"
        else ("Enabled" if new_val else "Disabled")
    )
    await call.answer(f"✅ {label} {status_text}")


@router.callback_query(F.data == "adm:maint")
async def maintenance_toggle(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    enabled = not await is_maintenance(session)
    await set_maintenance(session, enabled)
    await AdminLogRepository(session).log(
        call.from_user.id, "maintenance",
        detail="on" if enabled else "off",
    )
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_settings(bot, user, user_repo, session)
    await call.answer(
        t(user.language or "fa", "maint_toggled", state=t(
            user.language or "fa", "toggle_on" if enabled else "toggle_off")),
    )


@router.callback_query(F.data.startswith("adm:set:"))
async def settings_edit_start(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    field = call.data.rsplit(":", 1)[1]
    if field not in SETTING_FIELDS:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    # Special handling for default squad: show squad list buttons!
    if field == "default_squad_uuid":
        await state.clear()
        store = await get_store_settings(session)
        squads = await remnawave.get_internal_squads()
        lines = [
            "🧩 <b>انتخاب اسکواد پیش‌فرض فروشگاه</b>" if lang == "fa" else "🧩 <b>Select Default Store Squad</b>",
            SEPARATOR,
            "اسکوادی که اکانت‌های جدید پس از خرید خودکار به آن متصل می‌شوند را انتخاب کنید:" if lang == "fa" else "Select default squad for new accounts created via shop:",
        ]
        kb = InlineKeyboardBuilder()
        for sq in squads:
            sq_name = sq.get("name") or "Squad"
            sq_uuid = sq.get("uuid")
            is_active = (store.default_squad_uuid == sq_uuid)
            icon = "✅" if is_active else "🧩"
            kb.button(text=f"{icon} {sq_name}", callback_data=f"adm:setsquad:{sq_uuid}")
        kb.button(
            text="❌ بدون اسکواد پیش‌فرض (غیرفعال)" if lang == "fa" else "❌ No Default Squad (None)",
            callback_data="adm:setsquad:none",
        )
        kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
        # 2 columns for squads, then full width for None and Back
        sq_count = len(squads)
        sizes = [2] * (sq_count // 2)
        if sq_count % 2:
            sizes.append(1)
        sizes += [1, 1]
        kb.adjust(*sizes)
        await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await call.answer()
        return

    await state.set_state(SettingsStates.waiting_value)
    await state.update_data(settings_field=field)

    cancel_target = (
        "adm:settings:crypto" if ("ton_" in field or field in ("crypto_enabled", "usdt_rate_toman"))
        else ("adm:settings:topics" if field.startswith("topic_")
        else ("adm:settings:trial" if "trial" in field else ("adm:settings:referral" if "referral" in field else "adm:settings")))
    )
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data=cancel_target)
    kb.adjust(1)

    prompt_key = SETTING_FIELDS[field][0]
    extra = t(lang, "skip_for_none") if SETTING_FIELDS[field][1] is False else ""
    desc = SETTING_DESCRIPTIONS.get(lang, SETTING_DESCRIPTIONS["fa"]).get(field, "")

    parts = [f"⚙️ <b>{t(lang, prompt_key)}</b>", SEPARATOR]
    if desc:
        parts.append(f"💡 {desc}\n")
    parts.append(t(lang, "settings_value_prompt"))
    if extra:
        parts.append(f"\n{extra}")

    await render_menu(
        bot, user, user_repo,
        "\n".join(parts),
        kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:setsquad:"))
async def settings_set_squad(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    choice = call.data.rsplit(":", 1)[1]
    val = "" if choice == "none" else choice
    await AppSettingRepository(session).set("default_squad_uuid", val)
    await AdminLogRepository(session).log(
        call.from_user.id, "setting", detail=f"default_squad_uuid={val[:40]}"
    )
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_settings(bot, user, user_repo, session)
    await call.answer(t(user.language or "fa", "toast_squads_updated"))


@router.message(SettingsStates.waiting_value, F.text)
async def settings_value_save(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await delete_message_silently(bot, message.chat.id, message.message_id)

    data = await state.get_data()
    field = data.get("settings_field", "card_number")
    is_numeric = SETTING_FIELDS.get(field, ("", False))[1]

    raw = message.text.strip()
    value = raw
    SKIP_WORDS = ("/skip", "-", "—")
    cancel_target = (
        "adm:settings:crypto" if ("ton_" in field or field in ("crypto_enabled", "usdt_rate_toman"))
        else ("adm:settings:topics" if field.startswith("topic_")
        else ("adm:settings:trial" if "trial" in field else ("adm:settings:referral" if "referral" in field else "adm:settings")))
    )

    if field.startswith("topic_") or field == "expiry_grace_days":
        if raw in SKIP_WORDS or raw == "0":
            value = ""
        else:
            parsed = _parse_int(raw)
            if parsed is None or parsed < 0:
                kb = InlineKeyboardBuilder()
                kb.button(text=t(lang, "btn_cancel"), callback_data=cancel_target)
                kb.adjust(1)
                await render_menu(bot, user, user_repo, t(lang, "settings_invalid_number"), kb.as_markup())
                return
            value = str(parsed)
    elif field in ("trial_enabled", "referral_enabled"):
        parsed = _parse_int(raw)
        if parsed not in (0, 1):
            kb = InlineKeyboardBuilder()
            kb.button(text=t(lang, "btn_cancel"), callback_data=cancel_target)
            kb.adjust(1)
            await render_menu(bot, user, user_repo, "❌ لطفاً فقط عدد 1 (فعال) یا 0 (غیرفعال) را وارد کنید:", kb.as_markup())
            return
        value = str(parsed)
    elif is_numeric:
        parsed = _parse_int(raw)
        if parsed is None or parsed < 0:
            kb = InlineKeyboardBuilder()
            kb.button(text=t(lang, "btn_cancel"), callback_data=cancel_target)
            kb.adjust(1)
            await render_menu(bot, user, user_repo, t(lang, "settings_invalid_number"), kb.as_markup())
            return
        value = str(parsed)
    elif field == "support_contact":
        if raw in SKIP_WORDS or raw == "0":
            value = ""
            await AppSettingRepository(session).set("support_direct_enabled", "0")
        else:
            clean_contact = raw.strip()
            t_me_match = re.match(
                r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]{3,32})/?$",
                clean_contact,
                re.IGNORECASE,
            )
            user_match = re.match(r"^@?([A-Za-z0-9_]{3,32})$", clean_contact)
            url_match = re.match(r"^https?://[^\s]+$", clean_contact)

            if t_me_match:
                uname = t_me_match.group(1)
                value = f"https://t.me/{uname}"
            elif user_match:
                uname = user_match.group(1)
                value = f"@{uname}"
            elif url_match:
                value = clean_contact
            else:
                kb = InlineKeyboardBuilder()
                kb.button(text=t(lang, "btn_cancel"), callback_data="adm:settings")
                kb.adjust(1)
                err_msg = (
                    "❌ فرمت نامعتبر است.\n\n"
                    "لطفاً آیدی پشتیبانی را با <b>@</b> (مانند <code>@SupportUsername</code>) "
                    "یا لینک تلگرام (مانند <code>t.me/SupportUsername</code>) ارسال کنید:\n\n"
                    "<i>(برای حذف مقدار می‌توانید /skip یا 0 بفرستید)</i>"
                ) if lang == "fa" else (
                    "❌ Invalid format.\n\n"
                    "Please provide a Telegram username with <b>@</b> (e.g. <code>@SupportUsername</code>) "
                    "or link (e.g. <code>t.me/SupportUsername</code>):\n\n"
                    "<i>(Send /skip or 0 to clear)</i>"
                )
                await render_menu(bot, user, user_repo, err_msg, kb.as_markup())
                return
    elif raw in SKIP_WORDS:
        value = ""

    await AppSettingRepository(session).set(field, value)
    await AdminLogRepository(session).log(
        message.from_user.id, "setting", detail=f"{field}={value[:40]}"
    )
    await state.clear()
    if field.startswith("topic_"):
        await _render_topics_settings(bot, user, user_repo, session)
    elif "ton_" in field or field in ("crypto_enabled", "usdt_rate_toman"):
        await _render_crypto_settings(bot, user, user_repo, session)
    elif "trial" in field:
        await _render_trial_settings(bot, user, user_repo, session)
    elif "referral" in field:
        await _render_referral_settings(bot, user, user_repo, session)
    else:
        await _render_settings(bot, user, user_repo, session)


# --------------------------------------------------------------------- #
# Node / Server Status Monitor
# --------------------------------------------------------------------- #
COUNTRY_FLAGS_MAP: dict[str, tuple[str, str]] = {
    "netherlands": ("🇳🇱", "NL"),
    "netherland": ("🇳🇱", "NL"),
    "holland": ("🇳🇱", "NL"),
    "germany": ("🇩🇪", "DE"),
    "deutschland": ("🇩🇪", "DE"),
    "france": ("🇫🇷", "FR"),
    "united states": ("🇺🇸", "US"),
    "usa": ("🇺🇸", "US"),
    "united kingdom": ("🇬🇧", "GB"),
    "uk": ("🇬🇧", "GB"),
    "great britain": ("🇬🇧", "GB"),
    "england": ("🇬🇧", "GB"),
    "turkey": ("🇹🇷", "TR"),
    "turkiye": ("🇹🇷", "TR"),
    "finland": ("🇫🇮", "FI"),
    "sweden": ("🇸🇪", "SE"),
    "canada": ("🇨🇦", "CA"),
    "iran": ("🇮🇷", "IR"),
    "russia": ("🇷🇺", "RU"),
    "poland": ("🇵🇱", "PL"),
    "italy": ("🇮🇹", "IT"),
    "spain": ("🇪🇸", "ES"),
    "switzerland": ("🇨🇭", "CH"),
    "united arab emirates": ("🇦🇪", "AE"),
    "uae": ("🇦🇪", "AE"),
    "dubai": ("🇦🇪", "AE"),
    "singapore": ("🇸🇬", "SG"),
    "austria": ("🇦🇹", "AT"),
    "australia": ("🇦🇺", "AU"),
    "brazil": ("🇧🇷", "BR"),
    "norway": ("🇳🇴", "NO"),
    "denmark": ("🇩🇰", "DK"),
    "belgium": ("🇧🇪", "BE"),
    "japan": ("🇯🇵", "JP"),
}


def _extract_versions(n: dict) -> tuple[str | None, str | None]:
    versions = n.get("versions")
    if not isinstance(versions, dict):
        versions = {}

    sys_info = n.get("system") or n.get("sys") or {}
    if isinstance(sys_info, dict) and isinstance(sys_info.get("versions"), dict):
        versions = {**sys_info.get("versions"), **versions}

    xray_ver = (
        versions.get("xray")
        or versions.get("xrayVersion")
        or n.get("xrayVersion")
        or (n.get("core") if isinstance(n.get("core"), str) else None)
    )
    singbox_ver = (
        versions.get("singbox")
        or versions.get("sing-box")
        or versions.get("singboxVersion")
        or n.get("singboxVersion")
    )
    node_ver = (
        versions.get("node")
        or versions.get("nodeVersion")
        or n.get("nodeVersion")
        or versions.get("agent")
        or n.get("agentVersion")
    )
    core_ver = (
        versions.get("core")
        or n.get("coreVersion")
        or n.get("version")
    )

    core_label = None
    if xray_ver:
        core_label = f"Xray {xray_ver}"
    elif singbox_ver:
        core_label = f"Sing-Box {singbox_ver}"
    elif core_ver:
        core_label = f"Core {core_ver}" if not str(core_ver).lower().startswith("core") else str(core_ver)

    node_label = f"Node {node_ver}" if node_ver else None
    return core_label, node_label


def _extract_core_version(n: dict) -> str | None:
    core_label, node_label = _extract_versions(n)
    if core_label and node_label:
        return f"{core_label} | {node_label}"
    return core_label or node_label


def _format_node_title(n: dict, index: int) -> str:
    raw_name = str(n.get("name") or f"Node {index}").strip()
    country_code = str(n.get("countryCode") or n.get("country_code") or "").strip().upper()
    country_name = str(n.get("country") or "").strip().lower()

    flag = None
    if len(country_code) == 2 and country_code.isalpha() and country_code != "XX":
        flag = country_flag(country_code)

    clean_name = raw_name
    for kw, (f_emoji, _) in sorted(COUNTRY_FLAGS_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
        if pattern.search(clean_name):
            if not flag or flag == "🌐":
                flag = f_emoji
            clean_name = pattern.sub("", clean_name)
            break

    if (not flag or flag == "🌐") and country_name:
        for kw, (f_emoji, _) in COUNTRY_FLAGS_MAP.items():
            if kw in country_name:
                flag = f_emoji
                break

    if country_code and len(country_code) == 2 and country_code != "XX":
        code_pat = re.compile(rf"\b{re.escape(country_code)}\b", re.IGNORECASE)
        clean_name = code_pat.sub("", clean_name)

    clean_name = re.sub(r"[\-_:]+", " ", clean_name).strip()
    clean_name = re.sub(r"\s+", " ", clean_name).strip()

    # Check if a flag emoji is already present in clean_name
    has_flag = any(0x1F1E6 <= ord(c) <= 0x1F1FF for c in clean_name)
    if not has_flag:
        flag_prefix = flag if flag else (country_flag(country_code) if country_code else "🌐")
        if clean_name:
            final_title = f"{flag_prefix} {escape(clean_name)}"
        else:
            final_title = f"{flag_prefix}"
    else:
        final_title = escape(clean_name)

    return final_title


@router.callback_query(F.data == "adm:nodes")
async def admin_nodes_monitor(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    nodes = await remnawave.get_nodes()
    lines = [
        f"🖥 <b>{t(lang, 'nodes_title')}</b>",
        SEPARATOR,
    ]
    if nodes is None:
        lines.append(t(lang, "stats_error"))
    elif not nodes:
        lines.append("هیچ سرور یا نودی یافت نشد." if lang == "fa" else "No nodes found.")
    else:
        for i, n in enumerate(nodes, start=1):
            title = _format_node_title(n, i)
            address = escape(str(n.get("address") or "—"))
            port = n.get("port")
            addr_str = f"{address}:{port}" if port else address
            is_connected = n.get("isConnected")
            if is_connected is None:
                is_connected = str(n.get("status", "")).upper() == "CONNECTED"
            status_badge = "🟢" if is_connected else "🔴"

            core_version, node_version = _extract_versions(n)
            user_mult = (
                n.get("consumptionMultiplier")
                if n.get("consumptionMultiplier") is not None
                else n.get("userConsumptionMultiplier")
                if n.get("userConsumptionMultiplier") is not None
                else n.get("userTrafficMultiplier")
                if n.get("userTrafficMultiplier") is not None
                else n.get("trafficMultiplier")
                if n.get("trafficMultiplier") is not None
                else 1.0
            )
            node_mult = (
                n.get("nodeConsumptionMultiplier")
                if n.get("nodeConsumptionMultiplier") is not None
                else n.get("nodeTrafficMultiplier")
                if n.get("nodeTrafficMultiplier") is not None
                else n.get("multiplier")
            )

            sys_info = n.get("system") or n.get("sys") or {}
            cpu = sys_info.get("cpu") or n.get("cpu")
            ram = sys_info.get("ram") or sys_info.get("memory") or n.get("memory")
            os_name = sys_info.get("os") or n.get("os")
            uptime_raw = sys_info.get("uptime") or n.get("uptime") or n.get("uptimeSeconds")

            uptime_str = None
            if uptime_raw is not None:
                try:
                    s = int(uptime_raw)
                    if s > 0:
                        days = s // 86400
                        s %= 86400
                        hours = s // 3600
                        s %= 3600
                        minutes = s // 60
                        seconds = s % 60
                        parts = []
                        if days > 0:
                            parts.append(f"{days}d")
                        if hours > 0 or days > 0:
                            parts.append(f"{hours}h")
                        if minutes > 0 or hours > 0 or days > 0:
                            parts.append(f"{minutes}m")
                        parts.append(f"{seconds}s")
                        uptime_str = " ".join(parts)
                except (ValueError, TypeError):
                    uptime_str = str(uptime_raw)

            daily_traffic = n.get("trafficDailyBytes") or n.get("dailyTrafficBytes") or n.get("todayTrafficBytes")
            daily_str = f"{daily_traffic / (1024**3):.2f} GB" if daily_traffic else None
            traffic_used = n.get("trafficUsedBytes") or n.get("usedTrafficBytes")
            traf_str = f"{traffic_used / (1024**3):.2f} GB" if traffic_used else None
            online_users = n.get("usersOnline") or n.get("connectionCount")

            node_desc = [
                f"<b>{i}. {title}</b> ({status_badge})",
                f"   🌐 آدرس: <code>{addr_str}</code>" if lang == "fa" else f"   🌐 Host: <code>{addr_str}</code>",
            ]
            if core_version:
                node_desc.append(
                    f"   ⚙️ نسخه هسته: {escape(str(core_version))}" if lang == "fa" else f"   ⚙️ Core: {escape(str(core_version))}"
                )
            if node_version:
                node_desc.append(
                    f"   📡 نسخه نود: {escape(str(node_version))}" if lang == "fa" else f"   📡 Node: {escape(str(node_version))}"
                )
            specs_parts = []
            if cpu:
                specs_parts.append(f"CPU: {cpu}")
            if ram:
                specs_parts.append(f"RAM: {ram}")
            if os_name:
                specs_parts.append(f"OS: {os_name}")
            disk = sys_info.get("disk") or sys_info.get("storage") or n.get("disk")
            if disk:
                specs_parts.append(f"Disk: {disk}")
            load = sys_info.get("load") or sys_info.get("loadAvg") or n.get("load")
            if load:
                specs_parts.append(f"Load: {load}")
            if specs_parts:
                specs_str = escape(" | ".join(specs_parts))
                node_desc.append(
                    f"   💻 مشخصات سرور: {specs_str}" if lang == "fa" else f"   💻 System: {specs_str}"
                )
            if user_mult is not None:
                node_desc.append(
                    f"   👤 ضریب مصرف کاربر: <b>{user_mult}x</b>" if lang == "fa" else f"   👤 User Multiplier: <b>{user_mult}x</b>"
                )
            if node_mult is not None:
                node_desc.append(
                    f"   📡 ضریب مصرف نود: <b>{node_mult}x</b>" if lang == "fa" else f"   📡 Node Multiplier: <b>{node_mult}x</b>"
                )
            traf_info = []
            if daily_str:
                traf_info.append(f"امروز: <b>{daily_str}</b>" if lang == "fa" else f"Today: <b>{daily_str}</b>")
            if traf_str:
                traf_info.append(f"کل: <b>{traf_str}</b>" if lang == "fa" else f"Total: <b>{traf_str}</b>")
            if traf_info:
                node_desc.append(
                    f"   📊 ترافیک مصرفی: {' | '.join(traf_info)}" if lang == "fa" else f"   📊 Used Traffic: {' | '.join(traf_info)}"
                )
            if uptime_str:
                node_desc.append(
                    f"   ⏱ آپ‌تایم: {uptime_str}" if lang == "fa" else f"   ⏱ Uptime: {uptime_str}"
                )
            if online_users is not None:
                node_desc.append(
                    f"   👥 آنلاین: <b>{online_users}</b>" if lang == "fa" else f"   👥 Online: <b>{online_users}</b>"
                )
            lines.append("\n".join(node_desc))
            if i < len(nodes):
                lines.append("")

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 بروزرسانی" if lang == "fa" else "🔄 Refresh", callback_data="adm:nodes")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


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
# Coupon Management (Admin)
# --------------------------------------------------------------------- #
@router.callback_query(F.data == "adm:coupons")
async def admin_coupons_list(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    coupon_repo = CouponRepository(session)
    coupons = await coupon_repo.list_all()

    lines = [
        f"{t(lang, 'coupons_admin_title')}\n{SEPARATOR}",
    ]
    if not coupons:
        lines.append("هیچ کد تخفیفی ثبت نشده است." if lang == "fa" else "No discount coupons created yet.")
    else:
        for c in coupons:
            status_icon = "🟢" if c.is_active else "🔴"
            disc_str = f"{c.discount_percent}%" if c.discount_percent else f"{fmt(c.discount_amount)} {t(lang, 'svc_currency')}"
            uses_str = f"{c.used_count}/{c.max_uses}" if c.max_uses else f"{c.used_count}/∞"
            lines.append(f"{status_icon} <code>{c.code}</code> — {disc_str} ({uses_str})")

    kb = InlineKeyboardBuilder()
    for c in coupons:
        status_icon = "🟢" if c.is_active else "🔴"
        disc_str = f"{c.discount_percent}%" if c.discount_percent else f"{fmt(c.discount_amount)}"
        kb.button(text=f"{status_icon} {c.code} ({disc_str})", callback_data=f"adm:cpn:view:{c.id}")
    kb.button(text=t(lang, "btn_create_coupon"), callback_data="adm:cpn:add")
    kb.button(text=t(lang, "btn_back"), callback_data="adm:services")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("adm:cpn:view:"))
async def admin_coupon_detail(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        coupon_id = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    coupon_repo = CouponRepository(session)
    c = await coupon_repo.get_by_id(coupon_id)
    if c is None:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    disc_str = f"{c.discount_percent}%" if c.discount_percent else f"{fmt(c.discount_amount)} {t(lang, 'svc_currency')}"
    uses_str = f"{c.used_count} از {c.max_uses}" if c.max_uses else f"{c.used_count} (نامحدود)"
    status_str = "🟢 فعال" if c.is_active else "🔴 غیرفعال"

    lines = [
        f"🏷 <b>جزئیات کد تخفیف: <code>{c.code}</code></b>\n{SEPARATOR}",
        f"💰 میزان تخفیف: <b>{disc_str}</b>",
        f"👥 دفعات استفاده: <b>{uses_str}</b>",
        f"🔘 وضعیت: <b>{status_str}</b>",
    ]
    if c.expires_at:
        lines.append(f"📅 تاریخ انقضا: <code>{format_datetime(c.expires_at, lang)}</code>")

    kb = InlineKeyboardBuilder()
    toggle_text = "🔴 غیرفعال‌سازی" if c.is_active else "🟢 فعال‌سازی"
    kb.button(text=toggle_text, callback_data=f"adm:cpn:toggle:{c.id}")
    kb.button(text="🗑 حذف کد تخفیف", callback_data=f"adm:cpn:del:{c.id}")
    kb.button(text=t(lang, "btn_back"), callback_data="adm:coupons")
    kb.adjust(2, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("adm:cpn:toggle:"))
async def admin_coupon_toggle(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    coupon_id = int(call.data.rsplit(":", 1)[1])
    coupon_repo = CouponRepository(session)
    await coupon_repo.toggle_active(coupon_id)
    call.data = f"adm:cpn:view:{coupon_id}"
    await admin_coupon_detail(call, bot, user_repo, session)


@router.callback_query(F.data.startswith("adm:cpn:del:"))
async def admin_coupon_delete(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    coupon_id = int(call.data.rsplit(":", 1)[1])
    coupon_repo = CouponRepository(session)
    await coupon_repo.delete(coupon_id)
    await call.answer("کد تخفیف حذف شد." if call.from_user.language_code == "fa" else "Coupon deleted.")
    await admin_coupons_list(call, bot, user_repo, session, state)


@router.callback_query(F.data == "adm:cpn:add")
async def admin_coupon_add_start(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    await state.set_state(CouponManagementStates.waiting_code)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:coupons")
    kb.adjust(1)

    text = "🏷 <b>عنوان کد تخفیف را وارد کنید:</b>\n(مثال: NOROOZ, DISCOUNT20, ...)" if lang == "fa" else "🏷 <b>Enter Coupon Code:</b>\n<i>(e.g., SUMMER20)</i>"
    await render_menu(bot, user, user_repo, text, kb.as_markup())
    await call.answer()


@router.message(CouponManagementStates.waiting_code, F.text)
async def admin_coupon_add_code(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language or "fa"
    await delete_message_silently(bot, message.chat.id, message.message_id)

    code = message.text.strip().upper()
    if len(code) < 3 or len(code) > 32:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="adm:coupons")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "❌ کد نامعتبر است (بین ۳ تا ۳۲ کاراکتر):", kb.as_markup())
        return

    await state.update_data(coupon_code=code)
    await state.set_state(CouponManagementStates.waiting_discount)

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:coupons")
    kb.adjust(1)

    text = (
        "💰 <b>میزان تخفیف را وارد کنید:</b>\n\n"
        "• برای درصد تخفیف، علامت % بگذارید (مثال: <code>20%</code>)\n"
        "• برای مبلغ ثابت، مبلغ را به تومان وارد کنید (مثال: <code>50000</code>)"
        if lang == "fa"
        else "💰 <b>Enter discount value:</b>\n\n• For percentage, use % (e.g. <code>20%</code>)\n• For fixed amount, enter Toman (e.g. <code>50000</code>)"
    )
    await render_menu(bot, user, user_repo, text, kb.as_markup())


@router.message(CouponManagementStates.waiting_discount, F.text)
async def admin_coupon_add_discount(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language or "fa"
    await delete_message_silently(bot, message.chat.id, message.message_id)

    raw = message.text.strip().replace("٪", "%")
    is_percent = "%" in raw
    clean_val = raw.replace("%", "").strip()
    val = _parse_int(clean_val)
    if val is None or val <= 0 or (is_percent and val > 100):
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="adm:coupons")
        kb.adjust(1)
        await render_menu(bot, user, user_repo, "❌ مقدار نامعتبر است. لطفاً عدد معتبر وارد کنید:", kb.as_markup())
        return

    if is_percent:
        await state.update_data(discount_percent=val, discount_amount=0)
    else:
        await state.update_data(discount_percent=0, discount_amount=val)

    await state.set_state(CouponManagementStates.waiting_max_uses)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="adm:coupons")
    kb.adjust(1)

    text = (
        "👥 <b>حداکثر دفعات مجاز استفاده را وارد کنید:</b>\n"
        "(برای استفاده نامحدود عدد 0 یا /skip ارسال کنید)"
        if lang == "fa"
        else "👥 <b>Enter maximum total uses:</b>\n<i>(Enter 0 or /skip for unlimited)</i>"
    )
    await render_menu(bot, user, user_repo, text, kb.as_markup())


@router.message(CouponManagementStates.waiting_max_uses, F.text)
async def admin_coupon_add_max_uses(
    message: Message, bot: Bot, user_repo: UserRepository, session: AsyncSession, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language or "fa"
    await delete_message_silently(bot, message.chat.id, message.message_id)

    raw = message.text.strip()
    max_uses = None
    if raw not in ("/skip", "-", "—", "0"):
        val = _parse_int(raw)
        if val is not None and val > 0:
            max_uses = val

    data = await state.get_data()
    code = data.get("coupon_code")
    discount_percent = data.get("discount_percent") or None
    discount_amount = data.get("discount_amount") or 0

    coupon_repo = CouponRepository(session)
    await coupon_repo.create(
        code=code,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
        max_uses=max_uses,
    )
    await AdminLogRepository(session).log(
        message.from_user.id, "setting", detail=f"create_coupon={code}"
    )
    await state.clear()

    coupons = await coupon_repo.list_all()
    lines = [
        t(lang, "coupon_created", code=code),
        SEPARATOR,
        f"{t(lang, 'coupons_admin_title')}\n{SEPARATOR}",
    ]
    for c in coupons:
        status_icon = "🟢" if c.is_active else "🔴"
        disc_str = f"{c.discount_percent}%" if c.discount_percent else f"{fmt(c.discount_amount)} {t(lang, 'svc_currency')}"
        uses_str = f"{c.used_count}/{c.max_uses}" if c.max_uses else f"{c.used_count}/∞"
        lines.append(f"{status_icon} <code>{c.code}</code> — {disc_str} ({uses_str})")

    kb = InlineKeyboardBuilder()
    for c in coupons:
        status_icon = "🟢" if c.is_active else "🔴"
        disc_str = f"{c.discount_percent}%" if c.discount_percent else f"{fmt(c.discount_amount)}"
        kb.button(text=f"{status_icon} {c.code} ({disc_str})", callback_data=f"adm:cpn:view:{c.id}")
    kb.button(text=t(lang, "btn_create_coupon"), callback_data="adm:cpn:add")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
