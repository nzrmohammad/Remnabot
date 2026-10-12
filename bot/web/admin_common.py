"""Shared helper utilities and authentication guards for Admin Mini App API."""
import re
from typing import Any

from aiohttp import web

from bot.web.auth import get_authenticated_user
from bot.web.db import db_session

EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff]|[\u200d\u200c\u2600-\u27bf\u2300-\u23ff\u2b50-\u2b55\u203c-\u2049\u2122\u2139\u24c2\u3030\u303d\u3297\u3299]"
)


def _check_admin(request: web.Request) -> dict[str, Any] | None:
    """Validate admin authorization for TMA requests."""
    user = get_authenticated_user(request)
    if not user or not user.get("is_admin"):
        return None
    return user


def format_service_name_icon_first(name: str | None) -> str:
    """Format service name to place the icon on the visual left in RTL charts."""
    if not name:
        return "\u200e💎 پلن"
    raw = str(name).strip()
    emojis = "".join(EMOJI_PATTERN.findall(raw)).strip()
    clean_text = EMOJI_PATTERN.sub("", raw).strip()
    if not emojis:
        emojis = "💎"
    return f"\u200e{emojis} {clean_text}" if clean_text else emojis
