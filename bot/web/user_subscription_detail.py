"""Detailed bandwidth statistics and subscription construction for user dashboard."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import jdatetime
from sqlalchemy import select

from bot.db.models import Order
from bot.db.repositories.traffic_snapshot_repo import TrafficSnapshotRepository
from bot.services.formatting import country_flag, human_bytes, parse_iso, start_of_today

logger = logging.getLogger(__name__)


async def calc_bandwidth_stats(
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
        series = (
            await asyncio.wait_for(
                remnawave.get_user_bandwidth_stats(uid_arg, start_str, today_str),
                timeout=5.0,
            )
        ) or []
    except (TimeoutError, Exception) as exc:
        logger.warning("Failed or timed out fetching bandwidth stats for %s: %s", panel_user_id, exc)

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
            today_tuple = await asyncio.wait_for(
                remnawave.get_user_today_usage(uid_arg, start_today_dt.isoformat(), now_dt.isoformat()),
                timeout=4.0,
            )
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
        except (TimeoutError, Exception) as exc:
            logger.warning("Fallback today usage failed or timed out for %s: %s", panel_user_id, exc)

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


def calc_usage_curves(
    primary: dict[str, Any],
    devices: list[dict[str, Any]],
    traffic: dict[str, Any],
    used_bytes: int,
    today_used_gb: float,
    week_used_gb: float,
    panel_user_id: Any,
    source_breakdown: list[dict[str, Any]],
    snapshots_24h: list[Any] | None = None,
) -> dict[str, Any]:
    """Compute download/upload split, country donut chart, 24h curve, and platform distribution."""
    raw_up = int(traffic.get("uploadTrafficBytes") or primary.get("uploadTrafficBytes") or primary.get("up") or 0)
    raw_down = int(traffic.get("downloadTrafficBytes") or primary.get("downloadTrafficBytes") or primary.get("down") or 0)
    split_estimated = False
    if raw_up == 0 and raw_down == 0:
        if used_bytes > 0:
            raw_down = int(used_bytes * 0.85)
            raw_up = max(0, used_bytes - raw_down)
            split_estimated = True
        else:
            raw_down = 0
            raw_up = 0

    tot_updown = (raw_down + raw_up) or 1
    traffic_split = {
        "download_gb": round(raw_down / (1024**3), 2),
        "upload_gb": round(raw_up / (1024**3), 2),
        "download_percent": round((raw_down / tot_updown) * 100) if (raw_down + raw_up) > 0 else 0,
        "upload_percent": round((raw_up / tot_updown) * 100) if (raw_down + raw_up) > 0 else 0,
        "is_estimated": split_estimated,
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

    has_traffic = (today_used_gb > 0) or (week_used_gb > 0) or (used_bytes > 0)
    base_curve_gb = today_used_gb if today_used_gb > 0 else (round(week_used_gb / 7.0, 2) if week_used_gb > 0 else 0.0)

    hourly_curve_labels = [f"{h:02d}-{h+2:02d}" for h in range(0, 24, 2)]
    if not has_traffic or base_curve_gb <= 0.0:
        hourly_curve_vals = [0.0] * 12
        peak_hour_str = None
        is_curve_estimated = False
    else:
        # Check if real hourly snapshots exist in the database
        slot_bytes = [0] * 12
        if snapshots_24h:
            for s in snapshots_24h:
                s_ts = getattr(s, "timestamp", None)
                s_delta = getattr(s, "delta_bytes", 0) or 0
                if s_ts:
                    slot_idx = (s_ts.hour // 2) % 12
                    slot_bytes[slot_idx] += s_delta

        total_snap_bytes = sum(slot_bytes)
        if total_snap_bytes > 0:
            weights_12 = [b / total_snap_bytes for b in slot_bytes]
            hourly_curve_vals = [
                round(base_curve_gb * weights_12[i], 2) for i in range(12)
            ]
            peak_2h_idx = max(range(12), key=lambda i: hourly_curve_vals[i])
            peak_hour_str = f"{peak_2h_idx*2:02d}:00 - {peak_2h_idx*2 + 2:02d}:00"
            is_curve_estimated = False
            has_real_data = True
        else:
            hourly_curve_vals = [0.0] * 12
            peak_hour_str = None
            is_curve_estimated = False
            has_real_data = False

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
            "peak_hour": peak_hour_str,
            "is_estimated": is_curve_estimated,
            "has_real_data": has_real_data,
            "has_traffic": has_traffic,
        },
        "device_share": {"labels": list(platform_counts.keys()), "data": list(platform_counts.values())},
    }


async def build_active_subscription(
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

    bw = await calc_bandwidth_stats(remnawave, primary, panel_user_id, now_dt, tz_name)
    now_j = jdatetime.datetime.fromgregorian(datetime=now_dt)
    month_names = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
    current_month_name = month_names[now_j.month - 1] if 1 <= now_j.month <= 12 else "ماه جاری"

    devices = []
    try:
        devices = (
            await asyncio.wait_for(
                remnawave.get_user_hwid_devices(bw["uid_arg"], user_uuid=primary.get("uuid")),
                timeout=4.0,
            )
        ) or []
    except (TimeoutError, Exception) as exc:
        logger.warning("Failed or timed out fetching HWID devices for %s: %s", panel_user_id, exc)

    days_left = 0
    expire_jalali_str = ""
    expire_iso_str = None
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
            expire_iso_str = expire_dt.isoformat()
            if not expire_timestamp:
                expire_timestamp = int(expire_dt.timestamp())
    except Exception as exc:
        logger.warning("Failed to calculate expiration for %s: %s", panel_user_id, exc)

    sub_url = primary.get("subscriptionUrl") or primary.get("subscription_url")
    if not sub_url:
        order_res = await session.execute(
            select(Order.subscription_url).where(Order.telegram_id == telegram_id, Order.subscription_url.isnot(None)).order_by(Order.id.desc()).limit(1)
        )
        sub_url = order_res.scalar_one_or_none() or ""

    snapshots_24h = []
    if session:
        try:
            snapshot_repo = TrafficSnapshotRepository(session)
            snapshots_24h = await snapshot_repo.get_last_24_hours(now_dt)
        except Exception as e:
            logger.warning("Failed to fetch traffic snapshots for hourly curve: %s", e)

    curves = calc_usage_curves(
        primary,
        devices,
        traffic,
        used_bytes,
        bw["today_used_gb"],
        bw["week_used_gb"],
        panel_user_id,
        bw["all_nodes_breakdown"] or bw["week_breakdown"] or bw["today_breakdown"],
        snapshots_24h=snapshots_24h,
    )

    # Calculate Burn-rate & Projected Expiry
    recent_3days_bytes = bw["week_daily_totals"][-3:] if bw.get("week_daily_totals") else []
    recent_3days_gb = [round(b / (1024**3), 2) for b in recent_3days_bytes]
    avg_3days_gb = round(sum(recent_3days_gb) / len(recent_3days_gb), 2) if recent_3days_gb else 0.0
    if avg_3days_gb <= 0.0 and bw.get("today_used_gb", 0) > 0:
        avg_3days_gb = round(float(bw["today_used_gb"]), 2)

    projected_days = None
    burn_status = "normal"
    burn_text = ""

    if limit_bytes == 0:
        burn_status = "unlimited"
        burn_text = "حجم بسته شما نامحدود است."
    elif traffic_remaining_gb <= 0:
        burn_status = "exhausted"
        burn_text = "حجم بسته شما به پایان رسیده است."
    elif avg_3days_gb > 0:
        projected_days = round(traffic_remaining_gb / avg_3days_gb, 1)
        if days_left > 0 and projected_days < days_left:
            burn_status = "fast"
            burn_text = f"با الگوی مصرف فعلی، حجم شما تا حدود {int(projected_days) if projected_days.is_integer() else projected_days} روز دیگر به پایان می‌رسد (پیش از موعد انقضا)."
        elif days_left > 0 and projected_days >= days_left:
            burn_status = "safe"
            burn_text = f"با الگوی مصرف فعلی، حجم شما تا {days_left} روز آینده (تا انقضای اشتراک) کاملاً پاسخگو است."
        else:
            burn_status = "normal"
            burn_text = f"با الگوی مصرف فعلی، حجم شما تا حدود {int(projected_days) if projected_days.is_integer() else projected_days} روز دیگر به پایان می‌رسد."
    else:
        burn_status = "idle"
        burn_text = "مصرف قابل توجهی در ۳ روز اخیر ثبت نشده است."

    burn_rate = {
        "avg_daily_gb": avg_3days_gb,
        "projected_days": projected_days,
        "status": burn_status,
        "text": burn_text,
        "days_left_plan": days_left,
    }

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
        "expire_at": expire_iso_str,
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
        "burn_rate": burn_rate,
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


# Aliases for backward compatibility
_calc_bandwidth_stats = calc_bandwidth_stats
_calc_usage_curves = calc_usage_curves
_build_active_subscription = build_active_subscription
