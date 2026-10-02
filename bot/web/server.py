"""High-performance aiohttp web server for Telegram Mini App (TMA).

Integrates seamlessly into the same asyncio event loop as aiogram.
"""
import logging
from pathlib import Path

from aiohttp import web

from bot.web.cache import FastCache
from bot.web.routes_admin import (
    get_admin_overview,
    get_admin_settings,
    get_admin_topups,
    get_admin_users,
    post_admin_broadcast,
    post_admin_kill_sessions,
    post_admin_modify_user,
    post_admin_reply_ticket,
    post_admin_settings,
    post_admin_toggle_ban,
    post_admin_topup_action,
)
from bot.web.routes_user import (
    get_user_avatar,
    get_user_ip_info,
    get_user_me,
    get_user_nodes,
    get_user_topup_info,
    post_user_kill_device,
    post_user_purchase,
    post_user_revoke_sub,
    post_user_settings,
    post_user_spin,
    post_user_topup_card,
    post_user_topup_crypto,
    post_user_topup_crypto_check,
    post_user_validate_coupon,
)

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


@web.middleware
async def cors_and_security_middleware(request: web.Request, handler):
    """Add CORS and frame-security headers to enable Telegram Mini App embed."""
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        response = await handler(request)

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Telegram-Init-Data, X-Dev-Mode"
    )
    # Telegram Mini Apps run inside iframe in web.telegram.org
    response.headers["X-Frame-Options"] = "ALLOWALL"
    return response


async def serve_app_html(request: web.Request) -> web.Response:
    """Serve the user Mini App HTML."""
    html_path = TEMPLATES_DIR / "app.html"
    if not html_path.exists():
        return web.Response(text="User WebApp template not found", status=404)
    return web.FileResponse(
        html_path,
        headers={"Cache-Control": "no-cache, must-revalidate", "Content-Type": "text/html; charset=utf-8"},
    )


async def serve_admin_html(request: web.Request) -> web.Response:
    """Serve the admin Mini App HTML."""
    html_path = TEMPLATES_DIR / "admin.html"
    if not html_path.exists():
        return web.Response(text="Admin WebApp template not found", status=404)
    return web.FileResponse(
        html_path,
        headers={"Cache-Control": "no-cache, must-revalidate", "Content-Type": "text/html; charset=utf-8"},
    )


async def health_check(request: web.Request) -> web.Response:
    """Lightweight health check endpoint."""
    return web.json_response({"status": "ok", "service": "remnabot-tma"})


def create_web_app(
    bot,
    session_factory,
    remnawave,
    settings,
    redis_client=None,
    is_dev: bool = False,
) -> web.Application:
    """Build and configure the aiohttp web application."""
    app = web.Application(middlewares=[cors_and_security_middleware])

    # Injected dependencies
    app["bot"] = bot
    app["session_factory"] = session_factory
    app["remnawave"] = remnawave
    app["settings"] = settings
    app["bot_token"] = settings.BOT_TOKEN
    app["admin_ids"] = settings.ADMIN_IDS
    app["is_dev"] = is_dev
    app["cache"] = FastCache(redis_client=redis_client)

    # UI routes
    app.router.add_get("/", serve_app_html)
    app.router.add_get("/app", serve_app_html)
    app.router.add_get("/admin", serve_admin_html)
    app.router.add_get("/health", health_check)

    # Static files
    if STATIC_DIR.exists():
        app.router.add_static("/static", str(STATIC_DIR))

    # User APIs
    app.router.add_get("/api/user/me", get_user_me)
    app.router.add_get("/api/user/avatar", get_user_avatar)
    app.router.add_get("/api/user/topup_info", get_user_topup_info)
    app.router.add_post("/api/user/topup/card", post_user_topup_card)
    app.router.add_post("/api/user/topup/crypto", post_user_topup_crypto)
    app.router.add_post("/api/user/topup/crypto/check", post_user_topup_crypto_check)
    app.router.add_post("/api/user/validate_coupon", post_user_validate_coupon)
    app.router.add_post("/api/user/purchase", post_user_purchase)
    app.router.add_post("/api/user/settings", post_user_settings)
    app.router.add_post("/api/user/spin", post_user_spin)
    app.router.add_post("/api/user/revoke_sub", post_user_revoke_sub)
    app.router.add_post("/api/user/kill_device", post_user_kill_device)
    app.router.add_get("/api/user/nodes", get_user_nodes)
    app.router.add_get("/api/user/ip_info", get_user_ip_info)

    # Admin APIs
    app.router.add_get("/api/admin/overview", get_admin_overview)
    app.router.add_get("/api/admin/users", get_admin_users)
    app.router.add_post("/api/admin/user/modify", post_admin_modify_user)
    app.router.add_post("/api/admin/user/kill_sessions", post_admin_kill_sessions)
    app.router.add_post("/api/admin/user/toggle_ban", post_admin_toggle_ban)
    app.router.add_post("/api/admin/ticket/reply", post_admin_reply_ticket)
    app.router.add_post("/api/admin/broadcast", post_admin_broadcast)
    app.router.add_get("/api/admin/topups", get_admin_topups)
    app.router.add_post("/api/admin/topup/action", post_admin_topup_action)
    app.router.add_get("/api/admin/settings", get_admin_settings)
    app.router.add_post("/api/admin/settings", post_admin_settings)

    return app


async def start_web_server(
    app: web.Application, host: str = "0.0.0.0", port: int = 8080
) -> web.AppRunner:
    """Start the aiohttp web server runner asynchronously."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("🚀 TMA Web Server started at http://%s:%d", host, port)
    return runner
