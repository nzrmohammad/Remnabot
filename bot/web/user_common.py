"""Shared helper utilities and authentication guards for User Mini App API."""
from typing import Any

from aiohttp import web

from bot.web.auth import get_authenticated_user, get_client_ip, require_auth
from bot.web.db import db_session


def _check_user(request: web.Request) -> dict[str, Any] | None:
    """Validate user authorization for TMA requests."""
    return request.get("user") or get_authenticated_user(request)


def require_user(request: web.Request) -> tuple[dict[str, Any] | None, web.Response | None]:
    """Helper returning (user, None) or (None, 401 response)."""
    user = _check_user(request)
    if not user:
        return None, web.json_response(
            {"ok": False, "error": "Unauthorized"},
            status=401,
        )
    return user, None


__all__ = ["_check_user", "require_user", "require_auth", "get_client_ip", "db_session"]
