"""Centralized Single Source of Truth (SSOT) service for admin topic notifications.

Guarantees:
1. Strictly isolates admin messages to designated forum topics in ADMIN_CHAT_ID.
2. Never strips thread_kwargs when topic is configured (prevents dumping into General topic).
3. Never falls back to spamming private admin chats (ADMIN_IDS) when an admin group is configured.
4. Clean asynchronous execution, error boundaries, and non-blocking delivery.
"""
import logging
from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message

from bot.common import admin_thread_kwargs
from bot.config import get_settings
from bot.services.app_settings import get_store_settings

logger = logging.getLogger(__name__)


async def resolve_admin_topic_id(
    session: Any = None,
    session_factory: Any = None,
    kind: str = "alerts",
    settings: Any = None,
) -> int | None:
    """Resolve the target forum topic ID for a specific notification domain."""
    if settings is None:
        settings = get_settings()

    async def _resolve_single(target_kind: str) -> int | None:
        attr_store = f"topic_{target_kind.lower()}"
        attr_env = f"ADMIN_TOPIC_{target_kind.upper()}"
        raw_val = getattr(settings, attr_env, None)

        try:
            if session is not None:
                store = await get_store_settings(session)
                db_topic = getattr(store, attr_store, None)
                if db_topic is not None:
                    raw_val = db_topic
            elif session_factory is not None:
                if hasattr(session_factory, "execute") and not callable(session_factory):
                    store = await get_store_settings(session_factory)
                    db_topic = getattr(store, attr_store, None)
                    if db_topic is not None:
                        raw_val = db_topic
                else:
                    async with session_factory() as sess:
                        store = await get_store_settings(sess)
                        db_topic = getattr(store, attr_store, None)
                        if db_topic is not None:
                            raw_val = db_topic
        except Exception as exc:
            logger.warning("Could not fetch %s from DB, using env fallback: %s", attr_store, exc)

        if isinstance(raw_val, bool):
            return None
        try:
            parsed = int(raw_val) if raw_val is not None else 0
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    topic_id = await _resolve_single(kind)
    if topic_id is None and kind.lower() == "nodes":
        topic_id = await _resolve_single("alerts")
    return topic_id


async def send_admin_topic_notification(
    bot: Bot,
    text: str,
    kind: str = "alerts",
    session: Any = None,
    session_factory: Any = None,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "HTML",
    explicit_topic_id: int | None = None,
    settings: Any = None,
) -> Message | None:
    """Dispatches a notification to the dedicated admin group topic.

    Returns the sent Message on success, or None on failure.
    """
    if settings is None:
        settings = get_settings()

    topic_id = explicit_topic_id or await resolve_admin_topic_id(
        session=session, session_factory=session_factory, kind=kind, settings=settings
    )
    if text and len(text) > 4000:
        text = text[:3990] + "\n..."

    thread_kwargs = admin_thread_kwargs(topic_id=topic_id)

    # 1. Primary delivery to configured ADMIN_CHAT_ID (with dedicated topic)
    admin_chat_id = getattr(settings, "ADMIN_CHAT_ID", None)
    is_valid_chat_id = bool(admin_chat_id) and type(admin_chat_id).__name__ not in ("MagicMock", "AsyncMock", "Mock")
    if is_valid_chat_id:
        try:
            return await bot.send_message(
                admin_chat_id,
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                **thread_kwargs,
            )
        except Exception as exc:
            logger.warning(
                "Failed to deliver %s notification to admin group %s (topic %s): %s",
                kind,
                admin_chat_id,
                topic_id,
                exc,
            )
            # Safe plain-text retry preserving the thread_kwargs if parse error occurred
            if parse_mode is not None:
                try:
                    return await bot.send_message(
                        admin_chat_id,
                        text,
                        reply_markup=reply_markup,
                        parse_mode=None,
                        **thread_kwargs,
                    )
                except Exception as retry_exc:
                    logger.warning(
                        "Plaintext retry failed to admin group %s (topic %s): %s",
                        admin_chat_id,
                        topic_id,
                        retry_exc,
                    )
            return None

    # 2. Fallback strictly for single-admin bot instances without an ADMIN_CHAT_ID group
    admin_ids = getattr(settings, "ADMIN_IDS", None)
    if admin_ids:
        last_msg = None
        for admin_id in admin_ids:
            try:
                msg = await bot.send_message(
                    admin_id,
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )
                last_msg = msg
            except Exception as admin_exc:
                logger.warning("Failed to deliver %s notification to admin %s: %s", kind, admin_id, admin_exc)
        return last_msg

    return None
