"""TMA User Nodes, IP telemetry, Settings, and Avatar endpoints."""
import logging
from aiohttp import web

from bot.db.repositories.user_repo import UserRepository
from bot.web.auth import get_authenticated_user
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def get_user_nodes(request: web.Request) -> web.Response:
    """Return active cluster nodes for the network ping/health checker."""
    remnawave = request.app["remnawave"]
    cache: FastCache = request.app["cache"]
    cache_key = "tma:public:nodes"

    cached_nodes = await cache.get(cache_key)
    if cached_nodes:
        return web.json_response({"ok": True, "nodes": cached_nodes})

    nodes = await remnawave.get_nodes() or []
    cleaned_nodes = []
    for node in nodes:
        cleaned_nodes.append({
            "name": node.get("name", "Server"),
            "country_code": node.get("country_code", "EU"),
            "address": node.get("address", ""),
            "status": node.get("status", "ONLINE"),
        })

    await cache.set(cache_key, cleaned_nodes, ttl_seconds=30)
    return web.json_response({"ok": True, "nodes": cleaned_nodes})


async def get_user_ip_info(request: web.Request) -> web.Response:
    """Return the client's public IP detected by Nginx/proxy."""
    client_ip = (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote
        or "127.0.0.1"
    )
    return web.json_response({
        "ok": True,
        "ip": client_ip,
        "is_safe": not client_ip.startswith(("10.", "192.168.", "172.16.")),
    })


async def post_user_settings(request: web.Request) -> web.Response:
    """Save user settings (language, etc.)."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    telegram_id = int(user_auth["id"])
    language = body.get("language")
    key = body.get("key")
    value = body.get("value")

    session_factory = request.app["session_factory"]
    cache: FastCache = request.app["cache"]

    from bot.db.repositories.report_repo import ReportRepository
    from bot.db.repositories.alert_repo import AlertRepository

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create(telegram_id, user_auth.get("username"))
        if language in ("fa", "en"):
            user.language = language

        rep_repo = ReportRepository(session)
        rep_settings = await rep_repo.get_settings(telegram_id)
        alert_repo = AlertRepository(session)
        alert_settings = await alert_repo.get_settings(telegram_id)

        # 1. Direct fields in JSON body
        if "nightly" in body:
            rep_settings.nightly = bool(body["nightly"])
        if "weekly" in body:
            rep_settings.weekly = bool(body["weekly"])
        if "monthly" in body:
            rep_settings.monthly = bool(body["monthly"])
        if "clean_reports" in body:
            rep_settings.clean_reports = bool(body["clean_reports"])
        if "wheel_notify" in body:
            rep_settings.wheel_notify = bool(body["wheel_notify"])
        if "traffic_percent" in body:
            try:
                alert_settings.traffic_percent = max(0, min(99, int(body["traffic_percent"])))
            except (ValueError, TypeError):
                pass
        elif "low_traffic" in body:
            alert_settings.traffic_percent = 80 if body["low_traffic"] else 0

        if "expire_days" in body:
            try:
                alert_settings.expire_days = max(0, min(30, int(body["expire_days"])))
            except (ValueError, TypeError):
                pass
        elif "expire_warning" in body:
            alert_settings.expire_days = 3 if body["expire_warning"] else 0

        # 2. Key-value pair style {key: "...", value: ...}
        if key == "nightly":
            rep_settings.nightly = bool(value)
        elif key == "weekly":
            rep_settings.weekly = bool(value)
        elif key == "monthly":
            rep_settings.monthly = bool(value)
        elif key == "clean_reports":
            rep_settings.clean_reports = bool(value)
        elif key == "wheel_notify":
            rep_settings.wheel_notify = bool(value)
        elif key == "low_traffic":
            alert_settings.traffic_percent = 80 if value else 0
        elif key == "expire_warning":
            alert_settings.expire_days = 3 if value else 0
        elif key == "traffic_percent":
            try:
                alert_settings.traffic_percent = max(0, min(99, int(value)))
            except (ValueError, TypeError):
                pass
        elif key == "expire_days":
            try:
                alert_settings.expire_days = max(0, min(30, int(value)))
            except (ValueError, TypeError):
                pass

        await session.commit()
        await cache.delete(f"tma:user:{telegram_id}:dashboard")

        return web.json_response({
            "ok": True,
            "language": user.language,
            "settings": {
                "nightly": bool(rep_settings.nightly),
                "weekly": bool(rep_settings.weekly),
                "monthly": bool(rep_settings.monthly),
                "clean_reports": bool(rep_settings.clean_reports),
                "wheel_notify": bool(rep_settings.wheel_notify),
                "low_traffic": bool(alert_settings.traffic_percent > 0),
                "expire_warning": bool(alert_settings.expire_days > 0),
                "traffic_percent": alert_settings.traffic_percent if alert_settings.traffic_percent > 0 else 80,
                "expire_days": alert_settings.expire_days if alert_settings.expire_days > 0 else 3,
            },
        })


async def get_user_avatar(request: web.Request) -> web.Response:
    """Fetch user Telegram avatar and stream image bytes with caching."""
    target_id_param = request.query.get("user_id")
    telegram_id = None
    if target_id_param:
        try:
            telegram_id = int(target_id_param)
        except ValueError:
            pass

    if not telegram_id:
        user_auth = get_authenticated_user(request)
        if user_auth:
            telegram_id = int(user_auth["id"])

    if not telegram_id:
        return web.Response(status=404)

    cache = request.app.get("cache")
    cache_key = f"tma:avatar:{telegram_id}"
    if cache:
        cached_bytes = await cache.get(cache_key)
        if cached_bytes and isinstance(cached_bytes, (bytes, bytearray)):
            return web.Response(
                body=cached_bytes,
                content_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=86400"},
            )

    bot = request.app.get("bot")
    if not bot:
        return web.Response(status=404)

    try:
        photos = await bot.get_user_profile_photos(telegram_id, limit=1)
        if photos.total_count > 0 and photos.photos:
            file_id = photos.photos[0][0].file_id
            tg_file = await bot.get_file(file_id)
            if tg_file and tg_file.file_path:
                import io
                stream = io.BytesIO()
                await bot.download_file(tg_file.file_path, destination=stream)
                img_bytes = stream.getvalue()
                if img_bytes:
                    if cache:
                        await cache.set(cache_key, img_bytes, ttl_seconds=86400)
                    return web.Response(
                        body=img_bytes,
                        content_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"},
                    )
    except Exception as exc:
        logger.debug("Failed to fetch avatar for %s: %s", telegram_id, exc)

    return web.Response(status=404)
