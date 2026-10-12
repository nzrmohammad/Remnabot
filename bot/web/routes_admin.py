"""Admin API endpoints for Telegram Mini App Management Suite.

Central router aggregating domain-specific modular handlers:
- `bot.web.admin_users`: User accounts, sessions, SRH, HWID, and batch operations.
- `bot.web.admin_tickets`: Support tickets and bidirectional chat.
- `bot.web.admin_plans`: Services, packages, and coupon management.
- `bot.web.admin_topups`: Wallet topup verification and receipt inspection.
- `bot.web.admin_campaigns`: Mass messaging, broadcasts, and marketing campaigns.
"""
import asyncio
import json
import logging
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

from aiohttp import web
from sqlalchemy import func, select

from bot.common.helpers import get_limit_bytes, get_used_bytes
from bot.db.models import AdminLog, AppSetting, Coupon, CryptoInvoice, KnownDevice, NodeCost, Order, Service, Topup, User, Wallet
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.node_cost_repo import NodeCostRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.handlers.admin_nodes import COUNTRY_FLAGS_MAP
from bot.services.app_settings import get_store_settings
from bot.services.formatting import country_flag
from bot.web.admin_common import _check_admin, format_service_name_icon_first
from bot.web.cache import FastCache

try:
    import jdatetime
except ImportError:
    jdatetime = None

logger = logging.getLogger(__name__)

# Re-export modular domain handlers for seamless backward-compatibility
from bot.web.admin_users import (
    get_admin_users,
    post_admin_modify_user,
    post_admin_kill_sessions,
    post_admin_toggle_ban,
    post_admin_reset_trial,
    post_admin_user_wallet,
    post_admin_user_revoke_sub,
    get_admin_user_hwid_devices,
    get_admin_user_sessions,
    get_admin_sessions_explorer,
    get_admin_user_srh,
    post_admin_users_bulk_action,
    post_admin_user_delete_hwid,
)
from bot.web.admin_tickets import (
    get_admin_ticket_threads,
    get_admin_ticket_messages,
    post_admin_reply_ticket,
)
from bot.web.admin_plans import (
    get_admin_plans,
    post_admin_plan_save,
    post_admin_plan_toggle,
    post_admin_plan_delete,
    get_admin_coupons,
    post_admin_coupon_save,
    post_admin_coupon_toggle,
    post_admin_coupon_delete,
    get_admin_coupon_usages,
)
from bot.web.admin_topups import (
    get_admin_topups,
    post_admin_topup_action,
    get_admin_topup_photo,
)
from bot.web.admin_campaigns import (
    _BROADCAST_STATUSES,
    post_admin_broadcast,
    get_admin_broadcast_status,
    get_admin_campaigns,
    post_admin_campaign_create,
    post_admin_campaign_delete,
)

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

    session_factory = request.app["session_factory"]
    remnawave = request.app["remnawave"]

    async with session_factory() as session:
        store_settings = await get_store_settings(session)

        # 1. Total users count in bot DB
        user_count_res = await session.execute(select(func.count(User.id)))
        total_bot_users = int(user_count_res.scalar_one() or 0)

        # 2. Today's revenue
        now_utc = datetime.now(timezone.utc)
        start_of_day = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
        rev_res = await session.execute(
            select(func.coalesce(func.sum(Order.amount), 0)).where(
                Order.created_at >= start_of_day,
                Order.status == "paid",
            )
        )
        today_revenue = int(rev_res.scalar_one() or 0)

        # 3. Pending topup receipts
        topup_res = await session.execute(
            select(func.count(Topup.id)).where(Topup.status == "pending")
        )
        pending_topups = int(topup_res.scalar_one() or 0)

        # 4. Open support tickets (only real pending tickets; SupportMessage has no pending status)
        open_tickets = 0

        # 5. Remnawave cluster metrics
        panel_users = await remnawave.get_all_panel_users(size=1000) or []
        active_panel_users = sum(1 for u in panel_users if str(u.get("status", "")).upper() == "ACTIVE")

        # Sum of traffic used across panel using helper get_used_bytes
        total_traffic_bytes = sum(get_used_bytes(u) for u in panel_users)
        total_traffic_gb = round(total_traffic_bytes / (1024 ** 3), 2)

        # 30-day revenue for Net Profit & Infra-Billing
        thirty_days_ago = now_utc - timedelta(days=30)
        rev_30d_res = await session.execute(
            select(func.coalesce(func.sum(Order.amount), 0)).where(
                Order.created_at >= thirty_days_ago,
                Order.status == "paid",
            )
        )
        monthly_revenue = int(rev_30d_res.scalar_one() or 0)

        # Node infra costs mapping
        node_cost_repo = NodeCostRepository(session)
        all_node_costs = await node_cost_repo.list_all()
        costs_by_uuid = {str(c.node_uuid): c for c in all_node_costs}
        costs_by_id = {str(c.node_id): c for c in all_node_costs if c.node_id is not None}
        total_infra_cost_toman = sum(c.monthly_cost_toman for c in all_node_costs)
        total_infra_cost_eur = round(sum(c.monthly_cost_eur for c in all_node_costs), 2)
        net_profit_toman = monthly_revenue - total_infra_cost_toman
        profit_margin_percent = round((net_profit_toman / monthly_revenue * 100), 1) if monthly_revenue > 0 else None
        avg_cost_per_gb = round(total_infra_cost_toman / total_traffic_gb, 0) if total_traffic_gb > 0 else 0.0

        # Node information with country flags and real-time online status
        nodes = await remnawave.get_nodes() or []
        nodes_overview = []
        for i, n in enumerate(nodes, start=1):
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

            sys_info = n.get("system") or n.get("sys") or n.get("metrics") or n.get("usage") or {}

            # Helper functions to extract metrics safely without altering genuine panel values
            def _extract_cpu(src: dict) -> float | None:
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

            # Extract CPU, RAM & speeds from Remnawave v3 contract structure (system.info and system.stats)
            raw_sys = n.get("system") or n.get("sys") or {}
            sys_stats = raw_sys.get("stats") if isinstance(raw_sys, dict) else {}
            sys_info_meta = raw_sys.get("info") if isinstance(raw_sys, dict) else {}

            # CPU percentage (loadAvg[0] / cpus * 100)
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
                cpu_val = _extract_cpu(raw_sys)
            if cpu_val is None:
                cpu_val = _extract_cpu(n)

            # RAM percentage (memoryUsed / memoryTotal * 100)
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
                ram_val = _extract_ram(raw_sys)
            if ram_val is None:
                ram_val = _extract_ram(n)

            # Network download & upload speeds
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
                cpu_val = 0.0
                ram_val = 0.0
                dl_speed = 0.0
                ul_speed = 0.0

            address = str(n.get("address") or "—")
            port = n.get("port")
            addr_str = f"{address}:{port}" if port else address
            traffic_used = n.get("trafficUsedBytes") or n.get("usedTrafficBytes") or 0
            traffic_used_gb = round(traffic_used / (1024**3), 2) if traffic_used else 0.0

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
                        j_dt = jdatetime.datetime.fromgregorian(datetime=cost_entry.due_date)
                        due_date_jalali = j_dt.strftime("%Y/%m/%d")
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

            nodes_overview.append({
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
            })

        hwid_stats = await remnawave.get_hwid_stats() or {}
        sum_node_online = sum(n["connected_users"] for n in nodes_overview)
        online_dev = (
            hwid_stats.get("onlineDevices")
            or hwid_stats.get("online_devices")
            or hwid_stats.get("activeDevices")
        )
        if online_dev is not None and int(online_dev) > 0:
            online_devices = int(online_dev)
        else:
            online_devices = sum_node_online

        offline_nodes = sum(1 for n in nodes_overview if n["status"] == "OFFLINE")

        # 7-day and 30-day sales trend for dashboard charts
        seven_days_ago = now_utc - timedelta(days=6)
        thirty_days_ago = now_utc - timedelta(days=29)
        rev_30d_res = await session.execute(
            select(Order.created_at, Order.amount)
            .where(Order.status == "paid", Order.created_at >= thirty_days_ago)
        )
        rev_30d_rows = rev_30d_res.all()
        daily_revenue = {(now_utc - timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(6, -1, -1)}
        monthly_revenue = {(now_utc - timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(29, -1, -1)}
        for cat_dt, amt in rev_30d_rows:
            if cat_dt:
                ds = cat_dt.strftime("%Y-%m-%d")
                if ds in daily_revenue:
                    daily_revenue[ds] += (amt or 0)
                if ds in monthly_revenue:
                    monthly_revenue[ds] += (amt or 0)

        def _get_day_label(dt: datetime) -> str:
            if jdatetime:
                try:
                    return jdatetime.datetime.fromgregorian(datetime=dt).strftime("%m/%d")
                except Exception:
                    pass
            return dt.strftime("%m/%d")

        days_list = [now_utc - timedelta(days=i) for i in range(6, -1, -1)]
        chart_sales_labels = [_get_day_label(d) for d in days_list]
        chart_sales_data = list(daily_revenue.values())

        days_30_list = [now_utc - timedelta(days=i) for i in range(29, -1, -1)]
        chart_monthly_sales_labels = [_get_day_label(d) for d in days_30_list]
        chart_monthly_sales_data = list(monthly_revenue.values())
        monthly_sales_total = sum(chart_monthly_sales_data)

        # 7-day traffic consumption trend for dashboard charts
        traffic_result = await session.execute(
            select(Order.created_at, func.coalesce(Order.traffic_gb, Service.traffic_gb, 0))
            .join(Service, Order.service_id == Service.id, isouter=True)
            .where(Order.status == "paid", Order.created_at >= seven_days_ago)
        )
        traffic_rows = traffic_result.all()
        daily_traffic = {(now_utc - timedelta(days=i)).strftime("%Y-%m-%d"): 0.0 for i in range(6, -1, -1)}
        for cat_dt, t_gb in traffic_rows:
            if cat_dt:
                ds = cat_dt.strftime("%Y-%m-%d")
                if ds in daily_traffic:
                    daily_traffic[ds] += float(t_gb or 0)

        chart_traffic_labels = [_get_day_label(d) for d in days_list]

        # Calculate today's real cluster traffic matching bot reports exactly
        country_node_bytes: dict[str, int] = {}
        total_node_today_bytes = 0
        for n in nodes:
            if isinstance(n, dict):
                cc = str(n.get("countryCode") or n.get("country_code") or "").strip().upper()
                tb = (
                    n.get("trafficDailyBytes")
                    or n.get("dailyTrafficBytes")
                    or n.get("todayTrafficBytes")
                    or n.get("traffic")
                    or 0
                )
                try:
                    val = int(tb)
                    if cc:
                        country_node_bytes[cc] = country_node_bytes.get(cc, 0) + val
                    total_node_today_bytes += val
                except (ValueError, TypeError):
                    pass

        # 7-day traffic consumption trend for dashboard charts
        # Check cache for recent 7-day series unless explicitly refreshed
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

            # Remnawave user bandwidth stats for active panel users (aligned with bot reports)
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
                                            b_val = int(float(val or 0))
                                            daily_bytes_sum[idx] += b_val
                                        except (ValueError, TypeError):
                                            pass
                                val_today = int(float(s_data[-1])) if s_data else int(float(s.get("total") or 0))
                                if val_today > 0:
                                    if cc:
                                        user_today_country_bytes[cc] = user_today_country_bytes.get(cc, 0) + val_today
                                    user_today_total_bytes += val_today
                except Exception as exc:
                    logger.debug("Failed fetching user bandwidth stats: %s", exc)

            # Reconcile node telemetry and user bandwidth stats exactly as admin_summaries does
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
                # Track and check daily snapshot history in cache
                today_ds = now_utc.strftime("%Y-%m-%d")
                await cache.set(f"analytics:traffic:snapshot:{today_ds}", total_traffic_gb, ttl_seconds=86400 * 30)

                snapshot_deltas: list[float] = []
                for i in range(6, -1, -1):
                    target_ds = (now_utc - timedelta(days=i)).strftime("%Y-%m-%d")
                    prev_ds = (now_utc - timedelta(days=i + 1)).strftime("%Y-%m-%d")
                    s_curr = await cache.get(f"analytics:traffic:snapshot:{target_ds}")
                    s_prev = await cache.get(f"analytics:traffic:snapshot:{prev_ds}")
                    if s_curr is not None and s_prev is not None:
                        delta = max(0.0, float(s_curr) - float(s_prev))
                        snapshot_deltas.append(round(delta, 2))
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
                ttl_seconds=300
            )

        # -------------------------------------------------------------
        # 4 Strategic Management Charts
        # -------------------------------------------------------------
        # 1. Location share (from nodes_overview) - Emoji flag only (no NL/code text)
        country_agg: dict[str, dict[str, Any]] = {}
        for n in nodes_overview:
            flag = n.get("flag") or "🌐"
            lbl = flag
            if lbl not in country_agg:
                country_agg[lbl] = {"traffic_gb": 0.0, "nodes_count": 0}
            country_agg[lbl]["traffic_gb"] += float(n.get("traffic_used_gb") or 0.0)
            country_agg[lbl]["nodes_count"] += 1

        total_loc_gb = sum(v["traffic_gb"] for v in country_agg.values())
        loc_labels = []
        loc_data = []
        for k, v in sorted(country_agg.items(), key=lambda x: x[1]["traffic_gb"], reverse=True):
            loc_labels.append(k)
            loc_data.append(round(v["traffic_gb"], 2) if total_loc_gb > 0 else v["nodes_count"])

        if not loc_labels:
            loc_labels = ["🌐"]
            loc_data = [1]

        location_share = {
            "labels": loc_labels,
            "data": loc_data,
            "unit": "GB" if total_loc_gb > 0 else "سرور",
        }

        # 2. 24h Dynamic Peak Usage Distribution (Hourly traffic curve)
        now_dt = datetime.now(timezone.utc)
        twenty_four_h_ago = now_dt - timedelta(hours=24)

        baseline_weights = [
            0.025, 0.015, 0.010, 0.008, 0.006, 0.010, 0.018, 0.028,
            0.038, 0.048, 0.055, 0.052, 0.048, 0.045, 0.050, 0.058,
            0.068, 0.078, 0.088, 0.092, 0.082, 0.068, 0.050, 0.032
        ]

        hourly_counts = [0] * 24

        act_res = await session.execute(
            select(User.last_active_at).where(User.last_active_at >= twenty_four_h_ago)
        )
        for (u_act,) in act_res.all():
            if u_act:
                hourly_counts[u_act.hour] += 2

        ord_res = await session.execute(
            select(Order.created_at).where(Order.created_at >= twenty_four_h_ago)
        )
        for (o_dt,) in ord_res.all():
            if o_dt:
                hourly_counts[o_dt.hour] += 3

        dev_res = await session.execute(
            select(KnownDevice.created_at).where(KnownDevice.created_at >= twenty_four_h_ago)
        )
        for (d_dt,) in dev_res.all():
            if d_dt:
                hourly_counts[d_dt.hour] += 1

        total_real_events = sum(hourly_counts)
        base_h_gb = today_cluster_gb if today_cluster_gb > 0 else (total_traffic_gb / 30.0 if total_traffic_gb > 0 else 50.0)

        combined_weights = []
        for h in range(24):
            if total_real_events > 0:
                real_ratio = hourly_counts[h] / total_real_events
                weight = (real_ratio * 0.70) + (baseline_weights[h] * 0.30)
            else:
                weight = baseline_weights[h]
            combined_weights.append(weight)

        from bot.db.repositories.traffic_snapshot_repo import TrafficSnapshotRepository
        snapshot_repo = TrafficSnapshotRepository(session)
        snapshots_24h = await snapshot_repo.get_last_24_hours(now_utc)
        snapshots_by_hour = {s.timestamp.hour: s.delta_bytes for s in snapshots_24h}

        c_sum = sum(combined_weights) or 1.0
        hourly_labels = [f"{h:02d}:00" for h in range(24)]
        hourly_data = []
        for h in range(24):
            val = round(snapshots_by_hour[h] / (1024 ** 3), 2) if (h in snapshots_by_hour and snapshots_by_hour[h] > 0) else round((combined_weights[h] / c_sum) * base_h_gb, 2)
            hourly_data.append(round(val, 2))

        peak_idx = max(range(24), key=lambda i: hourly_data[i])
        peak_hour_str = f"{peak_idx:02d}:00"

        hourly_distribution = {
            "labels": hourly_labels,
            "data": hourly_data,
            "peak_hour": peak_hour_str,
            "unit": "GB",
            "is_real_telemetry": bool(snapshots_by_hour),
        }

        # 3. New vs Retention Users (7-day stacked bar)
        seven_orders_res = await session.execute(
            select(Order.telegram_id, Order.created_at)
            .where(Order.status == "paid", Order.created_at >= seven_days_ago)
        )
        orders_7d = seven_orders_res.all()
        day_keys = [d.strftime("%Y-%m-%d") for d in days_list]
        new_sales_day = {k: 0 for k in day_keys}
        renewal_sales_day = {k: 0 for k in day_keys}
        seen_user_ids: set[int] = set()

        prior_res = await session.execute(
            select(Order.telegram_id).where(Order.status == "paid", Order.created_at < seven_days_ago).distinct()
        )
        for uid in prior_res.scalars().all():
            if uid:
                seen_user_ids.add(uid)

        for u_id, o_dt in orders_7d:
            if not o_dt:
                continue
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

        # 4. Plan Sales Breakdown
        plan_res = await session.execute(
            select(Service.name, func.count(Order.id), func.coalesce(func.sum(Order.amount), 0))
            .join(Service, Order.service_id == Service.id)
            .where(Order.status == "paid")
            .group_by(Service.name)
            .order_by(func.count(Order.id).desc())
            .limit(5)
        )
        plan_rows = plan_res.all()
        if plan_rows:
            plan_labels = [format_service_name_icon_first(str(r[0])) for r in plan_rows]
            plan_sales = [int(r[1]) for r in plan_rows]
            plan_revenue = [int(r[2]) for r in plan_rows]
        else:
            srv_res = await session.execute(select(Service.name).where(Service.is_active.is_(True)).limit(5))
            srv_names = srv_res.scalars().all()
            plan_labels = [format_service_name_icon_first(str(n)) for n in srv_names] if srv_names else ["پلن ۱ ماهه 💎", "پلن ۳ ماهه 🚀", "پلن نامحدود ⚡"]
            plan_sales = [0] * len(plan_labels)
            plan_revenue = [0] * len(plan_labels)

        plan_distribution = {
            "labels": plan_labels,
            "sales_count": plan_sales,
            "revenue": plan_revenue,
        }

        # 5. OS & Platform Share (Android / iOS / Windows / macOS / Linux)
        platform_counts = {"Android": 0, "iOS": 0, "Windows": 0, "macOS/Linux": 0, "Other": 0}
        devices_raw: list[dict[str, Any]] = []
        try:
            devices_raw = await remnawave.get_all_hwid_devices(size=500) or []
        except Exception:
            pass
        if not devices_raw:
            kd_res = await session.execute(select(KnownDevice.platform, KnownDevice.device_model, KnownDevice.telegram_id))
            kd_rows = kd_res.all()
            for p_val, m_val, t_val in kd_rows:
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

        platform_distribution = {
            "labels": ["اندروید (Android)", "آیفون (iOS)", "ویندوز (Windows)", "مک و لینوکس", "سایر"],
            "data": [
                platform_counts["Android"],
                platform_counts["iOS"],
                platform_counts["Windows"],
                platform_counts["macOS/Linux"],
                platform_counts["Other"],
            ],
        }

        # 6. Payment Methods Breakdown (Card vs Crypto)
        topup_res = await session.execute(
            select(func.count(Topup.id), func.coalesce(func.sum(Topup.amount), 0)).where(Topup.status == "approved")
        )
        t_count, t_sum = topup_res.first() or (0, 0)

        crypto_res = await session.execute(
            select(func.count(CryptoInvoice.id), func.coalesce(func.sum(CryptoInvoice.amount_toman), 0)).where(CryptoInvoice.status == "paid")
        )
        c_count, c_sum = crypto_res.first() or (0, 0)

        payment_distribution = {
            "labels": ["کارت به کارت (ریالی)", "ارز دیجیتال (کریپتو / TON)"],
            "counts": [int(t_count or 0), int(c_count or 0)],
            "volumes": [int(t_sum or 0), int(c_sum or 0)],
        }

        # 7. Retention & Churn Rate Analysis
        user_orders_res = await session.execute(
            select(Order.telegram_id, func.count(Order.id))
            .where(Order.status == "paid")
            .group_by(Order.telegram_id)
        )
        user_orders = dict(user_orders_res.all())
        total_customers = len(user_orders)
        renewed_customers = sum(1 for cnt in user_orders.values() if cnt > 1)
        single_order_customers = total_customers - renewed_customers

        thirty_days_ago = now_utc - timedelta(days=30)
        old_single_res = await session.execute(
            select(Order.telegram_id)
            .where(Order.status == "paid", Order.created_at < thirty_days_ago)
            .group_by(Order.telegram_id)
            .having(func.count(Order.id) == 1)
        )
        churned_count = len(old_single_res.scalars().all())
        active_single = max(0, single_order_customers - churned_count)

        retention_rate = round((renewed_customers / total_customers * 100), 1) if total_customers > 0 else 0
        churn_rate = round((churned_count / total_customers * 100), 1) if total_customers > 0 else 0

        retention_stats = {
            "total_customers": total_customers,
            "renewed": renewed_customers,
            "active_single": active_single,
            "churned": churned_count,
            "retention_rate": retention_rate,
            "churn_rate": churn_rate,
            "labels": ["تمدید شده (مشتریان وفادار)", "دوره اول (فعال)", "ریزش (عدم تمدید)"],
            "data": [renewed_customers, active_single, churned_count],
        }

        # 8. HWID Inspector Distribution & Account Sharing Risk
        user_hwid_counts: dict[Any, int] = defaultdict(int)
        for d in devices_raw:
            uid = d.get("userId") or d.get("telegram_id")
            if uid:
                user_hwid_counts[uid] += 1

        single_device_users = sum(1 for cnt in user_hwid_counts.values() if cnt == 1)
        two_device_users = sum(1 for cnt in user_hwid_counts.values() if cnt == 2)
        three_plus_device_users = sum(1 for cnt in user_hwid_counts.values() if cnt >= 3)
        high_risk_sharing = sum(1 for cnt in user_hwid_counts.values() if cnt >= 4)

        hwid_distribution = {
            "labels": ["1 دستگاه", "2 دستگاه", "3+ دستگاه", "ریسک بالا (4+)"],
            "data": [single_device_users, two_device_users, three_plus_device_users, high_risk_sharing],
            "high_risk_count": high_risk_sharing,
            "total_monitored_users": len(user_hwid_counts),
        }

        data = {
            "metrics": {
                "total_users": total_bot_users,
                "active_panel_users": active_panel_users,
                "today_revenue_toman": today_revenue,
                "month_traffic_gb": total_traffic_gb,
                "online_devices": online_devices,
                "pending_topups": pending_topups,
                "open_tickets": open_tickets,
                "offline_nodes": offline_nodes,
                "monthly_revenue_toman": monthly_revenue,
                "total_infra_cost_toman": total_infra_cost_toman,
                "total_infra_cost_eur": total_infra_cost_eur,
                "net_profit_toman": net_profit_toman,
                "profit_margin_percent": profit_margin_percent,
                "avg_cost_per_gb": avg_cost_per_gb,
            },
            "nodes": nodes_overview,
            "charts": {
                "sales_labels": chart_sales_labels,
                "sales_data": chart_sales_data,
                "sales_30d_labels": chart_monthly_sales_labels,
                "sales_30d_data": chart_monthly_sales_data,
                "sales_30d_total": monthly_sales_total,
                "traffic_labels": chart_traffic_labels,
                "traffic_data": chart_traffic_data,
                "traffic_total_gb": traffic_total_gb,
                "today_traffic_gb": today_cluster_gb,
                "location_share": location_share,
                "hourly_distribution": hourly_distribution,
                "retention_trend": retention_trend,
                "plan_distribution": plan_distribution,
                "platform_distribution": platform_distribution,
                "payment_distribution": payment_distribution,
                "retention_stats": retention_stats,
                "hwid_distribution": hwid_distribution,
            },
            "rates": {
                "usdt_rate_toman": store_settings.usdt_rate_toman,
                "eur_rate_toman": store_settings.eur_rate_toman,
            },
        }

        await cache.set(cache_key, data, ttl_seconds=30)
        return web.json_response({"ok": True, "data": data, "cached": False})


async def get_admin_settings(request: web.Request) -> web.Response:
    """Return runtime editable app settings."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        store_settings = await get_store_settings(session)
        app_repo = AppSettingRepository(session)
        maint_val = await app_repo.get("maintenance")
        is_maintenance = maint_val == "1"

        data = {
            "maintenance": is_maintenance,
            "card_enabled": store_settings.card_enabled,
            "crypto_enabled": store_settings.crypto_enabled,
            "card_number": store_settings.card_number,
            "card_holder": store_settings.card_holder,
            "topup_min_amount": store_settings.topup_min_amount,
            "usdt_rate_toman": store_settings.usdt_rate_toman,
            "eur_rate_toman": store_settings.eur_rate_toman,
            "ton_rate_toman": store_settings.ton_rate_toman,
            "ton_wallet_address": store_settings.ton_wallet_address,
            "trial_enabled": store_settings.trial_enabled,
            "trial_traffic_gb": store_settings.trial_traffic_gb,
            "trial_duration_days": store_settings.trial_duration_days,
            "referral_enabled": store_settings.referral_enabled,
            "referral_reward_gb": store_settings.referral_reward_gb,
            "support_contact": store_settings.support_contact,
            "support_direct_enabled": store_settings.support_direct_enabled,
            "topic_topups": store_settings.topic_topups,
            "topic_orders": store_settings.topic_orders,
            "topic_support": store_settings.topic_support,
            "topic_alerts": store_settings.topic_alerts,
            "topic_crypto": store_settings.topic_crypto,
            "topic_errors": store_settings.topic_errors,
            "access_mode": store_settings.access_mode,
            "stars_enabled": store_settings.stars_enabled,
            "stars_rate_toman": store_settings.stars_rate_toman,
            "cryptobot_enabled": store_settings.cryptobot_enabled,
            "cryptobot_token": store_settings.cryptobot_token,
            "tutorial_channel_url": store_settings.tutorial_channel_url,
            "routing_tutorial_url": store_settings.routing_tutorial_url,
            "client_apps_json": store_settings.client_apps_json,
        }
        bot = request.app.get("bot")
        settings_cfg = request.app.get("settings")
        bot_username = getattr(settings_cfg, "BOT_USERNAME", "") or ""
        if not bot_username and bot:
            me_obj = getattr(bot, "_me", None)
            if me_obj and getattr(me_obj, "username", None):
                bot_username = me_obj.username
            elif hasattr(bot, "get_me"):
                try:
                    bot_info = await bot.get_me()
                    bot_username = bot_info.username or ""
                except Exception:
                    pass
        data["bot_username"] = bot_username
        return web.json_response({"ok": True, "settings": data})


async def post_admin_settings(request: web.Request) -> web.Response:
    """Update runtime editable app settings."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        app_repo = AppSettingRepository(session)

        # Boolean flags
        bool_keys = (
            "maintenance",
            "card_enabled",
            "crypto_enabled",
            "trial_enabled",
            "referral_enabled",
            "support_direct_enabled",
            "stars_enabled",
            "cryptobot_enabled",
        )
        for bool_key in bool_keys:
            if bool_key in body:
                val = bool(body[bool_key])
                await app_repo.set(bool_key, "1" if val else "0")

        # String fields
        str_keys = (
            "card_number",
            "card_holder",
            "ton_wallet_address",
            "support_contact",
            "access_mode",
            "cryptobot_token",
            "tutorial_channel_url",
            "routing_tutorial_url",
            "client_apps_json",
        )
        for str_key in str_keys:
            if str_key in body:
                await app_repo.set(str_key, str(body[str_key]).strip())

        # Numeric fields
        num_keys = (
            "topup_min_amount",
            "usdt_rate_toman",
            "eur_rate_toman",
            "ton_rate_toman",
            "trial_traffic_gb",
            "trial_duration_days",
            "referral_reward_gb",
            "stars_rate_toman",
        )
        for num_key in num_keys:
            if num_key in body:
                try:
                    num_val = int(body[num_key])
                    await app_repo.set(num_key, str(num_val))
                except (ValueError, TypeError):
                    pass

        # Telegram Forum Topic IDs
        topic_keys = (
            "topic_topups",
            "topic_orders",
            "topic_support",
            "topic_alerts",
            "topic_crypto",
            "topic_errors",
        )
        for t_key in topic_keys:
            if t_key in body:
                raw_t = body[t_key]
                if raw_t is None or str(raw_t).strip() == "":
                    await app_repo.set(t_key, "")
                else:
                    try:
                        int_t = int(raw_t)
                        await app_repo.set(t_key, str(int_t))
                    except (ValueError, TypeError):
                        pass

        session.add(
            AdminLog(
                admin_id=admin["id"],
                action="update_settings",
                detail="به‌روزرسانی تنظیمات سیستم از مینی‌اپ",
            )
        )
        await session.commit()

    return web.json_response({"ok": True, "message": "تنظیمات با موفقیت ذخیره شد."})


async def get_admin_crypto_rates(request: web.Request) -> web.Response:
    """Fetch live market prices for TON and USDT from domestic exchanges (Nobitex, Bitpin, Wallex) and Binance."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        from bot.services.crypto.nobitex import fetch_all_exchange_prices
        session_factory = request.app["session_factory"]
        async with session_factory() as session:
            store = await get_store_settings(session)
            current_usdt = store.usdt_rate_toman

        market_data = await fetch_all_exchange_prices(usdt_rate=current_usdt)
        best_ton_val, best_ton_src = market_data.get("best_ton") or (None, "")
        best_usdt_val, best_usdt_src = market_data.get("best_usdt") or (None, "")
        best_eur_val, best_eur_src = market_data.get("best_eur") or (None, "")

        return web.json_response({
            "ok": True,
            "best_ton": {"price": best_ton_val, "source": best_ton_src},
            "best_usdt": {"price": best_usdt_val, "source": best_usdt_src},
            "best_eur": {"price": best_eur_val, "source": best_eur_src},
            "ton_prices": market_data.get("ton") or {},
            "usdt_prices": market_data.get("usdt") or {},
            "eur_prices": market_data.get("eur") or {},
            "binance_usd": market_data.get("binance_usd"),
            "binance_eur_usd": market_data.get("binance_eur_usd"),
        })
    except Exception as exc:
        logger.exception("Error fetching crypto rates: %s", exc)
        return web.json_response({"ok": False, "error": "خطا در استعلام آنلاین قیمت‌ها"}, status=500)


async def get_admin_infra_billing(request: web.Request) -> web.Response:
    """Return infrastructure billing analytics, server costs, net profit, and renewal dates."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    session_factory = request.app["session_factory"]
    remnawave = request.app["remnawave"]
    now_utc = datetime.now(timezone.utc)
    thirty_days_ago = now_utc - timedelta(days=30)

    try:
        async with session_factory() as session:
            # 30-day revenue
            rev_30d_res = await session.execute(
                select(func.coalesce(func.sum(Order.amount), 0)).where(
                    Order.created_at >= thirty_days_ago,
                    Order.status == "paid",
                )
            )
            monthly_revenue = int(rev_30d_res.scalar_one() or 0)

            node_cost_repo = NodeCostRepository(session)
            all_costs = await node_cost_repo.list_all()
            costs_by_uuid = {str(c.node_uuid): c for c in all_costs}
            costs_by_id = {str(c.node_id): c for c in all_costs if c.node_id is not None}

            nodes = await remnawave.get_nodes() or []
            total_infra_cost_toman = sum(c.monthly_cost_toman for c in all_costs)
            total_infra_cost_eur = round(sum(c.monthly_cost_eur for c in all_costs), 2)
            net_profit_toman = monthly_revenue - total_infra_cost_toman
            profit_margin_percent = round((net_profit_toman / monthly_revenue * 100), 1) if monthly_revenue > 0 else None

            nodes_data = []
            total_traffic_gb = 0.0
            for i, n in enumerate(nodes, start=1):
                n_uuid = str(n.get("uuid") or n.get("id") or "")
                n_id = n.get("id")
                raw_name = str(n.get("name") or f"Node {i}").strip()
                traffic_bytes = n.get("trafficUsedBytes") or n.get("usedTrafficBytes") or 0
                traffic_gb = round(traffic_bytes / (1024**3), 2) if traffic_bytes else 0.0
                total_traffic_gb += traffic_gb

                cost_item = costs_by_uuid.get(n_uuid) or costs_by_id.get(str(n_id) if n_id else "")
                due_date_str = None
                due_date_jalali = None
                days_left = None
                if cost_item and cost_item.due_date:
                    due_date_str = cost_item.due_date.strftime("%Y-%m-%d")
                    days_left = (cost_item.due_date.date() - now_utc.date()).days
                    if jdatetime:
                        try:
                            j_dt = jdatetime.datetime.fromgregorian(datetime=cost_item.due_date)
                            due_date_jalali = j_dt.strftime("%Y/%m/%d")
                        except Exception:
                            due_date_jalali = due_date_str
                    else:
                        due_date_jalali = due_date_str

                cost_toman = cost_item.monthly_cost_toman if cost_item else 0
                cost_eur = cost_item.monthly_cost_eur if cost_item else 0.0
                currency = getattr(cost_item, "currency", "EUR") or "EUR" if cost_item else "EUR"
                provider = cost_item.provider if cost_item else None
                notes = cost_item.notes if cost_item else None
                cost_per_gb = round(cost_toman / traffic_gb, 0) if (cost_toman > 0 and traffic_gb > 0) else 0.0

                is_connected = n.get("isConnected")
                if is_connected is None:
                    is_connected = str(n.get("status", "")).upper() in ("CONNECTED", "ONLINE")

                nodes_data.append({
                    "uuid": n_uuid,
                    "id": n_id,
                    "name": raw_name,
                    "address": str(n.get("address") or "—"),
                    "status": "ONLINE" if is_connected else "OFFLINE",
                    "traffic_used_gb": traffic_gb,
                    "provider": provider,
                    "monthly_cost_toman": cost_toman,
                    "monthly_cost_eur": cost_eur,
                    "currency": currency,
                    "due_date": due_date_str,
                    "due_date_jalali": due_date_jalali,
                    "days_until_due": days_left,
                    "cost_per_gb": cost_per_gb,
                    "notes": notes,
                })

            avg_cost_per_gb = round(total_infra_cost_toman / total_traffic_gb, 0) if total_traffic_gb > 0 else 0.0

            return web.json_response({
                "ok": True,
                "data": {
                    "monthly_revenue_toman": monthly_revenue,
                    "total_infra_cost_toman": total_infra_cost_toman,
                    "total_infra_cost_eur": total_infra_cost_eur,
                    "net_profit_toman": net_profit_toman,
                    "profit_margin_percent": profit_margin_percent,
                    "total_traffic_gb": round(total_traffic_gb, 2),
                    "avg_cost_per_gb": avg_cost_per_gb,
                    "nodes": nodes_data,
                }
            })
    except Exception as exc:
        logger.exception("Error in get_admin_infra_billing: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def post_admin_node_cost(request: web.Request) -> web.Response:
    """Save or update infrastructure costs and renewal date for a server node."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    node_uuid = str(body.get("node_uuid") or body.get("uuid") or "").strip()
    if not node_uuid:
        return web.json_response({"ok": False, "error": "شناسه نود الزامی است."}, status=400)

    node_id = body.get("node_id")
    if node_id is not None:
        try:
            node_id = int(node_id)
        except (ValueError, TypeError):
            node_id = None

    node_name = body.get("node_name")
    provider = body.get("provider")
    try:
        monthly_cost_toman = max(0, int(body.get("monthly_cost_toman") or 0))
    except (ValueError, TypeError):
        monthly_cost_toman = 0

    try:
        monthly_cost_eur = max(0.0, float(body.get("monthly_cost_eur") or 0.0))
    except (ValueError, TypeError):
        monthly_cost_eur = 0.0

    currency = str(body.get("currency") or "EUR").strip().upper()
    if currency not in ("EUR", "USD"):
        currency = "EUR"

    raw_due_date = body.get("due_date")
    due_date = None
    if raw_due_date:
        try:
            clean_due = str(raw_due_date).strip()[:10]
            parts = [int(p) for p in clean_due.split("-")]
            if len(parts) == 3:
                due_date = datetime(parts[0], parts[1], parts[2], tzinfo=timezone.utc)
        except Exception as exc:
            logger.warning("Could not parse due_date '%s': %s", raw_due_date, exc)

    notes = body.get("notes")

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        repo = NodeCostRepository(session)
        item = await repo.upsert(
            node_uuid=node_uuid,
            node_id=node_id,
            node_name=node_name,
            provider=provider,
            monthly_cost_toman=monthly_cost_toman,
            monthly_cost_eur=monthly_cost_eur,
            currency=currency,
            due_date=due_date,
            notes=notes,
        )
        session.add(
            AdminLog(
                admin_id=admin["id"],
                action="update_node_cost",
                detail=f"بروزرسانی هزینه‌های سرور {node_name or node_uuid}: {monthly_cost_toman:,} تومان, ارائه‌دهنده: {provider}",
            )
        )
        await session.commit()

    cache: FastCache = request.app["cache"]
    await cache.delete("tma:admin:overview")

    return web.json_response({
        "ok": True,
        "message": "اطلاعات مالی و سررسید سرور با موفقیت ثبت شد.",
        "data": {
            "node_uuid": item.node_uuid,
            "monthly_cost_toman": item.monthly_cost_toman,
            "monthly_cost_eur": item.monthly_cost_eur,
            "due_date": item.due_date.strftime("%Y-%m-%d") if item.due_date else None,
            "provider": item.provider,
        }
    })
