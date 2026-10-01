"""Tests for Telegram Mini App (TMA) Web Service and HMAC Auth."""
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from bot.keyboards.inline import main_menu_keyboard
from bot.web.auth import validate_telegram_init_data
from bot.web.cache import FastCache
from bot.web.server import create_web_app


def generate_valid_init_data(bot_token: str, user_dict: dict, auth_date: int = None) -> str:
    """Helper to generate a cryptographically valid Telegram initData string."""
    if auth_date is None:
        auth_date = int(time.time())

    user_json = json.dumps(user_dict, separators=(",", ":"))
    params = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": user_json,
    }

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    hash_val = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    encoded_params = [f"{k}={v}" for k, v in params.items()]
    encoded_params.append(f"hash={hash_val}")
    return "&".join(encoded_params)


def test_hmac_validation_valid():
    bot_token = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
    user_payload = {"id": 987654, "first_name": "Ali", "username": "ali98"}

    valid_init_data = generate_valid_init_data(bot_token, user_payload)
    parsed_user = validate_telegram_init_data(valid_init_data, bot_token)

    assert parsed_user is not None
    assert parsed_user["id"] == 987654
    assert parsed_user["first_name"] == "Ali"


def test_hmac_validation_tampered():
    bot_token = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
    user_payload = {"id": 987654, "first_name": "Ali"}

    valid_init_data = generate_valid_init_data(bot_token, user_payload)
    # Tamper with the user ID
    tampered = valid_init_data.replace("987654", "111111")
    parsed_user = validate_telegram_init_data(tampered, bot_token)

    assert parsed_user is None


def test_hmac_validation_expired():
    bot_token = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
    user_payload = {"id": 987654, "first_name": "Ali"}

    # 2 days old
    old_time = int(time.time()) - 172800
    expired_init_data = generate_valid_init_data(bot_token, user_payload, auth_date=old_time)
    parsed_user = validate_telegram_init_data(expired_init_data, bot_token, max_age_seconds=86400)

    assert parsed_user is None


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_fast_cache():
    cache = FastCache(redis_client=None)

    # Set and get
    await cache.set("test:key", {"val": 123}, ttl_seconds=2)
    cached = await cache.get("test:key")
    assert cached == {"val": 123}

    # Delete
    await cache.delete("test:key")
    cached_after = await cache.get("test:key")
    assert cached_after is None


def test_main_menu_keyboard_with_webapp_url():
    # Without web_app_url: regular menu
    kb_no_web = main_menu_keyboard(lang="fa", is_admin=False, web_app_url="")
    all_buttons = [btn.text for row in kb_no_web.inline_keyboard for btn in row]
    assert not any("مینی‌اپ" in b for b in all_buttons)

    # With web_app_url: user button added at top
    kb_web = main_menu_keyboard(lang="fa", is_admin=False, web_app_url="https://app.test.com")
    first_row_btns = kb_web.inline_keyboard[0]
    assert len(first_row_btns) == 1
    assert "مینی‌اپ" in first_row_btns[0].text
    assert first_row_btns[0].web_app.url == "https://app.test.com/app"

    # With admin and web_app_url: admin panel button added
    kb_admin_web = main_menu_keyboard(lang="fa", is_admin=True, web_app_url="https://app.test.com")
    last_row_btns = kb_admin_web.inline_keyboard[-1]
    assert any("پنل وب کلاستر" in btn.text for btn in last_row_btns)
    web_admin_btn = [btn for btn in last_row_btns if "پنل وب کلاستر" in btn.text][0]
    assert web_admin_btn.web_app.url == "https://app.test.com/admin"


@pytest.mark.anyio
async def test_web_app_routes():
    bot = MagicMock()
    session_factory = MagicMock()
    remnawave = MagicMock()
    settings = MagicMock()
    settings.BOT_TOKEN = "123:abc"
    settings.ADMIN_IDS = [12345]

    app = create_web_app(
        bot=bot,
        session_factory=session_factory,
        remnawave=remnawave,
        settings=settings,
        is_dev=True,
    )

    # Verify routes registered
    registered_paths = [r.resource.canonical for r in app.router.routes() if r.resource]
    assert "/health" in registered_paths
    assert "/app" in registered_paths
    assert "/admin" in registered_paths
    assert "/api/user/me" in registered_paths
    assert "/api/user/spin" in registered_paths
    assert "/api/admin/overview" in registered_paths
