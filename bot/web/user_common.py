"""Shared helper utilities and authentication guards for User Mini App API."""
from typing import Any

from aiohttp import web

from bot.web.auth import get_authenticated_user, get_client_ip, require_auth, resolve_cached_auth
from bot.web.db import db_session


def format_support_link(raw_contact: str) -> str:
    """Normalize Telegram username/URL into a clickable https support URL."""
    raw = (raw_contact or "").strip()
    if not raw or raw in ("—", "-"):
        return ""
    if raw.startswith(("http://", "https://")):
        return raw
    if raw.startswith("t.me/"):
        return f"https://{raw}"
    if raw.startswith("@"):
        return f"https://t.me/{raw[1:]}"
    return f"https://t.me/{raw}"


def _check_user(request: web.Request) -> dict[str, Any] | None:
    """Validate user authorization for TMA requests (reusing cached middleware auth)."""
    return resolve_cached_auth(request, get_authenticated_user)


def require_user(request: web.Request) -> tuple[dict[str, Any] | None, web.Response | None]:
    """Helper returning (user, None) or (None, 401/403 response)."""
    user = _check_user(request)
    if not user:
        return None, web.json_response(
            {"ok": False, "error": "Unauthorized"},
            status=401,
        )

    # Check ban status from request or user auth dictionary
    is_banned = request.get("is_banned")
    if is_banned is None:
        is_banned = user.get("is_banned")

    if is_banned:
        return None, web.json_response(
            {
                "ok": False,
                "error": "banned",
                "message": "حساب کاربری شما مسدود شده است.",
            },
            status=403,
        )
    return user, None


def is_user_invited(db_user: Any, panel_users: list | None = None) -> bool:
    """Return True if an existing user is admitted under invite-only mode."""
    if db_user is not None and (
        getattr(db_user, "referred_by_id", None)
        or getattr(db_user, "campaign_code", None)
        or getattr(db_user, "is_verified", False)
    ):
        return True
    if panel_users:
        return any(str(u.get("status") or "").upper() != "DELETED" for u in panel_users)
    return False


async def enforce_invite_only(
    session: Any,
    telegram_id: int,
    user_auth: dict[str, Any],
    remnawave: Any = None,
    store: Any = None,
) -> web.Response | None:
    """Block uninvited users on mutating TMA actions when access_mode == 'invite_only'."""
    from sqlalchemy.ext.asyncio import AsyncSession

    if user_auth.get("is_admin", False):
        return None
    if not isinstance(session, AsyncSession):
        return None

    from bot.db.repositories.user_repo import UserRepository
    from bot.services.app_settings import get_store_settings

    if store is None:
        store = await get_store_settings(session)
    if getattr(store, "access_mode", "open") != "invite_only":
        return None

    db_user = await UserRepository(session).get_by_telegram_id(telegram_id)
    if is_user_invited(db_user):
        return None

    if remnawave is not None:
        try:
            panel_users = await remnawave.get_users_by_telegram_id(telegram_id)
            if is_user_invited(db_user, panel_users):
                return None
        except Exception:
            pass

    return web.json_response(
        {
            "ok": False,
            "error": "invite_only",
            "message": "عضویت در این سرویس فقط با لینک دعوت معتبر امکان‌پذیر است.",
        },
        status=403,
    )


__all__ = [
    "_check_user",
    "require_user",
    "require_auth",
    "get_client_ip",
    "db_session",
    "is_user_invited",
    "enforce_invite_only",
]
