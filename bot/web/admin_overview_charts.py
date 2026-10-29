"""Sales, network traffic, and strategic analytics charts for admin overview."""
import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from bot.common.helpers import get_used_bytes
from bot.db.models import CryptoInvoice, KnownDevice, Order, Service, Topup, User
from bot.db.repositories.traffic_snapshot_repo import TrafficSnapshotRepository
from bot.services.formatting import country_name, ltr_frag
from bot.web.admin_common import format_service_name_icon_first
from bot.web.cache import FastCache

try:
    import jdatetime
except ImportError:
    jdatetime = None

logger = logging.getLogger(__name__)


def get_day_label(dt: datetime) -> str:
    """Format short day label (MM/DD) honoring Jalali if present."""
    if jdatetime:
        try:
            return jdatetime.datetime.fromgregorian(datetime=dt).strftime("%m/%d")
        except Exception:
            pass
    return dt.strftime("%m/%d")


async def _calc_sales_trends(session, now_utc: datetime) -> tuple[list[str], list[int], list[str], list[int]]:
    """Calculate 7-day and 30-day daily sales totals."""
    days_list = [now_utc - timedelta(days=i) for i in range(6, -1, -1)]
    days_30_list = [now_utc - timedelta(days=i) for i in range(29, -1, -1)]
    thirty_days_ago = now_utc - timedelta(days=29)

    rev_30d_res = await session.execute(
        select(Order.created_at, Order.amount)
        .where(Order.status == "paid", Order.created_at >= thirty_days_ago)
    )
    daily_revenue = {(now_utc - timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(6, -1, -1)}
    monthly_revenue = {(now_utc - timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(29, -1, -1)}
    for cat_dt, amt in rev_30d_res.all():
        if cat_dt:
            ds = cat_dt.strftime("%Y-%m-%d")
            if ds in daily_revenue:
                daily_revenue[ds] += (amt or 0)
            if ds in monthly_revenue:
                monthly_revenue[ds] += (amt or 0)

    sales_7d_labels = [get_day_label(d) for d in days_list]
    sales_7d_data = list(daily_revenue.values())
    sales_30d_labels = [get_day_label(d) for d in days_30_list]
    sales_30d_data = list(monthly_revenue.values())
    return sales_7d_labels, sales_7d_data, sales_30d_labels, sales_30d_data


async def _fetch_user_bandwidth_series(remnawave, panel_users: list[dict], start_ds: str, end_ds: str):
    """Fetch live 7-day bandwidth stats for top active users concurrently."""
    daily_bytes_sum = [0] * 7
    has_real_stats = False
    active_uids = [
        int(u["id"])
        for u in sorted(panel_users, key=lambda x: get_used_bytes(x), reverse=True)
        if u.get("id") and get_used_bytes(u) > 0
    ]
    user_today_country_bytes: dict[str, int] = {}
    user_today_total_bytes = 0

    if hasattr(remnawave, "get_user_bandwidth_stats") and active_uids:
        try:
            sem = asyncio.Semaphore(10)
            async def _fetch_bw(uid: int):
                async with sem:
                    return await remnawave.get_user_bandwidth_stats(uid, start_ds, end_ds)

            bw_results = await asyncio.gather(*[_fetch_bw(uid) for uid in active_uids], return_exceptions=True)
            for r in bw_results:
                if isinstance(r, list):
                    for s in r:
                        cc = str(s.get("countryCode") or s.get("country_code") or "").strip().upper()
                        s_data = s.get("data") or []
                        if len(s_data) == 7:
                            has_real_stats = True
                            for idx, val in enumerate(s_data):
                                try:
                                    daily_bytes_sum[idx] += int(float(val or 0))
                                except (ValueError, TypeError):
                                    pass
                        val_today = int(float(s_data[-1])) if s_data else int(float(s.get("total") or 0))
                        if val_today > 0:
                            if cc:
                                user_today_country_bytes[cc] = user_today_country_bytes.get(cc, 0) + val_today
                            user_today_total_bytes += val_today
        except Exception as exc:
            logger.debug("Failed fetching user bandwidth stats: %s", exc)

    return daily_bytes_sum, has_real_stats, user_today_country_bytes, user_today_total_bytes


async def calc_sales_and_traffic_charts(
    session,
    remnawave,
    cache: FastCache,
    now_utc: datetime,
    is_refresh: bool,
    nodes: list[dict],
    panel_users: list[dict],
    total_traffic_gb: float,
) -> dict[str, Any]:
    """Calculate 7-day sales, 30-day sales, and 7-day traffic telemetry series."""
    days_list = [now_utc - timedelta(days=i) for i in range(6, -1, -1)]
    sales_7d_labels, sales_7d_data, sales_30d_labels, sales_30d_data = await _calc_sales_trends(session, now_utc)

    # Traffic telemetry calculation
    country_node_bytes: dict[str, int] = {}
    total_node_today_bytes = 0
    for n in nodes:
        if isinstance(n, dict):
            cc = str(n.get("countryCode") or n.get("country_code") or "").strip().upper()
            tb = n.get("trafficDailyBytes") or n.get("dailyTrafficBytes") or n.get("todayTrafficBytes") or n.get("traffic") or 0
            try:
                val = int(tb)
                if cc:
                    country_node_bytes[cc] = country_node_bytes.get(cc, 0) + val
                total_node_today_bytes += val
            except (ValueError, TypeError):
                pass

    cached_traffic = None if is_refresh else await cache.get("analytics:traffic:7day_series")
    if cached_traffic and isinstance(cached_traffic, dict) and "data" in cached_traffic:
        chart_traffic_data = list(cached_traffic["data"])
        today_cluster_gb = float(cached_traffic.get("today_traffic_gb") or chart_traffic_data[-1] or 0.0)
        traffic_total_gb = round(sum(chart_traffic_data), 2)
        is_traffic_real = bool(cached_traffic.get("is_real", True))
    else:
        start_ds = (now_utc - timedelta(days=6)).strftime("%Y-%m-%d")
        end_ds = now_utc.strftime("%Y-%m-%d")
        daily_bytes_sum, has_real_stats, user_today_country_bytes, user_today_total_bytes = (
            await _fetch_user_bandwidth_series(remnawave, panel_users, start_ds, end_ds)
        )
        for cc, val in user_today_country_bytes.items():
            if cc:
                country_node_bytes[cc] = max(country_node_bytes.get(cc, 0), val)

        today_cluster_bytes = sum(country_node_bytes.values()) if country_node_bytes else max(total_node_today_bytes, user_today_total_bytes)
        today_cluster_gb = round(today_cluster_bytes / (1024 ** 3), 2)

        if has_real_stats and sum(daily_bytes_sum) > 0:
            chart_traffic_data = [round(b / (1024 ** 3), 2) for b in daily_bytes_sum]
            chart_traffic_data[6] = today_cluster_gb
            traffic_total_gb = round(sum(chart_traffic_data), 2)
            is_traffic_real = True
        else:
            today_ds = now_utc.strftime("%Y-%m-%d")
            await cache.set(f"analytics:traffic:snapshot:{today_ds}", total_traffic_gb, ttl_seconds=86400 * 30)
            snapshot_deltas: list[float] = []
            for i in range(6, -1, -1):
                target_ds = (now_utc - timedelta(days=i)).strftime("%Y-%m-%d")
                prev_ds = (now_utc - timedelta(days=i + 1)).strftime("%Y-%m-%d")
                s_curr = await cache.get(f"analytics:traffic:snapshot:{target_ds}")
                s_prev = await cache.get(f"analytics:traffic:snapshot:{prev_ds}")
                if s_curr is not None and s_prev is not None:
                    snapshot_deltas.append(round(max(0.0, float(s_curr) - float(s_prev)), 2))
                else:
                    break

            chart_traffic_data = [0.0] * 7
            for idx, val in enumerate(snapshot_deltas):
                if idx < 7:
                    chart_traffic_data[idx] = val
            if today_cluster_gb > 0:
                chart_traffic_data[6] = today_cluster_gb
            traffic_total_gb = round(sum(chart_traffic_data), 2)
            is_traffic_real = len(snapshot_deltas) >= 7

        await cache.set(
            "analytics:traffic:7day_series",
            {
                "data": chart_traffic_data,
                "total_gb": traffic_total_gb,
                "today_traffic_gb": today_cluster_gb,
                "is_real": is_traffic_real,
            },
            ttl_seconds=300,
        )

    return {
        "sales_labels": sales_7d_labels,
        "sales_data": sales_7d_data,
        "sales_30d_labels": sales_30d_labels,
        "sales_30d_data": sales_30d_data,
        "sales_30d_total": sum(sales_30d_data),
        "traffic_labels": [get_day_label(d) for d in days_list],
        "traffic_data": chart_traffic_data,
        "traffic_total_gb": traffic_total_gb,
        "today_traffic_gb": today_cluster_gb,
        "is_traffic_real": is_traffic_real,
    }


def _calc_location_share(nodes_overview: list[dict]) -> dict[str, Any]:
    """Aggregate traffic usage and server count by node location/flag."""
    country_agg: dict[str, dict[str, Any]] = {}
    for n in nodes_overview:
        flag = n.get("flag") or "🌐"
        c_name = n.get("country_name") or country_name(n.get("country_code")) or ""
        lbl = f"{flag} {c_name}".strip() if c_name else flag
        if lbl not in country_agg:
            country_agg[lbl] = {"traffic_gb": 0.0, "nodes_count": 0}
        country_agg[lbl]["traffic_gb"] += float(n.get("traffic_used_gb") or 0.0)
        country_agg[lbl]["nodes_count"] += 1

    total_loc_gb = sum(v["traffic_gb"] for v in country_agg.values())
    loc_labels, loc_data = [], []
    for k, v in sorted(country_agg.items(), key=lambda x: x[1]["traffic_gb"], reverse=True):
        loc_labels.append(k)
        loc_data.append(round(v["traffic_gb"], 2) if total_loc_gb > 0 else v["nodes_count"])

    return {
        "labels": loc_labels or [],
        "data": loc_data or [],
        "unit": ltr_frag("GB") if total_loc_gb > 0 else "سرور",
        "has_data": bool(loc_labels and loc_data and any(v > 0 for v in loc_data)),
    }


async def _calc_hourly_distribution(session, now_utc: datetime) -> dict[str, Any]:
    """Calculate 24h peak hourly traffic curve from snapshots in rolling chronological order (Option 3)."""
    from datetime import timezone
    from zoneinfo import ZoneInfo
    from bot.config import get_settings

    settings = get_settings()
    tz_str = getattr(settings, "TIMEZONE", "Asia/Tehran")
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo("Asia/Tehran")

    local_now = now_utc.astimezone(tz) if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc).astimezone(tz)
    curr_h = local_now.hour

    # 24 hours in rolling chronological order from 23 hours ago to current hour (now)
    ordered_hours = [(curr_h - 23 + i) % 24 for i in range(24)]
    labels = [f"{h:02d}:00" for h in ordered_hours]

    snapshot_repo = TrafficSnapshotRepository(session)
    snapshots_24h = await snapshot_repo.get_last_24_hours(now_utc)

    snapshots_by_hour = {}
    for s in snapshots_24h:
        s_ts = s.timestamp
        s_local = s_ts.replace(tzinfo=timezone.utc).astimezone(tz) if s_ts.tzinfo is None else s_ts.astimezone(tz)
        snapshots_by_hour[s_local.hour] = s.delta_bytes

    if snapshots_by_hour:
        hourly_data = [round(snapshots_by_hour.get(h, 0) / (1024 ** 3), 2) for h in ordered_hours]
        peak_pos = max(range(24), key=lambda i: hourly_data[i])
        peak_h = ordered_hours[peak_pos]
        peak_hour_str = f"{peak_h:02d}:00"
        is_real_telemetry = True
    else:
        hourly_data = [0.0] * 24
        peak_hour_str = None
        is_real_telemetry = False

    return {
        "labels": labels,
        "data": hourly_data,
        "peak_hour": peak_hour_str,
        "unit": "GB",
        "is_real_telemetry": is_real_telemetry,
        "has_real_telemetry": is_real_telemetry,
        "telemetry_count": len(snapshots_by_hour),
    }


async def _calc_retention_trend(session, now_utc: datetime, days_list: list[datetime]) -> dict[str, Any]:
    """Distinguish new buyers from renewals over the last 7 days."""
    seven_days_ago = now_utc - timedelta(days=6)
    orders_7d = (await session.execute(
        select(Order.telegram_id, Order.created_at).where(Order.status == "paid", Order.created_at >= seven_days_ago)
    )).all()
    day_keys = [d.strftime("%Y-%m-%d") for d in days_list]
    new_sales_day = {k: 0 for k in day_keys}
    renewal_sales_day = {k: 0 for k in day_keys}
    seen_user_ids = set((await session.execute(
        select(Order.telegram_id).where(Order.status == "paid", Order.created_at < seven_days_ago).distinct()
    )).scalars().all())

    for u_id, o_dt in orders_7d:
        if o_dt:
            ds = o_dt.strftime("%Y-%m-%d")
            if ds in new_sales_day:
                if u_id not in seen_user_ids:
                    seen_user_ids.add(u_id)
                    new_sales_day[ds] += 1
                else:
                    renewal_sales_day[ds] += 1

    return {
        "labels": [get_day_label(d) for d in days_list],
        "new_sales": [new_sales_day[k] for k in day_keys],
        "renewal_sales": [renewal_sales_day[k] for k in day_keys],
    }


async def _calc_plan_distribution(session) -> dict[str, Any]:
    """Calculate popular plans by volume and sales."""
    plan_rows = (await session.execute(
        select(Service.name, func.count(Order.id), func.coalesce(func.sum(Order.amount), 0))
        .join(Service, Order.service_id == Service.id)
        .where(Order.status == "paid")
        .group_by(Service.name)
        .order_by(func.count(Order.id).desc())
        .limit(5)
    )).all()
    if plan_rows:
        plan_labels = [format_service_name_icon_first(str(r[0])) for r in plan_rows]
        plan_sales = [int(r[1]) for r in plan_rows]
        plan_revenue = [int(r[2]) for r in plan_rows]
    else:
        srv_names = (await session.execute(select(Service.name).where(Service.is_active.is_(True)).limit(5))).scalars().all()
        plan_labels = [format_service_name_icon_first(str(n)) for n in srv_names] if srv_names else []
        plan_sales = [0] * len(plan_labels)
        plan_revenue = [0] * len(plan_labels)

    return {
        "labels": plan_labels,
        "sales_count": plan_sales,
        "revenue": plan_revenue,
        "has_data": bool(plan_labels and any(s > 0 for s in plan_sales)),
    }


async def _calc_platform_and_hwid(session, remnawave) -> tuple[dict[str, Any], dict[str, Any]]:
    """Determine OS/client platforms and HWID device sharing risk."""
    platform_counts = {"Android": 0, "iOS": 0, "Windows": 0, "macOS/Linux": 0, "Other": 0}
    try:
        devices_raw = await remnawave.get_all_hwid_devices(size=500) or []
    except Exception:
        devices_raw = []
    if not devices_raw:
        for p_val, m_val, t_val in (await session.execute(select(KnownDevice.platform, KnownDevice.device_model, KnownDevice.telegram_id))).all():
            devices_raw.append({"platform": p_val, "os": p_val, "model": m_val, "userId": t_val})

    user_hwid_counts: dict[Any, int] = defaultdict(int)
    for dev in devices_raw:
        p_str = str(dev.get("platform") or dev.get("os") or dev.get("model") or "").lower()
        if any(k in p_str for k in ("android", "v2rayng", "hiddify", "sing-box", "nekobox", "clash")):
            platform_counts["Android"] += 1
        elif any(k in p_str for k in ("ios", "iphone", "ipad", "streisand", "v2box", "shadowrocket", "loon", "surge")):
            platform_counts["iOS"] += 1
        elif any(k in p_str for k in ("windows", "win32", "win64")):
            platform_counts["Windows"] += 1
        elif any(k in p_str for k in ("darwin", "mac", "macos", "linux", "ubuntu")):
            platform_counts["macOS/Linux"] += 1
        else:
            platform_counts["Other"] += 1

        uid = dev.get("userId") or dev.get("telegram_id")
        if uid:
            user_hwid_counts[uid] += 1

    single_device = sum(1 for cnt in user_hwid_counts.values() if cnt == 1)
    two_device = sum(1 for cnt in user_hwid_counts.values() if cnt == 2)
    three_plus = sum(1 for cnt in user_hwid_counts.values() if cnt >= 3)
    high_risk = sum(1 for cnt in user_hwid_counts.values() if cnt >= 4)

    order_user_map: dict[str, str] = {}
    try:
        order_rows = (await session.execute(
            select(Order.panel_user_id, Order.panel_username)
            .where(Order.panel_user_id.is_not(None), Order.panel_username.is_not(None))
        )).all()
        for p_id, p_name in order_rows:
            if p_id and p_name:
                order_user_map[str(p_id)] = p_name
    except Exception:
        pass

    dev_user_names: dict[Any, str] = {}
    for dev in devices_raw:
        uid = dev.get("userId") or dev.get("telegram_id") or dev.get("user_id")
        if uid and uid not in dev_user_names:
            u_obj = dev.get("user")
            p_name = None
            if isinstance(u_obj, dict):
                p_name = u_obj.get("username")
            if not p_name:
                p_name = dev.get("username") or dev.get("account_username")
            if p_name:
                dev_user_names[str(uid)] = p_name
                dev_user_names[uid] = p_name

    missing_panel_ids = [str(u) for u in user_hwid_counts if not (dev_user_names.get(str(u)) or dev_user_names.get(u) or order_user_map.get(str(u)))]
    if missing_panel_ids and remnawave:
        try:
            p_users = await remnawave.get_all_panel_users(size=1000) or []
            for pu in p_users:
                p_uid = str(pu.get("id", ""))
                p_uuid = str(pu.get("uuid", ""))
                p_uname = pu.get("username")
                if p_uname:
                    if p_uid:
                        dev_user_names[p_uid] = p_uname
                    if p_uuid:
                        dev_user_names[p_uuid] = p_uname
        except Exception:
            pass

    high_risk_users = []
    sorted_risk = sorted([(u, c) for u, c in user_hwid_counts.items() if c >= 3], key=lambda x: x[1], reverse=True)[:50]
    tg_candidates = []
    for u, _ in sorted_risk:
        try:
            tg_candidates.append(int(u))
        except (ValueError, TypeError):
            pass

    user_info_map = {}
    if tg_candidates:
        rows = (await session.execute(
            select(User.telegram_id, User.username, User.full_name).where(User.telegram_id.in_(tg_candidates))
        )).all()
        for t_id, uname, fname in rows:
            user_info_map[t_id] = {"username": uname, "full_name": fname}

    for u, c in sorted_risk:
        t_id = int(u) if str(u).isdigit() else None
        db_u = user_info_map.get(t_id) if t_id else None
        panel_name = dev_user_names.get(str(u)) or dev_user_names.get(u) or order_user_map.get(str(u))
        if not panel_name and db_u:
            panel_name = db_u.get("username") or db_u.get("full_name")

        display_name = panel_name or f"اکانت {u}"
        high_risk_users.append({
            "user_id": str(u),
            "telegram_id": t_id,
            "name": display_name,
            "username": panel_name or (db_u.get("username") if db_u else None),
            "device_count": c,
        })

    platform_dist = {
        "labels": ["اندروید (Android)", "آیفون (iOS)", "ویندوز (Windows)", "مک و لینوکس", "سایر"],
        "data": [platform_counts["Android"], platform_counts["iOS"], platform_counts["Windows"], platform_counts["macOS/Linux"], platform_counts["Other"]],
    }
    hwid_dist = {
        "labels": ["1 دستگاه", "2 دستگاه", "3+ دستگاه", "ریسک بالا (4+)"],
        "data": [single_device, two_device, three_plus, high_risk],
        "high_risk_count": len(high_risk_users),
        "total_monitored_users": len(user_hwid_counts),
        "high_risk_users": high_risk_users,
    }
    return platform_dist, hwid_dist


async def _calc_retention_and_payments(session, now_utc: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compute overall retention/churn rate and payment methods split."""
    card_count, card_sum = (await session.execute(
        select(func.count(Topup.id), func.coalesce(func.sum(Topup.amount), 0))
        .where(Topup.status == "approved", or_(Topup.receipt_hash.is_(None), ~Topup.receipt_hash.startswith("stars:")))
    )).first() or (0, 0)
    stars_count, stars_sum = (await session.execute(
        select(func.count(Topup.id), func.coalesce(func.sum(Topup.amount), 0))
        .where(Topup.status == "approved", Topup.receipt_hash.startswith("stars:"))
    )).first() or (0, 0)
    c_count, c_sum = (await session.execute(
        select(func.count(CryptoInvoice.id), func.coalesce(func.sum(CryptoInvoice.amount_toman), 0)).where(CryptoInvoice.status == "paid")
    )).first() or (0, 0)

    user_orders = dict((await session.execute(
        select(Order.telegram_id, func.count(Order.id)).where(Order.status == "paid").group_by(Order.telegram_id)
    )).all())
    total_customers = len(user_orders)
    renewed_customers = sum(1 for cnt in user_orders.values() if cnt > 1)
    single_order_customers = total_customers - renewed_customers

    thirty_days_ago = now_utc - timedelta(days=30)
    churned_count = len((await session.execute(
        select(Order.telegram_id).where(Order.status == "paid", Order.created_at < thirty_days_ago).group_by(Order.telegram_id).having(func.count(Order.id) == 1)
    )).scalars().all())
    active_single = max(0, single_order_customers - churned_count)

    payment_dist = {
        "labels": ["کارت به کارت (ریالی)", "ارز دیجیتال (کریپتو / TON)", "تلگرام استارز (XTR)"],
        "counts": [int(card_count or 0), int(c_count or 0), int(stars_count or 0)],
        "volumes": [int(card_sum or 0), int(c_sum or 0), int(stars_sum or 0)],
    }
    retention_stats = {
        "total_customers": total_customers,
        "renewed": renewed_customers,
        "active_single": active_single,
        "churned": churned_count,
        "retention_rate": round((renewed_customers / total_customers * 100), 1) if total_customers > 0 else 0,
        "churn_rate": round((churned_count / total_customers * 100), 1) if total_customers > 0 else 0,
        "labels": ["تمدید شده (مشتریان وفادار)", "دوره اول (فعال)", "ریزش (عدم تمدید)"],
        "data": [renewed_customers, active_single, churned_count],
    }
    return payment_dist, retention_stats


async def calc_strategic_charts(
    session,
    remnawave,
    now_utc: datetime,
    nodes_overview: list[dict],
    days_list: list[datetime],
    today_cluster_gb: float,
    total_traffic_gb: float,
) -> dict[str, Any]:
    """Calculate platform distribution, 24h peak usage curve, and retention analytics."""
    location_share = _calc_location_share(nodes_overview)
    hourly_distribution = await _calc_hourly_distribution(session, now_utc)
    retention_trend = await _calc_retention_trend(session, now_utc, days_list)
    plan_distribution = await _calc_plan_distribution(session)
    platform_distribution, hwid_distribution = await _calc_platform_and_hwid(session, remnawave)
    payment_distribution, retention_stats = await _calc_retention_and_payments(session, now_utc)

    return {
        "location_share": location_share,
        "hourly_distribution": hourly_distribution,
        "retention_trend": retention_trend,
        "plan_distribution": plan_distribution,
        "platform_distribution": platform_distribution,
        "payment_distribution": payment_distribution,
        "retention_stats": retention_stats,
        "hwid_distribution": hwid_distribution,
    }


# Aliases for backward compatibility
_get_day_label = get_day_label
_calc_sales_and_traffic_charts = calc_sales_and_traffic_charts
_calc_strategic_charts = calc_strategic_charts
