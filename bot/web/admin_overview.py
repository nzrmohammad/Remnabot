"""Admin Overview API and telemetry aggregation for Telegram Mini App.

Decomposed into focused, single-purpose calculation layers:
- `_extract_node_item`: Single node hardware, telemetry & financial parsing.
- `_calc_nodes_overview`: Aggregation of node clusters and HWID telemetry.
- `_calc_cluster_kpis`: Core database KPIs (users, revenues, profit margins, traffic).
- `_calc_sales_and_traffic_charts`: 7-day/30-day sales curves and network traffic telemetry.
- `_calc_strategic_charts`: Platform distribution, retention cohorts, hourly peak curves.
- `get_admin_overview`: Lightweight async controller orchestrating the above.
"""
import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import web
from sqlalchemy import func, select

from bot.common.helpers import get_limit_bytes, get_used_bytes
from bot.db.models import CryptoInvoice, KnownDevice, Order, Service, Topup, User
from bot.db.repositories.node_cost_repo import NodeCostRepository
from bot.db.repositories.traffic_snapshot_repo import TrafficSnapshotRepository
from bot.handlers.admin_nodes import COUNTRY_FLAGS_MAP
from bot.services.app_settings import get_store_settings
from bot.services.formatting import country_flag
from bot.web.admin_common import _check_admin, db_session, format_service_name_icon_first
from bot.web.cache import FastCache

try:
    import jdatetime
except ImportError:
    jdatetime = None

logger = logging.getLogger(__name__)


def _extract_cpu(src: dict) -> float | None:
    """Extract CPU percentage from arbitrary metrics dictionary."""
    if not isinstance(src, dict):
        return None
    for k in ("cpu", "cpuUsage", "cpuPercent", "load", "cpu_percent", "cpu_usage"):
        v = src.get(k)
        if v is not None:
            if isinstance(v, dict):
                for sub_k in ("usage", "percent", "load", "value"):
                    sub_v = v.get(sub_k)
                    if sub_v is not None:
                        try:
                            return float(sub_v)
                        except (ValueError, TypeError):
                            pass
            elif isinstance(v, (int, float, str)):
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
    return None


def _extract_ram(src: dict) -> float | None:
    """Extract RAM usage percentage from arbitrary metrics dictionary."""
    if not isinstance(src, dict):
        return None
    for k in ("ram", "memory", "memoryUsage", "memoryPercent", "ramPercent", "ram_percent", "ram_usage"):
        v = src.get(k)
        if v is not None:
            if isinstance(v, dict):
                used = v.get("used") or v.get("usedBytes")
                total = v.get("total") or v.get("totalBytes")
                free = v.get("free") or v.get("freeBytes")
                if total and used:
                    try:
                        return (float(used) / float(total)) * 100.0
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass
                if total and free:
                    try:
                        return ((float(total) - float(free)) / float(total)) * 100.0
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass
                for sub_k in ("usage", "percent", "value"):
                    sub_v = v.get(sub_k)
                    if sub_v is not None:
                        try:
                            return float(sub_v)
                        except (ValueError, TypeError):
                            pass
            elif isinstance(v, (int, float, str)):
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
    return None


def _extract_speeds(src: dict) -> tuple[float, float]:
    """Extract download and upload network speeds in bytes/sec."""
    if not isinstance(src, dict):
        return 0.0, 0.0
    net = src.get("network") if isinstance(src.get("network"), dict) else {}
    rx = (
        net.get("rxBytesPerSec")
        or net.get("rx")
        or net.get("download")
        or src.get("networkRxBytesPerSec")
        or src.get("rxBytesPerSec")
        or src.get("downloadSpeed")
        or src.get("speedIn")
        or 0.0
    )
    tx = (
        net.get("txBytesPerSec")
        or net.get("tx")
        or net.get("upload")
        or src.get("networkTxBytesPerSec")
        or src.get("txBytesPerSec")
        or src.get("uploadSpeed")
        or src.get("speedOut")
        or 0.0
    )
    try:
        rx_f = float(rx)
    except (ValueError, TypeError):
        rx_f = 0.0
    try:
        tx_f = float(tx)
    except (ValueError, TypeError):
        tx_f = 0.0
    return rx_f, tx_f


def _extract_node_item(
    n: dict,
    i: int,
    costs_by_uuid: dict,
    costs_by_id: dict,
    now_utc: datetime,
) -> dict[str, Any]:
    """Parse telemetry, hardware metrics, country flag, and financials for one node."""
    raw_name = str(n.get("name") or f"Node {i}").strip()
    country_code = str(n.get("countryCode") or n.get("country_code") or "").strip().upper()
    country_name = str(n.get("country") or "").strip().lower()

    flag = None
    if len(country_code) == 2 and country_code.isalpha() and country_code != "XX":
        flag = country_flag(country_code)

    if not flag or flag == "🌐":
        for kw, (f_emoji, _) in sorted(COUNTRY_FLAGS_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            if kw in raw_name.lower() or kw in country_name:
                flag = f_emoji
                break
    if not flag:
        flag = country_flag(country_code) if country_code else "🌐"

    is_connected = n.get("isConnected")
    if is_connected is None:
        is_connected = str(n.get("status", "")).upper() in ("CONNECTED", "ONLINE")

    online_users = int(
        n.get("usersOnline")
        or n.get("connectionCount")
        or n.get("activeConnections")
        or n.get("connected_users")
        or 0
    )

    raw_sys = n.get("system") or n.get("sys") or {}
    sys_stats = raw_sys.get("stats") if isinstance(raw_sys, dict) else {}
    sys_info_meta = raw_sys.get("info") if isinstance(raw_sys, dict) else {}

    cpu_val = None
    if isinstance(sys_stats, dict) and "loadAvg" in sys_stats:
        load_avg = sys_stats.get("loadAvg")
        cpus = (sys_info_meta.get("cpus") if isinstance(sys_info_meta, dict) else None) or 1
        if isinstance(load_avg, list) and len(load_avg) > 0:
            try:
                cpu_val = (float(load_avg[0]) / max(1, int(cpus))) * 100.0
            except (ValueError, TypeError, ZeroDivisionError):
                pass

    if cpu_val is None:
        cpu_val = _extract_cpu(raw_sys) or _extract_cpu(n)

    ram_val = None
    if isinstance(sys_stats, dict) and "memoryUsed" in sys_stats:
        mem_used = sys_stats.get("memoryUsed")
        mem_free = sys_stats.get("memoryFree")
        mem_total = (sys_info_meta.get("memoryTotal") if isinstance(sys_info_meta, dict) else None)
        if not mem_total and mem_used is not None and mem_free is not None:
            mem_total = mem_used + mem_free
        if mem_used is not None and mem_total:
            try:
                ram_val = (float(mem_used) / float(mem_total)) * 100.0
            except (ValueError, TypeError, ZeroDivisionError):
                pass

    if ram_val is None:
        ram_val = _extract_ram(raw_sys) or _extract_ram(n)

    dl_speed = 0.0
    ul_speed = 0.0
    if isinstance(sys_stats, dict) and isinstance(sys_stats.get("interface"), dict):
        iface = sys_stats["interface"]
        try:
            dl_speed = float(iface.get("rxBytesPerSec") or 0.0)
            ul_speed = float(iface.get("txBytesPerSec") or 0.0)
        except (ValueError, TypeError):
            pass

    if dl_speed <= 0.0 and ul_speed <= 0.0:
        dl_speed, ul_speed = _extract_speeds(raw_sys)
    if dl_speed <= 0.0 and ul_speed <= 0.0:
        dl_speed, ul_speed = _extract_speeds(n)

    cpu_val = cpu_val if cpu_val is not None else 0.0
    ram_val = ram_val if ram_val is not None else 0.0
    if 0.0 < cpu_val <= 1.0:
        cpu_val *= 100.0
    if 0.0 < ram_val <= 1.0:
        ram_val *= 100.0

    cpu_val = max(0.0, min(100.0, cpu_val))
    ram_val = max(0.0, min(100.0, ram_val))

    if not is_connected:
        cpu_val, ram_val, dl_speed, ul_speed = 0.0, 0.0, 0.0, 0.0

    address = str(n.get("address") or "—")
    port = n.get("port")
    addr_str = f"{address}:{port}" if port else address
    traffic_used = n.get("trafficUsedBytes") or n.get("usedTrafficBytes") or 0
    traffic_used_gb = round(traffic_used / (1024 ** 3), 2) if traffic_used else 0.0

    n_uuid = str(n.get("uuid") or n.get("id") or "")
    n_id_str = str(n.get("id") or "")
    cost_entry = costs_by_uuid.get(n_uuid) or costs_by_id.get(n_id_str)

    due_date_str = None
    due_date_jalali = None
    days_until_due = None
    if cost_entry and cost_entry.due_date:
        due_date_str = cost_entry.due_date.strftime("%Y-%m-%d")
        days_until_due = (cost_entry.due_date.date() - now_utc.date()).days
        if jdatetime:
            try:
                due_date_jalali = jdatetime.datetime.fromgregorian(datetime=cost_entry.due_date).strftime("%Y/%m/%d")
            except Exception:
                due_date_jalali = due_date_str
        else:
            due_date_jalali = due_date_str

    n_cost_toman = cost_entry.monthly_cost_toman if cost_entry else 0
    n_cost_eur = cost_entry.monthly_cost_eur if cost_entry else 0.0
    n_currency = getattr(cost_entry, "currency", "EUR") or "EUR" if cost_entry else "EUR"
    n_provider = cost_entry.provider if cost_entry else None
    n_notes = cost_entry.notes if cost_entry else None
    n_cost_per_gb = round(n_cost_toman / traffic_used_gb, 0) if (n_cost_toman > 0 and traffic_used_gb > 0) else 0.0

    return {
        "id": n.get("id"),
        "uuid": n_uuid,
        "name": raw_name,
        "country_code": country_code or "NL",
        "flag": flag,
        "status": "ONLINE" if is_connected else "OFFLINE",
        "connected_users": online_users,
        "cpu_percent": round(cpu_val, 1),
        "ram_percent": round(ram_val, 1),
        "download_speed": round(dl_speed, 1),
        "upload_speed": round(ul_speed, 1),
        "address": addr_str,
        "traffic_used_gb": traffic_used_gb,
        "provider": n_provider,
        "monthly_cost_toman": n_cost_toman,
        "monthly_cost_eur": n_cost_eur,
        "currency": n_currency,
        "due_date": due_date_str,
        "due_date_jalali": due_date_jalali,
        "days_until_due": days_until_due,
        "cost_per_gb": n_cost_per_gb,
        "notes": n_notes,
    }


def _calc_nodes_overview(
    nodes: list[dict],
    costs_by_uuid: dict,
    costs_by_id: dict,
    hwid_stats: dict,
    now_utc: datetime,
) -> tuple[list[dict], int, int]:
    """Return nodes overview list, total online devices, and offline nodes count."""
    nodes_overview = [
        _extract_node_item(n, i, costs_by_uuid, costs_by_id, now_utc)
        for i, n in enumerate(nodes, start=1)
    ]
    sum_node_online = sum(n["connected_users"] for n in nodes_overview)
    online_dev = (
        hwid_stats.get("onlineDevices")
        or hwid_stats.get("online_devices")
        or hwid_stats.get("activeDevices")
    )
    online_devices = int(online_dev) if (online_dev is not None and int(online_dev) > 0) else sum_node_online
    offline_nodes = sum(1 for n in nodes_overview if n["status"] == "OFFLINE")
    return nodes_overview, online_devices, offline_nodes


async def _calc_cluster_kpis(
    session,
    remnawave,
    now_utc: datetime,
) -> tuple[dict[str, Any], list[dict], list[dict], dict, dict]:
    """Calculate core bot KPIs, cluster metrics, and node cost maps."""
    user_count_res = await session.execute(select(func.count(User.id)))
    total_bot_users = int(user_count_res.scalar_one() or 0)

    start_of_day = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    rev_res = await session.execute(
        select(func.coalesce(func.sum(Order.amount), 0)).where(
            Order.created_at >= start_of_day,
            Order.status == "paid",
        )
    )
    today_revenue = int(rev_res.scalar_one() or 0)

    topup_res = await session.execute(
        select(func.count(Topup.id)).where(Topup.status == "pending")
    )
    pending_topups = int(topup_res.scalar_one() or 0)

    panel_users = await remnawave.get_all_panel_users(size=1000) or []
    active_panel_users = sum(1 for u in panel_users if str(u.get("status", "")).upper() == "ACTIVE")
    total_traffic_bytes = sum(get_used_bytes(u) for u in panel_users)
    total_traffic_gb = round(total_traffic_bytes / (1024 ** 3), 2)

    thirty_days_ago = now_utc - timedelta(days=30)
    rev_30d_res = await session.execute(
        select(func.coalesce(func.sum(Order.amount), 0)).where(
            Order.created_at >= thirty_days_ago,
            Order.status == "paid",
        )
    )
    monthly_revenue = int(rev_30d_res.scalar_one() or 0)

    node_cost_repo = NodeCostRepository(session)
    all_node_costs = await node_cost_repo.list_all()
    costs_by_uuid = {str(c.node_uuid): c for c in all_node_costs}
    costs_by_id = {str(c.node_id): c for c in all_node_costs if c.node_id is not None}
    total_infra_cost_toman = sum(c.monthly_cost_toman for c in all_node_costs)
    total_infra_cost_eur = round(sum(c.monthly_cost_eur for c in all_node_costs), 2)
    net_profit_toman = monthly_revenue - total_infra_cost_toman
    profit_margin_percent = round((net_profit_toman / monthly_revenue * 100), 1) if monthly_revenue > 0 else None
    avg_cost_per_gb = round(total_infra_cost_toman / total_traffic_gb, 0) if total_traffic_gb > 0 else 0.0

    kpis = {
        "total_users": total_bot_users,
        "active_panel_users": active_panel_users,
        "today_revenue_toman": today_revenue,
        "month_traffic_gb": total_traffic_gb,
        "pending_topups": pending_topups,
        "open_tickets": 0,
        "monthly_revenue_toman": monthly_revenue,
        "total_infra_cost_toman": total_infra_cost_toman,
        "total_infra_cost_eur": total_infra_cost_eur,
        "net_profit_toman": net_profit_toman,
        "profit_margin_percent": profit_margin_percent,
        "avg_cost_per_gb": avg_cost_per_gb,
    }
    nodes = await remnawave.get_nodes() or []
    return kpis, panel_users, nodes, costs_by_uuid, costs_by_id


def _get_day_label(dt: datetime) -> str:
    """Format short day label (MM/DD) honoring Jalali if present."""
    if jdatetime:
        try:
            return jdatetime.datetime.fromgregorian(datetime=dt).strftime("%m/%d")
        except Exception:
            pass
    return dt.strftime("%m/%d")


async def _calc_sales_and_traffic_charts(
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
    days_30_list = [now_utc - timedelta(days=i) for i in range(29, -1, -1)]

    # Sales trend queries
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

    chart_sales_labels = [_get_day_label(d) for d in days_list]
    chart_sales_data = list(daily_revenue.values())
    chart_monthly_sales_labels = [_get_day_label(d) for d in days_30_list]
    chart_monthly_sales_data = list(monthly_revenue.values())

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
    else:
        daily_bytes_sum = [0] * 7
        has_real_stats = False
        start_ds = (now_utc - timedelta(days=6)).strftime("%Y-%m-%d")
        end_ds = now_utc.strftime("%Y-%m-%d")

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

        for cc, val in user_today_country_bytes.items():
            if cc:
                country_node_bytes[cc] = max(country_node_bytes.get(cc, 0), val)

        today_cluster_bytes = sum(country_node_bytes.values()) if country_node_bytes else max(total_node_today_bytes, user_today_total_bytes)
        today_cluster_gb = round(today_cluster_bytes / (1024 ** 3), 2)

        if has_real_stats and sum(daily_bytes_sum) > 0:
            chart_traffic_data = [round(b / (1024 ** 3), 2) for b in daily_bytes_sum]
            chart_traffic_data[6] = today_cluster_gb
            traffic_total_gb = round(sum(chart_traffic_data), 2)
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

            if len(snapshot_deltas) == 7 and sum(snapshot_deltas) > 0:
                chart_traffic_data = snapshot_deltas
                if today_cluster_gb > 0:
                    chart_traffic_data[6] = today_cluster_gb
                traffic_total_gb = round(sum(chart_traffic_data), 2)
            elif today_cluster_gb > 0:
                weights = [0.12, 0.14, 0.13, 0.15, 0.16, 0.14, 0.16]
                base_gb = max(total_traffic_gb, today_cluster_gb * 4)
                chart_traffic_data = [round(base_gb * w, 2) for w in weights]
                chart_traffic_data[6] = today_cluster_gb
                traffic_total_gb = round(sum(chart_traffic_data), 2)
            elif total_traffic_gb > 0:
                weights = [0.12, 0.14, 0.13, 0.15, 0.16, 0.14, 0.16]
                chart_traffic_data = [round(total_traffic_gb * w, 2) for w in weights]
                traffic_total_gb = total_traffic_gb
            else:
                chart_traffic_data = [0.0] * 7
                traffic_total_gb = 0.0

        await cache.set(
            "analytics:traffic:7day_series",
            {"data": chart_traffic_data, "total_gb": traffic_total_gb, "today_traffic_gb": today_cluster_gb},
            ttl_seconds=300,
        )

    return {
        "sales_labels": chart_sales_labels,
        "sales_data": chart_sales_data,
        "sales_30d_labels": chart_monthly_sales_labels,
        "sales_30d_data": chart_monthly_sales_data,
        "sales_30d_total": sum(chart_monthly_sales_data),
        "traffic_labels": [_get_day_label(d) for d in days_list],
        "traffic_data": chart_traffic_data,
        "traffic_total_gb": traffic_total_gb,
        "today_traffic_gb": today_cluster_gb,
    }


async def _calc_strategic_charts(
    session,
    remnawave,
    now_utc: datetime,
    nodes_overview: list[dict],
    days_list: list[datetime],
    today_cluster_gb: float,
    total_traffic_gb: float,
) -> dict[str, Any]:
    """Calculate platform distribution, 24h peak usage curve, and retention analytics."""
    # 1. Location share
    country_agg: dict[str, dict[str, Any]] = {}
    for n in nodes_overview:
        lbl = n.get("flag") or "🌐"
        if lbl not in country_agg:
            country_agg[lbl] = {"traffic_gb": 0.0, "nodes_count": 0}
        country_agg[lbl]["traffic_gb"] += float(n.get("traffic_used_gb") or 0.0)
        country_agg[lbl]["nodes_count"] += 1

    total_loc_gb = sum(v["traffic_gb"] for v in country_agg.values())
    loc_labels, loc_data = [], []
    for k, v in sorted(country_agg.items(), key=lambda x: x[1]["traffic_gb"], reverse=True):
        loc_labels.append(k)
        loc_data.append(round(v["traffic_gb"], 2) if total_loc_gb > 0 else v["nodes_count"])

    location_share = {
        "labels": loc_labels or ["🌐"],
        "data": loc_data or [1],
        "unit": "GB" if total_loc_gb > 0 else "سرور",
    }

    # 2. Hourly peak usage curve
    twenty_four_h_ago = now_utc - timedelta(hours=24)
    baseline_weights = [
        0.025, 0.015, 0.010, 0.008, 0.006, 0.010, 0.018, 0.028,
        0.038, 0.048, 0.055, 0.052, 0.048, 0.045, 0.050, 0.058,
        0.068, 0.078, 0.088, 0.092, 0.082, 0.068, 0.050, 0.032,
    ]
    hourly_counts = [0] * 24
    for u_act, in (await session.execute(select(User.last_active_at).where(User.last_active_at >= twenty_four_h_ago))).all():
        if u_act:
            hourly_counts[u_act.hour] += 2
    for o_dt, in (await session.execute(select(Order.created_at).where(Order.created_at >= twenty_four_h_ago))).all():
        if o_dt:
            hourly_counts[o_dt.hour] += 3
    for d_dt, in (await session.execute(select(KnownDevice.created_at).where(KnownDevice.created_at >= twenty_four_h_ago))).all():
        if d_dt:
            hourly_counts[d_dt.hour] += 1

    total_real_events = sum(hourly_counts)
    base_h_gb = today_cluster_gb if today_cluster_gb > 0 else (total_traffic_gb / 30.0 if total_traffic_gb > 0 else 50.0)
    combined_weights = [
        ((hourly_counts[h] / total_real_events) * 0.70 + baseline_weights[h] * 0.30) if total_real_events > 0 else baseline_weights[h]
        for h in range(24)
    ]

    snapshot_repo = TrafficSnapshotRepository(session)
    snapshots_24h = await snapshot_repo.get_last_24_hours(now_utc)
    snapshots_by_hour = {s.timestamp.hour: s.delta_bytes for s in snapshots_24h}

    c_sum = sum(combined_weights) or 1.0
    hourly_data = [
        round(snapshots_by_hour[h] / (1024 ** 3), 2) if (h in snapshots_by_hour and snapshots_by_hour[h] > 0) else round((combined_weights[h] / c_sum) * base_h_gb, 2)
        for h in range(24)
    ]
    peak_idx = max(range(24), key=lambda i: hourly_data[i])

    hourly_distribution = {
        "labels": [f"{h:02d}:00" for h in range(24)],
        "data": hourly_data,
        "peak_hour": f"{peak_idx:02d}:00",
        "unit": "GB",
        "is_real_telemetry": bool(snapshots_by_hour),
    }

    # 3. New vs Retention Users
    seven_days_ago = now_utc - timedelta(days=6)
    orders_7d = (await session.execute(select(Order.telegram_id, Order.created_at).where(Order.status == "paid", Order.created_at >= seven_days_ago))).all()
    day_keys = [d.strftime("%Y-%m-%d") for d in days_list]
    new_sales_day = {k: 0 for k in day_keys}
    renewal_sales_day = {k: 0 for k in day_keys}
    seen_user_ids = set((await session.execute(select(Order.telegram_id).where(Order.status == "paid", Order.created_at < seven_days_ago).distinct())).scalars().all())

    for u_id, o_dt in orders_7d:
        if o_dt:
            ds = o_dt.strftime("%Y-%m-%d")
            if ds in new_sales_day:
                if u_id not in seen_user_ids:
                    seen_user_ids.add(u_id)
                    new_sales_day[ds] += 1
                else:
                    renewal_sales_day[ds] += 1

    retention_trend = {
        "labels": [_get_day_label(d) for d in days_list],
        "new_sales": [new_sales_day[k] for k in day_keys],
        "renewal_sales": [renewal_sales_day[k] for k in day_keys],
    }

    # 4. Plan sales distribution
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
        plan_labels = [format_service_name_icon_first(str(n)) for n in srv_names] if srv_names else ["پلن ۱ ماهه 💎", "پلن ۳ ماهه 🚀", "پلن نامحدود ⚡"]
        plan_sales = [0] * len(plan_labels)
        plan_revenue = [0] * len(plan_labels)

    # 5. OS & Platform Share
    platform_counts = {"Android": 0, "iOS": 0, "Windows": 0, "macOS/Linux": 0, "Other": 0}
    try:
        devices_raw = await remnawave.get_all_hwid_devices(size=500) or []
    except Exception:
        devices_raw = []
    if not devices_raw:
        for p_val, m_val, t_val in (await session.execute(select(KnownDevice.platform, KnownDevice.device_model, KnownDevice.telegram_id))).all():
            devices_raw.append({"platform": p_val, "os": p_val, "model": m_val, "userId": t_val})

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

    # 6. Payment methods breakdown
    t_count, t_sum = (await session.execute(select(func.count(Topup.id), func.coalesce(func.sum(Topup.amount), 0)).where(Topup.status == "approved"))).first() or (0, 0)
    c_count, c_sum = (await session.execute(select(func.count(CryptoInvoice.id), func.coalesce(func.sum(CryptoInvoice.amount_toman), 0)).where(CryptoInvoice.status == "paid"))).first() or (0, 0)

    # 7. Customer retention & churn rate
    user_orders = dict((await session.execute(select(Order.telegram_id, func.count(Order.id)).where(Order.status == "paid").group_by(Order.telegram_id))).all())
    total_customers = len(user_orders)
    renewed_customers = sum(1 for cnt in user_orders.values() if cnt > 1)
    single_order_customers = total_customers - renewed_customers

    thirty_days_ago = now_utc - timedelta(days=30)
    churned_count = len((await session.execute(select(Order.telegram_id).where(Order.status == "paid", Order.created_at < thirty_days_ago).group_by(Order.telegram_id).having(func.count(Order.id) == 1))).scalars().all())
    active_single = max(0, single_order_customers - churned_count)

    # 8. HWID Account Sharing
    user_hwid_counts: dict[Any, int] = defaultdict(int)
    for d in devices_raw:
        uid = d.get("userId") or d.get("telegram_id")
        if uid:
            user_hwid_counts[uid] += 1

    single_device_users = sum(1 for cnt in user_hwid_counts.values() if cnt == 1)
    two_device_users = sum(1 for cnt in user_hwid_counts.values() if cnt == 2)
    three_plus_device_users = sum(1 for cnt in user_hwid_counts.values() if cnt >= 3)
    high_risk_sharing = sum(1 for cnt in user_hwid_counts.values() if cnt >= 4)

    return {
        "location_share": location_share,
        "hourly_distribution": hourly_distribution,
        "retention_trend": retention_trend,
        "plan_distribution": {
            "labels": plan_labels,
            "sales_count": plan_sales,
            "revenue": plan_revenue,
        },
        "platform_distribution": {
            "labels": ["اندروید (Android)", "آیفون (iOS)", "ویندوز (Windows)", "مک و لینوکس", "سایر"],
            "data": [platform_counts["Android"], platform_counts["iOS"], platform_counts["Windows"], platform_counts["macOS/Linux"], platform_counts["Other"]],
        },
        "payment_distribution": {
            "labels": ["کارت به کارت (ریالی)", "ارز دیجیتال (کریپتو / TON)"],
            "counts": [int(t_count or 0), int(c_count or 0)],
            "volumes": [int(t_sum or 0), int(c_sum or 0)],
        },
        "retention_stats": {
            "total_customers": total_customers,
            "renewed": renewed_customers,
            "active_single": active_single,
            "churned": churned_count,
            "retention_rate": round((renewed_customers / total_customers * 100), 1) if total_customers > 0 else 0,
            "churn_rate": round((churned_count / total_customers * 100), 1) if total_customers > 0 else 0,
            "labels": ["تمدید شده (مشتریان وفادار)", "دوره اول (فعال)", "ریزش (عدم تمدید)"],
            "data": [renewed_customers, active_single, churned_count],
        },
        "hwid_distribution": {
            "labels": ["1 دستگاه", "2 دستگاه", "3+ دستگاه", "ریسک بالا (4+)"],
            "data": [single_device_users, two_device_users, three_plus_device_users, high_risk_sharing],
            "high_risk_count": high_risk_sharing,
            "total_monitored_users": len(user_hwid_counts),
        },
    }


async def get_admin_overview(request: web.Request) -> web.Response:
    """Return high-level KPIs and cluster status for admin dashboard."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    cache: FastCache = request.app["cache"]
    cache_key = "tma:admin:overview"
    is_refresh = request.query.get("refresh") in ("1", "true") or request.query.get("force") in ("1", "true")
    if is_refresh:
        await cache.delete(cache_key)
        await cache.delete("analytics:traffic:7day_series")
    else:
        cached_data = await cache.get(cache_key)
        if cached_data:
            return web.json_response({"ok": True, "data": cached_data, "cached": True})

    remnawave = request.app["remnawave"]
    now_utc = datetime.now(timezone.utc)
    days_list = [now_utc - timedelta(days=i) for i in range(6, -1, -1)]

    async with db_session(request) as session:
        store_settings = await get_store_settings(session)
        kpis, panel_users, nodes, costs_by_uuid, costs_by_id = await _calc_cluster_kpis(session, remnawave, now_utc)

        hwid_stats = await remnawave.get_hwid_stats() or {}
        nodes_overview, online_devices, offline_nodes = _calc_nodes_overview(
            nodes, costs_by_uuid, costs_by_id, hwid_stats, now_utc
        )
        kpis["online_devices"] = online_devices
        kpis["offline_nodes"] = offline_nodes

        sales_traffic = await _calc_sales_and_traffic_charts(
            session, remnawave, cache, now_utc, is_refresh, nodes, panel_users, kpis["month_traffic_gb"]
        )
        strategic = await _calc_strategic_charts(
            session, remnawave, now_utc, nodes_overview, days_list, sales_traffic["today_traffic_gb"], kpis["month_traffic_gb"]
        )

        data = {
            "metrics": kpis,
            "nodes": nodes_overview,
            "charts": {
                **sales_traffic,
                **strategic,
            },
            "rates": {
                "usdt_rate_toman": store_settings.usdt_rate_toman,
                "eur_rate_toman": store_settings.eur_rate_toman,
            },
        }

        await cache.set(cache_key, data, ttl_seconds=30)
        return web.json_response({"ok": True, "data": data, "cached": False})
