"""SSOT Support Chat thread history helper (PostgreSQL durable + Redis fast cache)."""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from bot.db.repositories.support_repo import SupportMessageRepository
from bot.services.formatting import now_tz

logger = logging.getLogger(__name__)

SUPPORT_CHAT_TTL = 86400 * 30
MAX_CHAT_MESSAGES = 50
MAX_ACTIVE_THREADS = 100

_CHAT_LOCKS: dict[int, asyncio.Lock] = {}


def _get_chat_lock(telegram_id: int) -> asyncio.Lock:
    if len(_CHAT_LOCKS) > 2000:
        idle = [k for k, lk in _CHAT_LOCKS.items() if not lk.locked()]
        for k in idle:
            _CHAT_LOCKS.pop(k, None)
    if telegram_id not in _CHAT_LOCKS:
        _CHAT_LOCKS[telegram_id] = asyncio.Lock()
    return _CHAT_LOCKS[telegram_id]


async def _acquire_dist_lock(cache: Any, lock_key: str, lock_token: str) -> bool:
    """Best-effort short spin-wait on distributed cache lock to avoid lost concurrent appends."""
    if not (cache and hasattr(cache, "set_nx")):
        return False
    for _ in range(10):
        try:
            if await cache.set_nx(lock_key, lock_token, ttl_seconds=5):
                return True
        except Exception:
            return False
        await asyncio.sleep(0.05)
    return False


async def _release_dist_lock(cache: Any, lock_key: str, lock_token: str) -> None:
    try:
        if hasattr(cache, "release_lock"):
            await cache.release_lock(lock_key, lock_token)
        elif hasattr(cache, "delete"):
            await cache.delete(lock_key)
    except Exception:
        pass


async def _read_json_list(cache: Any, redis: Any, key: str) -> list[Any]:
    if cache is not None and hasattr(cache, "get"):
        val = await cache.get(key)
        return list(val) if isinstance(val, list) else []
    if redis is not None:
        raw = await redis.get(key)
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            return list(parsed) if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


async def _write_json_list(cache: Any, redis: Any, key: str, items: list[Any]) -> None:
    if cache is not None and hasattr(cache, "set"):
        await cache.set(key, items, ttl_seconds=SUPPORT_CHAT_TTL)
        return
    if redis is not None:
        await redis.set(key, json.dumps(items, ensure_ascii=False), ex=SUPPORT_CHAT_TTL)


def _format_db_row(row: Any) -> dict[str, Any]:
    dt = getattr(row, "created_at", None) or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local_dt = dt.astimezone(ZoneInfo("Asia/Tehran"))
    return {
        "id": row.external_msg_id or f"db_{row.id}",
        "sender": row.sender,
        "text": row.text,
        "created_at": local_dt.strftime("%H:%M"),
        "timestamp": int(dt.timestamp()),
    }


async def get_support_messages(
    telegram_id: int,
    *,
    cache: Any = None,
    redis: Any = None,
    session: Any = None,
) -> list[dict[str, Any]]:
    """Load bounded chat history from fast cache, warming from PostgreSQL if cache is cold."""
    tid = int(telegram_id)
    chat_key = f"support:chat:{tid}"
    cached = await _read_json_list(cache, redis, chat_key)
    if cached:
        return cached

    if session is not None:
        try:
            rows = await SupportMessageRepository(session).list_chat_messages(tid, limit=MAX_CHAT_MESSAGES)
            if rows:
                msgs = [_format_db_row(r) for r in rows]
                await _write_json_list(cache, redis, chat_key, msgs)
                return msgs
        except Exception as exc:
            logger.debug("Support chat DB fallback load failed for %s: %s", tid, exc)
    return []


async def get_active_thread_ids(
    *,
    cache: Any = None,
    redis: Any = None,
    session: Any = None,
) -> list[int]:
    """Return ordered active support user Telegram IDs, falling back to PostgreSQL when cache cold."""
    raw = await _read_json_list(cache, redis, "support:active_thread_ids")
    parsed: list[int] = []
    for item in raw:
        try:
            parsed.append(int(item))
        except (TypeError, ValueError):
            continue
    if parsed:
        return parsed

    if session is not None:
        try:
            db_ids = await SupportMessageRepository(session).list_active_chat_user_ids(limit=MAX_ACTIVE_THREADS)
            if db_ids:
                await _write_json_list(cache, redis, "support:active_thread_ids", db_ids)
                return db_ids
        except Exception as exc:
            logger.debug("Support active threads DB fallback failed: %s", exc)
    return []


async def append_support_message(
    telegram_id: int,
    *,
    sender: str,
    text: str,
    msg_id: str | None = None,
    created_dt: datetime | None = None,
    cache: Any = None,
    redis: Any = None,
    session: Any = None,
    session_factory: Any = None,
) -> dict[str, Any]:
    """Persist a support message to PostgreSQL and atomically update Redis chat thread cache."""
    tid = int(telegram_id)
    if created_dt is None:
        created_dt = now_tz("Asia/Tehran")
    ts = int(created_dt.timestamp())
    ext_id = msg_id or f"{sender}_{int(time.time() * 1000)}"
    msg_obj = {
        "id": ext_id,
        "sender": sender,
        "text": text,
        "created_at": created_dt.strftime("%H:%M"),
        "timestamp": ts,
    }

    if session is not None:
        try:
            await SupportMessageRepository(session).add_chat_message(
                tid, sender, text, external_msg_id=ext_id, created_at=created_dt
            )
        except Exception as db_exc:
            logger.debug("Support chat DB insert skipped/failed: %s", db_exc)
    elif session_factory is not None:
        try:
            async with session_factory() as db_sess:
                await SupportMessageRepository(db_sess).add_chat_message(
                    tid, sender, text, external_msg_id=ext_id, created_at=created_dt
                )
                await db_sess.commit()
        except Exception as db_exc:
            logger.debug("Support chat standalone DB insert failed: %s", db_exc)

    if cache is None and redis is None:
        return msg_obj

    async with _get_chat_lock(tid):
        lock_key = f"lock:support:chat:{tid}"
        lock_token = secrets.token_hex(8)
        dist_locked = await _acquire_dist_lock(cache, lock_key, lock_token)
        try:
            chat_key = f"support:chat:{tid}"
            msgs = await _read_json_list(cache, redis, chat_key)
            msgs.append(msg_obj)
            if len(msgs) > MAX_CHAT_MESSAGES:
                msgs = msgs[-MAX_CHAT_MESSAGES:]
            await _write_json_list(cache, redis, chat_key, msgs)
        finally:
            if dist_locked:
                await _release_dist_lock(cache, lock_key, lock_token)

    async with _get_chat_lock(0):
        threads_lock_key = "lock:support:active_threads"
        threads_token = secrets.token_hex(8)
        dist_locked = await _acquire_dist_lock(cache, threads_lock_key, threads_token)
        try:
            active_ids = await get_active_thread_ids(cache=cache, redis=redis)
            if tid in active_ids:
                active_ids.remove(tid)
            active_ids.insert(0, tid)
            if len(active_ids) > MAX_ACTIVE_THREADS:
                active_ids = active_ids[:MAX_ACTIVE_THREADS]
            await _write_json_list(cache, redis, "support:active_thread_ids", active_ids)
        finally:
            if dist_locked:
                await _release_dist_lock(cache, threads_lock_key, threads_token)

    return msg_obj
