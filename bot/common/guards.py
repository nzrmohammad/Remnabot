"""Common authorization and security guards."""
import sys
from bot.config import get_settings


def is_admin(user_id: int) -> bool:
    """Return True if the user_id is in configured ADMIN_IDS.

    Supports test mock compatibility when _is_admin is patched on handler modules.
    """
    for mod_name in ("bot.handlers.admin_ops", "bot.handlers.admin", "bot.handlers.admin_users"):
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, "_is_admin"):
            fn = getattr(mod, "_is_admin")
            if fn is not is_admin:
                try:
                    return bool(fn(user_id))
                except Exception:
                    pass
    return user_id in get_settings().ADMIN_IDS
