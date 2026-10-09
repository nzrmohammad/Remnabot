"""Ultra-low latency multi-tier caching (In-Memory + Redis fallback).

Optimized for sub-millisecond response times in high-traffic Telegram Mini Apps.
"""
import asyncio
import json
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class FastCache:
    """In-memory L1 cache with Redis L2 synchronization."""

    def __init__(self, redis_client=None):
        self._memory: dict[str, tuple[float, Any]] = {}
        self._redis = redis_client
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Fetch item from memory first (L1), then Redis (L2)."""
        now = time.time()
        # L1: Memory check (0.01ms)
        if key in self._memory:
            expire_at, value = self._memory[key]
            if expire_at > now:
                return value
            else:
                del self._memory[key]

        # L2: Redis check
        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    data = json.loads(raw)
                    # Backfill memory for next hits
                    self._memory[key] = (now + 5.0, data)
                    return data
            except Exception as exc:
                logger.debug("Redis cache get error for %s: %s", key, exc)

        return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 15) -> None:
        """Store item in both Memory and Redis with TTL."""
        now = time.time()
        self._memory[key] = (now + ttl_seconds, value)

        if self._redis:
            try:
                raw = json.dumps(value, ensure_ascii=False)
                await self._redis.set(key, raw, ex=ttl_seconds)
            except Exception as exc:
                logger.debug("Redis cache set error for %s: %s", key, exc)

    async def delete(self, key: str) -> None:
        """Invalidate key and all sub-keys from memory and Redis."""
        keys_to_pop = [k for k in list(self._memory.keys()) if k == key or k.startswith(f"{key}:")]
        for k in keys_to_pop:
            self._memory.pop(k, None)
        if self._redis:
            try:
                await self._redis.delete(key)
                matched = await self._redis.keys(f"{key}:*")
                if matched:
                    await self._redis.delete(*matched)
            except Exception:
                pass


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
            return response

        return wrapper
    return decorator
