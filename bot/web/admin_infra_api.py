"""Admin Infrastructure Billing and Node Costs API handlers for Telegram Mini App."""
import asyncio
import logging
import math
import re
import socket
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from aiohttp import web
from sqlalchemy import func, select

from bot.db.models import AdminLog, Order
from bot.db.repositories.node_cost_repo import NodeCostRepository
from bot.services.configs import _is_internal_host
from bot.services.ssl_checker import (
    add_custom_ssl_domain,
    check_domain_ssl,
    check_domains_ssl,
    delete_custom_ssl_domain,
    get_system_ssl_domains,
)
from bot.web.admin_common import _check_admin as _default_check_admin
from bot.web.admin_common import db_session

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
            total_infra_cost_eur = round(math.fsum(float(c.monthly_cost_eur or 0.0) for c in all_costs), 2)
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
                from bot.web.admin_overview_nodes import extract_node_panel_fields

                currency = getattr(cost_item, "currency", "EUR") or "EUR" if cost_item else "EUR"
                panel_meta = extract_node_panel_fields(n)
                provider = (cost_item.provider if cost_item else None) or panel_meta.get("panel_provider_name")
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
                    **panel_meta,
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


async def _invalidate_node_caches(request: web.Request) -> None:
    """Clear overview and Remnawave cluster caches after node mutations."""
    cache = request.app.get("cache")
    if not cache:
        return
    await cache.delete("tma:admin:overview")
    from bot.services.panel_snapshot import SNAPSHOT_CLUSTER_KEY
    await cache.delete(SNAPSHOT_CLUSTER_KEY)


def _build_node_panel_payload(body: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Validate and map requested panel node fields to Remnawave UpdateNodeRequestDto keys."""
    panel_payload: dict[str, Any] = {}
    for body_key, dto_key in (
        ("consumption_multiplier", "consumptionMultiplier"),
        ("node_consumption_multiplier", "nodeConsumptionMultiplier"),
    ):
        if body_key in body and body[body_key] not in (None, ""):
            try:
                val = float(body[body_key])
            except (TypeError, ValueError):
                return {}, f"مقدار {dto_key} معتبر نیست."
            if math.isnan(val) or math.isinf(val) or val < 0 or val > 100:
                return {}, f"ضریب {dto_key} باید بین 0 تا 100 باشد."
            panel_payload[dto_key] = round(val, 4)

    if "is_traffic_tracking_active" in body and body["is_traffic_tracking_active"] is not None:
        raw_track = body["is_traffic_tracking_active"]
        if isinstance(raw_track, str):
            panel_payload["isTrafficTrackingActive"] = raw_track.strip().lower() in ("1", "true", "yes", "on")
        else:
            panel_payload["isTrafficTrackingActive"] = bool(raw_track)

    if "traffic_limit_gb" in body and body["traffic_limit_gb"] not in (None, ""):
        try:
            limit_gb = float(body["traffic_limit_gb"])
        except (TypeError, ValueError):
            return {}, "مقدار محدودیت حجم ترافیک نود معتبر نیست."
        if math.isnan(limit_gb) or math.isinf(limit_gb) or limit_gb < 0:
            return {}, "محدودیت حجم ترافیک نود باید صفر یا مثبت باشد."
        panel_payload["trafficLimitBytes"] = int(round(limit_gb * (1024 ** 3)))

    if "traffic_reset_day" in body and body["traffic_reset_day"] not in (None, ""):
        try:
            reset_day = int(body["traffic_reset_day"])
        except (TypeError, ValueError):
            return {}, "روز ریست ماهانه نود معتبر نیست."
        if reset_day < 1 or reset_day > 31:
            return {}, "روز ریست ماهانه باید بین 1 تا 31 باشد."
        panel_payload["trafficResetDay"] = reset_day

    if "notify_percent" in body and body["notify_percent"] not in (None, ""):
        try:
            notify_pct = int(body["notify_percent"])
        except (TypeError, ValueError):
            return {}, "درصد هشدار ترافیک نود معتبر نیست."
        if notify_pct < 0 or notify_pct > 100:
            return {}, "درصد هشدار ترافیک باید بین 0 تا 100 باشد."
        panel_payload["notifyPercent"] = notify_pct

    if "description" in body:
        desc_val = str(body.get("description") or "").strip()
        panel_payload["description"] = desc_val or None

    if "provider_uuid" in body:
        prov_val = str(body.get("provider_uuid") or "").strip()
        panel_payload["providerUuid"] = prov_val or None

    return panel_payload, None


async def get_admin_infra_providers(request: web.Request) -> web.Response:
    """Return configured hosting/infra providers from Remnawave panel."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    remnawave = request.app.get("remnawave")
    providers: list[dict[str, Any]] = []
    if remnawave and hasattr(remnawave, "get_infra_providers"):
        providers = await remnawave.get_infra_providers()
    return web.json_response({"ok": True, "providers": providers})


async def post_admin_node_cost(request: web.Request) -> web.Response:
    """Save or update infrastructure costs, renewal date, and optional panel settings for a node."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    node_uuid = str(body.get("node_uuid") or body.get("uuid") or "").strip()
    if not node_uuid:
        return web.json_response({"ok": False, "error": "شناسه نود الزامی است."}, status=400)

    panel_payload, validation_err = _build_node_panel_payload(body)
    if validation_err:
        return web.json_response({"ok": False, "error": validation_err}, status=400)

    remnawave = request.app.get("remnawave")
    if panel_payload and remnawave and hasattr(remnawave, "update_node"):
        ok_panel, panel_res = await remnawave.update_node(node_uuid, panel_payload)
        if not ok_panel:
            return web.json_response(
                {"ok": False, "error": f"خطا در بروزرسانی تنظیمات پنل Remnawave: {panel_res}"},
                status=502,
            )

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
                detail=f"بروزرسانی تنظیمات و هزینه سرور {node_name or node_uuid}: {monthly_cost_toman:,} تومان، ارائه‌دهنده: {provider or '—'}",
            )
        )
        await session.commit()

    await _invalidate_node_caches(request)

    bot_obj = request.app.get("bot")
    sf_obj = request.app.get("session_factory")
    if due_date is not None and bot_obj and sf_obj:
        if (due_date.date() - datetime.now(timezone.utc).date()).days <= 4:
            try:
                from bot.services.node_monitor import check_nodes_billing_due_dates
                await check_nodes_billing_due_dates(bot_obj, sf_obj)
            except Exception as exc:
                logger.warning("Immediate node billing due check failed: %s", exc)

    return web.json_response({
        "ok": True,
        "message": "اطلاعات سرور و تنظیمات پنل با موفقیت ثبت شد.",
        "data": {
            "node_uuid": item.node_uuid,
            "monthly_cost_toman": item.monthly_cost_toman,
            "monthly_cost_eur": item.monthly_cost_eur,
            "due_date": item.due_date.strftime("%Y-%m-%d") if item.due_date else None,
            "provider": item.provider,
            **({"panel_updated": True} if panel_payload else {}),
        }
    })


async def post_admin_node_restart(request: web.Request) -> web.Response:
    """Restart a single Remnawave node on admin request."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    node_uuid = str(body.get("node_uuid") or body.get("uuid") or "").strip()
    if not node_uuid:
        return web.json_response({"ok": False, "error": "شناسه نود الزامی است."}, status=400)

    node_name = str(body.get("node_name") or "").strip()
    force_restart = bool(body.get("force_restart", False))
    remnawave = request.app.get("remnawave")
    if not remnawave or not hasattr(remnawave, "restart_node"):
        return web.json_response({"ok": False, "error": "سرویس پنل در دسترس نیست."}, status=503)

    ok_restart, message = await remnawave.restart_node(node_uuid, force_restart=force_restart)
    if not ok_restart:
        return web.json_response({"ok": False, "error": f"خطا در ریستارت سرور: {message}"}, status=502)

    async with db_session(request) as session:
        session.add(
            AdminLog(
                admin_id=admin["id"],
                action="restart_node",
                detail=f"ریستارت سرور {node_name or node_uuid} (force={force_restart})",
            )
        )
        await session.commit()

    await _invalidate_node_caches(request)
    return web.json_response({"ok": True, "message": message})


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
    if not isinstance(body, dict):
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
    if not isinstance(body, dict):
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
    if not isinstance(body, dict):
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
    "happ": "Happ-proxy/happ-desktop",
    "nekoray": "MatsuriDayo/nekoray",
    "v2raya": "v2rayA/v2rayA",
    "singbox": "SagerNet/sing-box",
    "karing": "KaringX/karing",
    "pattn": "patterniha/PattN",
    "pattng": "patterniha/PattNG",
    "zedsecure": "CluvexStudio/ZedSecure",
    "blackwall": "ANODs/blackwall",
    "onexray": "YuanDevTeam/OneXray",
    "incy": "INCY-DEV/incy-platforms",
    "v2raytun": "DigneZzZ/v2raytun",
    "byp": "devlsam/byp",
}

APPSTORE_IDS: dict[str, str] = {
    "shadowrocket": "932747118",
    "streisand": "6450534064",
    "v2box": "6446814690",
}

_ASSET_IGNORE_TOKENS = (
    ".sig",
    ".asc",
    ".sha256",
    ".txt",
    ".json",
    ".aab",
    "fdroid",
    "webapi",
    "web.tar",
    "web.zip",
    "-core",
)


def _pick_first(assets: list[tuple[str, str]], *predicates) -> str:
    """Return the download URL of the first asset matching all predicates."""
    for pred in predicates:
        for low, url in assets:
            if pred(low):
                return url
    return ""


def _extract_github_downloads(app_id: str, assets_raw: Any) -> dict[str, dict[str, str]]:
    """Extract direct per-platform 64-bit download URLs from GitHub release assets."""
    if not isinstance(assets_raw, list):
        return {}
    assets: list[tuple[str, str]] = []
    for item in assets_raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        url = str(item.get("browser_download_url") or "").strip()
        low = name.lower()
        if not name or not url or any(tok in low for tok in _ASSET_IGNORE_TOKENS):
            continue
        assets.append((low, url))
    if not assets:
        return {}

    def is_x64(n: str) -> bool:
        return any(a in n for a in ("x64", "amd64", "x86_64", "win64", "windows-64", "windows64", "linux-64", "linux64"))

    def not_alt_arch(n: str) -> bool:
        return not any(a in n for a in ("arm64", "aarch64", "armv7", "windows-86", "windows-32", "ia32", "loong", "riscv"))

    downloads: dict[str, dict[str, str]] = {}

    apk_arm64 = _pick_first(
        assets,
        lambda n: n.endswith(".apk") and ("arm64-v8a" in n or "arm64_v8a" in n),
        lambda n: n.endswith(".apk") and "arm64" in n and "x86" not in n,
        lambda n: n.endswith(".apk") and "universal" in n,
        lambda n: n.endswith(".apk"),
    )
    if apk_arm64:
        downloads["android"] = {"direct_url": apk_arm64}

    win_setup = _pick_first(
        assets,
        lambda n: n.endswith((".exe", ".msi")) and "portable" not in n and is_x64(n) and not_alt_arch(n),
        lambda n: n.endswith((".exe", ".msi")) and "portable" not in n and ("windows" in n or "win" in n or "setup" in n or "installer" in n) and not_alt_arch(n),
        lambda n: n.endswith(".zip") and ("setup" in n or "installer" in n) and "portable" not in n and is_x64(n) and not_alt_arch(n),
    )
    win_portable = _pick_first(
        assets,
        lambda n: "portable" in n and n.endswith((".zip", ".7z", ".exe")) and is_x64(n) and not_alt_arch(n),
        lambda n: "portable" in n and n.endswith((".zip", ".7z", ".exe")) and ("windows" in n or "win" in n or "64" in n) and not_alt_arch(n),
        lambda n: n.endswith((".zip", ".7z")) and "setup" not in n and "installer" not in n and is_x64(n) and not_alt_arch(n) and (
            "windows" in n or "win" in n or "desktop" in n
        ),
    )
    if win_setup or win_portable:
        win_cfg: dict[str, str] = {}
        if win_setup:
            win_cfg["url"] = win_setup
        if win_portable and win_portable != win_setup:
            win_cfg["portable_url"] = win_portable
        downloads["windows"] = win_cfg

    mac_dmg = _pick_first(
        assets,
        lambda n: n.endswith(".dmg") and "universal" in n,
        lambda n: n.endswith(".dmg") and "arm64" in n,
        lambda n: n.endswith(".dmg") and ("x64" in n or "x86_64" in n or "64" in n or "macos" in n),
        lambda n: n.endswith(".pkg") and "macos" in n,
        lambda n: n.endswith((".dmg", ".pkg", ".zip")) and ("macos" in n or "darwin" in n or "mac" in n),
    )
    if mac_dmg:
        downloads["macos"] = {"url": mac_dmg}

    linux_pkg = _pick_first(
        assets,
        lambda n: n.endswith(".appimage") and is_x64(n) and not_alt_arch(n),
        lambda n: n.endswith(".deb") and is_x64(n) and not_alt_arch(n),
        lambda n: n.endswith((".tar.gz", ".tar.xz", ".zip", ".rpm")) and "linux" in n and is_x64(n) and not_alt_arch(n),
        lambda n: n.endswith(".tar.gz") and is_x64(n) and "appimage" in n and not_alt_arch(n),
    )
    if linux_pkg:
        downloads["linux"] = {"url": linux_pkg}

    return downloads


async def _fetch_single_github_release(session: Any, app_id: str, repo: str) -> tuple[str, str, dict[str, dict[str, str]]]:
    """Fetch version tag and platform download URLs for one GitHub or App Store app."""
    import asyncio

    # Case 1: App Store lookup for iOS-only apps
    if app_id in APPSTORE_IDS:
        track_id = APPSTORE_IDS[app_id]
        itunes_url = f"https://itunes.apple.com/lookup?id={track_id}"
        try:
            async with session.get(itunes_url, timeout=8) as resp:
                if resp.status == 200:
                    payload = await resp.json(content_type=None)
                    results = payload.get("results") or []
                    if results and isinstance(results[0], dict):
                        ver = str(results[0].get("version") or "").strip()
                        if ver:
                            return app_id, ver, {}
        except Exception as exc:
            logger.warning("Failed to fetch App Store version for %s: %s", app_id, exc)
        return app_id, "", {}

    if not repo:
        return app_id, "", {}

    # Case 2: GitHub Releases REST API
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    candidates = [url, f"https://api.github.com/repos/{repo}/releases?per_page=10"]
    for idx, endpoint in enumerate(candidates):
        try:
            async with session.get(endpoint, timeout=8) as resp:
                if resp.status == 403:
                    break
                if resp.status != 200:
                    continue
                payload = await resp.json()
                release = None
                if isinstance(payload, dict):
                    release = payload
                elif isinstance(payload, list):
                    release = next((r for r in payload if isinstance(r, dict) and not r.get("draft")), None) or (
                        payload[0] if payload and isinstance(payload[0], dict) else None
                    )
                if not release:
                    continue
                tag = str(release.get("tag_name") or "").strip()
                clean_ver = tag.lstrip("vV")
                if clean_ver.lower() == "draft" and idx == 0:
                    continue
                if clean_ver.lower() in ("latest", "release", "current"):
                    body_text = f"{release.get('name') or ''} {release.get('body') or ''}"
                    v_match = re.search(r"(\d+\.\d+(?:\.\d+)*)", body_text)
                    if v_match:
                        clean_ver = v_match.group(1)
                dl_map = _extract_github_downloads(app_id, release.get("assets"))
                if clean_ver:
                    if app_id == "blackwall" and clean_ver.lower().endswith("-en"):
                        clean_ver = clean_ver[:-3]
                    if app_id == "happ":
                        dl_map.setdefault("windows", {})["version"] = clean_ver
                        dl_map.setdefault("macos", {})["version"] = clean_ver
                        try:
                            async with session.get("https://api.github.com/repos/Happ-proxy/happ-android/releases/latest", timeout=6) as a_resp:
                                if a_resp.status == 200:
                                    a_data = await a_resp.json()
                                    a_tag = str(a_data.get("tag_name") or "").strip().lstrip("vV")
                                    a_dl = _extract_github_downloads("happ", a_data.get("assets"))
                                    if "android" in a_dl:
                                        dl_map["android"] = a_dl["android"]
                                    if a_tag:
                                        dl_map.setdefault("android", {})["version"] = a_tag
                        except Exception:
                            pass
                    if app_id == "incy":
                        body_str = f"{release.get('name') or ''} {release.get('body') or ''}"
                        d_m = re.search(r"Desktop\s*\*\*([0-9.]+)\*\*", body_str, re.IGNORECASE)
                        a_m = re.search(r"Android\s*\*\*([0-9.]+)\*\*", body_str, re.IGNORECASE)
                        d_ver = d_m.group(1) if d_m else "3.9.1"
                        a_ver = a_m.group(1) if a_m else "4.0.1"
                        dl_map.setdefault("windows", {})["version"] = d_ver
                        dl_map.setdefault("macos", {})["version"] = d_ver
                        dl_map.setdefault("linux", {})["version"] = d_ver
                        dl_map.setdefault("android", {})["version"] = a_ver
                        clean_ver = d_ver
                    return app_id, clean_ver, dl_map
        except Exception as exc:
            if idx == len(candidates) - 1:
                logger.warning("Failed to fetch GitHub release for %s (%s): %s", app_id, repo, exc)
        await asyncio.sleep(0)

    # Case 3: HTML redirect fallback (zero rate limit)
    try:
        redirect_url = f"https://github.com/{repo}/releases/latest"
        async with session.get(redirect_url, allow_redirects=False, timeout=8) as r:
            loc = r.headers.get("Location") or ""
            if "/releases/tag/" in loc:
                raw_tag = loc.rstrip("/").split("/")[-1].strip()
                clean_ver = raw_tag.lstrip("vV")
                if clean_ver.lower() in ("latest", "release", "current") and app_id == "incy":
                    clean_ver = "3.9.1"
                if clean_ver:
                    if app_id == "blackwall" and clean_ver.lower().endswith("-en"):
                        clean_ver = clean_ver[:-3]
                    dl_map: dict[str, dict[str, str]] = {}
                    if app_id == "happ":
                        dl_map.setdefault("windows", {})["version"] = clean_ver
                        dl_map.setdefault("macos", {})["version"] = clean_ver
                        try:
                            async with session.get("https://github.com/Happ-proxy/happ-android/releases/latest", allow_redirects=False, timeout=8) as ar:
                                aloc = ar.headers.get("Location") or ""
                                if "/releases/tag/" in aloc:
                                    a_tag = aloc.rstrip("/").split("/")[-1].strip().lstrip("vV")
                                    if a_tag:
                                        dl_map["android"] = {"version": a_tag}
                        except Exception:
                            pass
                    if app_id == "incy":
                        dl_map.setdefault("windows", {})["version"] = "3.9.1"
                        dl_map.setdefault("macos", {})["version"] = "3.9.1"
                        dl_map.setdefault("linux", {})["version"] = "3.9.1"
                        dl_map.setdefault("android", {})["version"] = "4.0.1"
                        clean_ver = "3.9.1"
                    return app_id, clean_ver, dl_map
    except Exception as exc:
        logger.debug("HTML redirect fallback failed for %s: %s", repo, exc)

    return app_id, "", {}


async def get_admin_github_releases(request: web.Request) -> web.Response:
    """Fetch latest release versions and direct 64-bit/Arm64v8 asset links from GitHub."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    target_app = request.query.get("app_id", "").strip().lower()
    all_targets: dict[str, str] = {**GITHUB_REPOS, **{k: "" for k in APPSTORE_IDS}}
    items_to_check = {target_app: all_targets[target_app]} if target_app in all_targets else all_targets

    versions: dict[str, str] = {}
    downloads: dict[str, dict[str, dict[str, str]]] = {}
    async with aiohttp.ClientSession(headers={"User-Agent": "Remnabot-App-Monitor/1.0"}) as session:
        results = await asyncio.gather(
            *(_fetch_single_github_release(session, app_id, repo) for app_id, repo in items_to_check.items()),
            return_exceptions=False,
        )
        for app_id, ver, dl_map in results:
            if ver:
                versions[app_id] = ver
            if dl_map:
                downloads[app_id] = dl_map

    return web.json_response({"ok": True, "versions": versions, "downloads": downloads})





def _cc_to_flag(cc: str) -> str:
    """Convert 2-letter country code to flag emoji."""
    if not cc or len(cc) != 2:
        return "🌐"
    try:
        return "".join(chr(127397 + ord(c)) for c in cc.upper())
    except Exception:
        return "🌐"


async def get_admin_tools_check_host(request: web.Request) -> web.Response:
    """Perform network check (Ping, HTTP, TCP, DNS) using Check-Host API with local fallback."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    if request.method == "POST":
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        host = (body.get("host") or "").strip()
        check_type = (body.get("check_type") or body.get("type") or "ping").lower().strip()
        port_val = body.get("port")
        max_nodes_val = body.get("max_nodes")
    else:
        host = (request.query.get("host") or "").strip()
        check_type = (request.query.get("type") or "ping").lower().strip()
        port_val = request.query.get("port")
        max_nodes_val = request.query.get("max_nodes")

    if not host:
        return web.json_response({"ok": False, "error": "نام دامنه یا آدرس آی‌پی الزامی است."}, status=400)

    original_host = host.strip()
    is_https = original_host.startswith("https://")
    clean_host = original_host.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0].strip("[] ")
    if not clean_host:
        return web.json_response({"ok": False, "error": "آدرس نامعتبر است."}, status=400)
    if _is_internal_host(clean_host):
        return web.json_response({"ok": False, "error": "بررسی آدرس‌های داخلی و خصوصی مجاز نیست."}, status=400)

    logger.info(
        "Admin network check requested: admin_id=%s host=%s check_type=%s port=%s",
        admin.get("id"), clean_host, check_type, port_val,
    )

    # Validate DNS existence and block internal/metadata SSRF targets for hostnames before testing
    is_ip = False
    try:
        socket.inet_aton(clean_host)
        is_ip = True
    except OSError:
        try:
            socket.inet_pton(socket.AF_INET6, clean_host)
            is_ip = True
        except OSError:
            pass

    if not is_ip:
        try:
            addr_info = await asyncio.get_running_loop().getaddrinfo(clean_host, None)
            if any(_is_internal_host(str(entry[4][0])) for entry in addr_info if entry and entry[4]):
                return web.json_response(
                    {"ok": False, "error": "دامنه به آدرس داخلی یا خصوصی اشاره دارد و مجاز نیست."},
                    status=400,
                )
        except Exception:
            return web.json_response({
                "ok": True,
                "type": check_type,
                "host": clean_host,
                "results": [
                    {
                        "node_name": "وضعیت دامنه / DNS",
                        "flag": "❌",
                        "ok": False,
                        "ping_ms": None,
                        "status": "دامنه نامعتبر (عدم پاسخ DNS)",
                    }
                ],
            })

    port = None
    if port_val is not None and str(port_val).isdigit():
        port = int(port_val)
    elif check_type in ("tcp",):
        port = 443

    results: list[dict[str, Any]] = []

    # 1. Try public Check-Host API
    try:
        endpoint = "ping"
        query_host = clean_host
        if check_type == "tcp":
            endpoint = "tcp"
            query_host = f"{clean_host}:{port or 443}"
        elif check_type == "http":
            endpoint = "http"
            if port and port not in (80, 443):
                query_host = f"{clean_host}:{port}"
            elif is_https:
                query_host = f"https://{clean_host}"
            else:
                query_host = clean_host
        elif check_type == "dns":
            endpoint = "dns"
            query_host = clean_host

        try:
            max_nodes = max(4, min(30, int(max_nodes_val or 10)))
        except (ValueError, TypeError):
            max_nodes = 10

        from urllib.parse import quote
        init_url = f"https://check-host.net/check-{endpoint}?host={quote(query_host)}&max_nodes={max_nodes}"
        headers = {"Accept": "application/json", "User-Agent": "Remnabot-Monitor/1.0"}

        import aiohttp
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(init_url, timeout=aiohttp.ClientTimeout(total=6)) as init_resp:
                if init_resp.status == 200:
                    init_data = await init_resp.json()
                    req_id = init_data.get("request_id")
                    nodes = init_data.get("nodes", {})
                    if req_id and nodes:
                        await asyncio.sleep(3.0)
                        res_url = f"https://check-host.net/check-result/{req_id}"
                        async with session.get(res_url, timeout=aiohttp.ClientTimeout(total=7)) as res_resp:
                            if res_resp.status == 200:
                                res_data = await res_resp.json()
                                for node_key, node_val in (res_data or {}).items():
                                    node_info = nodes.get(node_key, ["", "جهانی", ""])
                                    cc = node_info[0] if len(node_info) > 0 else "UN"
                                    country = node_info[1] if len(node_info) > 1 else "جهانی"
                                    city = node_info[2] if len(node_info) > 2 else ""
                                    loc_name = f"{country} ({city})" if city else country

                                    pings: list[float] = []
                                    status_text = "عدم پاسخ (Timeout)"
                                    is_ok = False

                                    if isinstance(node_val, list) and node_val:
                                        first_elem = node_val[0]
                                        if isinstance(first_elem, list):
                                            for p in first_elem:
                                                if isinstance(p, list) and len(p) >= 2:
                                                    if str(p[0]).upper() == "OK" and p[1] is not None:
                                                        try:
                                                            pings.append(float(p[1]))
                                                        except (ValueError, TypeError):
                                                            pass
                                                    elif p[0]:
                                                        status_text = str(p[0])
                                        elif isinstance(first_elem, dict):
                                            status_text = str(first_elem.get("status") or first_elem.get("error") or "عدم دسترسی")
                                            if first_elem.get("time") is not None:
                                                pings.append(float(first_elem["time"]))
                                            is_ok = first_elem.get("error") is None and bool(pings)
                                    elif isinstance(node_val, dict):
                                        status_text = str(node_val.get("status") or node_val.get("error") or "عدم دسترسی")
                                        if node_val.get("time") is not None:
                                            pings.append(float(node_val["time"]))
                                        is_ok = node_val.get("error") is None and bool(pings)

                                    if pings:
                                        is_ok = True
                                        avg_ms = round((sum(pings) / len(pings)) * 1000.0, 1)
                                        status_text = "OK"
                                    else:
                                        avg_ms = None
                                        is_ok = False
                                        if not status_text or status_text == "OK":
                                            status_text = "عدم پاسخ (Timeout)"

                                    results.append({
                                        "node_name": loc_name,
                                        "flag": _cc_to_flag(cc),
                                        "ok": is_ok,
                                        "ping_ms": avg_ms,
                                        "status": status_text,
                                    })
    except Exception as check_exc:
        logger.warning("Check-Host external API request failed, falling back to local diagnostics: %s", check_exc)

    # 2. Fallback to local socket / ping / DNS if external API failed or yielded no results
    if not results:
        loop = asyncio.get_event_loop()
        if check_type == "dns":
            try:
                addr_info = await loop.getaddrinfo(clean_host, None)
                ips = sorted(list({info[4][0] for info in addr_info}))
                for ip in ips[:6]:
                    results.append({
                        "node_name": f"DNS IP: {ip}",
                        "flag": "🔍",
                        "ok": True,
                        "ping_ms": None,
                        "status": "Resolved",
                    })
            except Exception as e:
                results.append({
                    "node_name": "تحلیل DNS",
                    "flag": "❌",
                    "ok": False,
                    "ping_ms": None,
                    "status": f"خطا: {e}",
                })
        else:
            # Measure local TCP / socket connection
            fallback_port = port if port is not None else (80 if check_type == "http" and not is_https else 443)
            t0 = time.monotonic()
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(clean_host, fallback_port),
                    timeout=3.0,
                )
                dt = (time.monotonic() - t0) * 1000.0
                writer.close()
                await writer.wait_closed()
                results.append({
                    "node_name": f"سرور اصلی (پورت {fallback_port})",
                    "flag": "🇮🇷",
                    "ok": True,
                    "ping_ms": round(dt, 1),
                    "status": "OPEN",
                })
            except Exception:
                results.append({
                    "node_name": f"سرور اصلی (پورت {fallback_port})",
                    "flag": "❌",
                    "ok": False,
                    "ping_ms": None,
                    "status": "عدم دسترسی",
                })

    # 3. Always ensure Iran node is included and prioritized in results
    if check_type != "dns":
        has_iran = any(
            r.get("flag") == "🇮🇷"
            or "iran" in str(r.get("node_name", "")).lower()
            or "ایران" in str(r.get("node_name", ""))
            for r in results
        )
        if not has_iran:
            fallback_port = port if port is not None else (80 if check_type == "http" and not is_https else 443)
            t0 = time.monotonic()
            iran_ok = False
            iran_ping = None
            iran_status = "عدم پاسخ (Timeout)"
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(clean_host, fallback_port),
                    timeout=2.5,
                )
                dt = (time.monotonic() - t0) * 1000.0
                writer.close()
                await writer.wait_closed()
                iran_ok = True
                iran_ping = round(dt, 1)
                iran_status = "OK"
            except Exception:
                iran_status = "Timeout"

            results.insert(0, {
                "node_name": "ایران (تهران)",
                "flag": "🇮🇷",
                "ok": iran_ok,
                "ping_ms": iran_ping,
                "status": iran_status,
            })
        else:
            iran_nodes = [
                r for r in results
                if r.get("flag") == "🇮🇷"
                or "iran" in str(r.get("node_name", "")).lower()
                or "ایران" in str(r.get("node_name", ""))
            ]
            other_nodes = [r for r in results if r not in iran_nodes]
            results = iran_nodes + other_nodes

    return web.json_response({
        "ok": True,
        "type": check_type,
        "host": clean_host,
        "results": results,
    })


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
    except TimeoutError:
        return web.json_response({"ok": False, "error": "پایگاه RIPE در زمان مقرر پاسخ نداد (Timeout)."}, status=504)
    except Exception as exc:
        logger.exception("ASN lookup error: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=500)
