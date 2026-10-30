"""Admin Users Detail, Sessions, SRH, and HWID Device Management."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import web

from bot.web.admin_common import _check_admin

try:
    import jdatetime
except ImportError:
    jdatetime = None

logger = logging.getLogger(__name__)


def _parse_client_app(ua: str) -> dict[str, str]:
    """Identify VPN client name, icon, and OS tag from user-agent string."""
    ua_str = (ua or "").strip()
    ua_lower = ua_str.lower()

    # Determine underlying OS first
    os_name = "دستگاه"
    os_icon = "📱"
    if "windows" in ua_lower or "win64" in ua_lower or "win32" in ua_lower or "wow64" in ua_lower:
        os_name = "ویندوز"
        os_icon = "🪟"
    elif "android" in ua_lower:
        os_name = "اندروید"
        os_icon = "🤖"
    elif "iphone" in ua_lower or "ipad" in ua_lower or "ios" in ua_lower or "cfnetwork" in ua_lower:
        os_name = "iOS"
        os_icon = "🍏"
    elif "macintosh" in ua_lower or "mac os" in ua_lower or "darwin" in ua_lower:
        os_name = "macOS"
        os_icon = "🍎"
    elif "linux" in ua_lower:
        os_name = "لینوکس"
        os_icon = "🐧"

    # Specific client applications
    if "incy" in ua_lower:
        return {"name": f"Incy ({os_name})", "icon": os_icon, "tag": os_name}
    if "v2rayng" in ua_lower:
        return {"name": "v2rayNG", "icon": "🤖", "tag": "اندروید"}
    if "v2rayn" in ua_lower:
        return {"name": "v2rayN", "icon": "🪟", "tag": "ویندوز"}
    if "streisand" in ua_lower:
        return {"name": "Streisand", "icon": "🛡️", "tag": "iOS"}
    if "sing-box" in ua_lower or "singbox" in ua_lower:
        return {"name": "Sing-box", "icon": "📦", "tag": os_name if os_name != "دستگاه" else "Multi"}
    if "happ" in ua_lower:
        return {"name": "Happ Proxy", "icon": "⚡", "tag": os_name if os_name != "دستگاه" else "iOS / Android"}
    if "nekoray" in ua_lower:
        return {"name": "NekoRay", "icon": "🐱", "tag": os_name if os_name != "دستگاه" else "ویندوز"}
    if "nekobox" in ua_lower:
        return {"name": "NekoBox", "icon": "🐱", "tag": os_name if os_name != "دستگاه" else "اندروید"}
    if "clash" in ua_lower or "meta" in ua_lower or "mihomo" in ua_lower:
        return {"name": "Clash Meta", "icon": "🐱", "tag": os_name if os_name != "دستگاه" else "Multi"}
    if "shadowrocket" in ua_lower:
        return {"name": "Shadowrocket", "icon": "🚀", "tag": "iOS"}
    if "v2box" in ua_lower:
        return {"name": "V2Box", "icon": "📦", "tag": "iOS / Mac"}
    if "foxray" in ua_lower:
        return {"name": "FoXray", "icon": "🦊", "tag": "iOS"}
    if "karing" in ua_lower:
        return {"name": "Karing", "icon": "🚗", "tag": os_name if os_name != "دستگاه" else "Multi"}
    if "hiddify" in ua_lower:
        return {"name": "Hiddify", "icon": "✨", "tag": os_name if os_name != "دستگاه" else "Multi"}
    if "curl" in ua_lower or "wget" in ua_lower or "python" in ua_lower:
        return {"name": "Script / Bot", "icon": "🤖", "tag": "Bot"}

    # Fallback: if OS was recognized, present it gracefully instead of generic "Client"
    if os_name != "دستگاه":
        clean_ua = ua_str.split("/")[0] if "/" in ua_str else ua_str[:20]
        display_name = f"{clean_ua} ({os_name})" if clean_ua and len(clean_ua) <= 15 else os_name
        return {"name": display_name, "icon": os_icon, "tag": os_name}

    return {"name": ua_str[:25] if ua_str else "دستگاه متصل", "icon": "🌐", "tag": "دستگاه"}


def _parse_srh_timestamp(created_at_raw: Any, now_utc: datetime) -> tuple[str, str, str]:
    """Parse raw timestamp into relative time, formatted date, and time strings."""
    if not created_at_raw:
        return "—", "—", "—"
    try:
        if isinstance(created_at_raw, str) and created_at_raw.strip().isdigit():
            created_at_raw = int(created_at_raw.strip())

        if isinstance(created_at_raw, (int, float)):
            divisor = 1000 if created_at_raw > 1e11 else 1
            parsed_dt = datetime.fromtimestamp(created_at_raw / divisor, tz=timezone.utc)
        else:
            s = str(created_at_raw).strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            if "." in s:
                parts = s.split(".")
                tail = parts[1]
                tz_part = ""
                if "+" in tail:
                    tail_sub, tz_part = tail.split("+", 1)
                    tz_part = "+" + tz_part
                elif "-" in tail:
                    tail_sub, tz_part = tail.split("-", 1)
                    tz_part = "-" + tz_part
                else:
                    tail_sub = tail
                s = f"{parts[0]}.{tail_sub[:6]}{tz_part}"
            parsed_dt = datetime.fromisoformat(s)
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)

        parsed_utc = parsed_dt.astimezone(timezone.utc)
        total_sec = (now_utc - parsed_utc).total_seconds()
        if -15000 <= total_sec <= -60:
            parsed_utc = parsed_utc - timedelta(hours=3, minutes=30)
            total_sec = (now_utc - parsed_utc).total_seconds()

        diff_sec = max(0, int(total_sec))
        if diff_sec < 60:
            rel_time = "لحظاتی پیش"
        elif diff_sec < 3600:
            rel_time = f"{diff_sec // 60} دقیقه پیش"
        elif diff_sec < 86400:
            rel_time = f"{diff_sec // 3600} ساعت پیش"
        else:
            rel_time = f"{diff_sec // 86400} روز پیش"

        tehran_tz = ZoneInfo("Asia/Tehran")
        dt_tehran = parsed_utc.astimezone(tehran_tz)
        time_str = dt_tehran.strftime("%H:%M")

        if jdatetime:
            try:
                p_j = jdatetime.datetime.fromgregorian(datetime=dt_tehran)
                date_str = f"{p_j.year}/{p_j.month:02d}/{p_j.day:02d} {p_j.hour:02d}:{p_j.minute:02d}"
                time_str = f"{p_j.hour:02d}:{p_j.minute:02d}"
            except Exception:
                date_str = dt_tehran.strftime("%Y/%m/%d %H:%M")
        else:
            date_str = dt_tehran.strftime("%Y/%m/%d %H:%M")

        return rel_time, date_str, time_str
    except Exception:
        return "ثبت‌شده", str(created_at_raw)[:19], "—"


async def _resolve_panel_user(remnawave, target_id: Any) -> tuple[Any, str | None]:
    """Resolve target_id (Telegram ID, Remnawave user ID, or username) to (primary_id, primary_uuid)."""
    target_str = str(target_id).strip()
    panel_users = None
    if target_str.isdigit():
        try:
            panel_users = await remnawave.get_users_by_telegram_id(int(target_str))
        except Exception:
            panel_users = None

    if not panel_users:
        try:
            p_user = await remnawave.get_panel_user_by_id(int(target_str) if target_str.isdigit() else target_str)
            if p_user:
                panel_users = [p_user]
        except Exception:
            pass

    if not panel_users:
        try:
            p_user = await remnawave.get_user_by_username(target_str)
            if p_user:
                panel_users = [p_user]
        except Exception:
            pass

    if panel_users and len(panel_users) > 0:
        return panel_users[0].get("id"), panel_users[0].get("uuid")
    return target_str, target_str

async def get_admin_user_hwid_devices(request: web.Request) -> web.Response:
    """Fetch all active connected HWID devices for a specific user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    target_id = request.query.get("telegram_id")
    if not target_id:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    primary_id, primary_uuid = await _resolve_panel_user(remnawave, target_id)
    devices = await remnawave.get_user_hwid_devices(primary_id, user_uuid=primary_uuid)
    return web.json_response({"ok": True, "devices": devices or []})


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
        return web.json_response({"ok": False, "error": "شناسه کاربر و شناسه سخت‌افزار (HWID) الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    primary_id, _ = await _resolve_panel_user(remnawave, target_id)
    success = await remnawave.delete_hwid_device(primary_id, hwid)
    if not success:
        return web.json_response({"ok": False, "error": "خطا در حذف دستگاه از پنل."}, status=502)

    return web.json_response({"ok": True, "message": "دستگاه با موفقیت قطع اتصال و حذف شد."})


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
        primary_id, _ = await _resolve_panel_user(remnawave, target_id)
        user_sessions = await remnawave.get_user_live_sessions(primary_id)
        return web.json_response({"ok": True, "data": user_sessions})
    except Exception as exc:
        logger.warning("Error fetching user live sessions: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def get_admin_sessions_explorer(request: web.Request) -> web.Response:
    """Scan and fetch real-time active connections across all nodes."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    remnawave = request.app["remnawave"]
    try:
        data = await remnawave.get_live_sessions_explorer()
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


async def get_admin_user_srh(request: web.Request) -> web.Response:
    """Fetch Subscription Request History (SRH) for a specific user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    target_id = request.query.get("telegram_id")
    panel_user_id = request.query.get("user_id") or request.query.get("panel_user_id")
    panel_user_uuid = request.query.get("uuid")
    remnawave = request.app["remnawave"]

    if target_id and (not panel_user_id or not panel_user_uuid):
        try:
            resolved_id, resolved_uuid = await _resolve_panel_user(remnawave, target_id)
            panel_user_id = panel_user_id or resolved_id
            panel_user_uuid = panel_user_uuid or resolved_uuid
        except Exception as resolve_exc:
            logger.warning("Failed to resolve user for SRH: %s", resolve_exc)

    if not panel_user_id and not panel_user_uuid and target_id:
        panel_user_id = target_id

    if not panel_user_id and not panel_user_uuid:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    raw_records = await remnawave.get_user_srh(panel_user_id or panel_user_uuid, user_uuid=panel_user_uuid, size=50)
    formatted = []
    now_utc = datetime.now(timezone.utc)
    for r in raw_records:
        ip = r.get("ip") or r.get("clientIp") or r.get("requestIp") or "—"
        ua = r.get("userAgent") or r.get("user_agent") or r.get("clientApp") or ""
        status_code = r.get("responseStatus") or r.get("status") or r.get("statusCode") or 200
        rule_name = r.get("srrRuleName") or r.get("ruleName") or ""
        client_info = _parse_client_app(ua)
        if rule_name and client_info["name"] == "کلاینت ناشناس":
            client_info["name"] = rule_name

        created_at_raw = None
        for k in ("requestDate", "requestedAt", "request_date", "requested_at", "createdAt", "created_at", "timestamp", "lastActivity"):
            if r.get(k):
                created_at_raw = r[k]
                break

        rel_time, date_str, time_str = _parse_srh_timestamp(created_at_raw, now_utc)
        formatted.append({
            "ip": ip,
            "user_agent": ua,
            "client_name": client_info["name"],
            "client_icon": client_info["icon"],
            "client_tag": client_info["tag"],
            "status_code": status_code,
            "is_success": str(status_code) in ("200", "201", "304", "OK"),
            "relative_time": rel_time,
            "date_str": date_str,
            "time_str": time_str,
        })

    return web.json_response({"ok": True, "data": formatted, "count": len(formatted)})
