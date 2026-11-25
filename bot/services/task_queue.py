"""Durable Redis-backed Broadcast Task Queue & Resumable Worker (SSOT for Bot & TMA)."""
from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from html import escape
from typing import Any

from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import BufferedInputFile

logger = logging.getLogger(__name__)

BROADCAST_RATE_DELAY = 0.042  # ~24 msgs/sec (safely below Telegram 30 msgs/sec global ceiling)
JOB_TTL_SECONDS = 86400 * 7
QUEUE_PENDING_KEY = "queue:broadcast:pending"
QUEUE_ACTIVE_SET_KEY = "queue:broadcast:active"
_ACTIVE_TASK_REGISTRY: set[asyncio.Task] = set()
_RUNNING_JOB_IDS: set[str] = set()


def _job_key(job_id: str) -> str:
    return f"queue:job:{job_id}"


def _stop_key(job_id: str) -> str:
    return f"queue:job:{job_id}:stop"


async def _load_job(cache: Any, job_id: str) -> dict[str, Any] | None:
    if not (cache and hasattr(cache, "get")):
        return None
    try:
        raw = await cache.get(_job_key(job_id))
        return dict(raw) if isinstance(raw, dict) else None
    except Exception as exc:
        logger.debug("Failed loading queued job %s: %s", job_id, exc)
        return None


async def save_broadcast_job(cache: Any, job: dict[str, Any]) -> None:
    """Persist checkpointed broadcast job state to Redis/FastCache and maintain active index."""
    if not (cache and hasattr(cache, "set")):
        return
    job_id = str(job["job_id"])
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        await cache.set(_job_key(job_id), job, ttl_seconds=JOB_TTL_SECONDS)
    except Exception as exc:
        logger.debug("Failed saving job checkpoint %s: %s", job_id, exc)

    redis = getattr(cache, "_redis", None)
    if redis is not None:
        try:
            if job.get("status") in ("queued", "running"):
                await redis.sadd(QUEUE_ACTIVE_SET_KEY, job_id)
                await redis.expire(QUEUE_ACTIVE_SET_KEY, JOB_TTL_SECONDS)
            else:
                await redis.srem(QUEUE_ACTIVE_SET_KEY, job_id)
        except Exception as exc:
            logger.debug("Failed syncing active broadcast set for %s: %s", job_id, exc)


async def request_job_stop(cache: Any, job_id: str) -> None:
    """Mark a queued/running broadcast job as stopped in Redis."""
    if cache and hasattr(cache, "set"):
        try:
            await cache.set(_stop_key(job_id), "1", ttl_seconds=86400)
        except Exception:
            pass
    job = await _load_job(cache, job_id)
    if job and job.get("status") in ("queued", "running"):
        job["status"] = "stopped"
        await save_broadcast_job(cache, job)


async def is_job_stopped(cache: Any, job_id: str) -> bool:
    if not (cache and hasattr(cache, "get")):
        return False
    try:
        return bool(await cache.get(_stop_key(job_id)))
    except Exception:
        return False


def _prepare_media_and_text(job: dict[str, Any]) -> tuple[Any, str, str | None]:
    """Resolve photo payload (file_id or BufferedInputFile) and message text cleanly."""
    kind = job.get("kind", "bot")
    parse_mode: str | None = "HTML" if kind == "web" else None
    if kind == "web":
        msg_text = str(job.get("text") or "")
    else:
        raw_draft = str(job.get("draft") or "")
        msg_text = escape(raw_draft) if raw_draft else ""

    photo_id = job.get("photo_id")
    if photo_id:
        return photo_id, msg_text, parse_mode

    photo_raw = str(job.get("photo_raw") or "")
    if not photo_raw:
        return None, msg_text, parse_mode

    if photo_raw.startswith("data:image/") and "base64," in photo_raw:
        try:
            header, b64_str = photo_raw.split("base64,", 1)
            img_bytes = base64.b64decode(b64_str)
            ext = "jpg" if ("jpeg" in header or "jpg" in header) else ("webp" if "webp" in header else "png")
            return BufferedInputFile(img_bytes, filename=f"broadcast.{ext}"), msg_text, parse_mode
        except Exception as exc:
            logger.warning("Failed to decode base64 broadcast photo: %s", exc)
            return None, msg_text, parse_mode
    return photo_raw, msg_text, parse_mode


async def _deliver_one(
    bot: Any,
    tid: int,
    photo_obj: Any,
    text: str,
    parse_mode: str | None,
) -> tuple[bool, int | None, str | None]:
    """Send a single broadcast message with flood-wait retry and text fallback."""
    kwargs = {"parse_mode": parse_mode} if parse_mode else {}

    async def _attempt_send(use_photo: bool):
        if use_photo and photo_obj is not None:
            sent_msg = await bot.send_photo(chat_id=tid, photo=photo_obj, caption=text or None, **kwargs)
            fid = sent_msg.photo[-1].file_id if getattr(sent_msg, "photo", None) else None
            return True, getattr(sent_msg, "message_id", None), fid
        sent_msg = await bot.send_message(chat_id=tid, text=text, **kwargs)
        return True, getattr(sent_msg, "message_id", None), None

    try:
        return await _attempt_send(use_photo=photo_obj is not None)
    except TelegramRetryAfter as retry_err:
        try:
            await asyncio.sleep(float(retry_err.retry_after) + 1.0)
            return await _attempt_send(use_photo=photo_obj is not None)
        except Exception:
            return False, None, None
    except Exception:
        if photo_obj is not None and text:
            try:
                return await _attempt_send(use_photo=False)
            except Exception:
                pass
        return False, None, None


async def execute_broadcast_job(
    bot: Any,
    job: dict[str, Any],
    *,
    cache: Any = None,
    in_memory_ref: dict[str, Any] | None = None,
    sync_status_fn: Callable[[dict[str, Any], bool], Awaitable[None]] | None = None,
    on_progress: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    on_complete: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Run or resume a rate-limited broadcast job from cursor_idx with periodic Redis checkpoints."""
    job_id = str(job["job_id"])
    if job_id in _RUNNING_JOB_IDS:
        return job
    _RUNNING_JOB_IDS.add(job_id)

    try:
        recipients: list[int] = [int(x) for x in (job.get("recipient_ids") or [])]
        cursor = max(0, int(job.get("cursor_idx") or 0))
        if job.get("status") == "queued":
            job["status"] = "running"
        photo_obj, msg_text, parse_mode = _prepare_media_and_text(job)
        reusable_photo_id: str | None = job.get("photo_id")

        await save_broadcast_job(cache, job)

        try:
            for idx in range(cursor, len(recipients)):
                if in_memory_ref and in_memory_ref.get("status") == "stopped":
                    job["status"] = "stopped"
                    break
                if idx % 5 == 0 and await is_job_stopped(cache, job_id):
                    job["status"] = "stopped"
                    if in_memory_ref is not None:
                        in_memory_ref["status"] = "stopped"
                    break

                tid = recipients[idx]
                active_photo = reusable_photo_id or photo_obj
                ok, sent_msg_id, new_file_id = await _deliver_one(
                    bot, tid, active_photo, msg_text, parse_mode
                )
                if new_file_id and not reusable_photo_id:
                    reusable_photo_id = new_file_id
                    job["photo_id"] = new_file_id

                if ok:
                    job["ok"] = int(job.get("ok") or 0) + 1
                    if sent_msg_id is not None:
                        sent_list = job.setdefault("sent", [])
                        sent_list.append([tid, int(sent_msg_id)])
                        if in_memory_ref is not None and isinstance(in_memory_ref.get("sent"), list):
                            in_memory_ref["sent"].append((tid, int(sent_msg_id)))
                else:
                    job["fail"] = int(job.get("fail") or 0) + 1

                job["cursor_idx"] = idx + 1

                if in_memory_ref is not None:
                    if "ok" in in_memory_ref:
                        in_memory_ref["ok"] = job["ok"]
                    if "fail" in in_memory_ref:
                        in_memory_ref["fail"] = job["fail"]
                    if "sent" in in_memory_ref and isinstance(in_memory_ref["sent"], int):
                        in_memory_ref["sent"] = job["ok"]
                    if "failed" in in_memory_ref:
                        in_memory_ref["failed"] = job["fail"]

                if (idx + 1) % 20 == 0:
                    await save_broadcast_job(cache, job)
                    if sync_status_fn:
                        await sync_status_fn(job, False)
                    if on_progress and job.get("status") == "running":
                        await on_progress(job)

                await asyncio.sleep(BROADCAST_RATE_DELAY)

        except asyncio.CancelledError:
            job["status"] = "stopped"
            await save_broadcast_job(cache, job)
            raise

        if job.get("status") != "stopped":
            job["status"] = "finished"

        if in_memory_ref is not None:
            if "status" in in_memory_ref:
                in_memory_ref["status"] = job["status"]
            if "is_completed" in in_memory_ref:
                in_memory_ref["is_completed"] = True
            if "ok" in in_memory_ref:
                in_memory_ref["ok"] = job["ok"]
            if "fail" in in_memory_ref:
                in_memory_ref["fail"] = job["fail"]
            if "sent" in in_memory_ref and isinstance(in_memory_ref["sent"], int):
                in_memory_ref["sent"] = job["ok"]
            if "failed" in in_memory_ref:
                in_memory_ref["failed"] = job["fail"]

        await save_broadcast_job(cache, job)
        if sync_status_fn:
            await sync_status_fn(job, True)
        if on_complete:
            await on_complete(job)
        return job
    finally:
        _RUNNING_JOB_IDS.discard(job_id)


async def get_queue_metrics(cache: Any) -> dict[str, Any]:
    """Inspect active/pending broadcast jobs stored in Redis."""
    active_jobs: list[dict[str, Any]] = []
    pending_count = 0
    redis = getattr(cache, "_redis", None) if cache else None
    if redis is not None:
        try:
            if hasattr(redis, "llen"):
                pending_count = int(await redis.llen(QUEUE_PENDING_KEY) or 0)
            if hasattr(redis, "smembers"):
                active_ids = await redis.smembers(QUEUE_ACTIVE_SET_KEY) or set()
                for raw_id in list(active_ids)[:20]:
                    jid = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
                    job = await _load_job(cache, jid)
                    if job:
                        active_jobs.append({
                            "job_id": jid,
                            "kind": job.get("kind"),
                            "status": job.get("status"),
                            "cursor_idx": int(job.get("cursor_idx") or 0),
                            "total": len(job.get("recipient_ids") or []),
                            "ok": int(job.get("ok") or 0),
                            "fail": int(job.get("fail") or 0),
                        })
        except Exception as exc:
            logger.debug("Queue metrics lookup error: %s", exc)
    return {
        "pending_queue_len": pending_count,
        "in_process_running": len(_RUNNING_JOB_IDS),
        "active_jobs": active_jobs,
    }


async def recover_pending_broadcasts(
    bot: Any,
    session_factory: Any = None,
    cache: Any = None,
) -> int:
    """Resume any unfinished Redis broadcast jobs left running/queued before a container restart."""
    redis = getattr(cache, "_redis", None) if cache else None
    if redis is None or not hasattr(redis, "smembers"):
        return 0

    resumed = 0
    try:
        raw_ids = await redis.smembers(QUEUE_ACTIVE_SET_KEY) or set()
        for raw_id in raw_ids:
            jid = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
            if jid in _RUNNING_JOB_IDS:
                continue
            job = await _load_job(cache, jid)
            if not job or job.get("status") not in ("queued", "running"):
                await redis.srem(QUEUE_ACTIVE_SET_KEY, jid)
                continue
            recipients = job.get("recipient_ids") or []
            if int(job.get("cursor_idx") or 0) >= len(recipients):
                job["status"] = "finished"
                await save_broadcast_job(cache, job)
                continue

            if job.get("kind") == "bot":
                from bot.handlers.admin_broadcast import (
                    ACTIVE_BROADCASTS,
                    _on_recovered_bot_complete,
                    _sync_bot_status,
                )
                ACTIVE_BROADCASTS[jid] = {
                    "status": "running",
                    "sent": [(int(p[0]), int(p[1])) for p in (job.get("sent") or []) if len(p) == 2],
                    "ok": int(job.get("ok") or 0),
                    "fail": int(job.get("fail") or 0),
                    "total": len(recipients),
                    "target": job.get("target", "all"),
                    "admin_id": int(job.get("admin_id") or 0),
                }

                async def _sync_bot(j: dict[str, Any], _done: bool, _bid=jid):
                    await _sync_bot_status(bot, _bid)

                async def _done_bot(j: dict[str, Any]):
                    await _on_recovered_bot_complete(bot, session_factory, j)

                t = asyncio.create_task(
                    execute_broadcast_job(
                        bot,
                        job,
                        cache=cache,
                        in_memory_ref=ACTIVE_BROADCASTS[jid],
                        sync_status_fn=_sync_bot,
                        on_complete=_done_bot,
                    ),
                    name=f"resume-bot-broadcast-{jid}",
                )
            else:
                from bot.web.admin_campaigns import _BROADCAST_STATUSES
                _BROADCAST_STATUSES[jid] = {
                    "id": jid,
                    "target": job.get("target", "all"),
                    "target_label": job.get("target_label", ""),
                    "total": len(recipients),
                    "sent": int(job.get("ok") or 0),
                    "failed": int(job.get("fail") or 0),
                    "is_completed": False,
                    "start_time": job.get("start_time") or datetime.now(timezone.utc).isoformat(),
                }

                async def _sync_web(j: dict[str, Any], _done: bool, _wid=jid):
                    if cache and hasattr(cache, "set") and _wid in _BROADCAST_STATUSES:
                        await cache.set(f"bcast:{_wid}", _BROADCAST_STATUSES[_wid], ttl_seconds=86400)

                t = asyncio.create_task(
                    execute_broadcast_job(
                        bot,
                        job,
                        cache=cache,
                        in_memory_ref=_BROADCAST_STATUSES[jid],
                        sync_status_fn=_sync_web,
                    ),
                    name=f"resume-web-broadcast-{jid}",
                )

            _ACTIVE_TASK_REGISTRY.add(t)
            t.add_done_callback(_ACTIVE_TASK_REGISTRY.discard)
            resumed += 1
            logger.info("Resumed unfinished %s broadcast %s from cursor %s/%s", job.get("kind"), jid, job.get("cursor_idx"), len(recipients))
    except Exception as exc:
        logger.warning("Broadcast queue recovery failed: %s", exc)
    return resumed
