"""Admin executive reports (nightly, weekly, monthly summaries)."""
import asyncio
from datetime import datetime, timedelta, timezone
from html import escape
import logging

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt
from bot.db.models import AlertState, User
from bot.db.repositories.order_repo import OrderRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.formatting import country_flag, format_date, human_bytes, parse_iso
from bot.services.remnawave import RemnawaveClient
from bot.services.reports.common import (
    _node_label,
    _weekday_name,
    make_node_flag_map,
)
from bot.services.reports.delivery import _deliver_admin_report
from bot.services.reports.jalali import (
    jalali_month_range,
    month_name,
)

logger = logging.getLogger(__name__)


async def _send_admin_nightly_summary(
    bot: Bot,
    session: AsyncSession,
    remnawave: RemnawaveClient,
    now: datetime,
    target_user_id: int | None = None,
) -> None:
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start.astimezone(timezone.utc)

    # 1. Orders & Revenue today
    order_repo = OrderRepository(session)
    orders_count = await order_repo.count(since=today_start_utc)
    revenue_today = await order_repo.total_revenue(since=today_start_utc)

    # 2. Wallet top-ups today
    wallet_repo = WalletRepository(session)
    topup_count, topup_amount = await wallet_repo.topup_stats(since=today_start_utc)

    total_payments = orders_count + topup_count
    total_amount = revenue_today + topup_amount
    payments_str = f"{total_payments} ({fmt(total_amount)} تومان)" if total_payments > 0 else "0"

    # 3. User growth
    user_repo = UserRepository(session)
    new_users = await user_repo.count(User.created_at >= today_start_utc)

    # 4. Cluster & Panel metrics
    panel_users = await remnawave.get_all_panel_users() or []
    total_panel_users = len(panel_users)
    active_panel_users = sum(
        1 for u in panel_users if str(u.get("status", "")).upper() == "ACTIVE"
    )

    # 5. Nodes telemetry & country totals
    nodes = await remnawave.get_nodes() or []
    country_totals: dict[str, int] = {}
    for n in nodes:
        cc = (n.get("countryCode") or "").upper()
        if cc:
            country_totals.setdefault(cc, 0)
        tb = n.get("todayTrafficBytes") or n.get("traffic") or 0
        try:
            val = int(tb)
            if cc:
                country_totals[cc] += val
        except (ValueError, TypeError):
            pass

    # 6. Active users today and their usage
    today_str = now.strftime("%Y-%m-%d")
    active_traffic_users = [
        u
        for u in panel_users
        if int(
            u.get("usedTrafficBytes")
            or (u.get("userTraffic") or {}).get("usedTrafficBytes")
            or 0
        )
        > 0
    ]

    sem = asyncio.Semaphore(10)

    async def _fetch_user_today(u: dict):
        uid = u.get("id")
        if not uid:
            return u, []
        async with sem:
            try:
                stats = (
                    await remnawave.get_user_bandwidth_stats(
                        int(uid), today_str, today_str
                    )
                    or []
                )
                return u, stats
            except Exception:
                return u, []

    user_stats_results = await asyncio.gather(
        *[_fetch_user_today(u) for u in active_traffic_users]
    )

    active_users_today: list[tuple[str, int, str]] = []
    user_country_totals: dict[str, int] = {}

    for u, stats in user_stats_results:
        username = str(u.get("username", "—"))
        user_node_usage: dict[str, int] = {}
        for row in stats:
            cc = (row.get("countryCode") or "").upper()
            data = row.get("data") or []
            val = int(data[-1]) if data else int(row.get("total") or 0)
            if val > 0:
                user_node_usage[cc] = user_node_usage.get(cc, 0) + val
                user_country_totals[cc] = user_country_totals.get(cc, 0) + val

        user_total = sum(user_node_usage.values())
        if user_total > 0:
            breakdown_parts = [
                f"{country_flag(cc)} {human_bytes(val)}"
                for cc, val in sorted(
                    user_node_usage.items(), key=lambda x: x[1], reverse=True
                )
            ]
            active_users_today.append((username, user_total, " ".join(breakdown_parts)))

    for cc, val in user_country_totals.items():
        if cc:
            country_totals[cc] = max(country_totals.get(cc, 0), val)

    total_bandwidth_today = sum(country_totals.values()) if country_totals else sum(
        u[1] for u in active_users_today
    )
    active_users_today.sort(key=lambda x: x[1], reverse=True)

    # 7. Expiring users in 0..3 days
    expiring_soon_users: list[tuple[int, str]] = []
    for u in panel_users:
        exp_iso = u.get("expireAt")
        if not exp_iso:
            continue
        exp_dt = parse_iso(exp_iso)
        if not exp_dt:
            continue
        days_left = (exp_dt.astimezone(now.tzinfo).date() - now.date()).days
        if 0 <= days_left <= 3:
            expiring_soon_users.append((days_left, str(u.get("username", "—"))))

    expiring_soon_users.sort(key=lambda x: (x[0], x[1].lower()))

    # 8. Expired users in last 24h
    one_day_ago = now - timedelta(days=1)
    expired_24h_users: list[str] = []
    for u in panel_users:
        exp_iso = u.get("expireAt")
        if not exp_iso:
            continue
        exp_dt = parse_iso(exp_iso)
        if not exp_dt:
            continue
        if one_day_ago <= exp_dt < now:
            expired_24h_users.append(str(u.get("username", "—")))

    expired_24h_users.sort(key=str.lower)

    # 9. Alerts sent today
    traffic_alerts_count = (
        await session.scalar(
            select(func.count(AlertState.account_id)).where(
                AlertState.traffic_alerted.is_(True),
                AlertState.updated_at >= today_start_utc,
            )
        )
        or 0
    )
    near_expiry_count = len(expiring_soon_users)
    expired_count = len(expired_24h_users)

    # Build report text
    date_str = format_date(now, "fa")
    lines = [
        f"👑 <b>گزارش جامع - {date_str} - 23:59</b>",
        SEPARATOR,
        "⚙️ <b>خلاصه وضعیت کل پنل</b>",
        f"👤 تعداد کل اکانت‌ها : {total_panel_users}",
        f"✅ اکانت‌های فعال : {active_panel_users}",
        f"➕ کاربران جدید امروز : {new_users}",
        f"💳 پرداخت‌های امروز : {payments_str}",
        f"⚡️ مصرف کل امروز : {human_bytes(total_bandwidth_today)}",
    ]

    if country_totals:
        for cc, val in sorted(country_totals.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"{country_flag(cc)} : {human_bytes(val)}")

    lines.append(SEPARATOR)
    lines.append("✅ <b>کاربران فعال امروز و مصرفشان</b>")
    if active_users_today:
        for i, (uname, u_total, b_str) in enumerate(active_users_today):
            lines.append(f"👤 {escape(uname)} : {human_bytes(u_total)}")
            lines.append(f" {b_str}")
            if i < len(active_users_today) - 1:
                lines.append("")
    else:
        lines.append("  (هیچ کاربری امروز مصرف نداشته است)")

    lines.append(SEPARATOR)
    lines.append("⚠️ <b>کاربرانی که تا ۳ روز آینده منقضی می شوند</b>")
    if expiring_soon_users:
        for d_left, uname in expiring_soon_users:
            lines.append(f"👤 {escape(uname)} : {d_left} روز")
    else:
        lines.append("  (هیچ کاربری در ۳ روز آینده منقضی نمی‌شود)")

    lines.append(SEPARATOR)
    lines.append("❌ <b>کاربران منقضی (24 ساعت اخیر)</b>")
    if expired_24h_users:
        for uname in expired_24h_users:
            lines.append(f"👤 {escape(uname)}")
    else:
        lines.append("  (هیچ کاربری در ۲۴ ساعت اخیر منقضی نشده است)")

    lines.append(SEPARATOR)
    lines.append("🔔 <b>هشدارهای ارسال شده امروز</b>")
    lines.append(f"کمبود حجم : {traffic_alerts_count}")
    lines.append(f"در آستانه انقضا : {near_expiry_count}")
    lines.append(f"منقضی شده : {expired_count}")

    text = "\n".join(lines)
    await _deliver_admin_report(bot, session, text, target_user_id=target_user_id)


async def _send_admin_weekly_summary(
    bot: Bot,
    session: AsyncSession,
    remnawave: RemnawaveClient,
    now: datetime,
    target_user_id: int | None = None,
) -> None:
    week_start = now - timedelta(days=6)
    week_start_utc = week_start.astimezone(timezone.utc)
    start_str = week_start.strftime("%Y-%m-%d")
    today_str = now.strftime("%Y-%m-%d")

    panel_users = await remnawave.get_all_panel_users() or []
    total_panel_users = len(panel_users)
    active_panel_users = sum(1 for u in panel_users if str(u.get("status", "")).upper() == "ACTIVE")

    # Orders & Wallet topups this week
    order_repo = OrderRepository(session)
    orders_count = await order_repo.count(since=week_start_utc)
    revenue_week = await order_repo.total_revenue(since=week_start_utc)

    wallet_repo = WalletRepository(session)
    topup_count, topup_amount = await wallet_repo.topup_stats(since=week_start_utc)

    weekly_payments = orders_count + topup_count
    weekly_amount = revenue_week + topup_amount
    weekly_payments_str = f"{weekly_payments} ({fmt(weekly_amount)} تومان)" if weekly_payments > 0 else "0"

    user_repo = UserRepository(session)
    new_users_week = await user_repo.count(User.created_at >= week_start_utc)

    active_traffic_users = [
        u
        for u in panel_users
        if int(
            u.get("usedTrafficBytes")
            or (u.get("userTraffic") or {}).get("usedTrafficBytes")
            or 0
        )
        > 0
    ]

    sem = asyncio.Semaphore(10)

    async def _fetch_user_week(u: dict):
        uid = u.get("id")
        if not uid:
            return u, []
        async with sem:
            try:
                stats = (
                    await remnawave.get_user_bandwidth_stats(
                        int(uid), start_str, today_str
                    )
                    or []
                )
                return u, stats
            except Exception:
                return u, []

    results = await asyncio.gather(*[_fetch_user_week(u) for u in active_traffic_users])

    all_nodes: list[dict] = []
    for u, stats in results:
        all_nodes.extend(stats)
    flag_map = make_node_flag_map(all_nodes)

    daily_champions: list[tuple[str, int]] = [("", 0) for _ in range(7)]
    user_weekly_totals: list[tuple[str, int]] = []
    day_totals: dict[int, int] = {i: 0 for i in range(7)}
    day_nodes: dict[int, dict[str, int]] = {i: {} for i in range(7)}
    weekly_nodes: dict[str, int] = {}

    for u, stats in results:
        username = str(u.get("username", "—"))
        user_total = 0
        user_day_totals = [0] * 7
        for row in stats:
            name = row.get("name") or row.get("nodeName") or "—"
            lbl = flag_map.get(name) or country_flag(row.get("countryCode"))
            data = row.get("data") or []
            last_7 = data[-7:] if len(data) >= 7 else ([0] * (7 - len(data)) + data)
            for d_idx in range(7):
                val = int(last_7[d_idx] or 0)
                if val > 0:
                    user_day_totals[d_idx] += val
                    day_nodes[d_idx][lbl] = day_nodes[d_idx].get(lbl, 0) + val
                    weekly_nodes[lbl] = weekly_nodes.get(lbl, 0) + val

        for d_idx in range(7):
            day_bytes = user_day_totals[d_idx]
            user_total += day_bytes
            day_totals[d_idx] += day_bytes
            if day_bytes > daily_champions[d_idx][1]:
                daily_champions[d_idx] = (username, day_bytes)
        if user_total > 0:
            user_weekly_totals.append((username, user_total))

    user_weekly_totals.sort(key=lambda x: x[1], reverse=True)
    week_total = sum(day_totals.values())

    date_str = format_date(now, "fa")
    lines = [
        f"👑 <b>گزارش جامع هفتگی پنل — {date_str}</b>",
        SEPARATOR,
        "⚙️ <b>خلاصه وضعیت هفته</b>",
        f"👤 تعداد کل اکانت‌ها : {total_panel_users}",
        f"✅ اکانت‌های فعال : {active_panel_users}",
        f"➕ کاربران جدید این هفته : {new_users_week}",
        f"💳 پرداخت‌های این هفته : {weekly_payments_str}",
        SEPARATOR,
        "⚡️ <b>مصرف روزانه کل پنل در ۷ روز اخیر:</b>",
    ]

    for d_idx in range(6, -1, -1):
        day_dt = week_start + timedelta(days=d_idx)
        d_name = _weekday_name(day_dt, "fa")
        d_str = format_date(day_dt, "fa")
        d_val = day_totals.get(d_idx, 0)
        lines.append("")
        lines.append(f"📅 {d_name} {d_str} : <b>{human_bytes(d_val)}</b>")
        sorted_nodes = sorted(day_nodes[d_idx].items(), key=lambda x: x[1], reverse=True)
        parts = [f"{lbl} {human_bytes(val)}" for lbl, val in sorted_nodes if val > 0]
        if parts:
            lines.append(f"   {' '.join(parts)}")

    lines.append("")
    lines.append(SEPARATOR)
    lines.append(f"⚡️ <b>مجموع مصرف کل این هفته : {human_bytes(week_total)}</b>")
    weekly_parts = [
        f"{lbl} {human_bytes(val)}"
        for lbl, val in sorted(weekly_nodes.items(), key=lambda x: x[1], reverse=True)
        if val > 0
    ]
    if weekly_parts:
        lines.append(f"   {' '.join(weekly_parts)}")

    lines.append(SEPARATOR)
    lines.append("🏆 <b>گزارش هفتگی پرمصرفترین کاربران</b>")
    lines.append("🥇 <b>۲۰ کاربر برتر این هفته:</b>")
    top_20 = user_weekly_totals[:20]
    if top_20:
        for rank, (uname, total_bytes) in enumerate(top_20, start=1):
            lines.append(f"{rank}. 👤 {escape(uname)} ({human_bytes(total_bytes)})")
    else:
        lines.append("  (هیچ مصرفی در این هفته ثبت نشده است)")

    lines.append(SEPARATOR)
    lines.append("🔥 <b>قهرمان هر روز هفته:</b>")
    for d_idx in range(7):
        day_dt = week_start + timedelta(days=d_idx)
        day_name = _weekday_name(day_dt, "fa")
        prefix = "🎉" if day_dt.weekday() == 4 else "🗓️"
        champ_uname, champ_bytes = daily_champions[d_idx]
        if champ_bytes > 0:
            lines.append(
                f"{prefix} {day_name}: {escape(champ_uname)} ({human_bytes(champ_bytes)})"
            )
        else:
            lines.append(f"{prefix} {day_name}: —")

    text = "\n".join(lines)
    await _deliver_admin_report(bot, session, text, target_user_id=target_user_id)


async def _send_admin_monthly_summary(
    bot: Bot,
    session: AsyncSession,
    remnawave: RemnawaveClient,
    now: datetime,
    target_user_id: int | None = None,
) -> None:
    month_start, month_end = jalali_month_range(now)
    month_start_utc = month_start.astimezone(timezone.utc)
    start_str = month_start.strftime("%Y-%m-%d")
    today_str = now.strftime("%Y-%m-%d")
    month_name_fa = month_name(now, "fa")
    days_count = (now.date() - month_start.date()).days + 1

    panel_users = await remnawave.get_all_panel_users() or []
    active_traffic_users = [
        u
        for u in panel_users
        if int(
            u.get("usedTrafficBytes")
            or (u.get("userTraffic") or {}).get("usedTrafficBytes")
            or 0
        )
        > 0
    ]

    order_repo = OrderRepository(session)
    orders_count = await order_repo.count(since=month_start_utc)
    revenue_month = await order_repo.total_revenue(since=month_start_utc)

    wallet_repo = WalletRepository(session)
    topup_count, topup_amount = await wallet_repo.topup_stats(since=month_start_utc)

    monthly_payments = orders_count + topup_count
    monthly_amount = revenue_month + topup_amount
    monthly_payments_str = f"{monthly_payments} ({fmt(monthly_amount)} تومان)" if monthly_payments > 0 else "0"

    user_repo = UserRepository(session)
    new_users_month = await user_repo.count(User.created_at >= month_start_utc)

    total_panel_users = len(panel_users)
    active_panel_users = sum(1 for u in panel_users if str(u.get("status", "")).upper() == "ACTIVE")

    sem = asyncio.Semaphore(10)

    async def _fetch_user_month(u: dict):
        uid = u.get("id")
        if not uid:
            return u, []
        async with sem:
            try:
                stats = (
                    await remnawave.get_user_bandwidth_stats(
                        int(uid), start_str, today_str
                    )
                    or []
                )
                return u, stats
            except Exception:
                return u, []

    results = await asyncio.gather(*[_fetch_user_month(u) for u in active_traffic_users])

    day_totals: dict[int, int] = {i: 0 for i in range(days_count)}
    day_nodes: dict[int, dict[str, int]] = {i: {} for i in range(days_count)}
    monthly_nodes: dict[str, int] = {}
    user_monthly_totals: list[tuple[str, int]] = []

    for u, stats in results:
        username = str(u.get("username", "—"))
        user_total = 0
        for d_idx in range(days_count):
            day_bytes = 0
            for row in stats:
                label = _node_label(row)
                data = row.get("data") or []
                if d_idx < len(data):
                    val = int(data[d_idx] or 0)
                    if val > 0:
                        day_bytes += val
                        day_nodes[d_idx][label] = day_nodes[d_idx].get(label, 0) + val
                        monthly_nodes[label] = monthly_nodes.get(label, 0) + val
            user_total += day_bytes
            day_totals[d_idx] += day_bytes
        if user_total > 0:
            user_monthly_totals.append((username, user_total))

    user_monthly_totals.sort(key=lambda x: x[1], reverse=True)
    month_total = sum(day_totals.values())

    lines = [
        f"👑 <b>گزارش جامع ماهانه پنل — {month_name_fa}</b>",
        SEPARATOR,
        "⚙️ <b>خلاصه وضعیت ماه</b>",
        f"👤 تعداد کل اکانت‌ها : {total_panel_users}",
        f"✅ اکانت‌های فعال : {active_panel_users}",
        f"➕ کاربران جدید این ماه : {new_users_month}",
        f"💳 پرداخت‌های این ماه : {monthly_payments_str}",
        SEPARATOR,
        f"⚡️ <b>مجموع مصرف کل ماه {month_name_fa} : {human_bytes(month_total)}</b>",
    ]

    for lbl, val in sorted(monthly_nodes.items(), key=lambda x: x[1], reverse=True)[:8]:
        if val > 0:
            lines.append(f"{lbl} : {human_bytes(val)}")

    busiest_days = sorted(
        [(d_idx, day_totals[d_idx]) for d_idx in range(days_count) if day_totals[d_idx] > 0],
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    if busiest_days:
        lines.append(SEPARATOR)
        lines.append("📈 <b>پرمصرف‌ترین روزهای ماه:</b>")
        for rank, (d_idx, val) in enumerate(busiest_days, start=1):
            day_dt = month_start + timedelta(days=d_idx)
            d_name = _weekday_name(day_dt, "fa")
            d_str = format_date(day_dt, "fa")
            lines.append(f"{rank}. {d_name} {d_str} : <b>{human_bytes(val)}</b>")

    lines.append(SEPARATOR)
    lines.append(f"🏆 <b>پرمصرف‌ترین کاربران ماه {month_name_fa} (Top 10):</b>")
    top_10 = user_monthly_totals[:10]
    if top_10:
        for rank, (uname, total_bytes) in enumerate(top_10, start=1):
            lines.append(f"{rank}. 👤 {escape(uname)} : <b>{human_bytes(total_bytes)}</b>")
    else:
        lines.append("  (هیچ مصرفی در این ماه ثبت نشده است)")

    text = "\n".join(lines)
    await _deliver_admin_report(bot, session, text, target_user_id=target_user_id)
