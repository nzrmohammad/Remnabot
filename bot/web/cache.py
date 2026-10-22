"""Ultra-low latency multi-tier caching (In-Memory + Redis fallback).

Optimized for sub-millisecond response times in high-traffic Telegram Mini Apps.
"""
import asyncio
import json
import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class FastCache:
    """In-memory L1 cache with Redis L2 synchronization and LRU eviction."""

    def __init__(self, redis_client=None, maxsize: int = 2000):
        self._memory: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._maxsize = maxsize
        self._redis = redis_client
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Fetch item from memory first (L1), then Redis (L2)."""
        now = time.time()
        # L1: Memory check (0.01ms)
        if key in self._memory:
            expire_at, value = self._memory[key]
            if expire_at > now:
                self._memory.move_to_end(key)
                return value
            else:
                del self._memory[key]

        # L2: Redis check
        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    data = json.loads(raw)
                    # Backfill memory for next hits with LRU eviction
                    self._memory[key] = (now + 5.0, data)
                    self._memory.move_to_end(key)
                    if len(self._memory) > self._maxsize:
                        self._memory.popitem(last=False)
                    return data
            except Exception as exc:
                logger.debug("Redis cache get error for %s: %s", key, exc)

        return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 15) -> None:
        """Store item in both Memory and Redis with TTL and LRU bounds."""
        now = time.time()
        self._memory[key] = (now + ttl_seconds, value)
        self._memory.move_to_end(key)
        if len(self._memory) > self._maxsize:
            self._memory.popitem(last=False)

        if self._redis:
            try:
                raw = json.dumps(value, ensure_ascii=False)
                await self._redis.set(key, raw, ex=ttl_seconds)
            except Exception as exc:
                logger.debug("Redis cache set error for %s: %s", key, exc)

    async def set_nx(self, key: str, value: Any, ttl_seconds: int = 15) -> bool:
        """Store item if not exists (atomic distributed lock)."""
        now = time.time()
        if self._redis:
            try:
                raw = json.dumps(value, ensure_ascii=False)
                res = await self._redis.set(key, raw, ex=ttl_seconds, nx=True)
                return bool(res)
            except Exception as exc:
                logger.debug("Redis cache set_nx error for %s: %s", key, exc)

        async with self._lock:
            if key in self._memory:
                expire_at, _ = self._memory[key]
                if expire_at > now:
                    return False
            self._memory[key] = (now + ttl_seconds, value)
            return True

    async def delete(self, key: str) -> None:
        """Invalidate key and all sub-keys from memory and Redis without blocking."""
        keys_to_pop = [k for k in list(self._memory.keys()) if k == key or k.startswith(f"{key}:")]
        for k in keys_to_pop:
            self._memory.pop(k, None)
        if self._redis:
            try:
                await self._redis.delete(key)
                matched = []
                if hasattr(self._redis, "scan_iter"):
                    async for k in self._redis.scan_iter(match=f"{key}:*"):
                        matched.append(k)
                elif hasattr(self._redis, "keys"):
                    matched = await self._redis.keys(f"{key}:*")
                if matched:
                    await self._redis.delete(*matched)
            except Exception as exc:
                logger.debug("Redis cache delete error for %s: %s", key, exc)

    async def release_lock(self, key: str, token: str) -> bool:
        """Safely release distributed lock only if the current value matches token."""
        async with self._lock:
            if key in self._memory:
                _, val = self._memory[key]
                if val == token:
                    del self._memory[key]

        if self._redis:
            try:
                lua = """
                local val = redis.call('get', KEYS[1])
                if val and cjson.decode(val) == ARGV[1] then
                    return redis.call('del', KEYS[1])
                else
                    return 0
                end
                """
                res = await self._redis.eval(lua, 1, key, token)
                return bool(res)
            except Exception as exc:
                logger.warning("Redis release_lock error for %s: %s; letting TTL expire naturally", key, exc)
                return False
        return True


def cached(ttl_seconds: int = 15, key_prefix: str = "tma:cache"):
    """Decorator to cache async API handler responses."""
    def decorator(func: Callable):
        async def wrapper(request, *args, **kwargs):
            cache: FastCache = request.app.get("cache")
            if not cache:
                return await func(request, *args, **kwargs)

            # Build cache key based on user ID or path
            user = request.get("user", {})
            user_id = user.get("id", "anon")
            cache_key = f"{key_prefix}:{func.__name__}:{user_id}:{request.query_string}"

            cached_data = await cache.get(cache_key)
            if cached_data is not None:
                from aiohttp import web
                return web.json_response(cached_data, headers={"X-Cache": "HIT"})

            response = await func(request, *args, **kwargs)
            if response is not None and getattr(response, "status", None) == 200:
                content_type = getattr(response, "content_type", "")
                if content_type == "application/json" and hasattr(response, "body") and response.body:
                    try:
                        payload = json.loads(response.body)
                        await cache.set(cache_key, payload, ttl_seconds=ttl_seconds)
                        response.headers["X-Cache"] = "MISS"
                    except Exception as exc:
                        logger.debug("Failed to cache response in @cached: %s", exc)

            return response

        return wrapper
    return decorator
