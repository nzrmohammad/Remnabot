"""Admin Infrastructure Billing and Node Costs API handlers for Telegram Mini App."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
import socket
import time
import aiohttp
from aiohttp import web
from sqlalchemy import func, select

from bot.db.models import AdminLog, Order
from bot.db.repositories.node_cost_repo import NodeCostRepository
from bot.web.admin_common import _check_admin as _default_check_admin, db_session
from bot.web.cache import FastCache
from bot.services.ssl_checker import (
    check_domain_ssl,
    check_domains_ssl,
    get_system_ssl_domains,
    add_custom_ssl_domain,
    delete_custom_ssl_domain,
)

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
    domain_items = []
    if "session_factory" in request.app or "session" in request:
        try:
            async with db_session(request) as session:
                domain_items = await get_system_ssl_domains(remnawave, session)
        except Exception:
            domain_items = await get_system_ssl_domains(remnawave)
    else:
        domain_items = await get_system_ssl_domains(remnawave)
    domains = [item["domain"] for item in domain_items]
    labels_map = {item["domain"]: item["label"] for item in domain_items}
    custom_map = {item["domain"]: item.get("is_custom", False) for item in domain_items}

    results = await check_domains_ssl(domains)
    for res in results:
        res["label"] = labels_map.get(res["domain"], "دامنه سرور")
        res["is_custom"] = custom_map.get(res["domain"], False)

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
    res["is_custom"] = False
    return web.json_response({"ok": True, "data": res})


async def post_admin_add_ssl_domain(request: web.Request) -> web.Response:
    """Add a custom domain to monitor SSL health."""
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

    async with db_session(request) as session:
        await add_custom_ssl_domain(session, domain)

    res = await check_domain_ssl(domain)
    res["label"] = "دامنه سفارشی ادمین"
    res["is_custom"] = True
    return web.json_response({"ok": True, "data": res, "message": "دامنه با موفقیت ثبت شد."})


async def post_admin_delete_ssl_domain(request: web.Request) -> web.Response:
    """Remove a custom domain from SSL monitor."""
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

    async with db_session(request) as session:
        await delete_custom_ssl_domain(session, domain)

    return web.json_response({"ok": True, "message": "دامنه با موفقیت حذف گردید."})


GITHUB_REPOS: dict[str, str] = {
    "v2rayng": "2dust/v2rayNG",
    "v2rayn": "2dust/v2rayN",
    "hiddify": "hiddify/hiddify-app",
    "happ": "happ-proxy/happ",
    "nekoray": "MatsuriDayo/nekoray",
    "v2raya": "v2rayA/v2rayA",
    "singbox": "SagerNet/sing-box",
}


async def get_admin_github_releases(request: web.Request) -> web.Response:
    """Fetch latest release versions from GitHub for supported open-source clients."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    target_app = request.query.get("app_id", "").strip().lower()
    items_to_check = {target_app: GITHUB_REPOS[target_app]} if target_app in GITHUB_REPOS else GITHUB_REPOS

    versions: dict[str, str] = {}
    import aiohttp
    async with aiohttp.ClientSession(headers={"User-Agent": "Remnabot-App-Monitor/1.0"}) as session:
        for app_id, repo in items_to_check.items():
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tag = str(data.get("tag_name") or "").strip()
                        clean_ver = tag.lstrip("vV")
                        if clean_ver:
                            versions[app_id] = clean_ver
            except Exception as exc:
                logger.warning("Failed to fetch GitHub release for %s (%s): %s", app_id, repo, exc)

    return web.json_response({"ok": True, "versions": versions})





async def get_admin_tools_check_host(request: web.Request) -> web.Response:
    """Perform network check (IP Info, Ping, HTTP, TCP, UDP, DNS) on target host/IP."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    host = (request.query.get("host") or "").strip()
    check_type = (request.query.get("type") or "info").lower().strip()
    port_str = (request.query.get("port") or "").strip()

    if not host:
        return web.json_response({"ok": False, "error": "نام دامنه یا آدرس آی‌پی الزامی است."}, status=400)

    clean_host = host.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip()
    if not clean_host:
        return web.json_response({"ok": False, "error": "آدرس نامعتبر است."}, status=400)

    port = 443
    if port_str.isdigit():
        port = int(port_str)
    elif check_type in ("http", "info"):
        port = 80
    elif check_type in ("ping", "tcp"):
        port = 443

    result = {}
    try:
        if check_type == "info":
            async with aiohttp.ClientSession() as s:
                url = f"http://ip-api.com/json/{clean_host}?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as,query"
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = {
                            "status": data.get("status"),
                            "ip": data.get("query"),
                            "country": data.get("country"),
                            "country_code": data.get("countryCode"),
                            "city": data.get("city"),
                            "region": data.get("regionName"),
                            "isp": data.get("isp"),
                            "org": data.get("org"),
                            "asn": data.get("as"),
                            "timezone": data.get("timezone"),
                        }
                    else:
                        result = {"error": f"HTTP {resp.status}"}

        elif check_type == "dns":
            loop = asyncio.get_event_loop()
            try:
                addr_info = await loop.getaddrinfo(clean_host, None)
                ips = sorted(list({info[4][0] for info in addr_info}))
                result = {
                    "host": clean_host,
                    "resolved_ips": ips,
                    "count": len(ips),
                }
            except Exception as e:
                result = {"error": f"خطا در تحلیل دامنه DNS: {e}"}

        elif check_type in ("ping", "tcp"):
            t0 = time.monotonic()
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(clean_host, port),
                    timeout=4.0
                )
                dt = (time.monotonic() - t0) * 1000.0
                writer.close()
                await writer.wait_closed()
                result = {
                    "host": clean_host,
                    "port": port,
                    "status": "OPEN",
                    "latency_ms": round(dt, 1),
                    "accessible": True,
                }
            except asyncio.TimeoutError:
                result = {
                    "host": clean_host,
                    "port": port,
                    "status": "TIMEOUT",
                    "latency_ms": None,
                    "accessible": False,
                }
            except Exception as e:
                result = {
                    "host": clean_host,
                    "port": port,
                    "status": "CLOSED",
                    "error": str(e),
                    "accessible": False,
                }

        elif check_type == "udp":
            t0 = time.monotonic()
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)
            try:
                loop = asyncio.get_event_loop()
                await loop.sock_connect(sock, (clean_host, port))
                await loop.sock_sendall(sock, b"\x00")
                dt = (time.monotonic() - t0) * 1000.0
                result = {
                    "host": clean_host,
                    "port": port,
                    "status": "SENT",
                    "latency_ms": round(dt, 1),
                    "accessible": True,
                }
            except Exception as e:
                result = {
                    "host": clean_host,
                    "port": port,
                    "status": "ERROR",
                    "error": str(e),
                    "accessible": False,
                }
            finally:
                sock.close()

        elif check_type == "http":
            t0 = time.monotonic()
            url = f"https://{clean_host}" if port == 443 else (f"http://{clean_host}:{port}" if port != 80 else f"http://{clean_host}")
            async with aiohttp.ClientSession() as s:
                try:
                    async with s.get(url, timeout=aiohttp.ClientTimeout(total=5), allow_redirects=True, ssl=False) as resp:
                        dt = (time.monotonic() - t0) * 1000.0
                        result = {
                            "url": url,
                            "status_code": resp.status,
                            "latency_ms": round(dt, 1),
                            "server": resp.headers.get("Server", "Unknown"),
                            "content_type": resp.headers.get("Content-Type", ""),
                            "accessible": True,
                        }
                except Exception as e:
                    result = {
                        "url": url,
                        "accessible": False,
                        "error": str(e),
                    }

        return web.json_response({"ok": True, "type": check_type, "host": clean_host, "result": result})
    except Exception as exc:
        logger.exception("Check-host error: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def get_admin_tools_asn_prefixes(request: web.Request) -> web.Response:
    """Fetch announced IP prefixes (CIDRs) for a given Autonomous System Number (ASN)."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    raw_asn = (request.query.get("asn") or "").strip().upper()
    if not raw_asn:
        return web.json_response({"ok": False, "error": "شماره ASN الزامی است (مثال: AS44244 یا 13335)."}, status=400)

    clean_asn = raw_asn.replace("AS", "").strip()
    if not clean_asn.isdigit():
        return web.json_response({"ok": False, "error": "فرمت ASN نامعتبر است. فقط از عدد یا پیشوند AS استفاده کنید."}, status=400)

    url = f"https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{clean_asn}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return web.json_response({"ok": False, "error": f"خطا در دریافت اطلاعات از پایگاه داده RIPE (کد {resp.status})."}, status=502)
                data = await resp.json()

        raw_prefixes = data.get("data", {}).get("prefixes", [])
        ipv4_list = []
        ipv6_list = []
        for p in raw_prefixes:
            prefix_str = p.get("prefix")
            if not prefix_str:
                continue
            if ":" in prefix_str:
                ipv6_list.append(prefix_str)
            else:
                ipv4_list.append(prefix_str)

        all_prefixes = sorted(ipv4_list) + sorted(ipv6_list)
        return web.json_response({
            "ok": True,
            "asn": f"AS{clean_asn}",
            "total_count": len(all_prefixes),
            "ipv4_count": len(ipv4_list),
            "ipv6_count": len(ipv6_list),
            "prefixes": all_prefixes,
        })
    except asyncio.TimeoutError:
        return web.json_response({"ok": False, "error": "پایگاه RIPE در زمان مقرر پاسخ نداد (Timeout)."}, status=504)
    except Exception as exc:
        logger.exception("ASN lookup error: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=500)
