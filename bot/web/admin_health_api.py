"""Admin System Health & Reconciliation Dashboard API handlers."""
import logging

from aiohttp import web

from bot.services.reconcile import run_reconcile
from bot.services.system_health import collect_system_health
from bot.web.admin_common import _check_admin, db_session

logger = logging.getLogger(__name__)


async def get_admin_system_health(request: web.Request) -> web.Response:
    """Return cluster health, latencies, backup state, watchers, and reconciliation mismatches."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    force_refresh = request.query.get("refresh") in ("1", "true")
    remnawave = request.app.get("remnawave")
    cache = request.app.get("cache")
    settings = request.app.get("settings")

    async with db_session(request) as session:
        health = await collect_system_health(
            session,
            remnawave,
            cache=cache,
            settings=settings,
            force_refresh=force_refresh,
        )
    return web.json_response({"ok": True, "health": health})


async def post_admin_reconcile_run(request: web.Request) -> web.Response:
    """Trigger immediate reconciliation sweep from the Admin Health Dashboard."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    bot = request.app.get("bot")
    session_factory = request.app.get("session_factory")
    remnawave = request.app.get("remnawave")
    if not session_factory:
        return web.json_response({"ok": False, "error": "Database unavailable"}, status=503)

    closed_count = await run_reconcile(bot, session_factory, remnawave=remnawave)
    return web.json_response({
        "ok": True,
        "closed_count": closed_count,
        "message": f"بررسی و آشتی خودکار انجام شد ({closed_count} مورد معلق اصلاح گردید).",
    })
