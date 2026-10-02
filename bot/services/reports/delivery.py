"""Report delivery and message chunking helpers."""
import logging
import re

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR
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


async def _safe_send_message(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except Exception as exc:
        err_msg = str(exc).lower()
        if "entity" in err_msg or "parse" in err_msg or "html" in err_msg:
            try:
                plain_text = re.sub(r"<[^>]+>", "", text)
                clean_kwargs = {k: v for k, v in kwargs.items() if k != "parse_mode"}
                await bot.send_message(chat_id, plain_text, parse_mode=None, **clean_kwargs)
                return True
            except Exception as retry_exc:
                logger.warning("Failed plain-text retry to %s: %s", chat_id, retry_exc)
        raise exc


async def _deliver_admin_report(
    bot: Bot, session: AsyncSession, text: str, target_user_id: int | None = None
) -> None:
    settings = get_settings()
    store = await get_store_settings(session)
    topic_id = store.topic_alerts if store.topic_alerts is not None else settings.ADMIN_TOPIC_ALERTS
    thread_kwargs = {"message_thread_id": topic_id} if topic_id else {}

    chunks = _chunk_text(text)
    for chunk in chunks:
        delivered_to_group = False
        if settings.ADMIN_CHAT_ID:
            try:
                await _safe_send_message(bot, settings.ADMIN_CHAT_ID, chunk, **thread_kwargs)
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
                        await _safe_send_message(bot, settings.ADMIN_CHAT_ID, chunk)
                        delivered_to_group = True
                    except Exception as fallback_exc:
                        logger.warning(
                            "Admin report delivery to chat %s without thread also failed: %s",
                            settings.ADMIN_CHAT_ID,
                            fallback_exc,
                        )

        if target_user_id:
            try:
                await _safe_send_message(bot, target_user_id, chunk)
            except Exception as direct_exc:
                logger.warning("Admin report direct delivery to admin %s failed: %s", target_user_id, direct_exc)

        if not delivered_to_group and settings.ADMIN_IDS:
            for aid in settings.ADMIN_IDS:
                if aid == target_user_id:
                    continue
                try:
                    await _safe_send_message(bot, aid, chunk)
                except Exception as admin_exc:
                    logger.warning("Admin report fallback to admin %s failed: %s", aid, admin_exc)
