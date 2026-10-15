"""Admin Infrastructure Billing and Node Costs API handlers for Telegram Mini App."""
import logging
from datetime import datetime, timedelta, timezone
from aiohttp import web
from sqlalchemy import func, select

from bot.db.models import AdminLog, Order
from bot.db.repositories.node_cost_repo import NodeCostRepository
from bot.web.admin_common import _check_admin as _default_check_admin, db_session
from bot.web.cache import FastCache
from bot.services.ssl_checker import check_domain_ssl, check_domains_ssl, get_system_ssl_domains

try:
    import jdatetime
except ImportError:
    jdatetime = None

logger = logging.getLogger(__name__)


def _check_admin(request):
    import bot.web.routes_admin as routes_admin
    check_fn = getattr(routes_admin, "_check_admin", _default_check_admin)
    return check_fn(request)


async def get_admin_infra_billing(request: web.Request) -> web.Response:
    """Return infrastructure billing analytics, server costs, net profit, and renewal dates."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    remnawave = request.app["remnawave"]
    now_utc = datetime.now(timezone.utc)
    thirty_days_ago = now_utc - timedelta(days=30)

    try:
        async with db_session(request) as session:
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
                            due_date_jalali = jdatetime.datetime.fromgregorian(datetime=cost_item.due_date).strftime("%Y/%m/%d")
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

    async with db_session(request) as session:
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

    cache = request.app.get("cache")
    if cache:
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


async def get_admin_ssl_health(request: web.Request) -> web.Response:
    """Check SSL certificate expiration and health for all system domains and nodes."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    remnawave = request.app.get("remnawave")
    domain_items = await get_system_ssl_domains(remnawave)
    domains = [item["domain"] for item in domain_items]
    labels_map = {item["domain"]: item["label"] for item in domain_items}

    results = await check_domains_ssl(domains)
    for res in results:
        res["label"] = labels_map.get(res["domain"], "دامنه سرور")

    return web.json_response({"ok": True, "data": results})


async def post_admin_ssl_check(request: web.Request) -> web.Response:
    """Check SSL certificate for an arbitrary custom domain."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    domain = str(body.get("domain") or "").strip()
    if not domain:
        return web.json_response({"ok": False, "error": "آدرس دامنه الزامی است."}, status=400)

    res = await check_domain_ssl(domain)
    res["label"] = "بررسی دستی"
    return web.json_response({"ok": True, "data": res})

