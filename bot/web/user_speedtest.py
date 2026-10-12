"""Client-side speedtest endpoints (Ping, Download, and Upload)."""
import asyncio
import inspect
import logging
import os
import time

from aiohttp import web

from bot.web.user_common import get_client_ip, require_user

logger = logging.getLogger(__name__)

# Lazy-allocated 1 MB non-compressible random buffer
_SPEEDTEST_CHUNK: bytes | None = None


def _get_speedtest_chunk() -> bytes:
    """Return pre-allocated 1 MB random buffer, lazy-initialized on first use."""
    global _SPEEDTEST_CHUNK
    if _SPEEDTEST_CHUNK is None:
        _SPEEDTEST_CHUNK = os.urandom(1024 * 1024)
    return _SPEEDTEST_CHUNK


async def get_user_speedtest_ping(request: web.Request) -> web.Response:
    """Lightweight ping probe returning server timestamp, server info, and client IP."""
    user_auth, err = require_user(request)
    if err:
        return err

    settings = request.app.get("settings") if hasattr(request.app, "get") else None
    server_name = "سرور اختصاصی اشتراک"
    server_ip = ""
    if settings:
        val_name = getattr(settings, "SPEEDTEST_SERVER_NAME", None)
        if isinstance(val_name, str) and val_name:
            server_name = val_name
        val_ip = getattr(settings, "SPEEDTEST_SERVER_IP", None)
        if isinstance(val_ip, str) and val_ip:
            server_ip = val_ip

    if not server_ip:
        host_header = request.headers.get("Host", "") or request.host or ""
        server_ip = host_header.split(":")[0] if host_header else "سرور اصلی"

    client_ip = get_client_ip(request)
    return web.json_response(
        {
            "ok": True,
            "t": int(time.time() * 1000),
            "ip": client_ip,
            "server": {
                "name": server_name,
                "ip": server_ip,
            },
        },
        headers={
            "Cache-Control": "no-store, no-cache, no-transform, must-revalidate, max-age=0",
        },
    )


async def get_user_speedtest_payload(request: web.Request) -> web.StreamResponse:
    """Stream non-compressible random binary payload for measuring user download speed."""
    user_auth, err = require_user(request)
    if err:
        return err

    user_id = user_auth.get("id")
    client_ip = get_client_ip(request)

    cache = request.app.get("cache") if hasattr(request.app, "get") else None
    if cache and hasattr(cache, "get"):
        try:
            rl_key = f"tma:speedtest:limit:{user_id or client_ip}"
            if inspect.iscoroutinefunction(cache.get):
                req_count = await cache.get(rl_key)
            else:
                res = cache.get(rl_key)
                req_count = (await res) if asyncio.iscoroutine(res) else res

            if isinstance(req_count, (int, float)) and req_count >= 10:
                return web.json_response(
                    {"ok": False, "error": "محدودیت تعداد درخواست تست سرعت. لطفاً ۳۰ ثانیه دیگر تلاش فرمایید."},
                    status=429,
                    headers={"Retry-After": "30"},
                )

            if hasattr(cache, "set"):
                if inspect.iscoroutinefunction(cache.set):
                    await cache.set(rl_key, (req_count or 0) + 1, ttl_seconds=30)
                else:
                    set_res = cache.set(rl_key, (req_count or 0) + 1, ttl_seconds=30)
                    if asyncio.iscoroutine(set_res):
                        await set_res
        except Exception:
            pass

    try:
        req_bytes = int(request.query.get("bytes", 25 * 1024 * 1024))
    except (ValueError, TypeError):
        req_bytes = 25 * 1024 * 1024

    # Bound size between 256 KB and 32 MB
    target_bytes = max(256 * 1024, min(req_bytes, 32 * 1024 * 1024))

    chunk = _get_speedtest_chunk()
    chunk_len = len(chunk)
    full_chunks = target_bytes // chunk_len
    remainder = target_bytes % chunk_len

    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Length": str(target_bytes),
            "Cache-Control": "no-store, no-cache, no-transform, must-revalidate, max-age=0",
        },
    )
    await resp.prepare(request)

    try:
        for _ in range(full_chunks):
            await resp.write(chunk)
        if remainder > 0:
            await resp.write(chunk[:remainder])
        await resp.write_eof()
    except (ConnectionResetError, asyncio.CancelledError):
        pass

    return resp


async def post_user_speedtest_upload(request: web.Request) -> web.Response:
    """Measure upload throughput by receiving chunks without disk I/O."""
    user_auth, err = require_user(request)
    if err:
        return err

    user_id = user_auth.get("id")
    client_ip = get_client_ip(request)

    cache = request.app.get("cache") if hasattr(request.app, "get") else None
    if cache and hasattr(cache, "get"):
        try:
            rl_key = f"tma:speedtest:limit:upload:{user_id or client_ip}"
            if inspect.iscoroutinefunction(cache.get):
                req_count = await cache.get(rl_key)
            else:
                res = cache.get(rl_key)
                req_count = (await res) if asyncio.iscoroutine(res) else res

            if isinstance(req_count, (int, float)) and req_count >= 10:
                return web.json_response(
                    {"ok": False, "error": "محدودیت تعداد درخواست تست آپلود. لطفاً ۳۰ ثانیه دیگر تلاش فرمایید."},
                    status=429,
                    headers={"Retry-After": "30"},
                )

            if hasattr(cache, "set"):
                if inspect.iscoroutinefunction(cache.set):
                    await cache.set(rl_key, (req_count or 0) + 1, ttl_seconds=30)
                else:
                    set_res = cache.set(rl_key, (req_count or 0) + 1, ttl_seconds=30)
                    if asyncio.iscoroutine(set_res):
                        await set_res
        except Exception:
            pass

    total_bytes = 0
    try:
        if hasattr(request.content, "read"):
            while True:
                chunk = await request.content.read(65536)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > 32 * 1024 * 1024:
                    break
        elif isinstance(request.content, (bytes, bytearray)):
            total_bytes = len(request.content)
        else:
            body = await request.read()
            total_bytes = len(body)
    except (asyncio.CancelledError, ConnectionResetError):
        pass

    return web.json_response(
        {"ok": True, "received_bytes": total_bytes},
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        },
    )
