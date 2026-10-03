"""Common text parsing and sanitization utilities."""
import sys

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def parse_int(text: str) -> int | None:
    """Parse integer from Persian/Arabic/English text, stripping commas and whitespace."""
    if not text:
        return None
    cleaned = text.translate(_DIGIT_MAP).replace(",", "").replace("،", "").strip()
    if not cleaned.isdigit() and not (cleaned.startswith("-") and cleaned[1:].isdigit()):
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def resolve_op(name: str, fallback):
    """Resolve an operation or repository from handler modules if patched by tests."""
    for mod_name in (
        "bot.handlers.admin",
        "bot.handlers.admin_ops",
        "bot.handlers.admin_settings",
        "bot.handlers.admin_users",
        "bot.handlers.admin_orders",
        "bot.handlers.service_request",
        "bot.handlers.wallet",
    ):
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, name):
            val = getattr(mod, name)
            if val is not fallback:
                return val
    return fallback


def get_used_bytes(u: dict) -> int:
    """Safely extract used traffic bytes from a panel user payload."""
    if isinstance(u.get("userTraffic"), dict):
        try:
            return int(u["userTraffic"].get("usedTrafficBytes") or 0)
        except (ValueError, TypeError):
            pass
    try:
        return int(u.get("usedTrafficBytes") or 0)
    except (ValueError, TypeError):
        return 0


def get_limit_bytes(u: dict) -> int:
    """Safely extract traffic limit bytes from a panel user payload."""
    try:
        return int(u.get("trafficLimitBytes") or 0)
    except (ValueError, TypeError):
        return 0


def get_online_at(u: dict):
    """Safely parse onlineAt ISO timestamp from a panel user payload."""
    from datetime import datetime
    online_str = None
    if isinstance(u.get("userTraffic"), dict):
        online_str = u["userTraffic"].get("onlineAt")
    if not online_str:
        online_str = u.get("onlineAt")
    if not online_str:
        return None
    try:
        return datetime.fromisoformat(str(online_str).replace("Z", "+00:00"))
    except Exception:
        return None
