"""Report delivery and message chunking helpers."""
import logging
import re

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, admin_thread_kwargs
from bot.config import get_settings
from bot.services.app_settings import get_store_settings

logger = logging.getLogger(__name__)


def _chunk_text(text: str, max_chars: int = 3800) -> list[str]:
    """Splits a long report into chunks <= max_chars, breaking on SEPARATOR or newlines."""
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    parts = text.split(f"\n{SEPARATOR}\n")
    for i, part in enumerate(parts):
        part_text = part if i == 0 else f"{SEPARATOR}\n{part}"
        if current_len + len(part_text) + 1 <= max_chars:
            current.append(part_text)
            current_len += len(part_text) + 1
        else:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0

            if len(part_text) > max_chars:
                lines = part_text.split("\n")
                line_chunk: list[str] = []
                line_chunk_len = 0
                for line in lines:
                    if line_chunk_len + len(line) + 1 <= max_chars:
                        line_chunk.append(line)
                        line_chunk_len += len(line) + 1
                    else:
                        if line_chunk:
                            chunks.append("\n".join(line_chunk))
                        line_chunk = [line]
                        line_chunk_len = len(line)
                if line_chunk:
                    chunks.append("\n".join(line_chunk))
            else:
                current.append(part_text)
                current_len = len(part_text)

    if current:
        chunks.append("\n".join(current))
    return chunks


import json
from typing import Any


async def _safe_send_message(bot: Bot, chat_id: int, text: str, **kwargs) -> Any:
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except Exception as exc:
        logger.warning("Failed sending message to %s: %s", chat_id, exc)
        err_msg = str(exc).lower()
        if "entity" in err_msg or "parse" in err_msg or "html" in err_msg:
            try:
                plain_text = re.sub(r"<[^>]+>", "", text)
                clean_kwargs = {k: v for k, v in kwargs.items() if k != "parse_mode"}
                return await bot.send_message(chat_id, plain_text, parse_mode=None, **clean_kwargs)
            except Exception as retry_exc:
                logger.warning("Failed plain-text retry to %s: %s", chat_id, retry_exc)
        raise exc


async def _deliver_admin_report(
    bot: Bot,
    session: AsyncSession,
    text: str,
    target_user_id: int | None = None,
    kind: str = "general",
) -> None:
    settings = get_settings()
    store = await get_store_settings(session)
    thread_kwargs = admin_thread_kwargs(store, settings, kind="reports")
    if not thread_kwargs:
        thread_kwargs = admin_thread_kwargs(store, settings, kind="alerts")
    topic_id = thread_kwargs.get("message_thread_id")

    from bot.db.repositories.app_setting_repo import AppSettingRepository

    app_repo = AppSettingRepository(session)

    # 1. Clean previous admin reports for this specific kind to avoid chat clutter
    clean_key = f"last_admin_report_msg_ids_{kind}"
    if target_user_id:
        clean_key = f"last_admin_report_msg_ids_{kind}_{target_user_id}"

    try:
        prev_raw = await app_repo.get(clean_key)
        if prev_raw:
            prev_records = json.loads(prev_raw)
            for c_id, m_id in prev_records:
                try:
                    await bot.delete_message(chat_id=c_id, message_id=m_id)
                except Exception:
                    pass
    except Exception as clean_err:
        logger.debug("Failed cleaning previous admin report messages: %s", clean_err)

    new_sent_records: list[list[int]] = []
    chunks = _chunk_text(text)
    for chunk in chunks:
        delivered_to_group = False
        if settings.ADMIN_CHAT_ID:
            try:
                msg = await _safe_send_message(bot, settings.ADMIN_CHAT_ID, chunk, **thread_kwargs)
                if msg:
                    new_sent_records.append([settings.ADMIN_CHAT_ID, msg.message_id])
                delivered_to_group = True
            except Exception as exc:
                logger.warning(
                    "Admin report delivery to chat %s (topic %s) failed: %s",
                    settings.ADMIN_CHAT_ID,
                    topic_id,
                    exc,
                )
                if thread_kwargs:
                    try:
                        msg = await _safe_send_message(bot, settings.ADMIN_CHAT_ID, chunk)
                        if msg:
                            new_sent_records.append([settings.ADMIN_CHAT_ID, msg.message_id])
                        delivered_to_group = True
                    except Exception as fallback_exc:
                        logger.warning(
                            "Admin report delivery to chat %s without thread also failed: %s",
                            settings.ADMIN_CHAT_ID,
                            fallback_exc,
                        )

        if target_user_id:
            try:
                msg = await _safe_send_message(bot, target_user_id, chunk)
                if msg:
                    new_sent_records.append([target_user_id, msg.message_id])
            except Exception as direct_exc:
                logger.warning("Admin report direct delivery to admin %s failed: %s", target_user_id, direct_exc)

        if not delivered_to_group and settings.ADMIN_IDS:
            for aid in settings.ADMIN_IDS:
                if aid == target_user_id:
                    continue
                try:
                    msg = await _safe_send_message(bot, aid, chunk)
                    if msg:
                        new_sent_records.append([aid, msg.message_id])
                except Exception as admin_exc:
                    logger.warning("Admin report fallback to admin %s failed: %s", aid, admin_exc)

    if new_sent_records:
        try:
            await app_repo.set(clean_key, json.dumps(new_sent_records))
            await session.commit()
        except Exception as save_err:
            logger.debug("Failed saving admin report message ids: %s", save_err)

