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
        if "low_traffic" in body:
            alert_settings.traffic_percent = 80 if body["low_traffic"] else 0
        if "expire_warning" in body:
            alert_settings.expire_days = 3 if body["expire_warning"] else 0

        # 2. Key-value pair style {key: "...", value: ...}
        if key == "nightly":
            rep_settings.nightly = bool(value)
        elif key == "weekly":
            rep_settings.weekly = bool(value)
        elif key == "monthly":
            rep_settings.monthly = bool(value)
        elif key == "low_traffic":
            alert_settings.traffic_percent = 80 if value else 0
        elif key == "expire_warning":
            alert_settings.expire_days = 3 if value else 0

        await session.commit()
        await cache.delete(f"tma:user:{telegram_id}:dashboard")

        return web.json_response({
            "ok": True,
            "language": user.language,
            "settings": {
                "nightly": bool(rep_settings.nightly),
                "weekly": bool(rep_settings.weekly),
                "monthly": bool(rep_settings.monthly),
                "low_traffic": bool(alert_settings.traffic_percent > 0),
                "expire_warning": bool(alert_settings.expire_days > 0),
            },
        })


async def get_user_avatar(request: web.Request) -> web.Response:
    """Fetch user Telegram avatar or redirect to it."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.Response(status=401)

    telegram_id = int(user_auth["id"])
    bot = request.app.get("bot")
    if not bot:
        return web.Response(status=404)

    try:
        photos = await bot.get_user_profile_photos(telegram_id, limit=1)
        if photos.total_count > 0 and photos.photos:
            file_id = photos.photos[0][0].file_id
            tg_file = await bot.get_file(file_id)
            if tg_file and tg_file.file_path:
                file_url = f"https://api.telegram.org/file/bot{bot.token}/{tg_file.file_path}"
                raise web.HTTPFound(location=file_url)
    except web.HTTPFound:
        raise
    except Exception as exc:
        logger.debug("Failed to fetch avatar for %s: %s", telegram_id, exc)

    return web.Response(status=404)
