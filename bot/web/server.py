"""High-performance aiohttp web server for Telegram Mini App (TMA).

Integrates seamlessly into the same asyncio event loop as aiogram.
"""
import html
import json
import logging
import time
from collections import defaultdict, deque
from pathlib import Path

from aiohttp import web

from bot.web.cache import FastCache
from bot.web.routes_admin import (
    get_admin_broadcast_status,
    get_admin_coupon_usages,
    get_admin_coupons,
    get_admin_crypto_rates,
    get_admin_infra_billing,
    get_admin_overview,
    get_admin_plans,
    get_admin_settings,
    get_admin_ticket_messages,
    get_admin_ticket_threads,
    get_admin_topup_photo,
    get_admin_topups,
    get_admin_sessions_explorer,
    get_admin_user_hwid_devices,
    get_admin_user_sessions,
    get_admin_user_srh,
    get_admin_users,
    post_admin_users_bulk_action,
    post_admin_broadcast,
    post_admin_coupon_delete,
    post_admin_coupon_save,
    post_admin_coupon_toggle,
    post_admin_kill_sessions,
    post_admin_modify_user,
    post_admin_node_cost,
    post_admin_plan_delete,
    post_admin_plan_save,
    post_admin_plan_toggle,
    post_admin_reply_ticket,
    post_admin_reset_trial,
    post_admin_settings,
    post_admin_toggle_ban,
    post_admin_topup_action,
    post_admin_user_delete_hwid,
    post_admin_user_revoke_sub,
    post_admin_user_wallet,
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
    get_user_support_messages,
    post_user_support_message,
    get_user_subscription_configs,
)

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


_API_WINDOW = 60.0
_API_MAX_GENERAL = 120  # 120 requests/min per IP
_API_MAX_SENSITIVE = 20 # 20 requests/min on sensitive financial/coupon endpoints
_api_buckets: dict[str, deque[float]] = defaultdict(deque)


@web.middleware
async def api_rate_limit_middleware(request: web.Request, handler):
    # Only rate-limit public /api/user/ endpoints; administrative endpoints are completely exempt
    if not request.path.startswith("/api/user/"):
        return await handler(request)

    if request.app.get("is_dev", False) or request.method == "OPTIONS":
        return await handler(request)

    client_ip = (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote
        or "127.0.0.1"
    )

    sensitive_paths = {
        "/api/user/validate_coupon",
        "/api/user/purchase",
        "/api/user/spin",
        "/api/user/topup/card",
        "/api/user/topup/crypto",
        "/api/user/topup/crypto/check",
    }
    is_sensitive = request.path in sensitive_paths and request.method == "POST"
    max_reqs = _API_MAX_SENSITIVE if is_sensitive else _API_MAX_GENERAL

    now = time.monotonic()
    bucket_key = f"{client_ip}:sens" if is_sensitive else f"{client_ip}:gen"
    bucket = _api_buckets[bucket_key]

    while bucket and now - bucket[0] > _API_WINDOW:
        bucket.popleft()

    if len(bucket) >= max_reqs:
        logger.warning("API rate limit exceeded for IP %s on %s", client_ip, request.path)
        return web.json_response(
            {"ok": False, "error": "درخواست‌های بیش از حد مجاز. لطفاً کمی صبر کنید.", "code": "rate_limited"},
            status=429,
            headers={"Retry-After": "30"},
        )

    bucket.append(now)

    if len(_api_buckets) > 5000:
        stale = [k for k, b in _api_buckets.items() if not b or now - b[-1] > _API_WINDOW]
        for k in stale:
            del _api_buckets[k]

    return await handler(request)


@web.middleware
async def cors_and_security_middleware(request: web.Request, handler):
    """Add CORS and frame-security headers to enable Telegram Mini App embed."""
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        response = await handler(request)

    settings = request.app.get("settings")
    trusted_origins = {"https://web.telegram.org", "https://telegram.org"}
    if settings and getattr(settings, "WEB_APP_URL", ""):
        from urllib.parse import urlparse
        parsed = urlparse(settings.WEB_APP_URL)
        if parsed.scheme and parsed.netloc:
            trusted_origins.add(f"{parsed.scheme}://{parsed.netloc}")

    request_origin = request.headers.get("Origin", "")
    if request_origin in trusted_origins or request.app.get("is_dev", False):
        response.headers["Access-Control-Allow-Origin"] = request_origin or "*"
    elif any(request_origin.endswith(domain) for domain in [".telegram.org", "telegram.org"]):
        response.headers["Access-Control-Allow-Origin"] = request_origin

    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Telegram-Init-Data, X-Dev-Mode"
    )
    # Telegram Mini Apps run inside iframe in web.telegram.org
    response.headers["X-Frame-Options"] = "ALLOWALL"

    # Long-term caching for static assets (/static/...)
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=604800, stale-while-revalidate=86400"

    # Enable automatic gzip/deflate compression for responses > 512 bytes
    if isinstance(response, web.Response) and response.body and len(response.body) > 512:
        accept_enc = request.headers.get("Accept-Encoding", "")
        if "gzip" in accept_enc or "deflate" in accept_enc:
            response.enable_compression()

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


async def serve_open_client(request: web.Request) -> web.Response:
    """Serve a bridge page to launch external VPN clients from Telegram Mini App."""
    scheme = request.query.get("scheme", "").strip()
    name = request.query.get("name", "نرم‌افزار").strip()
    sub_url = request.query.get("url", "").strip()

    safe_schemes = ("v2rayng://", "hiddify://", "happ://", "incy://", "streisand://", "v2box://", "sing-box://")
    if not any(scheme.lower().startswith(s) for s in safe_schemes):
        return web.Response(text="طرح‌واره نامعتبر است.", status=400)

    html_content = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>اتصال به {html.escape(name)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Vazirmatn", sans-serif;
      background: #0f172a;
      color: #f8fafc;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      padding: 1rem;
      box-sizing: border-box;
      text-align: center;
    }}
    .card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 1.5rem;
      padding: 2rem 1.5rem;
      max-width: 400px;
      width: 100%;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
    }}
    .btn {{
      display: block;
      width: 100%;
      padding: 0.75rem 1rem;
      margin-top: 0.75rem;
      border-radius: 0.75rem;
      font-weight: bold;
      font-size: 0.875rem;
      text-decoration: none;
      cursor: pointer;
      box-sizing: border-box;
      transition: all 0.2s;
    }}
    .btn-primary {{
      background: #0284c7;
      color: #ffffff;
      border: none;
    }}
    .btn-primary:hover {{
      background: #0369a1;
    }}
    .btn-secondary {{
      background: transparent;
      border: 1px solid #475569;
      color: #94a3b8;
    }}
    .btn-secondary:hover {{
      background: #334155;
      color: #ffffff;
    }}
    .hint {{
      font-size: 0.75rem;
      color: #94a3b8;
      margin-top: 1rem;
      line-height: 1.6;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🚀</div>
    <h2 style="font-size: 1.125rem; margin-bottom: 0.5rem;">در حال انتقال به {html.escape(name)}...</h2>
    <p style="font-size: 0.8125rem; color: #cbd5e1; margin-bottom: 1.25rem;">
      در صورت باز نشدن خودکار برنامه، دکمه زیر را لمس نمایید یا از گزینه کپی لینک استفاده کنید.
    </p>
    <a href="{html.escape(scheme)}" class="btn btn-primary" id="launchBtn">باز کردن برنامه {html.escape(name)}</a>
    <button type="button" class="btn btn-secondary" id="copyBtn">📋 کپی لینک اشتراک</button>
    <p class="hint">
      اگر برنامه روی دستگاه شما نصب نیست، ابتدا آن را نصب کرده و سپس اشتراک را ایمپورت کنید.
    </p>
  </div>
  <script>
    const scheme = {json.dumps(scheme)};
    const subUrl = {json.dumps(sub_url)};
    try {{
      window.location.href = scheme;
    }} catch(e) {{}}
    document.getElementById('copyBtn').addEventListener('click', () => {{
      if (navigator.clipboard && subUrl) {{
        navigator.clipboard.writeText(subUrl).then(() => alert('لینک اشتراک با موفقیت کپی شد.'));
      }}
    }});
  </script>
</body>
</html>"""
    return web.Response(text=html_content, content_type="text/html", charset="utf-8")


@web.middleware
async def global_error_middleware(request: web.Request, handler):
    """Catch unhandled exceptions in TMA web routes and log them with context."""
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled TMA web error on %s %s: %s", request.method, request.path, exc)
        return web.json_response(
            {"ok": False, "error": "خطای داخلی سرور رخ داد.", "code": "internal_error"},
            status=500,
        )


def create_web_app(
    bot,
    session_factory,
    remnawave,
    settings,
    redis_client=None,
    is_dev: bool = False,
) -> web.Application:
    app = web.Application(
        middlewares=[cors_and_security_middleware, global_error_middleware, api_rate_limit_middleware],
        client_max_size=16 * 1024 * 1024,
    )

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
    app.router.add_get("/open-client", serve_open_client)

    # Static files
    if STATIC_DIR.exists():
        app.router.add_static("/static", str(STATIC_DIR), append_version=True)

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
    app.router.add_get("/api/user/support/messages", get_user_support_messages)
    app.router.add_post("/api/user/support/messages", post_user_support_message)
    app.router.add_get("/api/user/subscription/configs", get_user_subscription_configs)

    # Admin APIs
    app.router.add_get("/api/admin/overview", get_admin_overview)
    app.router.add_get("/api/admin/users", get_admin_users)
    app.router.add_post("/api/admin/user/modify", post_admin_modify_user)
    app.router.add_post("/api/admin/user/wallet", post_admin_user_wallet)
    app.router.add_post("/api/admin/user/revoke_sub", post_admin_user_revoke_sub)
    app.router.add_get("/api/admin/user/hwid_devices", get_admin_user_hwid_devices)
    app.router.add_get("/api/admin/user/sessions", get_admin_user_sessions)
    app.router.add_get("/api/admin/user/srh", get_admin_user_srh)
    app.router.add_get("/api/admin/sessions-explorer", get_admin_sessions_explorer)
    app.router.add_post("/api/admin/users/bulk-action", post_admin_users_bulk_action)
    app.router.add_post("/api/admin/user/delete_hwid", post_admin_user_delete_hwid)
    app.router.add_post("/api/admin/user/kill_sessions", post_admin_kill_sessions)
    app.router.add_post("/api/admin/user/toggle_ban", post_admin_toggle_ban)
    app.router.add_post("/api/admin/ticket/reply", post_admin_reply_ticket)
    app.router.add_get("/api/admin/tickets/threads", get_admin_ticket_threads)
    app.router.add_get("/api/admin/tickets/messages", get_admin_ticket_messages)
    app.router.add_post("/api/admin/broadcast", post_admin_broadcast)
    app.router.add_get("/api/admin/broadcast/status", get_admin_broadcast_status)
    app.router.add_post("/api/admin/user/reset_trial", post_admin_reset_trial)
    app.router.add_get("/api/admin/plans", get_admin_plans)
    app.router.add_post("/api/admin/plan/save", post_admin_plan_save)
    app.router.add_post("/api/admin/plan/toggle", post_admin_plan_toggle)
    app.router.add_post("/api/admin/plan/delete", post_admin_plan_delete)
    app.router.add_get("/api/admin/coupons", get_admin_coupons)
    app.router.add_get("/api/admin/coupons/{id}/usages", get_admin_coupon_usages)
    app.router.add_post("/api/admin/coupon/save", post_admin_coupon_save)
    app.router.add_post("/api/admin/coupon/toggle", post_admin_coupon_toggle)
    app.router.add_post("/api/admin/coupon/delete", post_admin_coupon_delete)
    app.router.add_get("/api/admin/topups", get_admin_topups)
    app.router.add_get("/api/admin/topup/photo", get_admin_topup_photo)
    app.router.add_post("/api/admin/topup/action", post_admin_topup_action)
    app.router.add_get("/api/admin/crypto/rates", get_admin_crypto_rates)
    app.router.add_get("/api/admin/settings", get_admin_settings)
    app.router.add_post("/api/admin/settings", post_admin_settings)
    app.router.add_get("/api/admin/infra/billing", get_admin_infra_billing)
    app.router.add_post("/api/admin/infra/node-cost", post_admin_node_cost)

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
