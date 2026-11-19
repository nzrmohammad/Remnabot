"""Global per-user rate limit (anti-spam / anti-abuse).

Token-bucket per Telegram user: MAX_EVENTS events per WINDOW_SECONDS.
Exceeded updates are dropped early (before DB/FSM work). Callbacks get a
"too fast" toast; messages are silently ignored.

Limits are generous for normal tapping; only floods hit them.
"""
import logging
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject, Update

logger = logging.getLogger(__name__)

MAX_EVENTS = 30
WINDOW_SECONDS = 60.0

_buckets: dict[int, deque[float]] = defaultdict(deque)


def _extract_user_and_inner(
    event: TelegramObject, data: dict[str, Any]
) -> tuple[int | None, Any, TelegramObject]:
    inner = event
    if isinstance(event, Update):
        inner = (
            event.message
            or event.edited_message
            or event.callback_query
            or event.inline_query
            or event.chosen_inline_result
            or event.pre_checkout_query
            or event.shipping_query
            or event
        )
    user_obj = (
        getattr(inner, "from_user", None)
        or getattr(event, "from_user", None)
        or data.get("event_from_user")
    )
    uid = user_obj.id if user_obj is not None else None
    return uid, user_obj, inner


class RateLimitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        uid, user_obj, inner = _extract_user_and_inner(event, data)
        if uid is None:
            return await handler(event, data)
        # Admins are exempt (broadcasts, approvals).
        try:
            from bot.config import get_settings
            if uid in get_settings().ADMIN_IDS:
                return await handler(event, data)
        except Exception as exc:
            logger.warning("Failed to check admin status in rate_limit: %s", exc)

        now = time.monotonic()
        bucket = _buckets[uid]
        while bucket and now - bucket[0] > WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= MAX_EVENTS:
            logger.warning("rate-limited user %s", uid)
            if isinstance(inner, CallbackQuery):
                try:
                    user_lang = getattr(user_obj, "language_code", "fa") or "fa"
                    toast = "⏳ Too fast — please wait a bit." if user_lang.startswith("en") else "⏳ لطفاً کمی صبور باشید..."
                    await inner.answer(toast, show_alert=False)
                except Exception:
                    pass
            return None
        bucket.append(now)
        # Bound memory: gracefully prune idle users without wiping active limits.
        if len(_buckets) > 10000:
            stale = [u for u, b in _buckets.items() if not b or now - b[-1] > WINDOW_SECONDS]
            for u in stale:
                del _buckets[u]
            if len(_buckets) > 10000:
                for u in list(_buckets.keys())[:2500]:
                    del _buckets[u]
        return await handler(event, data)
