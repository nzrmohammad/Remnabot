def is_admin(user_id: int) -> bool:
    from bot.common import guards
    return guards.is_admin(user_id)


from bot.common.helpers import get_limit_bytes, get_online_at, get_used_bytes, parse_int
from bot.common.links import ad_link, ref_link
from bot.common.ui import SEPARATOR, admin_thread_kwargs, fmt

__all__ = [
    "is_admin",
    "SEPARATOR",
    "parse_int",
    "fmt",
    "admin_thread_kwargs",
    "get_used_bytes",
    "get_limit_bytes",
    "get_online_at",
    "ref_link",
    "ad_link",
]
