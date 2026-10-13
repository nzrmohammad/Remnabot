"""Client-side speedtest endpoints (Ping, Download, and Upload)."""
import asyncio
import inspect
import logging
import os
import time

import aiohttp
from aiohttp import web

from bot.web.user_common import get_client_ip, require_user

logger = logging.getLogger(__name__)

# Lazy-allocated 1 MB non-compressible random buffer
_SPEEDTEST_CHUNK: bytes | None = None
_ISP_CACHE: dict[str, str] = {}


def _get_speedtest_chunk() -> bytes:
    """Return pre-allocated 1 MB random buffer, lazy-initialized on first use."""
    global _SPEEDTEST_CHUNK
    if _SPEEDTEST_CHUNK is None:
        _SPEEDTEST_CHUNK = os.urandom(1024 * 1024)
    return _SPEEDTEST_CHUNK


async def _lookup_isp(client_ip: str) -> str:
    """Resolve ISP / organization for a client IP with in-memory caching."""
    if not client_ip or client_ip.startswith(("127.", "10.", "192.168.", "172.16.", "::1")):
        return "شبکه محلی (Local)"
    if client_ip in _ISP_CACHE:
        return _ISP_CACHE[client_ip]

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.2)) as session:
            async with session.get(f"http://ip-api.com/json/{client_ip}?fields=status,isp,org") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "success":
                        isp_name = str(data.get("isp") or data.get("org") or "").strip()
                        if isp_name:
                            _ISP_CACHE[client_ip] = isp_name
                            return isp_name
    except Exception:
        pass
    return ""


async def get_user_speedtest_ping(request: web.Request) -> web.Response:
    """Lightweight ping probe returning server timestamp, server info, and client IP."""
    user_auth, err = require_user(request)
    if err:
        return err

    settings = request.app.get("settings") if hasattr(request.app, "get") else None
    server_name = "Cloudflare Anycast CDN (جهانی)"
    server_ip = "Anycast Edge"
    if settings:
        val_name = getattr(settings, "SPEEDTEST_SERVER_NAME", None)
        if isinstance(val_name, str) and val_name:
            server_name = val_name
        val_ip = getattr(settings, "SPEEDTEST_SERVER_IP", None)
        if isinstance(val_ip, str) and val_ip:
            server_ip = val_ip

    client_ip = get_client_ip(request)
    isp = await _lookup_isp(client_ip)

    return web.json_response(
        {
            "ok": True,
            "t": int(time.time() * 1000),
            "ip": client_ip,
            "isp": isp,
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

            if isinstance(req_count, (int, float)) and req_count >= 30:
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
