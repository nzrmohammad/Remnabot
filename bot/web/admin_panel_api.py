"""Extended Remnawave Panel Control Admin API handlers for Telegram Mini App."""
from __future__ import annotations

import asyncio
import json as _json
import logging
from datetime import datetime, timezone
from typing import Any

from aiohttp import web

from bot.db.models import AdminLog
from bot.web.admin_common import _check_admin as _default_check_admin
from bot.web.admin_common import db_session
from bot.web.admin_infra_api import _invalidate_node_caches

logger = logging.getLogger(__name__)


def _check_admin(request: web.Request) -> dict[str, Any] | None:
    import bot.web.routes_admin as routes_admin

    check_fn = getattr(routes_admin, "_check_admin", _default_check_admin)
    return check_fn(request)


async def _parse_json(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


def _require_admin_remnawave(
    request: web.Request,
) -> tuple[dict[str, Any] | None, Any, web.Response | None]:
    admin = _check_admin(request)
    if not admin:
        return None, None, web.json_response({"ok": False, "error": "Forbidden"}, status=403)
    remnawave = request.app.get("remnawave")
    if not remnawave:
        return None, None, web.json_response({"ok": False, "error": "سرویس پنل در دسترس نیست."}, status=503)
    return admin, remnawave, None


async def _audit_and_refresh(request: web.Request, admin_id: int, action: str, detail: str) -> None:
    async with db_session(request) as session:
        session.add(AdminLog(admin_id=admin_id, action=action, detail=detail[:500]))
        await session.commit()
    await _invalidate_node_caches(request)


# --- 1. Node Lifecycle & Cluster Actions ---
async def post_admin_panel_node_action(request: web.Request) -> web.Response:
    """Execute node enable/disable/reset-traffic or cluster restart-all action."""
    admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    body = await _parse_json(request)
    action = str(body.get("action") or "").strip().lower()
    node_uuid = str(body.get("node_uuid") or "").strip()
    node_name = str(body.get("node_name") or node_uuid or "cluster").strip()
    force_restart = bool(body.get("force_restart", False))

    if action == "restart_all":
        ok, msg = await remnawave.restart_all_nodes(force_restart=force_restart)
    elif action in ("enable", "disable", "reset_traffic"):
        if not node_uuid:
            return web.json_response({"ok": False, "error": "شناسه سرور الزامی است."}, status=400)
        if action == "enable":
            ok, msg = await remnawave.set_node_enabled(node_uuid, True)
        elif action == "disable":
            ok, msg = await remnawave.set_node_enabled(node_uuid, False)
        else:
            ok, msg = await remnawave.reset_node_traffic(node_uuid)
    else:
        return web.json_response({"ok": False, "error": "عملیات نامعتبر است."}, status=400)

    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=502)

    await _audit_and_refresh(request, admin["id"], f"node_{action}", f"{action} روی سرور {node_name}")
    return web.json_response({"ok": True, "message": msg})


# --- 2. Unified Panel Control Overview ---
async def get_admin_panel_control(request: web.Request) -> web.Response:
    """Concurrently fetch Hosts, Config Profiles, Snippets, External Squads, Sub Settings, Infra & Tokens."""
    _admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    (
        hosts_res,
        profiles_res,
        snippets_res,
        ext_squads_res,
        int_squads_res,
        sub_settings_res,
        providers_res,
        billing_nodes_res,
        tokens_res,
    ) = await asyncio.gather(
        remnawave.get_hosts(),
        remnawave.get_config_profiles(),
        remnawave.get_snippets(),
        remnawave.get_external_squads(),
        remnawave.get_internal_squads(),
        remnawave.get_subscription_settings(),
        remnawave.get_infra_providers(),
        remnawave.get_infra_billing_nodes(),
        remnawave.get_api_tokens(),
        return_exceptions=True,
    )

    def _safe(val: Any, fallback: Any) -> Any:
        return fallback if isinstance(val, Exception) or val is None else val

    return web.json_response({
        "ok": True,
        "data": {
            "hosts": _safe(hosts_res, []),
            "config_profiles": _safe(profiles_res, []),
            "snippets": _safe(snippets_res, []),
            "external_squads": _safe(ext_squads_res, []),
            "internal_squads": _safe(int_squads_res, []),
            "subscription_settings": _safe(sub_settings_res, {}),
            "infra_providers": _safe(providers_res, []),
            "infra_billing_nodes": _safe(billing_nodes_res, []),
            "api_tokens_info": _safe(tokens_res, {"ok": False, "tokens": [], "jwt_required": False}),
        },
    })


# --- 3. Hosts Management ---
async def post_admin_panel_host_save(request: web.Request) -> web.Response:
    """Create or update a Remnawave host."""
    admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    body = await _parse_json(request)
    host_uuid = str(body.get("uuid") or "").strip()
    remark = str(body.get("remark") or "").strip()
    address = str(body.get("address") or "").strip()
    if not remark or not address:
        return web.json_response({"ok": False, "error": "نام و آدرس هاست الزامی است."}, status=400)

    try:
        port = int(body.get("port") or 443)
        if port < 1 or port > 65535:
            raise ValueError("port")
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "شماره پورت معتبر نیست (1 تا 65535)."}, status=400)

    payload: dict[str, Any] = {
        "remark": remark,
        "address": address,
        "port": port,
        "isDisabled": bool(body.get("is_disabled", False)),
    }
    if body.get("sni") is not None:
        payload["sni"] = str(body.get("sni") or "").strip() or None
    if body.get("host") is not None:
        payload["host"] = str(body.get("host") or "").strip() or None

    inbound_uuid = str(body.get("inbound_uuid") or "").strip()
    cfg_profile_uuid = str(body.get("config_profile_uuid") or "").strip()
    if inbound_uuid:
        payload["inboundUuid"] = inbound_uuid
    if cfg_profile_uuid and inbound_uuid:
        payload["inbound"] = {"configProfileUuid": cfg_profile_uuid, "configProfileInboundUuid": inbound_uuid}

    if "squad_uuids" in body:
        raw_squads = body.get("squad_uuids") or []
        squad_uuids = [str(x).strip() for x in raw_squads if str(x).strip()] if isinstance(raw_squads, list) else []
        squad_mode = str(body.get("squad_mode") or "EXCLUDE").strip().upper()
        if squad_mode not in ("ALLOW_ONLY", "EXCLUDE"):
            squad_mode = "EXCLUDE"
        payload["internalSquads"] = {"mode": squad_mode, "squads": squad_uuids}

    if host_uuid:
        payload["uuid"] = host_uuid
        ok, res = await remnawave.update_host(payload)
    else:
        ok, res = await remnawave.create_host(payload)

    if not ok:
        return web.json_response({"ok": False, "error": str(res)}, status=502)

    await _audit_and_refresh(request, admin["id"], "save_panel_host", f"هاست {remark} ({address}:{port})")
    return web.json_response({"ok": True, "message": "هاست با موفقیت ذخیره شد.", "host": res})


async def post_admin_panel_hosts_bulk(request: web.Request) -> web.Response:
    """Run bulk enable/disable/delete on panel hosts."""
    admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    body = await _parse_json(request)
    action = str(body.get("action") or "").strip().lower()
    raw_uuids = body.get("uuids") or []
    uuids = [str(u).strip() for u in raw_uuids if str(u).strip()] if isinstance(raw_uuids, list) else []
    ok, msg = await remnawave.bulk_hosts_action(action, uuids)
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=400 if "نامعتبر" in msg else 502)

    await _audit_and_refresh(request, admin["id"], f"hosts_bulk_{action}", msg)
    return web.json_response({"ok": True, "message": msg})


# --- 4. Snippets Management ---
async def post_admin_panel_snippet_save(request: web.Request) -> web.Response:
    """Create or update an Xray config JSON snippet."""
    admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    body = await _parse_json(request)
    name = str(body.get("name") or "").strip()
    raw_snippet = body.get("snippet")
    update = bool(body.get("is_edit", False))
    if not name or raw_snippet is None:
        return web.json_response({"ok": False, "error": "نام و محتوای JSON اسنیپت الزامی است."}, status=400)

    if isinstance(raw_snippet, str):
        try:
            parsed_snippet = _json.loads(raw_snippet)
        except Exception as exc:
            return web.json_response({"ok": False, "error": f"فرمت JSON نامعتبر است: {exc}"}, status=400)
    else:
        parsed_snippet = raw_snippet

    ok, res = await remnawave.save_snippet(name, parsed_snippet, update=update)
    if not ok:
        return web.json_response({"ok": False, "error": str(res)}, status=502)

    await _audit_and_refresh(request, admin["id"], "save_panel_snippet", f"اسنیپت {name}")
    return web.json_response({"ok": True, "message": f"اسنیپت «{name}» ذخیره شد.", "data": res})


async def post_admin_panel_snippet_delete(request: web.Request) -> web.Response:
    """Delete an Xray config snippet."""
    admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    body = await _parse_json(request)
    name = str(body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "نام اسنیپت الزامی است."}, status=400)

    ok, res = await remnawave.delete_snippet(name)
    if not ok:
        return web.json_response({"ok": False, "error": str(res)}, status=502)

    await _audit_and_refresh(request, admin["id"], "delete_panel_snippet", f"حذف اسنیپت {name}")
    return web.json_response({"ok": True, "message": f"اسنیپت «{name}» حذف شد."})


# --- 5. Subscription Settings & External Squads ---
async def post_admin_panel_subscription_settings(request: web.Request) -> web.Response:
    """Update Remnawave global subscription settings."""
    admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    body = await _parse_json(request)
    payload: dict[str, Any] = {}
    if body.get("uuid"):
        payload["uuid"] = str(body["uuid"]).strip()
    if "profile_title" in body:
        payload["profileTitle"] = str(body.get("profile_title") or "").strip()
    if "support_link" in body:
        payload["supportLink"] = str(body.get("support_link") or "").strip()
    if "profile_update_interval" in body and body["profile_update_interval"] not in (None, ""):
        try:
            interval = max(1, int(body["profile_update_interval"]))
            payload["profileUpdateInterval"] = interval
        except (TypeError, ValueError):
            return web.json_response({"ok": False, "error": "بازه آپدیت ساب باید عدد صحیح باشد."}, status=400)
    if "is_profile_webpage_url_enabled" in body:
        payload["isProfileWebpageUrlEnabled"] = bool(body["is_profile_webpage_url_enabled"])
    if "serve_json_at_base_subscription" in body:
        payload["serveJsonAtBaseSubscription"] = bool(body["serve_json_at_base_subscription"])

    ok, res = await remnawave.update_subscription_settings(payload)
    if not ok:
        return web.json_response({"ok": False, "error": str(res)}, status=502)

    await _audit_and_refresh(request, admin["id"], "update_sub_settings", "بروزرسانی تنظیمات سابسکریپشن پنل")
    return web.json_response({"ok": True, "message": "تنظیمات ساب در پنل ذخیره شد.", "settings": res})


async def post_admin_panel_external_squad_users(request: web.Request) -> web.Response:
    """Bulk assign or remove panel users on an external squad."""
    admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    body = await _parse_json(request)
    squad_uuid = str(body.get("squad_uuid") or "").strip()
    action = str(body.get("action") or "add").strip().lower()
    raw_users = body.get("user_uuids") or []
    user_uuids = [str(u).strip() for u in raw_users if str(u).strip()] if isinstance(raw_users, list) else []

    ok, msg = await remnawave.external_squad_users_action(squad_uuid, user_uuids, action=action)
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=400 if "نامعتبر" in msg else 502)

    await _audit_and_refresh(request, admin["id"], f"external_squad_{action}", f"{action} برای {len(user_uuids)} کاربر")
    return web.json_response({"ok": True, "message": msg})


# --- 6. Full Infra Billing Providers & Node Linkage ---
async def post_admin_infra_provider_save(request: web.Request) -> web.Response:
    """Create or update a Remnawave infra billing provider."""
    admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    body = await _parse_json(request)
    prov_uuid = str(body.get("uuid") or "").strip()
    name = str(body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "نام ارائه‌دهنده الزامی است."}, status=400)
    login_url = str(body.get("login_url") or "").strip() or None
    favicon_link = str(body.get("favicon_link") or "").strip() or None

    if prov_uuid:
        ok, res = await remnawave.update_infra_provider(
            prov_uuid, name=name, login_url=login_url, favicon_link=favicon_link
        )
    else:
        ok, res = await remnawave.create_infra_provider(name, login_url=login_url, favicon_link=favicon_link)
    if not ok:
        return web.json_response({"ok": False, "error": str(res)}, status=502)

    await _audit_and_refresh(request, admin["id"], "save_infra_provider", f"ارائه‌دهنده {name}")
    return web.json_response({"ok": True, "message": f"ارائه‌دهنده «{name}» ذخیره شد.", "provider": res})


async def post_admin_infra_provider_delete(request: web.Request) -> web.Response:
    """Delete a Remnawave infra billing provider."""
    admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    body = await _parse_json(request)
    prov_uuid = str(body.get("uuid") or "").strip()
    if not prov_uuid:
        return web.json_response({"ok": False, "error": "شناسه ارائه‌دهنده الزامی است."}, status=400)

    ok, res = await remnawave.delete_infra_provider(prov_uuid)
    if not ok:
        return web.json_response({"ok": False, "error": str(res)}, status=502)

    await _audit_and_refresh(request, admin["id"], "delete_infra_provider", f"حذف ارائه‌دهنده {prov_uuid}")
    return web.json_response({"ok": True, "message": "ارائه‌دهنده حذف شد."})


async def post_admin_infra_node_sync(request: web.Request) -> web.Response:
    """Sync node provider and next billing date into Remnawave /api/infra-billing/nodes."""
    admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    body = await _parse_json(request)
    node_uuid = str(body.get("node_uuid") or "").strip()
    provider_uuid = str(body.get("provider_uuid") or "").strip()
    due_date = str(body.get("due_date") or "").strip()
    if not node_uuid or not provider_uuid:
        return web.json_response({"ok": False, "error": "انتخاب نود و ارائه‌دهنده الزامی است."}, status=400)

    next_billing_at = None
    if due_date:
        try:
            dt = datetime.strptime(due_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            next_billing_at = dt.isoformat().replace("+00:00", "Z")
        except ValueError:
            return web.json_response({"ok": False, "error": "فرمت تاریخ سررسید نامعتبر است."}, status=400)

    ok, res = await remnawave.sync_infra_billing_node(
        provider_uuid, node_uuid, next_billing_at=next_billing_at
    )
    if not ok:
        return web.json_response({"ok": False, "error": str(res)}, status=502)

    await _audit_and_refresh(request, admin["id"], "sync_infra_node", f"سینک بیلینگ نود {node_uuid}")
    return web.json_response({"ok": True, "message": "اطلاعات بیلینگ نود با پنل همگام شد.", "data": res})


# --- 7. API Tokens ---
async def post_admin_panel_token_create(request: web.Request) -> web.Response:
    """Create a panel API token (if Admin JWT is configured)."""
    admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    body = await _parse_json(request)
    token_name = str(body.get("token_name") or "").strip()
    if not token_name:
        return web.json_response({"ok": False, "error": "نام توکن الزامی است."}, status=400)

    ok, res = await remnawave.create_api_token(token_name)
    if not ok:
        return web.json_response({"ok": False, "error": str(res)}, status=502)

    await _audit_and_refresh(request, admin["id"], "create_api_token", f"ساخت توکن {token_name}")
    return web.json_response({"ok": True, "message": "توکن API ایجاد شد.", "token": res})


async def post_admin_panel_token_delete(request: web.Request) -> web.Response:
    """Delete/revoke a panel API token."""
    admin, remnawave, err = _require_admin_remnawave(request)
    if err:
        return err

    body = await _parse_json(request)
    token_uuid = str(body.get("uuid") or "").strip()
    if not token_uuid:
        return web.json_response({"ok": False, "error": "شناسه توکن الزامی است."}, status=400)

    ok, res = await remnawave.delete_api_token(token_uuid)
    if not ok:
        return web.json_response({"ok": False, "error": str(res)}, status=502)

    await _audit_and_refresh(request, admin["id"], "delete_api_token", f"حذف توکن {token_uuid}")
    return web.json_response({"ok": True, "message": "توکن با موفقیت حذف شد."})
