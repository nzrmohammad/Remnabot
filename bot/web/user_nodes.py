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

    session_factory = request.app["session_factory"]
    cache: FastCache = request.app["cache"]

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create(telegram_id, user_auth.get("username"))
        if language in ("fa", "en"):
            user.language = language
            await session.commit()
            await cache.delete(f"tma:user:{telegram_id}:dashboard")

        return web.json_response({"ok": True, "language": user.language})


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
