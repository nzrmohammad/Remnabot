"""Common text parsing and sanitization utilities."""

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


async def check_channel_membership(bot, channel: str, user_id: int) -> bool:
    """Check if user is a member of the specified channel.

    Returns True if member or if check cannot be performed (failsafe).
    """
    if not bot or not channel:
        return True
    clean_channel = channel.strip()
    if clean_channel.startswith("https://t.me/"):
        clean_channel = "@" + clean_channel.removeprefix("https://t.me/").strip("/")
    try:
        member = await bot.get_chat_member(chat_id=clean_channel, user_id=user_id)
        status = getattr(member, "status", None)
        return status in ("creator", "administrator", "member", "restricted")
    except Exception:
        # If bot is not in channel or channel is unreachable, allow user through
        return True
