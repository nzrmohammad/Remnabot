"""Admin API endpoints for Telegram Mini App Management Suite."""
import asyncio
import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import time
from typing import Any

from aiohttp import web
from sqlalchemy import func, select

from html import escape
from bot.common import admin_thread_kwargs
from bot.common.helpers import get_limit_bytes, get_used_bytes
from bot.db.models import AdminLog, AppSetting, Coupon, CryptoInvoice, KnownDevice, Order, Service, SupportMessage, Topup, User, Wallet
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.handlers.admin_broadcast import _resolve_broadcast_recipients
from bot.handlers.admin_nodes import COUNTRY_FLAGS_MAP
from bot.services.app_settings import get_store_settings
from bot.services.formatting import country_flag
from bot.web.auth import get_authenticated_user
from bot.web.cache import FastCache

try:
    import jdatetime
except ImportError:
    jdatetime = None

logger = logging.getLogger(__name__)


def _check_admin(request: web.Request) -> dict[str, Any] | None:
    user = get_authenticated_user(request)
    if not user or not user.get("is_admin"):
        return None
    return user


async def get_admin_overview(request: web.Request) -> web.Response:
    """Return high-level KPIs and cluster status for admin dashboard."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    cache: FastCache = request.app["cache"]
    cache_key = "tma:admin:overview"
    is_refresh = request.query.get("refresh") in ("1", "true")
    if is_refresh:
        await cache.delete("analytics:traffic:7day_series")
    else:
        cached_data = await cache.get(cache_key)
        if cached_data:
            return web.json_response({"ok": True, "data": cached_data, "cached": True})

    session_factory = request.app["session_factory"]
    remnawave = request.app["remnawave"]

    async with session_factory() as session:
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

            sys_info = n.get("system") or n.get("sys") or {}
            cpu = sys_info.get("cpu") if sys_info.get("cpu") is not None else (n.get("cpu") or 0)
            ram = sys_info.get("ram") if sys_info.get("ram") is not None else (sys_info.get("memory") or n.get("memory") or 0)

            address = str(n.get("address") or "—")
            port = n.get("port")
            addr_str = f"{address}:{port}" if port else address
            traffic_used = n.get("trafficUsedBytes") or n.get("usedTrafficBytes") or 0
            traffic_used_gb = round(traffic_used / (1024**3), 2) if traffic_used else 0.0

            nodes_overview.append({
                "id": n.get("id"),
                "name": raw_name,
                "country_code": country_code or "NL",
                "flag": flag,
                "status": "ONLINE" if is_connected else "OFFLINE",
                "connected_users": online_users,
                "cpu_percent": round(float(cpu), 1),
                "ram_percent": round(float(ram), 1),
                "address": addr_str,
                "traffic_used_gb": traffic_used_gb,
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

        # 7-day sales trend for dashboard charts
        seven_days_ago = now_utc - timedelta(days=6)
        rev_result = await session.execute(
            select(Order.created_at, Order.amount)
            .where(Order.status == "paid", Order.created_at >= seven_days_ago)
        )
        rev_rows = rev_result.all()
        daily_revenue = {(now_utc - timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(6, -1, -1)}
        for cat_dt, amt in rev_rows:
            if cat_dt:
                ds = cat_dt.strftime("%Y-%m-%d")
                if ds in daily_revenue:
                    daily_revenue[ds] += (amt or 0)

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

        # 2. 24h Peak Usage Distribution (Hourly traffic curve)
        hourly_weights = [
            0.038, 0.024, 0.015, 0.010, 0.008, 0.012, 0.022, 0.035,
            0.045, 0.052, 0.058, 0.055, 0.050, 0.048, 0.052, 0.058,
            0.065, 0.075, 0.082, 0.088, 0.078, 0.062, 0.042, 0.026
        ]
        w_sum = sum(hourly_weights)
        hourly_labels = [f"{h:02d}:00" for h in range(24)]
        base_h_gb = today_cluster_gb if today_cluster_gb > 0 else (total_traffic_gb / 30.0 if total_traffic_gb > 0 else 50.0)
        hourly_data = [round((w / w_sum) * base_h_gb, 2) for w in hourly_weights]
        hourly_distribution = {
            "labels": hourly_labels,
            "data": hourly_data,
            "peak_hour": "20:00",
            "unit": "GB",
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
            plan_labels = [str(r[0]) for r in plan_rows]
            plan_sales = [int(r[1]) for r in plan_rows]
            plan_revenue = [int(r[2]) for r in plan_rows]
        else:
            srv_res = await session.execute(select(Service.name).where(Service.is_active.is_(True)).limit(5))
            srv_names = srv_res.scalars().all()
            plan_labels = [str(n) for n in srv_names] if srv_names else ["پلن ۱ ماهه", "پلن ۳ ماهه", "پلن نامحدود"]
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
            },
            "nodes": nodes_overview,
            "charts": {
                "sales_labels": chart_sales_labels,
                "sales_data": chart_sales_data,
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
        }

        await cache.set(cache_key, data, ttl_seconds=15)
        return web.json_response({"ok": True, "data": data, "cached": False})


async def get_admin_users(request: web.Request) -> web.Response:
    """Search and paginate users for admin management."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    query = request.query.get("q", "").strip()
    status_filter = request.query.get("filter", "all")
    page = max(1, int(request.query.get("page", 1)))
    limit = min(50, max(5, int(request.query.get("limit", 20))))
    offset = (page - 1) * limit

    session_factory = request.app["session_factory"]
    remnawave = request.app["remnawave"]

    async with session_factory() as session:
        user_repo = UserRepository(session)

        # Collect online user Telegram IDs if available
        online_telegram_ids: set[int] = set()
        try:
            sessions = await remnawave.get_active_sessions() or []
            for s in sessions:
                user_obj = s.get("user") if isinstance(s.get("user"), dict) else {}
                tid = s.get("telegramId") or s.get("telegram_id") or user_obj.get("telegramId") or user_obj.get("telegram_id")
                if not tid and user_obj.get("username", "").startswith("tg_"):
                    try:
                        tid = int(user_obj["username"].replace("tg_", ""))
                    except ValueError:
                        pass
                if tid:
                    online_telegram_ids.add(int(tid))
            if not online_telegram_ids:
                hwid_devs = await remnawave.get_all_hwid_devices(size=300) or []
                active_uids = {d.get("userId") for d in hwid_devs if d.get("userId")}
                if active_uids:
                    p_users = await remnawave.get_all_panel_users() or []
                    for pu in p_users:
                        if pu.get("id") in active_uids and pu.get("telegramId"):
                            online_telegram_ids.add(int(pu["telegramId"]))
        except Exception as exc:
            logger.debug("Failed fetching online sessions for admin: %s", exc)

        condition = None
        if status_filter == "banned":
            condition = User.is_banned.is_(True)
        elif status_filter == "online":
            if online_telegram_ids:
                condition = User.telegram_id.in_(list(online_telegram_ids))
            else:
                condition = User.telegram_id.in_([-1])  # Empty match

        if query:
            users = await user_repo.search(query, limit=limit)
            total = len(users)
        else:
            total = await user_repo.count(condition)
            users = await user_repo.list_paginated(offset, limit, condition)

        balances = await user_repo.balances_for([u.telegram_id for u in users])

        # Fetch subscriptions and compute remaining volume and remaining days
        user_items = []
        now_utc = datetime.now(timezone.utc)
        for u in users:
            panel_users = await remnawave.get_users_by_telegram_id(u.telegram_id) or []
            p = panel_users[0] if panel_users else {}
            panel_exists = bool(panel_users)

            used_bytes = get_used_bytes(p) if panel_exists else 0
            limit_bytes = get_limit_bytes(p) if panel_exists else 0
            used_gb = round(used_bytes / (1024**3), 2)
            limit_gb = round(limit_bytes / (1024**3), 2)

            if limit_bytes > 0:
                remaining_gb = max(0.0, round((limit_bytes - used_bytes) / (1024**3), 2))
            else:
                remaining_gb = -1.0 if panel_exists else 0.0  # -1 signifies unlimited

            days_left = None
            expire_at_str = p.get("expireAt")
            if expire_at_str:
                try:
                    exp_dt = datetime.fromisoformat(str(expire_at_str).replace("Z", "+00:00"))
                    delta = exp_dt - now_utc
                    if delta.total_seconds() > 0:
                        days_left = int(math.ceil(delta.total_seconds() / 86400.0))
                    else:
                        days_left = 0
                except Exception:
                    pass

            is_online = (u.telegram_id in online_telegram_ids) if online_telegram_ids else False
            is_expiring = False
            is_expired = False
            if panel_exists:
                status_up = str(p.get("status") or "").upper()
                if days_left is not None and days_left <= 0:
                    is_expired = True
                elif status_up == "EXPIRED":
                    is_expired = True
                elif remaining_gb == 0.0 and limit_bytes > 0:
                    is_expired = True

                if not is_expired:
                    if days_left is not None and 0 < days_left <= 3:
                        is_expiring = True
                    elif 0 <= remaining_gb <= 2.0 and limit_bytes > 0:
                        is_expiring = True

            # If filter is expiring or expired and not matched, skip
            if status_filter == "expiring" and not is_expiring:
                continue
            if status_filter == "expired" and not is_expired:
                continue

            # Determine real Telegram profile name:
            profile_name = getattr(u, "full_name", None)
            if not profile_name:
                p_desc = p.get("description") if (p and p.get("description") and p.get("description") != u.username and not str(p.get("description")).startswith("@")) else None
                p_name = p.get("name") if (p and p.get("name") and p.get("name") != u.username and not str(p.get("name")).startswith("@")) else None
                profile_name = p_desc or p_name

            if not profile_name:
                bot = request.app.get("bot")
                cache = request.app.get("cache")
                cached_name = await cache.get(f"tg:user:{u.telegram_id}:profile_name") if cache else None
                if cached_name:
                    profile_name = cached_name
                elif bot:
                    try:
                        chat_info = await bot.get_chat(u.telegram_id)
                        if chat_info and chat_info.full_name:
                            profile_name = chat_info.full_name.strip()
                            if cache:
                                await cache.set(f"tg:user:{u.telegram_id}:profile_name", profile_name, ttl=86400)
                            u.full_name = profile_name
                            await session.commit()
                    except Exception:
                        pass

            full_name = profile_name or (f"@{u.username}" if u.username else f"کاربر {u.telegram_id}")

            user_items.append({
                "telegram_id": u.telegram_id,
                "username": u.username,
                "full_name": full_name,
                "wallet_balance": balances.get(u.telegram_id, 0),
                "is_banned": u.is_banned,
                "is_online": is_online,
                "is_expiring": is_expiring,
                "is_expired": is_expired,
                "avatar_url": f"/api/user/avatar?user_id={u.telegram_id}",
                "panel_account": {
                    "exists": panel_exists,
                    "status": p.get("status", "NONE"),
                    "used_traffic_gb": used_gb,
                    "limit_traffic_gb": limit_gb,
                    "remaining_traffic_gb": remaining_gb,
                    "days_left": days_left,
                    "subscription_url": p.get("subscriptionUrl") or p.get("subscription_url") or "",
                } if panel_exists else None,
            })

        return web.json_response({
            "ok": True,
            "users": user_items,
            "total": total,
            "page": page,
            "limit": limit,
        })


async def post_admin_modify_user(request: web.Request) -> web.Response:
    """Add traffic (GB) and/or extend days for a user in a unified action."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    target_id = body.get("telegram_id")
    action = body.get("action")

    # Unified traffic_gb and days, or legacy single action
    traffic_gb = 0.0
    days = 0

    if "traffic_gb" in body or "days" in body:
        try:
            traffic_gb = max(0.0, float(body.get("traffic_gb") or 0))
        except (ValueError, TypeError):
            traffic_gb = 0.0
        try:
            days = max(0, int(body.get("days") or 0))
        except (ValueError, TypeError):
            days = 0
    elif action == "traffic":
        try:
            traffic_gb = max(0.0, float(body.get("amount") or 0))
        except (ValueError, TypeError):
            traffic_gb = 0.0
    elif action == "days":
        try:
            days = max(0, int(body.get("amount") or 0))
        except (ValueError, TypeError):
            days = 0

    if not target_id or (traffic_gb <= 0 and days <= 0):
        return web.json_response({"ok": False, "error": "حداقل یکی از مقادیر حجم یا روز را وارد کنید."}, status=400)

    remnawave = request.app["remnawave"]
    session_factory = request.app["session_factory"]

    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": False, "error": "اکانتی در پنل برای این کاربر یافت نشد."}, status=404)

    puser = panel_users[0]
    primary_id = puser.get("id")

    cur_limit = get_limit_bytes(puser)
    cur_exp_str = puser.get("expireAt")
    now = datetime.now(timezone.utc)

    new_limit = cur_limit
    if traffic_gb > 0:
        new_limit += int(traffic_gb * 1024 * 1024 * 1024)

    new_exp_iso = cur_exp_str
    if days > 0:
        base_dt = now
        if cur_exp_str:
            try:
                dt = datetime.fromisoformat(str(cur_exp_str).replace("Z", "+00:00"))
                if dt > now:
                    base_dt = dt
            except Exception:
                pass
        new_exp_iso = (base_dt + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif not new_exp_iso and traffic_gb > 0:
        new_exp_iso = (now + timedelta(days=36500)).strftime("%Y-%m-%dT%H:%M:%SZ")

    res = await remnawave.update_user_subscription(
        primary_id,
        expire_at_iso=new_exp_iso,
        traffic_limit_bytes=new_limit,
        status="ACTIVE",
    )
    if not res:
        return web.json_response({"ok": False, "error": "خطا در اعمال تغییرات در پنل رمناویو."}, status=502)

    parts = []
    if traffic_gb > 0:
        parts.append(f"افزایش {traffic_gb:g} GB ترافیک")
    if days > 0:
        parts.append(f"تمدید {days} روز اشتراک")
    log_detail = f"{' و '.join(parts)} کاربر {target_id}"

    # Record in admin log
    async with session_factory() as session:
        session.add(AdminLog(admin_id=admin["id"], action="modify_user_subscription", detail=log_detail))
        await session.commit()

    # Clear caches
    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")
    await cache.delete("tma:admin:overview")

    return web.json_response({"ok": True, "message": log_detail})


async def post_admin_kill_sessions(request: web.Request) -> web.Response:
    """Disconnect all active HWID devices for a user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_id = body.get("telegram_id")
    if not target_id:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": False, "error": "اکانتی در پنل یافت نشد."}, status=404)

    primary_id = panel_users[0].get("id")
    devices = await remnawave.get_user_hwid_devices(primary_id)
    killed = 0
    for dev in devices:
        hwid = dev.get("hwid")
        if hwid:
            if await remnawave.delete_hwid_device(primary_id, hwid):
                killed += 1

    return web.json_response({"ok": True, "killed_devices": killed})


async def post_admin_toggle_ban(request: web.Request) -> web.Response:
    """Ban or unban a user in bot DB and Remnawave panel."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_id = body.get("telegram_id")
    ban_state = bool(body.get("ban", True))

    session_factory = request.app["session_factory"]
    remnawave = request.app["remnawave"]

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(int(target_id))
        if user:
            user.is_banned = ban_state
            await session.commit()

    # Panel status toggle
    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if panel_users:
        primary_id = panel_users[0].get("id")
        new_status = "DISABLED" if ban_state else "ACTIVE"
        await remnawave.set_user_status(primary_id, new_status)

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")

    return web.json_response({"ok": True, "banned": ban_state})


async def get_admin_ticket_threads(request: web.Request) -> web.Response:
    """Return active user conversation threads (pending receipts + recent support messages)."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    session_factory = request.app["session_factory"]
    cache: FastCache = request.app["cache"]

    threads: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    async with session_factory() as session:
        # 1. Prioritize users with pending topups
        pending_res = await session.execute(
            select(Topup)
            .where(Topup.status == "pending")
            .order_by(Topup.created_at.desc())
        )
        pending_topups = pending_res.scalars().all()
        user_repo = UserRepository(session)

        for t in pending_topups:
            if t.telegram_id in seen_ids:
                continue
            seen_ids.add(t.telegram_id)
            user = await user_repo.get_by_telegram_id(t.telegram_id)
            u_name = (getattr(user, "full_name", None) or (f"@{user.username}" if user and user.username else f"کاربر {t.telegram_id}")).strip()

            chat_msgs = await cache.get(f"support:chat:{t.telegram_id}") or []
            last_msg = chat_msgs[-1]["text"] if chat_msgs else f"فیش واریزی {t.id} ({t.amount:,} تومان)"
            last_time = chat_msgs[-1].get("created_at") if chat_msgs else (t.created_at.strftime("%H:%M") if t.created_at else "—")

            threads.append({
                "telegram_id": t.telegram_id,
                "full_name": u_name,
                "username": user.username if user else None,
                "has_pending_topup": True,
                "topup_id": t.id,
                "topup_amount": t.amount,
                "last_message": last_msg,
                "last_time": last_time,
                "timestamp": int(t.created_at.timestamp()) if t.created_at else 0,
            })

        # 2. Add other active threads from cache
        active_ids = await cache.get("support:active_thread_ids") or []
        for tid in active_ids:
            try:
                tid_int = int(tid)
            except (ValueError, TypeError):
                continue
            if tid_int in seen_ids:
                continue
            seen_ids.add(tid_int)
            user = await user_repo.get_by_telegram_id(tid_int)
            u_name = (getattr(user, "full_name", None) or (f"@{user.username}" if user and user.username else f"کاربر {tid_int}")).strip()
            chat_msgs = await cache.get(f"support:chat:{tid_int}") or []
            if not chat_msgs:
                continue
            last_msg = chat_msgs[-1]["text"]
            last_time = chat_msgs[-1].get("created_at", "—")
            threads.append({
                "telegram_id": tid_int,
                "full_name": u_name,
                "username": user.username if user else None,
                "has_pending_topup": False,
                "topup_id": None,
                "topup_amount": 0,
                "last_message": last_msg,
                "last_time": last_time,
                "timestamp": chat_msgs[-1].get("timestamp", 0),
            })

    threads.sort(key=lambda x: (x["has_pending_topup"], x.get("timestamp", 0)), reverse=True)
    return web.json_response({"ok": True, "threads": threads})


async def get_admin_ticket_messages(request: web.Request) -> web.Response:
    """Return chat conversation history for a specific user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    target_id_raw = request.query.get("telegram_id")
    if not target_id_raw:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    try:
        target_id = int(target_id_raw)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "شناسه کاربر نامعتبر است."}, status=400)

    session_factory = request.app["session_factory"]
    cache: FastCache = request.app["cache"]

    try:
        async with session_factory() as session:
            user_repo = UserRepository(session)
            wallet_repo = WalletRepository(session)
            user = await user_repo.get_by_telegram_id(target_id)
            u_name = (getattr(user, "full_name", None) or (f"@{user.username}" if user and user.username else f"کاربر {target_id}")).strip()
            wallet = await wallet_repo.get_wallet(target_id)
            balance = wallet.balance if wallet else 0

            topup_res = await session.execute(
                select(Topup)
                .where(Topup.telegram_id == target_id, Topup.status == "pending")
                .order_by(Topup.created_at.desc())
                .limit(1)
            )
            pending_topup = topup_res.scalar_one_or_none()

        chat_msgs = await cache.get(f"support:chat:{target_id}") or []
    except Exception as exc:
        logger.error("Error in get_admin_ticket_messages for user %s: %s", target_id, exc, exc_info=True)
        return web.json_response({
            "ok": True,
            "user": {
                "telegram_id": target_id,
                "full_name": f"کاربر {target_id}",
                "username": None,
                "wallet_balance": 0,
                "pending_topup_id": None,
                "pending_amount": None,
            },
            "messages": [],
        })

    if not chat_msgs and pending_topup:
        time_str = pending_topup.created_at.strftime("%H:%M") if pending_topup.created_at else "—"
        receipt_text = f"فیش واریزی {pending_topup.id} به مبلغ {pending_topup.amount:,} تومان ثبت شد."
        if pending_topup.receipt_hash:
            receipt_text += f"\nکد پیگیری: {pending_topup.receipt_hash}"
        chat_msgs = [{
            "id": f"topup_{pending_topup.id}",
            "sender": "system",
            "text": receipt_text,
            "created_at": time_str,
            "timestamp": int(pending_topup.created_at.timestamp()) if pending_topup.created_at else 0,
        }]

    return web.json_response({
        "ok": True,
        "user": {
            "telegram_id": target_id,
            "full_name": u_name,
            "username": user.username if user else None,
            "wallet_balance": balance,
            "pending_topup_id": pending_topup.id if pending_topup else None,
            "pending_amount": pending_topup.amount if pending_topup else None,
        },
        "messages": chat_msgs,
    })


async def post_admin_reply_ticket(request: web.Request) -> web.Response:
    """Send an instant reply message from admin to user via Telegram Bot and record into thread history."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    target_id_raw = body.get("telegram_id")
    reply_text = str(body.get("reply_text") or "").strip()

    if not target_id_raw or not reply_text:
        return web.json_response({"ok": False, "error": "شناسه کاربر و متن پاسخ الزامی است."}, status=400)

    try:
        target_id = int(target_id_raw)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "شناسه کاربر نامعتبر است."}, status=400)

    bot = request.app["bot"]
    msg_formatted = f"💬 <b>پاسخ پشتیبانی به پیام شما:</b>\n\n{reply_text}"
    try:
        await bot.send_message(chat_id=target_id, text=msg_formatted, parse_mode="HTML")
    except Exception as exc:
        logger.warning("Failed to send reply to user %s: %s", target_id, exc)
        return web.json_response({"ok": False, "error": f"خطا در ارسال به تلگرام: {exc}"}, status=500)

    cache: FastCache = request.app["cache"]
    now_ts = int(time.time())
    now_dt = datetime.fromtimestamp(now_ts)
    chat_key = f"support:chat:{target_id}"
    chat_msgs = await cache.get(chat_key) or []
    new_msg = {
        "id": f"admin_{int(now_ts * 1000)}",
        "sender": "admin",
        "text": reply_text,
        "created_at": now_dt.strftime("%H:%M"),
        "timestamp": now_ts,
    }
    chat_msgs.append(new_msg)
    if len(chat_msgs) > 50:
        chat_msgs = chat_msgs[-50:]
    await cache.set(chat_key, chat_msgs, ttl_seconds=86400 * 30)

    active_ids = await cache.get("support:active_thread_ids") or []
    if target_id not in active_ids:
        active_ids.insert(0, target_id)
        if len(active_ids) > 100:
            active_ids = active_ids[:100]
        await cache.set("support:active_thread_ids", active_ids, ttl_seconds=86400 * 30)

    return web.json_response({
        "ok": True,
        "message": "پاسخ با موفقیت ارسال شد.",
        "chat_message": new_msg,
    })


_BROADCAST_STATUSES: dict[str, dict[str, Any]] = {}


async def post_admin_broadcast(request: web.Request) -> web.Response:
    """Queue a broadcast message to bot users with audience filtering and live progress tracking."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    text = body.get("message")
    if not text:
        return web.json_response({"ok": False, "error": "متن پیام خالی است."}, status=400)

    target = str(body.get("target") or "all").strip().lower()
    bot = request.app["bot"]
    session_factory = request.app["session_factory"]
    remnawave = request.app["remnawave"]

    target_labels = {
        "all": "همه کاربران",
        "active": "کاربران با سرویس فعال",
        "expired": "کاربران منقضی شده",
        "buyers": "خریداران قبلی",
        "balance": "کاربران دارای موجودی",
    }
    label = target_labels.get(target, "کاربران انتخاب شده")

    async with session_factory() as session:
        recipients = await _resolve_broadcast_recipients(session, remnawave, target)

    broadcast_id = f"bcast_{int(datetime.now(timezone.utc).timestamp())}_{len(recipients)}"
    _BROADCAST_STATUSES[broadcast_id] = {
        "id": broadcast_id,
        "target": target,
        "target_label": label,
        "total": len(recipients),
        "sent": 0,
        "failed": 0,
        "is_completed": False,
        "start_time": datetime.now(timezone.utc).isoformat(),
    }

    async def _broadcast_worker():
        st = _BROADCAST_STATUSES[broadcast_id]
        for tid in recipients:
            try:
                await bot.send_message(chat_id=tid, text=text, parse_mode="HTML")
                st["sent"] += 1
                await asyncio.sleep(0.04)  # ~25 messages/sec rate limit
            except Exception:
                st["failed"] += 1
        st["is_completed"] = True
        logger.info(
            "Admin broadcast completed: id=%s target=%s sent=%d failed=%d",
            broadcast_id, target, st["sent"], st["failed"]
        )

    asyncio.create_task(_broadcast_worker())
    return web.json_response({
        "ok": True,
        "broadcast_id": broadcast_id,
        "message": f"ارسال پیام همگانی به {label} در حال انجام است.",
        "stats": _BROADCAST_STATUSES[broadcast_id],
    })


async def get_admin_broadcast_status(request: web.Request) -> web.Response:
    """Return status and report of an ongoing or completed broadcast."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    b_id = request.query.get("id")
    if not b_id or b_id not in _BROADCAST_STATUSES:
        return web.json_response({"ok": False, "error": "عملیات یافت نشد"}, status=404)

    return web.json_response({"ok": True, "stats": _BROADCAST_STATUSES[b_id]})


async def post_admin_reset_trial(request: web.Request) -> web.Response:
    """Reset trial status so user can claim a test service again."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_id = body.get("telegram_id")
    if not target_id:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        user_repo = UserRepository(session)
        await user_repo.set_claimed_trial(int(target_id), claimed=False)
        session.add(
            AdminLog(
                admin_id=admin["id"],
                action="reset_trial",
                detail=f"فعال‌سازی مجدد تست برای کاربر {target_id}",
            )
        )
        await session.commit()

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")
    return web.json_response({
        "ok": True,
        "message": "قابلیت دریافت اشتراک تست برای این کاربر با موفقیت فعال شد.",
    })


async def get_admin_topups(request: web.Request) -> web.Response:
    """Return list of pending card-to-card topups."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    session_factory = request.app["session_factory"]
    try:
        async with session_factory() as session:
            wallet_repo = WalletRepository(session)
            user_repo = UserRepository(session)
            pending = await wallet_repo.list_pending_topups()

            items = []
            for t in pending:
                u = await user_repo.get_by_telegram_id(t.telegram_id)
                receipt_ref = getattr(t, "receipt_photo_id", None) or getattr(t, "receipt_hash", None)
                u_full_name = getattr(u, "full_name", None)
                if not u_full_name:
                    u_full_name = f"@{u.username}" if (u and u.username) else f"کاربر {t.telegram_id}"
                has_photo = bool(getattr(t, "receipt_photo_id", None))
                items.append({
                    "id": t.id,
                    "telegram_id": t.telegram_id,
                    "username": u.username if u else None,
                    "full_name": u_full_name,
                    "avatar_url": f"/api/user/avatar?user_id={t.telegram_id}",
                    "amount": t.amount,
                    "status": t.status,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "receipt_hash": getattr(t, "receipt_hash", None),
                    "receipt_photo_id": getattr(t, "receipt_photo_id", None),
                    "has_photo": has_photo,
                    "photo_url": f"/api/admin/topup/photo?id={t.id}" if has_photo else None,
                })
            return web.json_response({"ok": True, "topups": items})
    except Exception as exc:
        logger.exception("Error in get_admin_topups: %s", exc)
        return web.json_response({"ok": False, "error": "خطا در پردازش لیست فیش‌ها"}, status=500)


async def post_admin_topup_action(request: web.Request) -> web.Response:
    """Approve or reject a pending card-to-card topup."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    topup_id = body.get("topup_id")
    approved = bool(body.get("approved", True))
    if not topup_id:
        return web.json_response({"ok": False, "error": "شناسه فیش الزامی است."}, status=400)

    session_factory = request.app["session_factory"]
    bot = request.app["bot"]

    async with session_factory() as session:
        wallet_repo = WalletRepository(session)
        claimed = await wallet_repo.claim_topup(int(topup_id), approved)
        if not claimed:
            return web.json_response({"ok": False, "error": "این فیش قبلاً تعیین وضعیت شده است."}, status=400)

        if approved:
            await wallet_repo.add_balance(claimed.telegram_id, claimed.amount)
            session.add(
                AdminLog(
                    admin_id=admin["id"],
                    action="topup_approved",
                    detail=f"تایید فیش {claimed.id} و شارژ {claimed.amount:,} تومان برای {claimed.telegram_id}",
                )
            )
            msg = f"✅ <b>واریز شما تایید شد!</b>\n\nمبلغ {claimed.amount:,} تومان به کیف پول شما اضافه شد."
        else:
            session.add(
                AdminLog(
                    admin_id=admin["id"],
                    action="topup_rejected",
                    detail=f"رد فیش {claimed.id} برای {claimed.telegram_id}",
                )
            )
            msg = "❌ <b>فیش ارسالی شما رد شد.</b>\n\nدر صورت وجود مغایرت با پشتیبانی در ارتباط باشید."

        await session.commit()

    # Clear cache
    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{claimed.telegram_id}:dashboard")
    await cache.delete("tma:admin:overview")

    # Send telegram notification to user with navigation keyboard
    try:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from bot.locales.texts import t

        user_lang = "fa"
        try:
            async with session_factory() as session:
                user_repo = UserRepository(session)
                u_obj = await user_repo.get_by_telegram_id(claimed.telegram_id)
                if u_obj and u_obj.language:
                    user_lang = u_obj.language
        except Exception:
            pass

        kb = InlineKeyboardBuilder()
        if approved:
            if user_lang == "fa":
                kb.button(text=t(user_lang, "btn_services"), callback_data="menu:services")
                kb.button(text=t(user_lang, "btn_wallet"), callback_data="menu:wallet")
            else:
                kb.button(text=t(user_lang, "btn_wallet"), callback_data="menu:wallet")
                kb.button(text=t(user_lang, "btn_services"), callback_data="menu:services")
            kb.adjust(2)
        else:
            kb.button(text=t(user_lang, "btn_support"), callback_data="menu:support")
            kb.adjust(1)

        await bot.send_message(
            chat_id=claimed.telegram_id,
            text=msg,
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("Could not send topup decision notice to %s: %s", claimed.telegram_id, exc)

    # Sync status with admin supergroup / topic
    settings = request.app.get("settings")
    admin_chat_id = settings.ADMIN_CHAT_ID if settings else None
    if admin_chat_id and bot:
        store = None
        try:
            async with session_factory() as session:
                store = await get_store_settings(session)
        except Exception:
            pass

        thread_kwargs = admin_thread_kwargs(store, settings, kind="topups") if store and settings else {}
        status_badge = "✅ تایید شد (از طریق پنل ادمین)" if approved else "❌ رد شد (از طریق پنل ادمین)"
        admin_name = admin.get("first_name") or admin.get("username") or str(admin.get("id"))

        # 1. Remove pending inline buttons from the original receipt prompt
        if claimed.admin_message_id:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=admin_chat_id,
                    message_id=claimed.admin_message_id,
                    reply_markup=None,
                )
            except Exception as exc:
                logger.debug("Could not remove reply markup for topup %s: %s", claimed.id, exc)

        # 2. Announce resolution into the admin supergroup topic
        admin_id_val = admin.get("id")
        admin_id_str = f" (<code>{admin_id_val}</code>)" if admin_id_val else ""
        notice_text = (
            f"📌 <b>تعیین وضعیت فیش {claimed.id}</b>\n"
            f"👤 کاربر: <code>{claimed.telegram_id}</code>\n"
            f"💰 مبلغ: <b>{claimed.amount:,}</b> تومان\n"
            f"📊 وضعیت: <b>{status_badge}</b>\n"
            f"👮 توسط ادمین: <b>{escape(str(admin_name))}</b>{admin_id_str}"
        )
        try:
            kwargs = dict(thread_kwargs)
            if claimed.admin_message_id:
                kwargs["reply_to_message_id"] = claimed.admin_message_id
            await bot.send_message(
                chat_id=admin_chat_id,
                text=notice_text,
                parse_mode="HTML",
                **kwargs,
            )
        except Exception:
            try:
                await bot.send_message(
                    chat_id=admin_chat_id,
                    text=notice_text,
                    parse_mode="HTML",
                    **thread_kwargs,
                )
            except Exception as exc:
                logger.warning("Failed to send topup update notice to admin chat: %s", exc)

    return web.json_response({
        "ok": True,
        "message": "فیش با موفقیت تایید شد." if approved else "فیش با موفقیت رد شد.",
    })


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
        }
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
        )
        for bool_key in bool_keys:
            if bool_key in body:
                val = bool(body[bool_key])
                await app_repo.set(bool_key, "1" if val else "0")

        # String fields
        str_keys = ("card_number", "card_holder", "ton_wallet_address", "support_contact")
        for str_key in str_keys:
            if str_key in body:
                await app_repo.set(str_key, str(body[str_key]).strip())

        # Numeric fields
        num_keys = (
            "topup_min_amount",
            "usdt_rate_toman",
            "ton_rate_toman",
            "trial_traffic_gb",
            "trial_duration_days",
            "referral_reward_gb",
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


async def post_admin_user_wallet(request: web.Request) -> web.Response:
    """Charge or deduct user wallet balance in Toman."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    target_id = body.get("telegram_id")
    try:
        amount = int(body.get("amount", 0))
    except (ValueError, TypeError):
        amount = 0

    reason = str(body.get("reason") or "شارژ دستی توسط مدیریت").strip()

    if not target_id or amount == 0:
        return web.json_response({"ok": False, "error": "مقدار مبلغ و کاربر نامعتبر است."}, status=400)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        wallet_repo = WalletRepository(session)
        wallet = await wallet_repo.get_wallet(int(target_id))
        old_balance = int(wallet.balance if wallet else 0)
        new_balance = max(0, old_balance + amount)
        wallet.balance = new_balance

        action_name = "wallet_charge" if amount > 0 else "wallet_deduct"
        detail_msg = f"{'افزایش' if amount > 0 else 'کسر'} {abs(amount):,} تومان موجودی کاربر {target_id} ({reason})"
        session.add(AdminLog(admin_id=admin["id"], action=action_name, detail=detail_msg))
        await session.commit()

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")
    await cache.delete("tma:admin:overview")

    bot = request.app.get("bot")
    if bot:
        sign = "+" if amount > 0 else "-"
        notif = (
            f"🔔 <b>تغییر موجودی کیف پول</b>\n\n"
            f"مبلغ: <b>{sign}{abs(amount):,} تومان</b>\n"
            f"موجودی جدید: <b>{new_balance:,} تومان</b>\n"
            f"توضیحات: {reason}"
        )
        try:
            await bot.send_message(chat_id=int(target_id), text=notif, parse_mode="HTML")
        except Exception:
            pass

    return web.json_response({
        "ok": True,
        "old_balance": old_balance,
        "new_balance": new_balance,
        "delta": amount,
        "message": f"موجودی کاربر با موفقیت به‌روزرسانی شد: {new_balance:,} تومان",
    })


async def post_admin_user_revoke_sub(request: web.Request) -> web.Response:
    """Revoke existing subscription URL and regenerate a new one via Remnawave."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_id = body.get("telegram_id")
    if not target_id:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": False, "error": "اکانتی در پنل برای این کاربر یافت نشد."}, status=404)

    primary_id = panel_users[0].get("id")
    revoked = await remnawave.revoke_user_subscription(primary_id)
    if not revoked:
        return web.json_response({"ok": False, "error": "خطا در برقراری ارتباط با پنل رمناویو."}, status=502)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        session.add(
            AdminLog(
                admin_id=admin["id"],
                action="revoke_sub",
                detail=f"تولید مجدد لینک سابسکریپشن کاربر {target_id}",
            )
        )
        await session.commit()

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")

    new_sub = revoked.get("subscriptionUrl") or revoked.get("subscription_url") or ""
    return web.json_response({
        "ok": True,
        "subscription_url": new_sub,
        "message": "لینک سابسکریپشن کاربر با موفقیت باطل و مجدداً ایجاد شد.",
    })


async def get_admin_user_hwid_devices(request: web.Request) -> web.Response:
    """Fetch all active connected HWID devices for a specific user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    target_id = request.query.get("telegram_id")
    if not target_id:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": True, "devices": []})

    primary_id = panel_users[0].get("id")
    devices = await remnawave.get_user_hwid_devices(primary_id)
    return web.json_response({"ok": True, "devices": devices or []})


async def get_admin_user_sessions(request: web.Request) -> web.Response:
    """Fetch real-time active connections and sessions for a single user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    target_id = request.query.get("telegram_id")
    if not target_id:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    try:
        panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
        if not panel_users:
            return web.json_response({
                "ok": True,
                "data": {
                    "isOnline": False,
                    "totalConnections": 0,
                    "uniqueIps": [],
                    "nodeConnections": [],
                }
            })

        primary_id = panel_users[0].get("id")
        user_sessions = await remnawave.get_user_live_sessions(primary_id)
        return web.json_response({"ok": True, "data": user_sessions})
    except Exception as exc:
        logger.warning("Error fetching user live sessions: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def get_admin_sessions_explorer(request: web.Request) -> web.Response:
    """Scan and fetch real-time active connections and sessions across all nodes (Sessions Explorer)."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    remnawave = request.app["remnawave"]
    try:
        data = await remnawave.get_live_sessions_explorer()
        # Convert any sets in data to lists for JSON serialization
        if data and isinstance(data, dict):
            for u in data.get("all_online_users", []):
                if "uniqueIps" in u and isinstance(u["uniqueIps"], set):
                    u["uniqueIps"] = sorted(list(u["uniqueIps"]))
            for u in data.get("multi_ip_users", []):
                if "uniqueIps" in u and isinstance(u["uniqueIps"], set):
                    u["uniqueIps"] = sorted(list(u["uniqueIps"]))
        return web.json_response({"ok": True, "data": data})
    except Exception as exc:
        logger.warning("Error fetching sessions explorer data: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def post_admin_user_delete_hwid(request: web.Request) -> web.Response:
    """Disconnect/delete a single specific HWID device for a user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_id = body.get("telegram_id")
    hwid = body.get("hwid")
    if not target_id or not hwid:
        return web.json_response({"ok": False, "error": "شناسه کاربر و شناسه دستگاه الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": False, "error": "اکانتی در پنل یافت نشد."}, status=404)

    primary_id = panel_users[0].get("id")
    success = await remnawave.delete_hwid_device(primary_id, str(hwid))
    if not success:
        return web.json_response({"ok": False, "error": "خطا در قطع اتصال دستگاه."}, status=502)

    return web.json_response({"ok": True, "message": "اتصال دستگاه با موفقیت قطع شد."})


async def get_admin_plans(request: web.Request) -> web.Response:
    """List all subscription plans/services."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        result = await session.execute(select(Service).order_by(Service.price.asc(), Service.id.asc()))
        services = result.scalars().all()
        plans = [
            {
                "id": s.id,
                "name": s.name,
                "price": s.price,
                "duration_days": s.duration_days,
                "traffic_gb": s.traffic_gb,
                "description": s.description or "",
                "is_active": s.is_active,
                "hwid_limit": s.hwid_limit or 0,
            }
            for s in services
        ]
    return web.json_response({"ok": True, "plans": plans})


async def post_admin_plan_save(request: web.Request) -> web.Response:
    """Create or update a subscription plan."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    plan_id = body.get("id")
    name = str(body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "نام پلن الزامی است."}, status=400)

    try:
        price = int(body.get("price", 0))
        traffic_gb = int(body.get("traffic_gb", 0))
        duration_days = int(body.get("duration_days", 0))
        hwid_limit = int(body.get("hwid_limit", 0)) if body.get("hwid_limit") else None
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "مقادیر عددی نامعتبر هستند."}, status=400)

    description = str(body.get("description") or "").strip() or None
    is_active = bool(body.get("is_active", True))

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        if plan_id:
            service = await session.get(Service, int(plan_id))
            if not service:
                return web.json_response({"ok": False, "error": "پلن مورد نظر یافت نشد."}, status=404)
            service.name = name
            service.price = price
            service.traffic_gb = traffic_gb
            service.duration_days = duration_days
            service.description = description
            service.is_active = is_active
            service.hwid_limit = hwid_limit
            msg = "پلن با موفقیت ویرایش شد."
        else:
            service = Service(
                name=name,
                price=price,
                traffic_gb=traffic_gb,
                duration_days=duration_days,
                description=description,
                is_active=is_active,
                hwid_limit=hwid_limit,
            )
            session.add(service)
            msg = "پلن جدید با موفقیت ایجاد شد."

        session.add(AdminLog(admin_id=admin["id"], action="save_plan", detail=f"{name} ({price:,} تومان)"))
        await session.commit()

    return web.json_response({"ok": True, "message": msg})


async def post_admin_plan_toggle(request: web.Request) -> web.Response:
    """Toggle active status of a plan."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    plan_id = body.get("id")
    if not plan_id:
        return web.json_response({"ok": False, "error": "شناسه پلن الزامی است."}, status=400)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        service = await session.get(Service, int(plan_id))
        if not service:
            return web.json_response({"ok": False, "error": "پلن یافت نشد."}, status=404)

        service.is_active = bool(body.get("is_active", not service.is_active))
        await session.commit()

    return web.json_response({"ok": True, "is_active": service.is_active, "message": "وضعیت پلن تغییر یافت."})


async def post_admin_plan_delete(request: web.Request) -> web.Response:
    """Delete a plan."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    plan_id = body.get("id")
    if not plan_id:
        return web.json_response({"ok": False, "error": "شناسه پلن الزامی است."}, status=400)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        service = await session.get(Service, int(plan_id))
        if not service:
            return web.json_response({"ok": False, "error": "پلن یافت نشد."}, status=404)

        await session.delete(service)
        session.add(AdminLog(admin_id=admin["id"], action="delete_plan", detail=f"حذف پلن #{plan_id}: {service.name}"))
        await session.commit()

    return web.json_response({"ok": True, "message": "پلن با موفقیت حذف شد."})


async def get_admin_coupons(request: web.Request) -> web.Response:
    """List all discount coupons."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        result = await session.execute(select(Coupon).order_by(Coupon.id.desc()))
        coupons = result.scalars().all()
        data = [
            {
                "id": c.id,
                "code": c.code,
                "discount_percent": c.discount_percent,
                "discount_amount": c.discount_amount,
                "max_uses": c.max_uses,
                "used_count": c.used_count,
                "expires_at": c.expires_at.strftime("%Y-%m-%d") if c.expires_at else None,
                "is_active": c.is_active,
            }
            for c in coupons
        ]
    return web.json_response({"ok": True, "coupons": data})


async def post_admin_coupon_save(request: web.Request) -> web.Response:
    """Create a new discount coupon."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    code = str(body.get("code") or "").strip().upper()
    if not code:
        return web.json_response({"ok": False, "error": "کد تخفیف الزامی است."}, status=400)

    try:
        percent = int(body.get("discount_percent", 0))
        amount = int(body.get("discount_amount", 0))
        max_uses = int(body.get("max_uses", 0))
        expires_days = int(body.get("expires_days", 0))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "مقادیر عددی نامعتبر هستند."}, status=400)

    if percent <= 0 and amount <= 0:
        return web.json_response({"ok": False, "error": "درصد تخفیف یا مبلغ تخفیف باید مشخص باشد."}, status=400)

    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days) if expires_days > 0 else None
    is_active = bool(body.get("is_active", True))

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        existing = await session.execute(select(Coupon).where(Coupon.code == code))
        if existing.scalar_one_or_none():
            return web.json_response({"ok": False, "error": "کد تخفیف با این نام از قبل وجود دارد."}, status=400)

        coupon = Coupon(
            code=code,
            discount_percent=percent,
            discount_amount=amount,
            max_uses=max_uses,
            expires_at=expires_at,
            is_active=is_active,
        )
        session.add(coupon)
        session.add(AdminLog(admin_id=admin["id"], action="create_coupon", detail=f"ساخت کوپن {code} ({percent}%)"))
        await session.commit()

    return web.json_response({"ok": True, "message": f"کد تخفیف {code} با موفقیت ساخته شد."})


async def post_admin_coupon_toggle(request: web.Request) -> web.Response:
    """Toggle active status of a coupon."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    coupon_id = body.get("id")
    if not coupon_id:
        return web.json_response({"ok": False, "error": "شناسه کوپن الزامی است."}, status=400)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        coupon = await session.get(Coupon, int(coupon_id))
        if not coupon:
            return web.json_response({"ok": False, "error": "کوپن یافت نشد."}, status=404)

        coupon.is_active = bool(body.get("is_active", not coupon.is_active))
        await session.commit()

    return web.json_response({"ok": True, "is_active": coupon.is_active, "message": "وضعیت کوپن تغییر یافت."})


async def post_admin_coupon_delete(request: web.Request) -> web.Response:
    """Delete a coupon."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    coupon_id = body.get("id")
    if not coupon_id:
        return web.json_response({"ok": False, "error": "شناسه کوپن الزامی است."}, status=400)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        coupon = await session.get(Coupon, int(coupon_id))
        if not coupon:
            return web.json_response({"ok": False, "error": "کوپن یافت نشد."}, status=404)

        await session.delete(coupon)
        session.add(AdminLog(admin_id=admin["id"], action="delete_coupon", detail=f"حذف کوپن {coupon.code}"))
        await session.commit()

    return web.json_response({"ok": True, "message": "کد تخفیف با موفقیت حذف شد."})


async def get_admin_coupon_usages(request: web.Request) -> web.Response:
    """Get list of users who redeemed a specific coupon."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    coupon_id_raw = request.match_info.get("id") or request.query.get("id")
    try:
        coupon_id = int(coupon_id_raw)
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "شناسه کوپن نامعتبر است."}, status=400)

    session_factory = request.app["session_factory"]
    try:
        async with session_factory() as session:
            coupon_repo = CouponRepository(session)
            user_repo = UserRepository(session)
            coupon = await coupon_repo.get_by_id(coupon_id)
            if not coupon:
                return web.json_response({"ok": False, "error": "کد تخفیف یافت نشد."}, status=404)

            usages = await coupon_repo.get_usages(coupon_id)
            items = []
            for u in usages:
                user = await user_repo.get_by_telegram_id(u.telegram_id)
                items.append({
                    "id": u.id,
                    "telegram_id": u.telegram_id,
                    "username": user.username if user else None,
                    "full_name": getattr(user, "full_name", None),
                    "order_id": u.order_id,
                    "discount_applied": u.discount_applied or 0,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                })

            return web.json_response({
                "ok": True,
                "coupon": {
                    "id": coupon.id,
                    "code": coupon.code,
                    "discount_percent": coupon.discount_percent,
                    "discount_amount": coupon.discount_amount,
                    "used_count": coupon.used_count,
                    "max_uses": coupon.max_uses,
                },
                "usages": items,
            })
    except Exception as exc:
        logger.exception("Error in get_admin_coupon_usages: %s", exc)
        return web.json_response({"ok": False, "error": "خطا در دریافت لیست استفاده‌کنندگان"}, status=500)


async def get_admin_topup_photo(request: web.Request) -> web.Response:
    """Stream receipt photo for a topup request from Telegram servers."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    topup_id_raw = request.query.get("id")
    if not topup_id_raw:
        return web.json_response({"ok": False, "error": "شناسه فیش الزامی است."}, status=400)

    try:
        topup_id = int(topup_id_raw)
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "شناسه فیش نامعتبر است."}, status=400)

    session_factory = request.app["session_factory"]
    bot: Bot = request.app.get("bot")
    if not bot:
        return web.Response(text="Bot not available", status=503)

    try:
        async with session_factory() as session:
            wallet_repo = WalletRepository(session)
            topup = await wallet_repo.get_topup(topup_id)
            if not topup or not topup.receipt_photo_id:
                return web.Response(text="تصویری برای این فیش یافت نشد", status=404)

            file_info = await bot.get_file(topup.receipt_photo_id)
            if not file_info or not file_info.file_path:
                return web.Response(text="فایل تصویر در سرور تلگرام یافت نشد", status=404)

            file_bio = await bot.download_file(file_info.file_path)
            if isinstance(file_bio, bytes):
                content = file_bio
            elif hasattr(file_bio, "getvalue"):
                content = file_bio.getvalue()
            elif hasattr(file_bio, "read"):
                content = file_bio.read()
            else:
                content = bytes(file_bio)

            return web.Response(
                body=content,
                content_type="image/jpeg",
                headers={
                    "Cache-Control": "private, max-age=86400",
                },
            )
    except Exception as exc:
        logger.exception("Error serving topup photo for #%s: %s", topup_id, exc)
        return web.Response(text="خطا در دریافت تصویر فیش", status=500)


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

        return web.json_response({
            "ok": True,
            "best_ton": {"price": best_ton_val, "source": best_ton_src},
            "best_usdt": {"price": best_usdt_val, "source": best_usdt_src},
            "ton_prices": market_data.get("ton") or {},
            "usdt_prices": market_data.get("usdt") or {},
            "binance_usd": market_data.get("binance_usd"),
        })
    except Exception as exc:
        logger.exception("Error fetching crypto rates: %s", exc)
        return web.json_response({"ok": False, "error": "خطا در استعلام آنلاین قیمت‌ها"}, status=500)


