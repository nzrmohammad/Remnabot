"""Common authorization and security guards."""
from bot.config import get_settings


def is_admin(user_id: int) -> bool:
    """Return True if the user_id is in configured ADMIN_IDS."""
    return user_id in get_settings().ADMIN_IDS
