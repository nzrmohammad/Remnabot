"""Admin Overview API and telemetry aggregation for Telegram Mini App.

Decomposed into focused modules:
- `bot.web.admin_overview_nodes`: Node metrics, telemetry extraction, and cluster KPIs.
- `bot.web.admin_overview_charts`: Sales, network traffic, and strategic analytics charts.
- `get_admin_overview`: Lightweight async controller orchestrating admin dashboard data.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import web

from bot.services.app_settings import get_store_settings
from bot.web.admin_common import _check_admin, db_session
from bot.web.admin_overview_charts import (
    calc_sales_and_traffic_charts,
    calc_strategic_charts,
    get_day_label,
)
from bot.web.admin_overview_nodes import (
    calc_cluster_kpis,
    calc_nodes_overview,
    extract_cpu,
    extract_node_item,
    extract_ram,
    extract_speeds,
)
from bot.web.cache import FastCache

# Backward-compatibility aliases
_extract_cpu = extract_cpu
_extract_ram = extract_ram
_extract_speeds = extract_speeds
_extract_node_item = extract_node_item
_calc_nodes_overview = calc_nodes_overview
_calc_cluster_kpis = calc_cluster_kpis
_get_day_label = get_day_label
_calc_sales_and_traffic_charts = calc_sales_and_traffic_charts
_calc_strategic_charts = calc_strategic_charts


async def _fetch_and_build_overview(
    session: Any,
    remnawave: Any,
    cache: FastCache,
    now_utc: datetime,
    is_refresh: bool,
) -> dict[str, Any]:
    """Fetch database metrics, telemetry and compute charts."""
    store_settings = await get_store_settings(session)
    days_list = [now_utc - timedelta(days=i) for i in range(6, -1, -1)]

    kpis, panel_users, nodes, costs_by_uuid, costs_by_id = await calc_cluster_kpis(
        session, remnawave, now_utc
    )

    month_traffic = kpis.get("month_traffic_gb") or 0.0
    monthly_rev = kpis.get("monthly_revenue_toman") or 0
    avg_revenue_per_gb = round(monthly_rev / month_traffic, 1) if month_traffic > 0 else 0.0

    hwid_stats = await remnawave.get_hwid_stats() or {}
    nodes_overview, online_devices, offline_nodes = calc_nodes_overview(
        nodes, costs_by_uuid, costs_by_id, hwid_stats, now_utc, avg_revenue_per_gb=avg_revenue_per_gb
    )
    kpis["online_devices"] = online_devices
    kpis["offline_nodes"] = offline_nodes

    sales_traffic = await calc_sales_and_traffic_charts(
        session, remnawave, cache, now_utc, is_refresh, nodes, panel_users, kpis["month_traffic_gb"]
    )
    strategic = await calc_strategic_charts(
        session,
        remnawave,
        now_utc,
        nodes_overview,
        days_list,
        sales_traffic["today_traffic_gb"],
        kpis["month_traffic_gb"],
        panel_users=panel_users,
        traffic_series=sales_traffic.get("chart_traffic_data"),
    )

    return {
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

    async with db_session(request) as session:
        data = await _fetch_and_build_overview(session, remnawave, cache, now_utc, is_refresh)
        await cache.set(cache_key, data, ttl_seconds=30)
        return web.json_response({"ok": True, "data": data, "cached": False})
