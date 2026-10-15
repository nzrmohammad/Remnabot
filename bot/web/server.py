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

from bot.web import routes_admin, routes_user
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


_API_WINDOW = 60.0
_API_MAX_GENERAL = 120  # 120 requests/min per IP
_API_MAX_SENSITIVE = 20 # 20 requests/min on sensitive financial/coupon endpoints
_api_buckets: dict[str, deque[float]] = defaultdict(deque)

DEFAULT_TRUSTED_ORIGINS = frozenset({"https://web.telegram.org", "https://telegram.org"})


@web.middleware
async def api_rate_limit_middleware(request: web.Request, handler):
    # Only rate-limit public /api/user/ endpoints; administrative endpoints are completely exempt
    if not request.path.startswith("/api/user/"):
        return await handler(request)

    if request.app.get("is_dev", False) or request.method == "OPTIONS":
        return await handler(request)

    from bot.web.auth import get_client_ip
    client_ip = get_client_ip(request)

    sensitive_paths = {
        "/api/user/validate_coupon",
        "/api/user/purchase",
        "/api/user/spin",
        "/api/user/topup/card",
        "/api/user/topup/crypto",
        "/api/user/topup/crypto/check",
        "/api/user/topup/stars",
    }
    is_sensitive = request.path in sensitive_paths and request.method == "POST"
    max_reqs = _API_MAX_SENSITIVE if is_sensitive else _API_MAX_GENERAL

    now = time.monotonic()
    cache = request.app.get("cache")
    redis = getattr(cache, "_redis", None) if cache else None

    # Distributed Redis rate-limiting if Redis is active
    if redis:
        try:
            rl_key = f"tma:rl:{client_ip}:{'sens' if is_sensitive else 'gen'}"
            pipe = redis.pipeline()
            pipe.incr(rl_key)
            pipe.expire(rl_key, int(_API_WINDOW))
            results = await pipe.execute()
            if results and int(results[0]) > max_reqs:
                logger.warning("Redis API rate limit exceeded for IP %s on %s", client_ip, request.path)
                return web.json_response(
                    {"ok": False, "error": "درخواست‌های بیش از حد مجاز. لطفاً کمی صبر کنید.", "code": "rate_limited"},
                    status=429,
                    headers={"Retry-After": "30"},
                )
            return await handler(request)
        except Exception as exc:
            logger.debug("Redis rate limit fallback to memory: %s", exc)

    # In-memory rate limiting fallback
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
    trusted_origins = set(DEFAULT_TRUSTED_ORIGINS)
    if settings and getattr(settings, "WEB_APP_URL", ""):
        from urllib.parse import urlparse
        parsed = urlparse(settings.WEB_APP_URL)
        if parsed.scheme and parsed.netloc:
            trusted_origins.add(f"{parsed.scheme}://{parsed.netloc}")

    request_origin = request.headers.get("Origin", "")
    if request_origin and (
        request_origin in trusted_origins
        or request.app.get("is_dev", False)
        or any(request_origin.endswith(domain) for domain in [".telegram.org", "telegram.org"])
    ):
        response.headers["Access-Control-Allow-Origin"] = request_origin

    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Telegram-Init-Data, X-Dev-Mode"
    )
    # Telegram Mini Apps run inside iframe in web.telegram.org
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org"
    )

    # Caching strategy for static assets (/static/...)
    if request.path.startswith("/static/"):
        if request.path.startswith("/static/js/") or request.path.startswith("/static/css/"):
            response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
        else:
            response.headers["Cache-Control"] = "public, max-age=604800, stale-while-revalidate=86400"
        if request.path.startswith("/static/fonts/"):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Content-Type"] = "font/woff2"

    # Enable automatic gzip/deflate compression for static files and API responses > 512 bytes (exclude speedtest payloads)
    if not request.path.startswith("/api/user/speedtest"):
        accept_enc = request.headers.get("Accept-Encoding", "")
        if "gzip" in accept_enc or "deflate" in accept_enc:
            if isinstance(response, web.FileResponse):
                response.enable_compression()
            elif isinstance(response, web.Response) and response.body and len(response.body) > 512:
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
    """Catch unhandled exceptions in TMA web routes and report them to the admin topic."""
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled TMA web error on %s %s: %s", request.method, request.path, exc)
        if request.path.startswith("/api/"):
            try:
                from bot.services.error_reporter import report_error
                bot = request.app.get("bot")
                session_factory = request.app.get("session_factory")
                if bot and session_factory:
                    user_id = None
                    if "user_auth" in request and isinstance(request["user_auth"], dict):
                        user_id = request["user_auth"].get("id")
                    elif "user_id" in request:
                        user_id = request["user_id"]
                    await report_error(
                        bot,
                        session_factory,
                        exc,
                        context=f"WEB {request.method} {request.path}",
                        user_id=user_id,
                    )
            except Exception as rep_err:
                logger.warning("Failed to dispatch web error to topic: %s", rep_err)
        return web.json_response(
            {"ok": False, "error": "خطای داخلی سرور رخ داد.", "code": "internal_error"},
            status=500,
        )


topic_error_middleware = global_error_middleware


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
    app.router.add_get("/api/user/me", routes_user.get_user_me)
    app.router.add_get("/api/user/avatar", routes_user.get_user_avatar)
    app.router.add_get("/api/user/topup_info", routes_user.get_user_topup_info)
    app.router.add_post("/api/user/topup/card", routes_user.post_user_topup_card)
    app.router.add_post("/api/user/topup/crypto", routes_user.post_user_topup_crypto)
    app.router.add_post("/api/user/topup/crypto/check", routes_user.post_user_topup_crypto_check)
    app.router.add_post("/api/user/topup/stars", routes_user.post_user_topup_stars)
    app.router.add_post("/api/user/validate_coupon", routes_user.post_user_validate_coupon)
    app.router.add_post("/api/user/wallet/redeem", routes_user.post_user_redeem_voucher)
    app.router.add_post("/api/user/wallet/redeem-voucher", routes_user.post_user_redeem_voucher)
    app.router.add_post("/api/user/auto-renew", routes_user.post_user_auto_renew)
    app.router.add_post("/api/user/purchase", routes_user.post_user_purchase)
    app.router.add_post("/api/user/settings", routes_user.post_user_settings)
    app.router.add_post("/api/user/set_birthday", routes_user.post_user_set_birthday)
    app.router.add_post("/api/user/spin", routes_user.post_user_spin)
    app.router.add_post("/api/user/revoke_sub", routes_user.post_user_revoke_sub)
    app.router.add_post("/api/user/kill_device", routes_user.post_user_kill_device)
    app.router.add_get("/api/user/nodes", routes_user.get_user_nodes)
    app.router.add_get("/api/user/ip_info", routes_user.get_user_ip_info)
    app.router.add_get("/api/user/support/messages", routes_user.get_user_support_messages)
    app.router.add_post("/api/user/support/messages", routes_user.post_user_support_message)
    app.router.add_get("/api/user/subscription/configs", routes_user.get_user_subscription_configs)
    app.router.add_get("/api/user/speedtest/ping", routes_user.get_user_speedtest_ping)
    app.router.add_get("/api/user/speedtest/payload", routes_user.get_user_speedtest_payload)
    app.router.add_post("/api/user/speedtest/upload", routes_user.post_user_speedtest_upload)

    # Admin APIs
    app.router.add_get("/api/admin/overview", routes_admin.get_admin_overview)
    app.router.add_get("/api/admin/users", routes_admin.get_admin_users)
    app.router.add_post("/api/admin/user/modify", routes_admin.post_admin_modify_user)
    app.router.add_post("/api/admin/user/wallet", routes_admin.post_admin_user_wallet)
    app.router.add_post("/api/admin/user/revoke_sub", routes_admin.post_admin_user_revoke_sub)
    app.router.add_get("/api/admin/user/hwid_devices", routes_admin.get_admin_user_hwid_devices)
    app.router.add_get("/api/admin/user/sessions", routes_admin.get_admin_user_sessions)
    app.router.add_get("/api/admin/user/srh", routes_admin.get_admin_user_srh)
    app.router.add_get("/api/admin/sessions-explorer", routes_admin.get_admin_sessions_explorer)
    app.router.add_post("/api/admin/users/bulk-action", routes_admin.post_admin_users_bulk_action)
    app.router.add_post("/api/admin/user/delete_hwid", routes_admin.post_admin_user_delete_hwid)
    app.router.add_post("/api/admin/user/kill_sessions", routes_admin.post_admin_kill_sessions)
    app.router.add_post("/api/admin/user/toggle_ban", routes_admin.post_admin_toggle_ban)
    app.router.add_post("/api/admin/ticket/reply", routes_admin.post_admin_reply_ticket)
    app.router.add_get("/api/admin/tickets/threads", routes_admin.get_admin_ticket_threads)
    app.router.add_get("/api/admin/tickets/messages", routes_admin.get_admin_ticket_messages)
    app.router.add_post("/api/admin/broadcast", routes_admin.post_admin_broadcast)
    app.router.add_get("/api/admin/broadcast/status", routes_admin.get_admin_broadcast_status)
    app.router.add_post("/api/admin/user/reset_trial", routes_admin.post_admin_reset_trial)
    app.router.add_get("/api/admin/plans", routes_admin.get_admin_plans)
    app.router.add_post("/api/admin/plan/save", routes_admin.post_admin_plan_save)
    app.router.add_post("/api/admin/plan/toggle", routes_admin.post_admin_plan_toggle)
    app.router.add_post("/api/admin/plan/delete", routes_admin.post_admin_plan_delete)
    app.router.add_get("/api/admin/coupons", routes_admin.get_admin_coupons)
    app.router.add_get("/api/admin/coupons/{id}/usages", routes_admin.get_admin_coupon_usages)
    app.router.add_post("/api/admin/coupon/save", routes_admin.post_admin_coupon_save)
    app.router.add_post("/api/admin/coupon/toggle", routes_admin.post_admin_coupon_toggle)
    app.router.add_post("/api/admin/coupon/delete", routes_admin.post_admin_coupon_delete)
    app.router.add_post("/api/admin/coupons/batch-generate", routes_admin.post_admin_batch_vouchers)
    app.router.add_get("/api/admin/topups", routes_admin.get_admin_topups)
    app.router.add_get("/api/admin/topup/photo", routes_admin.get_admin_topup_photo)
    app.router.add_post("/api/admin/topup/action", routes_admin.post_admin_topup_action)
    app.router.add_get("/api/admin/crypto/rates", routes_admin.get_admin_crypto_rates)
    app.router.add_get("/api/admin/settings", routes_admin.get_admin_settings)
    app.router.add_post("/api/admin/settings", routes_admin.post_admin_settings)
    app.router.add_get("/api/admin/campaigns", routes_admin.get_admin_campaigns)
    app.router.add_post("/api/admin/campaigns", routes_admin.post_admin_campaign_create)
    app.router.add_post("/api/admin/campaign/create", routes_admin.post_admin_campaign_create)
    app.router.add_post("/api/admin/campaigns/delete", routes_admin.post_admin_campaign_delete)
    app.router.add_post("/api/admin/campaign/delete", routes_admin.post_admin_campaign_delete)
    app.router.add_get("/api/admin/infra/billing", routes_admin.get_admin_infra_billing)
    app.router.add_post("/api/admin/infra/node-cost", routes_admin.post_admin_node_cost)
    app.router.add_get("/api/admin/infra/ssl-health", routes_admin.get_admin_ssl_health)
    app.router.add_post("/api/admin/infra/ssl-check", routes_admin.post_admin_ssl_check)

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
