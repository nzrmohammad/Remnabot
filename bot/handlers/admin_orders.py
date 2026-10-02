"""Admin Orders, Sales, Refunds, and Telemetry Reports Hub."""
import logging
import math
from datetime import datetime, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, is_admin
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.order_repo import OrderRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.formatting import country_flag, format_datetime
from bot.services.menu import delete_message_silently, render_menu
from bot.services.remnawave import RemnawaveClient
from bot.states.admin import OrderManagementStates

logger = logging.getLogger(__name__)
router = Router(name="admin_orders")

def _is_admin(user_id: int) -> bool:
    import bot.handlers.admin_ops as _ops
    fn = getattr(_ops, "_is_admin", is_admin)
    return fn(user_id)

ORDERS_PER_PAGE = 8
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


PLATFORM_EMOJI = {
    "android": "🤖",
    "ios": "🍏",
    "windows": "🖥",
    "macos": "💻",
    "linux": "🐧",
}


async def _revert_panel_subscription(remnawave, order) -> None:
    """Roll back what the purchase granted: subtract duration/traffic.

    Best-effort: if the panel is down or the account is gone, the wallet
    refund already happened, so we only log.
    """
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
    import bot.handlers.admin_ops as _ops
    order_repo_cls = getattr(_ops, "OrderRepository", OrderRepository)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

    lang = user.language or "fa"
    order = await order_repo_cls(session).get(order_id)
    if order is None:
        await render_menu_fn(
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
    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


async def _render_orders_list(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    status: str = "all",
    page: int = 0,
    query: str | None = None,
) -> None:
    import bot.handlers.admin_ops as _ops
    order_repo_cls = getattr(_ops, "OrderRepository", OrderRepository)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

    lang = user.language or "fa"
    order_repo = order_repo_cls(session)
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

    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "adm:noop")
async def admin_noop(call: CallbackQuery):
    await call.answer()


async def _render_reports_hub(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    remnawave: RemnawaveClient,
) -> None:
    import bot.handlers.admin_ops as _ops
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

    lang = user.language or "fa"

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
        # Row 3: Manual Report Triggers
        kb.button(text="📅 ارسال گزارش هفتگی", callback_data="adm:rep:trigger:weekly")
        kb.button(text="🌙 ارسال گزارش شبانه", callback_data="adm:rep:trigger:nightly")
        # Row 4: Monthly Report
        kb.button(text="🗓️ ارسال گزارش ماهانه به تاپیک", callback_data="adm:rep:trigger:monthly")
    else:
        kb.button(text="🔍 HWID Inspector", callback_data="adm:rep:hwid")
        kb.button(text="🌐 SRH Inspector", callback_data="adm:rep:srh")
        kb.button(text="⚡ Sessions Explorer", callback_data="adm:rep:sessions:0")
        kb.button(text="🌙 Send Nightly Report", callback_data="adm:rep:trigger:nightly")
        kb.button(text="📅 Send Weekly Report", callback_data="adm:rep:trigger:weekly")
        kb.button(text="🗓️ Send Monthly Report to Topic", callback_data="adm:rep:trigger:monthly")

    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(2, 1, 2, 1, 1)

    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data.startswith("adm:rep:trigger:"))
async def trigger_admin_report_handler(
    call: CallbackQuery, bot: Bot, session: AsyncSession, remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    kind = call.data.split(":")[3]
    from bot.services.reports import (
        _send_admin_nightly_summary,
        _send_admin_weekly_summary,
        _send_admin_monthly_summary,
    )
    from bot.services.formatting import now_tz
    from bot.config import get_settings
    now = now_tz(get_settings().TIMEZONE)

    await call.answer("⏳ در حال پردازش و ارسال گزارش...")
    try:
        if kind == "nightly":
            report_name = "گزارش شبانه"
            await _send_admin_nightly_summary(bot, session, remnawave, now, target_user_id=call.from_user.id)
        elif kind == "weekly":
            report_name = "گزارش هفتگی"
            await _send_admin_weekly_summary(bot, session, remnawave, now, target_user_id=call.from_user.id)
        elif kind == "monthly":
            report_name = "گزارش ماهانه"
            await _send_admin_monthly_summary(bot, session, remnawave, now, target_user_id=call.from_user.id)
        else:
            report_name = "گزارش"

        try:
            await bot.send_message(
                call.from_user.id,
                f"✅ <b>{report_name}</b> با موفقیت تولید و ارسال شد."
            )
        except Exception:
            pass
    except Exception as exc:
        logger.exception("Manual trigger of admin report failed: %s", exc)
        try:
            await bot.send_message(
                call.from_user.id,
                f"❌ <b>خطا در ارسال گزارش:</b>\n<code>{exc}</code>"
            )
        except Exception:
            pass


async def _render_hwid_inspector(
    bot: Bot, user, user_repo: UserRepository, remnawave: RemnawaveClient
) -> None:
    import bot.handlers.admin_ops as _ops
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

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

    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


async def _render_srh_inspector(
    bot: Bot, user, user_repo: UserRepository, remnawave: RemnawaveClient
) -> None:
    import bot.handlers.admin_ops as _ops
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

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

    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


async def _render_sessions_explorer(
    bot: Bot,
    user,
    user_repo: UserRepository,
    remnawave: RemnawaveClient,
    page: int = 0,
) -> None:
    import bot.handlers.admin_ops as _ops
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

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

    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


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

    import bot.handlers.admin_ops as _ops
    render_menu_fn = getattr(_ops, "render_menu", render_menu)
    await render_menu_fn(bot, user, user_repo, t(lang, "ord_search_prompt"), kb.as_markup())
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

    import bot.handlers.admin_ops as _ops
    order_repo_cls = getattr(_ops, "OrderRepository", OrderRepository)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

    order_repo = order_repo_cls(session)
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
        await render_menu_fn(
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
