"""Common authorization and security guards."""
from bot.config import get_settings


def is_admin(user_id: int) -> bool:
    """Return True if the user_id is in configured ADMIN_IDS."""
    return user_id in get_settings().ADMIN_IDS


def safe_split_cb(data: str | None, min_parts: int, separator: str = ":") -> list[str] | None:
    """Safely split callback data and assert minimum number of parts.

    Returns the list of parts if length >= min_parts, otherwise None.
    """
    if not data or not isinstance(data, str):
        return None
    parts = data.split(separator)
    if len(parts) < min_parts:
        return None
    return parts
