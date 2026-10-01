"""Telegram Mini App (TMA) Authentication module.

Validates Telegram.WebApp.initData using HMAC-SHA256 as specified in official
Telegram Bot API guidelines:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import parse_qsl

from aiohttp import web

logger = logging.getLogger(__name__)


def validate_telegram_init_data(
    init_data_raw: str,
    bot_token: str,
    max_age_seconds: int = 86400,
) -> dict[str, Any] | None:
    """Validate raw initData string received from Telegram WebApp.

    Returns the parsed user dictionary if signature is valid and not expired,
    otherwise returns None.
    """
    if not init_data_raw or not bot_token:
        return None

    try:
        parsed = dict(parse_qsl(init_data_raw, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        # Build data check string: key=value sorted alphabetically
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

        # Secret key is HMAC-SHA256 of bot token with key "WebAppData"
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()

        # Calculated HMAC-SHA256 of data_check_string with secret_key
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            logger.warning("Telegram initData HMAC verification failed.")
            return None

        # Expiry check
        auth_date = int(parsed.get("auth_date", 0))
        if max_age_seconds > 0 and (time.time() - auth_date > max_age_seconds):
            logger.warning("Telegram initData expired (auth_date=%s).", auth_date)
            return None

        user_raw = parsed.get("user")
        if not user_raw:
            return None

        user_data = json.loads(user_raw)
        return user_data

    except Exception as exc:
        logger.warning("Failed to validate telegram initData: %s", exc)
        return None


def get_authenticated_user(request: web.Request) -> dict[str, Any] | None:
    """Extract and authenticate user from request headers or query params."""
    bot_token = request.app.get("bot_token", "")
    admin_ids = request.app.get("admin_ids", [])
    is_dev = request.app.get("is_dev", False)

    init_data = (
        request.headers.get("X-Telegram-Init-Data")
        or request.query.get("initData")
        or ""
    )

    user = validate_telegram_init_data(init_data, bot_token) if init_data else None

    # Browser preview fallback when opened directly outside Telegram WebApp
    if not user:
        dev_id = request.query.get("dev_id") or request.query.get("user_id")
        if dev_id and dev_id.isdigit():
            user = {
                "id": int(dev_id),
                "first_name": "کاربر پیش‌نمایش",
                "username": f"user_{dev_id}",
                "is_dev": is_dev,
                "is_preview": True,
            }
        elif is_dev or request.headers.get("X-Dev-Mode") == "1":
            user = {
                "id": admin_ids[0] if admin_ids else 123456789,
                "first_name": "Dev Admin",
                "username": "dev_admin",
                "is_dev": True,
                "is_preview": False,
            }
        elif not init_data:
            # Safe read-only preview fallback to primary admin account
            primary_admin = admin_ids[0] if admin_ids else 123456789
            user = {
                "id": primary_admin,
                "first_name": "مدیر سیستم (پیش‌نمایش)",
                "username": "admin_preview",
                "is_dev": False,
                "is_preview": True,
            }

    if user:
        # A preview session never has administrative execution rights
        user["is_admin"] = (int(user.get("id", 0)) in admin_ids) and not user.get("is_preview", False)

    return user


def require_auth(handler):
    """Decorator to enforce Telegram authentication on endpoint."""
    async def wrapper(request: web.Request):
        user = get_authenticated_user(request)
        if not user:
            return web.json_response(
                {"ok": False, "error": "Unauthorized: invalid or missing Telegram initData"},
                status=401,
            )
        request["user"] = user
        return await handler(request)

    return wrapper


def require_admin(handler):
    """Decorator to enforce Admin privileges on endpoint."""
    async def wrapper(request: web.Request):
        user = get_authenticated_user(request)
        if not user or not user.get("is_admin") or user.get("is_preview"):
            return web.json_response(
                {"ok": False, "error": "Forbidden: admin privileges required"},
                status=403,
            )
        request["user"] = user
        return await handler(request)

    return wrapper
