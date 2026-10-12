"""Centralized Telegram deep link generators."""


def ref_link(bot_username: str | None, user_id: int | str) -> str:
    """Generate a referral start deep link for the Telegram bot."""
    uid = str(user_id or "").strip()
    if bot_username:
        clean = bot_username.lstrip("@").strip()
        return f"https://t.me/{clean}?start=ref_{uid}"
    return f"https://t.me/?start=ref_{uid}"


def ad_link(bot_username: str | None, code: str) -> str:
    """Generate an advertising campaign start deep link for the Telegram bot."""
    c = str(code or "").strip()
    if bot_username:
        clean = bot_username.lstrip("@").strip()
        return f"https://t.me/{clean}?start=ad_{c}"
    return f"https://t.me/?start=ad_{c}"


__all__ = ["ref_link", "ad_link"]
