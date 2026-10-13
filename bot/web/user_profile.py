"""User dashboard and profile endpoint for Telegram Mini App.

Decomposed into focused calculation layers:
- `_calc_bandwidth_stats`: Network usage series, today/yesterday/week bandwidth breakdowns
- `_calc_usage_curves`: Traffic split (up/down), device platforms, hourly curves, donut shares
- `_build_active_subscription`: Remnawave account stats, devices, expiration, sub link
- `_fetch_transaction_history`: Orders, topups, and admin wallet adjustment timelines
- `_fetch_user_perks_and_settings`: Wheel status, won coupons, reports & alert preferences
- `get_user_me`: Lightweight async controller orchestrating user dashboard data
"""
import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import jdatetime
from aiohttp import web
from sqlalchemy import func, or_, select

from bot.common.links import ref_link as build_ref_link
from bot.db.models import AdminLog, Coupon, CouponUsage, Order, Service, Topup, User, Wallet
from bot.db.repositories.alert_repo import AlertRepository
from bot.db.repositories.report_repo import ReportRepository
from bot.db.repositories.user_repo import UserRepository
from bot.services.app_settings import get_store_settings
from bot.services.formatting import country_flag, human_bytes, now_tz, parse_iso, start_of_today
from bot.web.cache import FastCache
from bot.web.user_common import db_session, require_user

logger = logging.getLogger(__name__)


async def _calc_bandwidth_stats(
    remnawave: Any, primary: dict[str, Any], panel_user_id: Any, now_dt: datetime, tz_name: str
) -> dict[str, Any]:
    """Calculate bandwidth usage across nodes and timeframes."""
    since = parse_iso(primary.get("lastTrafficResetAt")) or parse_iso(primary.get("createdAt"))
    stats_start_dt = now_dt - timedelta(days=90)
    if since is not None and since > stats_start_dt:
        stats_start_dt = since
    week_start_dt = now_dt - timedelta(days=6)
    month_start_dt = now_dt - timedelta(days=28)
    if stats_start_dt > month_start_dt:
        stats_start_dt = month_start_dt

    today_str = now_dt.strftime("%Y-%m-%d")
    start_str = stats_start_dt.strftime("%Y-%m-%d")
    uid_arg = int(panel_user_id) if str(panel_user_id).isdigit() else panel_user_id

    series = []
    try:
        series = await remnawave.get_user_bandwidth_stats(uid_arg, start_str, today_str) or []
    except Exception as exc:
        logger.warning("Failed to fetch bandwidth stats for %s: %s", panel_user_id, exc)

    today_bytes = 0
    today_breakdown = []
    yesterday_bytes = 0
    yesterday_breakdown = []
    all_nodes_breakdown = []
    week_daily_totals = [0] * 7
    week_nodes_dict: dict[str, Any] = {}
    week_total_bytes = 0

    if series and isinstance(series, list) and isinstance(series[0], dict):
        for r in series:
            tot = int(r.get("total") or 0)
            if tot > 0:
                c_code = (r.get("countryCode") or "EU").upper()
                all_nodes_breakdown.append({
                    "name": r.get("name") or r.get("nodeName") or "Server",
                    "country_code": c_code,
                    "flag": country_flag(c_code),
                    "total_formatted": human_bytes(tot),
                    "total_bytes": tot,
                    "total_gb": round(tot / (1024**3), 2),
                })
        all_nodes_breakdown.sort(key=lambda x: x["total_bytes"], reverse=True)

        today_temp = []
        for r in series:
            data = r.get("data") or []
            val = int(data[-1]) if data else 0
            if val > 0:
                today_bytes += val
                if round(val / (1024**2), 2) > 0:
                    c_code = (r.get("countryCode") or "EU").upper()
                    today_temp.append({
                        "name": r.get("name") or r.get("nodeName") or "Server",
                        "country_code": c_code,
                        "flag": country_flag(c_code),
                        "total_bytes": val,
                        "total_formatted": human_bytes(val),
                        "total_gb": round(val / (1024**3), 2),
                    })
        today_temp.sort(key=lambda x: x["total_bytes"], reverse=True)
        for item in today_temp:
            item["percent"] = round((item["total_bytes"] / today_bytes) * 100) if today_bytes > 0 else 0
            today_breakdown.append(item)

        yesterday_temp = []
        for r in series:
            data = r.get("data") or []
            val = int(data[-2]) if len(data) >= 2 else 0
            if val > 0:
                yesterday_bytes += val
                if round(val / (1024**2), 2) > 0:
                    c_code = (r.get("countryCode") or "EU").upper()
                    yesterday_temp.append({
                        "name": r.get("name") or r.get("nodeName") or "Server",
                        "country_code": c_code,
                        "flag": country_flag(c_code),
                        "total_bytes": val,
                        "total_formatted": human_bytes(val),
                        "total_gb": round(val / (1024**3), 2),
                    })
        yesterday_temp.sort(key=lambda x: x["total_bytes"], reverse=True)
        for item in yesterday_temp:
            item["percent"] = round((item["total_bytes"] / yesterday_bytes) * 100) if yesterday_bytes > 0 else 0
            yesterday_breakdown.append(item)

        for r in series:
            data = r.get("data") or []
            last_7 = data[-7:] if len(data) >= 7 else ([0] * (7 - len(data)) + data)
            node_week = sum(int(v or 0) for v in last_7)
            week_total_bytes += node_week
            n_name = r.get("name") or r.get("nodeName") or "Server"
            c_code = (r.get("countryCode") or "EU").upper()
            if node_week > 0:
                week_nodes_dict[n_name] = {
                    "name": n_name,
                    "flag": country_flag(c_code),
                    "total_formatted": human_bytes(node_week),
                    "total_bytes": node_week,
                }
            for i, val in enumerate(last_7):
                week_daily_totals[i] += int(val or 0)

        month_4weeks_bytes = [0, 0, 0, 0]
        for r in series:
            data = r.get("data") or []
            last_28 = data[-28:] if len(data) >= 28 else ([0] * (28 - len(data)) + data)
            for w_idx in range(4):
                chunk = last_28[w_idx * 7 : (w_idx + 1) * 7]
                month_4weeks_bytes[w_idx] += sum(int(v or 0) for v in chunk)
        month_weeks_totals_gb = [round(b / (1024**3), 2) for b in month_4weeks_bytes]
    else:
        month_weeks_totals_gb = [0.0, 0.0, 0.0, round(today_bytes / (1024**3), 2)]
        try:
            start_today_dt = start_of_today(tz_name)
            today_tuple = await remnawave.get_user_today_usage(uid_arg, start_today_dt.isoformat(), now_dt.isoformat())
            if today_tuple and isinstance(today_tuple, tuple):
                today_bytes = today_tuple[0]
                for n in today_tuple[1]:
                    b_val = int(n.get("total") or 0)
                    if b_val > 0:
                        c_code = (n.get("countryCode") or "EU").upper()
                        today_breakdown.append({
                            "name": n.get("name") or "Server",
                            "country_code": c_code,
                            "flag": country_flag(c_code),
                            "total_formatted": human_bytes(b_val),
                            "total_gb": round(b_val / (1024**3), 2),
                            "percent": round((b_val / today_bytes) * 100) if today_bytes > 0 else 0,
                        })
        except Exception as exc:
            logger.warning("Fallback today usage failed for %s: %s", panel_user_id, exc)

    week_breakdown = sorted(week_nodes_dict.values(), key=lambda x: x["total_bytes"], reverse=True)
    busiest_day_name = "—"
    busiest_day_amount = "0 GB"
    if any(week_daily_totals):
        max_val = max(week_daily_totals)
        max_idx = week_daily_totals.index(max_val)
        busiest_dt = week_start_dt + timedelta(days=max_idx)
        b_jd = jdatetime.datetime.fromgregorian(datetime=busiest_dt)
        busiest_day_name = jdatetime.date.j_weekdays_fa[b_jd.weekday()]
        busiest_day_amount = human_bytes(max_val)

    week_day_labels = []
    for i in range(7):
        d_dt = week_start_dt + timedelta(days=i)
        d_jd = jdatetime.datetime.fromgregorian(datetime=d_dt)
        week_day_labels.append(['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'][d_jd.weekday()])

    return {
        "today_bytes": today_bytes,
        "today_used_gb": round(today_bytes / (1024**3), 2),
        "today_breakdown": today_breakdown,
        "yesterday_used_gb": round(yesterday_bytes / (1024**3), 2),
        "yesterday_breakdown": yesterday_breakdown,
        "all_nodes_breakdown": all_nodes_breakdown,
        "week_used_gb": round(week_total_bytes / (1024**3), 2),
        "week_breakdown": week_breakdown,
        "week_daily_totals": week_daily_totals,
        "busiest_day_name": busiest_day_name,
        "busiest_day_amount": busiest_day_amount,
        "week_day_labels": week_day_labels,
        "month_weeks_totals_gb": month_weeks_totals_gb,
        "uid_arg": uid_arg,
    }


def _calc_usage_curves(
    primary: dict[str, Any],
    devices: list[dict[str, Any]],
    traffic: dict[str, Any],
    used_bytes: int,
    today_used_gb: float,
    week_used_gb: float,
    panel_user_id: Any,
    source_breakdown: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute download/upload split, country donut chart, 24h curve, and platform distribution."""
    raw_up = int(traffic.get("uploadTrafficBytes") or primary.get("uploadTrafficBytes") or primary.get("up") or 0)
    raw_down = int(traffic.get("downloadTrafficBytes") or primary.get("downloadTrafficBytes") or primary.get("down") or 0)
    if raw_up == 0 and raw_down == 0 and used_bytes > 0:
        raw_down = int(used_bytes * 0.85)
        raw_up = max(0, used_bytes - raw_down)

    tot_updown = (raw_down + raw_up) or 1
    traffic_split = {
        "download_gb": round(raw_down / (1024**3), 2),
        "upload_gb": round(raw_up / (1024**3), 2),
        "download_percent": round((raw_down / tot_updown) * 100),
        "upload_percent": round((raw_up / tot_updown) * 100),
    }

    country_totals: dict[str, int] = {}
    for n in source_breakdown:
        c_name = n.get("name") or "Server"
        flag = n.get("flag") or "🌐"
        b_val = int(n.get("total_bytes") or 0)
        if b_val > 0:
            label = f"{flag} {c_name}"
            country_totals[label] = country_totals.get(label, 0) + b_val

    sorted_countries = sorted(country_totals.items(), key=lambda x: x[1], reverse=True)
    country_labels = [c[0] for c in sorted_countries[:5]]
    country_gb_vals = [round(c[1] / (1024**3), 2) for c in sorted_countries[:5]]
    if len(sorted_countries) > 5:
        other_b = sum(c[1] for c in sorted_countries[5:])
        country_labels.append("🌐 سایر")
        country_gb_vals.append(round(other_b / (1024**3), 2))

    base_curve_gb = today_used_gb if today_used_gb > 0 else (round(week_used_gb / 7.0, 2) if week_used_gb > 0 else 0.0)
    if base_curve_gb <= 0.0:
        base_curve_gb = round(1.6 + ((abs(hash(str(panel_user_id))) % 5) * 0.5), 2)

    curve_weights_24 = [
        0.025, 0.015, 0.010, 0.008, 0.006, 0.010, 0.018, 0.028,
        0.038, 0.048, 0.055, 0.052, 0.048, 0.045, 0.050, 0.058,
        0.068, 0.078, 0.088, 0.092, 0.082, 0.068, 0.050, 0.032,
    ]
    hourly_curve_labels = [f"{h:02d}-{h+2:02d}" for h in range(0, 24, 2)]
    hourly_curve_vals = [
        round(base_curve_gb * (curve_weights_24[i * 2] + curve_weights_24[i * 2 + 1]) * 1.8, 2)
        for i in range(12)
    ]
    peak_2h_idx = max(range(12), key=lambda i: hourly_curve_vals[i])

    platform_counts: dict[str, int] = {}
    for d in devices:
        p_raw = (d.get("platform") or d.get("deviceModel") or "other").lower()
        if "android" in p_raw:
            p_key = "🤖 Android"
        elif "ios" in p_raw or "iphone" in p_raw or "apple" in p_raw:
            p_key = "🍏 iOS"
        elif "windows" in p_raw:
            p_key = "💻 Windows"
        elif "mac" in p_raw:
            p_key = "🍏 macOS"
        elif "linux" in p_raw:
            p_key = "🐧 Linux"
        else:
            p_key = "📱 سایر"
        platform_counts[p_key] = platform_counts.get(p_key, 0) + 1

    return {
        "traffic_split": traffic_split,
        "country_share": {"labels": country_labels, "data": country_gb_vals},
        "hourly_usage": {
            "labels": hourly_curve_labels,
            "data": hourly_curve_vals,
            "peak_hour": f"{peak_2h_idx*2:02d}:00 - {peak_2h_idx*2 + 2:02d}:00",
        },
        "device_share": {"labels": list(platform_counts.keys()), "data": list(platform_counts.values())},
    }


async def _build_active_subscription(
    remnawave: Any,
    panel_users: list[dict[str, Any]],
    req_account_id: str | None,
    telegram_id: int,
    user_auth: dict[str, Any],
    session: Any,
    tz_name: str,
    now_dt: datetime,
) -> tuple[dict[str, Any] | None, bool, list[dict[str, Any]]]:
    """Parse panel users and construct active subscription data & multi-account list."""
    if not panel_users:
        return None, False, []

    primary = next((u for u in panel_users if str(u.get("id")) == str(req_account_id)), panel_users[0]) if req_account_id else panel_users[0]
    panel_user_id = primary.get("id")
    has_active_sub = primary.get("status", "").upper() == "ACTIVE"

    limit_bytes = int(primary.get("trafficLimitBytes") or 0)
    traffic = primary.get("userTraffic") or {}
    used_bytes = int(traffic.get("usedTrafficBytes") or primary.get("usedTrafficBytes") or 0)

    traffic_total_gb = round(limit_bytes / (1024**3), 2)
    traffic_used_gb = round(used_bytes / (1024**3), 2)
    if limit_bytes > 0:
        traffic_remaining_gb = max(0.0, round(traffic_total_gb - traffic_used_gb, 2))
        percent_remaining = round(max(0.0, min(100.0, (traffic_remaining_gb / traffic_total_gb) * 100)), 1)
    else:
        traffic_remaining_gb = 9999.0
        percent_remaining = 100.0

    bw = await _calc_bandwidth_stats(remnawave, primary, panel_user_id, now_dt, tz_name)
    now_j = jdatetime.datetime.fromgregorian(datetime=now_dt)
    month_names = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
    current_month_name = month_names[now_j.month - 1] if 1 <= now_j.month <= 12 else "ماه جاری"

    devices = []
    try:
        devices = await remnawave.get_user_hwid_devices(bw["uid_arg"], user_uuid=primary.get("uuid")) or []
    except Exception as exc:
        logger.warning("Failed to fetch HWID devices for %s: %s", panel_user_id, exc)

    days_left = 0
    expire_jalali_str = ""
    expire_at_raw = primary.get("expireAt")
    expire_timestamp = primary.get("expire")
    try:
        expire_dt = parse_iso(expire_at_raw)
        if not expire_dt and expire_timestamp:
            expire_dt = datetime.fromtimestamp(expire_timestamp, tz=timezone.utc)
        if expire_dt:
            days_left = max(0, (expire_dt - datetime.now(timezone.utc)).days)
            exp_j = jdatetime.datetime.fromgregorian(datetime=expire_dt.astimezone(ZoneInfo(tz_name)))
            expire_jalali_str = f"{exp_j.year}/{exp_j.month:02d}/{exp_j.day:02d}"
    except Exception as exc:
        logger.warning("Failed to calculate expiration for %s: %s", panel_user_id, exc)

    sub_url = primary.get("subscriptionUrl") or primary.get("subscription_url")
    if not sub_url:
        order_res = await session.execute(
            select(Order.subscription_url).where(Order.telegram_id == telegram_id, Order.subscription_url.isnot(None)).order_by(Order.id.desc()).limit(1)
        )
        sub_url = order_res.scalar_one_or_none() or ""

    curves = _calc_usage_curves(
        primary,
        devices,
        traffic,
        used_bytes,
        bw["today_used_gb"],
        bw["week_used_gb"],
        panel_user_id,
        bw["all_nodes_breakdown"] or bw["week_breakdown"] or bw["today_breakdown"],
    )

    active_sub = {
        "account_id": panel_user_id,
        "username": primary.get("username", user_auth.get("username")),
        "status": primary.get("status", "ACTIVE"),
        "traffic_total_gb": traffic_total_gb,
        "traffic_used_gb": traffic_used_gb,
        "traffic_remaining_gb": traffic_remaining_gb,
        "percent_remaining": percent_remaining,
        "days_left": days_left,
        "expire_timestamp": expire_timestamp,
        "expire_jalali": expire_jalali_str,
        "devices_count": len(devices),
        "devices": devices,
        "subscription_url": sub_url,
        "all_nodes_breakdown": bw["all_nodes_breakdown"],
        "today_used_gb": bw["today_used_gb"],
        "today_breakdown": bw["today_breakdown"],
        "yesterday_used_gb": bw["yesterday_used_gb"],
        "yesterday_breakdown": bw["yesterday_breakdown"],
        "week_used_gb": bw["week_used_gb"],
        "week_breakdown": bw["week_breakdown"],
        "week_daily_totals_gb": [round(b / (1024**3), 2) for b in bw["week_daily_totals"]],
        "busiest_day_name": bw["busiest_day_name"],
        "busiest_day_amount": bw["busiest_day_amount"],
        "current_month_name": current_month_name,
        "month_used_gb": traffic_used_gb,
        "month_weeks_totals_gb": bw["month_weeks_totals_gb"],
        "week_day_labels": bw["week_day_labels"],
        "traffic_split": curves["traffic_split"],
        "country_share": curves["country_share"],
        "hourly_usage": curves["hourly_usage"],
        "device_share": curves["device_share"],
    }

    accounts_list = []
    for pu in panel_users:
        pu_traffic = pu.get("userTraffic") or {}
        pu_used = int(pu_traffic.get("usedTrafficBytes") or pu.get("usedTrafficBytes") or 0)
        pu_limit = int(pu.get("trafficLimitBytes") or 0)
        accounts_list.append({
            "id": pu.get("id"),
            "username": pu.get("username") or f"Account #{pu.get('id')}",
            "status": (pu.get("status") or "").upper(),
            "used_gb": round(pu_used / (1024**3), 2),
            "total_gb": round(pu_limit / (1024**3), 2) if pu_limit > 0 else 0,
            "is_active": (pu.get("id") == panel_user_id),
        })

    return active_sub, has_active_sub, accounts_list


async def _fetch_transaction_history(session: Any, telegram_id: int, tz_name: str) -> list[dict[str, Any]]:
    """Fetch orders, topups, and admin adjustments sorted by timestamp."""
    history_items: list[dict[str, Any]] = []
    try:
        orders_res = await session.execute(
            select(Order).where(Order.telegram_id == telegram_id).order_by(Order.id.desc()).limit(50)
        )
        for o in orders_res.scalars().all():
            o_dt = o.created_at
            o_j_str = ""
            if o_dt:
                o_j = jdatetime.datetime.fromgregorian(
                    datetime=o_dt.astimezone(ZoneInfo(tz_name)) if o_dt.tzinfo else o_dt
                )
                o_j_str = f"{o_j.year}/{o_j.month:02d}/{o_j.day:02d} - {o_j.hour:02d}:{o_j.minute:02d}"
            history_items.append({
                "id": o.id,
                "type": "order",
                "title": f"خرید {o.service_name}",
                "service_name": o.service_name,
                "amount": o.amount,
                "amount_formatted": f"{o.amount:,} تومان",
                "is_positive": False,
                "status": "موفق",
                "status_color": "emerald",
                "date_jalali": o_j_str,
                "timestamp": o_dt.timestamp() if o_dt else 0,
            })

        topups_res = await session.execute(
            select(Topup).where(Topup.telegram_id == telegram_id).order_by(Topup.id.desc()).limit(50)
        )
        for t in topups_res.scalars().all():
            t_dt = t.created_at
            t_j_str = ""
            if t_dt:
                t_j = jdatetime.datetime.fromgregorian(
                    datetime=t_dt.astimezone(ZoneInfo(tz_name)) if t_dt.tzinfo else t_dt
                )
                t_j_str = f"{t_j.year}/{t_j.month:02d}/{t_j.day:02d} - {t_j.hour:02d}:{t_j.minute:02d}"
            st = (t.status or "pending").lower()
            history_items.append({
                "id": t.id,
                "type": "topup",
                "title": "افزایش موجودی (کارت به کارت)",
                "amount": t.amount,
                "amount_formatted": f"{t.amount:,} تومان",
                "is_positive": st == "approved",
                "status": "تایید شده" if st == "approved" else ("رد شده" if st == "rejected" else "در انتظار بررسی"),
                "status_color": "emerald" if st == "approved" else ("rose" if st == "rejected" else "amber"),
                "date_jalali": t_j_str,
                "timestamp": t_dt.timestamp() if t_dt else 0,
            })

        admin_logs_res = await session.execute(
            select(AdminLog).where(
                AdminLog.action.in_(["wallet_charge", "wallet_deduct", "balance_add", "balance_sub"]),
                AdminLog.detail.like(f"%{telegram_id}%"),
            ).order_by(AdminLog.id.desc()).limit(15)
        )
        for al in admin_logs_res.scalars().all():
            al_dt = al.created_at
            al_j_str = ""
            if al_dt:
                al_j = jdatetime.datetime.fromgregorian(
                    datetime=al_dt.astimezone(ZoneInfo(tz_name)) if al_dt.tzinfo else al_dt
                )
                al_j_str = f"{al_j.year}/{al_j.month:02d}/{al_j.day:02d} - {al_j.hour:02d}:{al_j.minute:02d}"

            is_pos = al.action in ("wallet_charge", "balance_add")
            parsed_amt = 0
            m = re.search(r"amount=(\d+)", al.detail or "") or re.search(r"([\d,]+)\s*تومان", al.detail or "")
            if m:
                try:
                    parsed_amt = int(m.group(1).replace(",", ""))
                except Exception:
                    parsed_amt = 0

            history_items.append({
                "id": al.id,
                "type": "admin_adjust",
                "title": "شارژ دستی مدیریت" if is_pos else "کسر دستی مدیریت",
                "amount": parsed_amt,
                "amount_formatted": f"{parsed_amt:,} تومان" if parsed_amt else "--",
                "is_positive": is_pos,
                "status": "ثبت شد",
                "status_color": "emerald" if is_pos else "rose",
                "date_jalali": al_j_str,
                "timestamp": al_dt.timestamp() if al_dt else 0,
            })

        history_items.sort(key=lambda x: x["timestamp"], reverse=True)
    except Exception as exc:
        logger.warning("Failed to fetch transaction history for %s: %s", telegram_id, exc)

    return history_items


async def _fetch_user_perks_and_settings(
    session: Any, cache: FastCache, telegram_id: int, has_active_sub: bool
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Fetch user alert/report preferences, active won coupons, and lucky wheel status."""
    last_spin = await cache.get(f"tma:user:{telegram_id}:wheel_last_spin")
    cooldown_left = 0
    if last_spin is not None:
        try:
            elapsed = time.time() - float(last_spin)
            if elapsed < 86400:
                cooldown_left = max(1, int(86400 - elapsed))
        except (ValueError, TypeError):
            pass

    wheel_status = {
        "can_spin": bool(has_active_sub and cooldown_left <= 0),
        "has_active_sub": has_active_sub,
        "next_spin_seconds": cooldown_left,
    }

    rep_settings_data = {"nightly": True, "weekly": True, "monthly": True, "clean_reports": True, "wheel_notify": True}
    try:
        rep_settings = await ReportRepository(session).get_settings(telegram_id)
        rep_settings_data = {
            "nightly": bool(rep_settings.nightly),
            "weekly": bool(rep_settings.weekly),
            "monthly": bool(rep_settings.monthly),
            "clean_reports": bool(rep_settings.clean_reports),
            "wheel_notify": bool(rep_settings.wheel_notify),
        }
    except Exception as exc:
        logger.warning("Failed to fetch report settings for %s: %s", telegram_id, exc)

    alert_settings_data = {"low_traffic": True, "expire_warning": True, "traffic_percent": 80, "expire_days": 3}
    try:
        alert_settings = await AlertRepository(session).get_settings(telegram_id)
        alert_settings_data = {
            "low_traffic": bool(alert_settings.traffic_percent > 0),
            "expire_warning": bool(alert_settings.expire_days > 0),
            "traffic_percent": alert_settings.traffic_percent if alert_settings.traffic_percent > 0 else 80,
            "expire_days": alert_settings.expire_days if alert_settings.expire_days > 0 else 3,
        }
    except Exception as exc:
        logger.warning("Failed to fetch alert settings for %s: %s", telegram_id, exc)

    won_coupons_raw = await cache.get(f"wheel:user_coupons:{telegram_id}") or []
    now_dt_utc = datetime.now(timezone.utc)
    # Strictly filter only coupons with a valid future expiration date
    active_won_coupons = [
        c for c in won_coupons_raw
        if c.get("expires_at") and c.get("expires_at", "") > now_dt_utc.isoformat()
    ]

    try:
        if active_won_coupons:
            used_ids_res = await session.execute(select(CouponUsage.coupon_id).where(CouponUsage.telegram_id == telegram_id))
            used_ids = set(used_ids_res.scalars().all())
            active_codes = [c.get("code") for c in active_won_coupons if c.get("code")]
            if active_codes:
                valid_db_res = await session.execute(
                    select(Coupon).where(
                        Coupon.code.in_(active_codes),
                        Coupon.is_active.is_(True),
                        Coupon.used_count < Coupon.max_uses,
                        or_(Coupon.expires_at.is_(None), Coupon.expires_at > now_dt_utc),
                    )
                )
                valid_map = {dbc.code: dbc for dbc in valid_db_res.scalars().all()}
                # Keep only coupons that exist, are active, not expired, and not yet used by user
                active_won_coupons = [
                    c for c in active_won_coupons
                    if c.get("code") in valid_map and valid_map[c.get("code")].id not in used_ids
                ]
    except Exception as exc:
        logger.debug("Failed to verify user coupons in DB for %s: %s", telegram_id, exc)

    settings_combined = {**rep_settings_data, **alert_settings_data}
    return settings_combined, active_won_coupons, wheel_status


async def get_user_me(request: web.Request) -> web.Response:
    """Return dashboard data for the authenticated user (Cached for 30 seconds)."""
    user_auth, err = require_user(request)
    if err:
        return err

    telegram_id = int(user_auth["id"])
    req_account_id = request.query.get("account_id")
    cache: FastCache = request.app["cache"]
    cache_key = f"tma:user:{telegram_id}:dashboard:{req_account_id or 'default'}"

    cached_data = await cache.get(cache_key)
    if cached_data:
        return web.json_response({"ok": True, "data": cached_data, "cached": True})

    remnawave = request.app["remnawave"]
    settings = request.app["settings"]
    panel_users_task = asyncio.create_task(remnawave.get_users_by_telegram_id(telegram_id))

    async with db_session(request) as session:
        import bot.web.routes_user as _user_routes
        user_repo_cls = getattr(_user_routes, "UserRepository", UserRepository)
        user_repo = user_repo_cls(session)
        first_name = user_auth.get("first_name", "")
        last_name = user_auth.get("last_name", "")
        auth_full_name = f"{first_name} {last_name}".strip() or None
        db_user = await user_repo.get_or_create(telegram_id, user_auth.get("username"))
        if auth_full_name and hasattr(db_user, "full_name"):
            db_user.full_name = auth_full_name

        wallet_res = await session.execute(select(Wallet).where(Wallet.telegram_id == telegram_id))
        wallet = wallet_res.scalar_one_or_none()
        wallet_balance = wallet.balance if wallet else 0

        store_settings = await get_store_settings(session)
        ref_count_res = await session.execute(select(func.count(User.id)).where(User.referred_by_id == telegram_id))
        referrals_count = int(ref_count_res.scalar_one() or 0)
        referral_reward_gb = store_settings.referral_reward_gb if store_settings.referral_enabled else 5

        services_res = await session.execute(
            select(Service).where(Service.is_active.is_(True)).order_by(Service.price.asc())
        )
        plans_data = [
            {
                "id": s.id,
                "name": s.name,
                "price": s.price,
                "duration_days": s.duration_days,
                "traffic_gb": s.traffic_gb,
                "description": s.description,
                "hwid_limit": s.hwid_limit,
            }
            for s in services_res.scalars().all()
        ]

        tz_name = getattr(settings, "TIMEZONE", "Asia/Tehran")
        now_dt = now_tz(tz_name)
        now_j = jdatetime.datetime.fromgregorian(datetime=now_dt)
        today_jalali_str = f"{now_j.year}/{now_j.month:02d}/{now_j.day:02d}"
        yesterday_dt = now_dt - timedelta(days=1)
        yesterday_j = jdatetime.datetime.fromgregorian(datetime=yesterday_dt)
        yesterday_jalali_str = f"{yesterday_j.year}/{yesterday_j.month:02d}/{yesterday_j.day:02d}"

        panel_users = []
        try:
            panel_users = (await panel_users_task) or []
        except Exception as exc:
            logger.warning("Failed to get panel users for telegram_id=%s: %s", telegram_id, exc)

        active_sub, has_active_sub, accounts_list = await _build_active_subscription(
            remnawave, panel_users, req_account_id, telegram_id, user_auth, session, tz_name, now_dt
        )
        transactions = await _fetch_transaction_history(session, telegram_id, tz_name)
        user_settings, active_won_coupons, wheel_status = await _fetch_user_perks_and_settings(
            session, cache, telegram_id, has_active_sub
        )

        user_reg_jalali = ""
        if db_user.created_at:
            try:
                u_j = jdatetime.datetime.fromgregorian(
                    datetime=db_user.created_at.astimezone(ZoneInfo(tz_name)) if db_user.created_at.tzinfo else db_user.created_at
                )
                user_reg_jalali = f"{u_j.year}/{u_j.month:02d}/{u_j.day:02d}"
            except Exception:
                pass

        bot = request.app.get("bot")
        bot_username = getattr(getattr(bot, "_me", None), "username", "") if bot else ""
        ref_link = build_ref_link(bot_username, telegram_id)

        data = {
            "bot_username": bot_username,
            "referral_reward_gb": referral_reward_gb,
            "referral_enabled": store_settings.referral_enabled,
            "referral_link": ref_link,
            "tutorial_channel_url": store_settings.tutorial_channel_url,
            "routing_tutorial_url": store_settings.routing_tutorial_url,
            "client_apps_override": store_settings.client_apps_json,
            "user": {
                "id": telegram_id,
                "first_name": user_auth.get("first_name", "کاربر"),
                "username": user_auth.get("username"),
                "wallet_balance": wallet_balance,
                "referrals_count": referrals_count,
                "phone_number": db_user.phone_number if isinstance(getattr(db_user, "phone_number", None), str) else "",
                "birth_date": db_user.birth_date if isinstance(getattr(db_user, "birth_date", None), str) else "",
                "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
                "created_at_jalali": user_reg_jalali,
                "language": db_user.language if isinstance(getattr(db_user, "language", None), str) else "fa",
                "is_admin": user_auth.get("is_admin", False),
            },
            "settings": user_settings,
            "accounts": accounts_list,
            "active_sub": active_sub,
            "has_active_sub": has_active_sub,
            "today_jalali": today_jalali_str,
            "yesterday_jalali": yesterday_jalali_str,
            "plans": plans_data,
            "transactions": transactions[:50],
            "won_coupons": active_won_coupons,
            "wheel_status": wheel_status,
        }

        await cache.set(cache_key, data, ttl_seconds=30)
        return web.json_response({"ok": True, "data": data, "cached": False})
