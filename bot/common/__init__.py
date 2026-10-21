def is_admin(user_id: int) -> bool:
    from bot.common import guards
    return guards.is_admin(user_id)


def safe_split_cb(data: str | None, min_parts: int, separator: str = ":") -> list[str] | None:
    from bot.common import guards
    return guards.safe_split_cb(data, min_parts, separator)


from bot.common.helpers import get_limit_bytes, get_online_at, get_used_bytes, parse_int
from bot.common.links import ad_link, ref_link
from bot.common.ui import (
    SEPARATOR,
    _back_admin,
    admin_thread_kwargs,
    back_admin_builder,
    fmt,
)

__all__ = [
    "is_admin",
    "safe_split_cb",
    "SEPARATOR",
    "parse_int",
    "fmt",
    "admin_thread_kwargs",
    "get_used_bytes",
    "get_limit_bytes",
    "get_online_at",
    "ref_link",
    "ad_link",
    "back_admin_builder",
    "_back_admin",
]
