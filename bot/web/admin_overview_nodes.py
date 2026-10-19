"""Node metrics, telemetry extraction, and cluster KPIs for admin overview."""
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from bot.common.helpers import get_used_bytes
from bot.db.models import Order, Topup, User
from bot.db.repositories.node_cost_repo import NodeCostRepository
from bot.handlers.admin_nodes import COUNTRY_FLAGS_MAP
from bot.services.formatting import country_flag, country_name

try:
    import jdatetime
except ImportError:
    jdatetime = None


def extract_cpu(src: dict) -> float | None:
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


def extract_ram(src: dict) -> float | None:
    """Extract RAM usage percentage from arbitrary metrics dictionary."""
    if not isinstance(src, dict):
        return None
    for k in ("ram", "memory", "memoryUsage", "memoryPercent", "ramPercent", "ram_percent", "ram_usage"):
        v = src.get(k)
        if v is None:
            continue
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


def extract_speeds(src: dict) -> tuple[float, float]:
    """Extract download and upload network speeds in bytes/sec."""
    if not isinstance(src, dict):
        return 0.0, 0.0
    net = src.get("network") if isinstance(src.get("network"), dict) else {}
    rx = (
        net.get("rxBytesPerSec") or net.get("rx") or net.get("download")
        or src.get("networkRxBytesPerSec") or src.get("rxBytesPerSec")
        or src.get("downloadSpeed") or src.get("speedIn") or 0.0
    )
    tx = (
        net.get("txBytesPerSec") or net.get("tx") or net.get("upload")
        or src.get("networkTxBytesPerSec") or src.get("txBytesPerSec")
        or src.get("uploadSpeed") or src.get("speedOut") or 0.0
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


def _extract_node_flag(raw_name: str, country_code: str, country_name: str) -> str:
    """Resolve country flag emoji from code or node name."""
    flag = None
    if len(country_code) == 2 and country_code.isalpha() and country_code != "XX":
        flag = country_flag(country_code)
    if not flag or flag == "🌐":
        for kw, (f_emoji, _) in sorted(COUNTRY_FLAGS_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            if kw in raw_name.lower() or kw in country_name:
                flag = f_emoji
                break
    return flag or (country_flag(country_code) if country_code else "🌐")


def _extract_node_metrics(raw_sys: dict, n: dict, is_connected: bool) -> tuple[float, float, float, float]:
    """Calculate CPU, RAM, and speeds for a node."""
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
        cpu_val = extract_cpu(raw_sys) or extract_cpu(n)

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
        ram_val = extract_ram(raw_sys) or extract_ram(n)

    dl_speed, ul_speed = 0.0, 0.0
    if isinstance(sys_stats, dict) and isinstance(sys_stats.get("interface"), dict):
        iface = sys_stats["interface"]
        try:
            dl_speed = float(iface.get("rxBytesPerSec") or 0.0)
            ul_speed = float(iface.get("txBytesPerSec") or 0.0)
        except (ValueError, TypeError):
            pass

    if dl_speed <= 0.0 and ul_speed <= 0.0:
        dl_speed, ul_speed = extract_speeds(raw_sys)
    if dl_speed <= 0.0 and ul_speed <= 0.0:
        dl_speed, ul_speed = extract_speeds(n)

    cpu_val = max(0.0, min(100.0, (cpu_val * 100.0 if 0.0 < (cpu_val or 0.0) <= 1.0 else (cpu_val or 0.0))))
    ram_val = max(0.0, min(100.0, (ram_val * 100.0 if 0.0 < (ram_val or 0.0) <= 1.0 else (ram_val or 0.0))))
    if not is_connected:
        return 0.0, 0.0, 0.0, 0.0
    return cpu_val, ram_val, dl_speed, ul_speed


def _extract_node_costs(
    cost_entry: Any,
    now_utc: datetime,
    traffic_used_gb: float,
    avg_revenue_per_gb: float = 0.0,
) -> dict[str, Any]:
    """Format node financial cost, estimated revenue, ROI, and due date info."""
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

    cost_toman = cost_entry.monthly_cost_toman if cost_entry else 0
    cost_eur = cost_entry.monthly_cost_eur if cost_entry else 0.0
    currency = getattr(cost_entry, "currency", "EUR") or "EUR" if cost_entry else "EUR"
    provider = cost_entry.provider if cost_entry else None
    notes = cost_entry.notes if cost_entry else None
    cost_per_gb = round(cost_toman / traffic_used_gb, 0) if (cost_toman > 0 and traffic_used_gb > 0) else 0.0

    est_revenue_toman = int(round(traffic_used_gb * avg_revenue_per_gb)) if avg_revenue_per_gb > 0 else 0
    net_profit_toman = est_revenue_toman - cost_toman
    roi_percent = round((net_profit_toman / cost_toman) * 100, 1) if cost_toman > 0 else (100.0 if est_revenue_toman > 0 else 0.0)

    return {
        "monthly_cost_toman": cost_toman,
        "monthly_cost_eur": cost_eur,
        "currency": currency,
        "due_date": due_date_str,
        "due_date_jalali": due_date_jalali,
        "days_until_due": days_until_due,
        "cost_per_gb": cost_per_gb,
        "provider": provider,
        "notes": notes,
        "est_revenue_toman": est_revenue_toman,
        "net_profit_toman": net_profit_toman,
        "roi_percent": roi_percent,
        "is_profitable": net_profit_toman >= 0,
    }


def extract_node_item(
    n: dict,
    i: int,
    costs_by_uuid: dict,
    costs_by_id: dict,
    now_utc: datetime,
    avg_revenue_per_gb: float = 0.0,
) -> dict[str, Any]:
    """Parse telemetry, hardware metrics, country flag, and financials for one node."""
    raw_name = str(n.get("name") or f"Node {i}").strip()
    country_code = str(n.get("countryCode") or n.get("country_code") or "").strip().upper()
    c_raw = str(n.get("country") or "").strip().lower()
    flag = _extract_node_flag(raw_name, country_code, c_raw)
    c_fa_name = country_name(country_code) or country_name(raw_name) or country_name(c_raw)

    is_connected = n.get("isConnected")
    if is_connected is None:
        is_connected = str(n.get("status", "")).upper() in ("CONNECTED", "ONLINE")

    online_users = int(
        n.get("usersOnline") or n.get("connectionCount")
        or n.get("activeConnections") or n.get("connected_users") or 0
    )
    raw_sys = n.get("system") or n.get("sys") or {}
    cpu_val, ram_val, dl_speed, ul_speed = _extract_node_metrics(raw_sys, n, is_connected)

    address = str(n.get("address") or "—")
    port = n.get("port")
    addr_str = f"{address}:{port}" if port else address
    traffic_used = n.get("trafficUsedBytes") or n.get("usedTrafficBytes") or 0
    traffic_used_gb = round(traffic_used / (1024 ** 3), 2) if traffic_used else 0.0

    n_uuid = str(n.get("uuid") or n.get("id") or "")
    n_id_str = str(n.get("id") or "")
    cost_entry = costs_by_uuid.get(n_uuid) or costs_by_id.get(n_id_str)
    cost_data = _extract_node_costs(cost_entry, now_utc, traffic_used_gb, avg_revenue_per_gb)

    return {
        "id": n.get("id"),
        "uuid": n_uuid,
        "name": raw_name,
        "country_code": country_code or "NL",
        "country_name": c_fa_name or "هلند",
        "flag": flag,
        "status": "ONLINE" if is_connected else "OFFLINE",
        "connected_users": online_users,
        "cpu_percent": round(cpu_val, 1),
        "ram_percent": round(ram_val, 1),
        "download_speed": round(dl_speed, 1),
        "upload_speed": round(ul_speed, 1),
        "address": addr_str,
        "traffic_used_gb": traffic_used_gb,
        **cost_data,
    }


def calc_nodes_overview(
    nodes: list[dict],
    costs_by_uuid: dict,
    costs_by_id: dict,
    hwid_stats: dict,
    now_utc: datetime,
    avg_revenue_per_gb: float = 0.0,
) -> tuple[list[dict], int, int]:
    """Return nodes overview list, total online devices, and offline nodes count."""
    nodes_overview = [
        extract_node_item(n, i, costs_by_uuid, costs_by_id, now_utc, avg_revenue_per_gb)
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


async def calc_cluster_kpis(
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


# Aliases for backward compatibility
_extract_cpu = extract_cpu
_extract_ram = extract_ram
_extract_speeds = extract_speeds
_extract_node_item = extract_node_item
_calc_nodes_overview = calc_nodes_overview
_calc_cluster_kpis = calc_cluster_kpis
