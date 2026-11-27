"""Client-side speedtest endpoints (Ping, Download, and Upload)."""
import asyncio
import inspect
import ipaddress
import logging
import os
import time

import aiohttp
from aiohttp import web

from bot.services.http_client import shared_http_session
from bot.web.user_common import get_client_ip, require_user

logger = logging.getLogger(__name__)

# Lazy-allocated 1 MB non-compressible random buffer
_SPEEDTEST_CHUNK: bytes | None = None
_MAX_ISP_CACHE = 500
_ISP_CACHE: dict[str, str] = {}

_MAX_DOWNLOAD_CHUNK_BYTES = 16 * 1024 * 1024
_MAX_UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024
_DOWNLOAD_QUOTA_BYTES_PER_WINDOW = 256 * 1024 * 1024
_UPLOAD_QUOTA_BYTES_PER_WINDOW = 128 * 1024 * 1024


def _get_speedtest_chunk() -> bytes:
    """Return pre-allocated 1 MB random buffer, lazy-initialized on first use."""
    global _SPEEDTEST_CHUNK
    if _SPEEDTEST_CHUNK is None:
        _SPEEDTEST_CHUNK = os.urandom(1024 * 1024)
    return _SPEEDTEST_CHUNK


async def _cache_get_int(cache, key: str) -> int:
    if not hasattr(cache, "get"):
        return 0
    if inspect.iscoroutinefunction(cache.get):
        val = await cache.get(key)
    else:
        res = cache.get(key)
        val = (await res) if asyncio.iscoroutine(res) else res
    return int(val) if isinstance(val, (int, float)) else 0


async def _cache_add_int(cache, key: str, delta: int, ttl_seconds: int) -> int:
    if delta == 1 and hasattr(cache, "incr"):
        res = cache.incr(key, ttl_seconds=ttl_seconds)
        return int(await res if asyncio.iscoroutine(res) else res)
    cur = await _cache_get_int(cache, key)
    new_val = cur + delta
    if hasattr(cache, "set"):
        if inspect.iscoroutinefunction(cache.set):
            await cache.set(key, new_val, ttl_seconds=ttl_seconds)
        else:
            res = cache.set(key, new_val, ttl_seconds=ttl_seconds)
            if asyncio.iscoroutine(res):
                await res
    return new_val


async def _enforce_speedtest_limits(
    request: web.Request,
    *,
    bucket: str,
    user_id: object,
    client_ip: str,
    max_requests: int,
    ttl_seconds: int,
    err_message: str,
    add_bytes: int = 0,
    max_bytes: int = 0,
) -> web.Response | None:
    """Enforce per-user and per-IP request count + optional byte-volume limits."""
    cache = request.app.get("cache") if hasattr(request.app, "get") else None
    if not cache:
        return None
    subjects: list[str] = []
    if user_id:
        subjects.append(f"uid:{user_id}")
    if client_ip and client_ip != "127.0.0.1":
        subjects.append(f"ip:{client_ip}")
    if not subjects:
        subjects.append(f"ip:{client_ip or 'unknown'}")

    try:
        for subj in subjects:
            rl_key = f"tma:speedtest:{bucket}:{subj}"
            count = await _cache_add_int(cache, rl_key, 1, ttl_seconds)
            if count > max_requests:
                return web.json_response(
                    {"ok": False, "error": err_message},
                    status=429,
                    headers={"Retry-After": str(ttl_seconds)},
                )
            if max_bytes > 0 and add_bytes > 0:
                bytes_key = f"tma:speedtest:{bucket}:bytes:{subj}"
                used_bytes = await _cache_get_int(cache, bytes_key)
                if used_bytes + add_bytes > max_bytes:
                    return web.json_response(
                        {"ok": False, "error": err_message},
                        status=429,
                        headers={"Retry-After": str(ttl_seconds)},
                    )
                await _cache_add_int(cache, bytes_key, add_bytes, ttl_seconds)
    except Exception:
        pass
    return None


async def _lookup_isp(client_ip: str) -> str:
    """Resolve ISP / organization for a client IP using HTTPS ipwho.is with HTTP ip-api fallback."""
    try:
        ip_obj = ipaddress.ip_address(str(client_ip or "").strip())
    except ValueError:
        return ""
    if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
        return "شبکه محلی (Local)"

    norm_ip = str(ip_obj)
    if norm_ip in _ISP_CACHE:
        return _ISP_CACHE[norm_ip]

    isp_name = ""
    timeout = aiohttp.ClientTimeout(total=1.5)
    try:
        async with shared_http_session(timeout=timeout) as session:
            try:
                async with session.get(f"https://ipwho.is/{norm_ip}?fields=success,connection", timeout=timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            conn = data.get("connection") or {}
                            isp_name = str(conn.get("isp") or conn.get("org") or "").strip()
            except Exception:
                isp_name = ""

            if not isp_name:
                # ip-api.com free tier serves HTTP only (HTTPS fails on free plan)
                async with session.get(f"http://ip-api.com/json/{norm_ip}?fields=status,isp,org", timeout=timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("status") == "success":
                            isp_name = str(data.get("isp") or data.get("org") or "").strip()
    except Exception:
        pass

    if isp_name:
        if len(_ISP_CACHE) >= _MAX_ISP_CACHE:
            _ISP_CACHE.pop(next(iter(_ISP_CACHE)))
        _ISP_CACHE[norm_ip] = isp_name
    return isp_name


async def get_user_speedtest_ping(request: web.Request) -> web.Response:
    """Lightweight ping probe returning server timestamp, server info, and client IP with rate limiting."""
    user_auth, err = require_user(request)
    if err:
        return err

    user_id = user_auth.get("id")
    client_ip = get_client_ip(request)

    rl_resp = await _enforce_speedtest_limits(
        request,
        bucket="ping",
        user_id=user_id,
        client_ip=client_ip,
        max_requests=40,
        ttl_seconds=30,
        err_message="محدودیت تعداد درخواست تست پینگ. لطفاً 30 ثانیه دیگر تلاش فرمایید.",
    )
    if rl_resp:
        return rl_resp

    server_name = "سرور اختصاصی"
    server_ip = "Anycast Edge"

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

    try:
        req_bytes = int(request.query.get("bytes", 8 * 1024 * 1024))
    except (ValueError, TypeError):
        req_bytes = 8 * 1024 * 1024

    # Bound chunk size between 256 KB and 16 MB
    target_bytes = max(256 * 1024, min(req_bytes, _MAX_DOWNLOAD_CHUNK_BYTES))

    user_id = user_auth.get("id")
    client_ip = get_client_ip(request)
    rl_resp = await _enforce_speedtest_limits(
        request,
        bucket="download",
        user_id=user_id,
        client_ip=client_ip,
        max_requests=24,
        ttl_seconds=60,
        err_message="محدودیت تعداد یا حجم درخواست تست سرعت. لطفاً 1 دقیقه دیگر تلاش فرمایید.",
        add_bytes=target_bytes,
        max_bytes=_DOWNLOAD_QUOTA_BYTES_PER_WINDOW,
    )
    if rl_resp:
        return rl_resp

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
    try:
        declared_len = max(0, int(request.headers.get("Content-Length", "0") or 0))
    except (ValueError, TypeError):
        declared_len = 0

    if declared_len > _MAX_UPLOAD_CHUNK_BYTES:
        return web.json_response(
            {"ok": False, "error": "حجم بسته آپلود بیش از حد مجاز است."},
            status=413,
        )

    rl_resp = await _enforce_speedtest_limits(
        request,
        bucket="upload",
        user_id=user_id,
        client_ip=client_ip,
        max_requests=60,
        ttl_seconds=60,
        err_message="محدودیت تعداد یا حجم درخواست تست آپلود. لطفاً 1 دقیقه دیگر تلاش فرمایید.",
        add_bytes=declared_len or (512 * 1024),
        max_bytes=_UPLOAD_QUOTA_BYTES_PER_WINDOW,
    )
    if rl_resp:
        return rl_resp

    total_bytes = 0
    try:
        if hasattr(request.content, "read"):
            while True:
                chunk = await request.content.read(65536)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > _MAX_UPLOAD_CHUNK_BYTES:
                    break
        elif isinstance(request.content, (bytes, bytearray)):
            total_bytes = min(len(request.content), _MAX_UPLOAD_CHUNK_BYTES)
        else:
            body = await request.read()
            total_bytes = min(len(body), _MAX_UPLOAD_CHUNK_BYTES)
    except (asyncio.CancelledError, ConnectionResetError):
        pass

    return web.json_response(
        {"ok": True, "received_bytes": total_bytes},
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        },
    )
