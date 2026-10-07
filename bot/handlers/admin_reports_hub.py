"""Admin Reports Hub, Diagnostics, HWID, SRH, and Live Sessions Explorer."""
import logging
import math
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, is_admin, resolve_op
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.formatting import country_flag
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)
router = Router(name="admin_reports_hub")

_is_admin = is_admin


async def _render_reports_hub(
    bot: Bot,
    user,
    user_repo: UserRepository,
    session: AsyncSession,
    remnawave: RemnawaveClient,
) -> None:
    render_menu_fn = resolve_op("render_menu", render_menu)

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
    from bot.config import get_settings
    from bot.services.formatting import now_tz
    from bot.services.reports import (
        _send_admin_monthly_summary,
        _send_admin_nightly_summary,
        _send_admin_weekly_summary,
    )
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
    render_menu_fn = resolve_op("render_menu", render_menu)

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
    render_menu_fn = resolve_op("render_menu", render_menu)

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
    render_menu_fn = resolve_op("render_menu", render_menu)

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

    target_users = multi_users if multi_users else data.get("all_online_users", [])
    PER_PAGE = 5
    total_pages = max(1, math.ceil(len(target_users) / PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    current_batch = target_users[page * PER_PAGE : (page + 1) * PER_PAGE]

    if current_batch:
        header_title = (
            f"📋 <b>کاربران با بیش از یک IP (صفحه {page + 1} از {total_pages}):</b>"
            if multi_users
            else f"📋 <b>لیست اتصالات کاربران آنلاین (صفحه {page + 1} از {total_pages}):</b>"
        ) if lang == "fa" else (
            f"📋 <b>Multi-IP Users List (Page {page + 1}/{total_pages}):</b>"
            if multi_users
            else f"📋 <b>Online Connected Users (Page {page + 1}/{total_pages}):</b>"
        )
        lines.append(header_title)
        lines.append("")
        for idx, u in enumerate(current_batch, start=page * PER_PAGE + 1):
            uname = escape(str(u["username"]))
            ip_cnt = len(u["uniqueIps"])
            badge = f" — ⚠️ <code>{ip_cnt} IP</code>" if ip_cnt > 1 else f" — <code>{ip_cnt} IP</code>"
            lines.append(f" {idx}) 👤 <b>{uname}</b>{badge}")
            for nc in u["nodeConnections"]:
                flag = country_flag(nc.get("countryCode"))
                n_name = escape(str(nc.get("nodeName") or "Node"))
                for ip in nc.get("ips", []):
                    lines.append(f"     ▫️ {flag} {n_name} : <code>{escape(str(ip))}</code>")
            lines.append("")
    else:
        lines.append(
            "🟢 <i>در حال حاضر اتصال فعالی روی نودها ثبت نشده است.</i>"
            if lang == "fa"
            else "🟢 <i>No active sessions found across nodes.</i>"
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
    kb.button(
        text="🌐 Sessions Explorer در پنل",
        url="https://dashboard.cloudvibe.ir/dashboard/tools/sessions-explorer",
    )
    kb.button(text="🔙 بازگشت به گزارشات", callback_data="adm:sales")
    kb.adjust(len(nav_row) if nav_row else 1, 1, 1, 1)

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
    render_hub_fn = resolve_op("_render_reports_hub", _render_reports_hub)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await state.clear()
    await render_hub_fn(bot, user, user_repo, session, remnawave)
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
    render_hwid_fn = resolve_op("_render_hwid_inspector", _render_hwid_inspector)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_hwid_fn(bot, user, user_repo, remnawave)
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
    render_srh_fn = resolve_op("_render_srh_inspector", _render_srh_inspector)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_srh_fn(bot, user, user_repo, remnawave)
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
    render_sessions_fn = resolve_op("_render_sessions_explorer", _render_sessions_explorer)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_sessions_fn(bot, user, user_repo, remnawave, page=page)
    await call.answer()
