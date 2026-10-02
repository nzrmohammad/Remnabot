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


@pytest.mark.anyio
async def test_auth_browser_preview_fallback():
    from bot.web.auth import get_authenticated_user
    from aiohttp.test_utils import make_mocked_request

    # 1. In production (is_dev=False), unauthenticated requests MUST be rejected (returns None)
    app_prod = {
        "bot_token": "123:abc",
        "admin_ids": [55555],
        "is_dev": False,
    }
    req_prod = make_mocked_request("GET", "/api/user/me", app=app_prod)
    assert get_authenticated_user(req_prod) is None

    req_prod_id = make_mocked_request("GET", "/api/user/me?user_id=88888", app=app_prod)
    assert get_authenticated_user(req_prod_id) is None

    # 2. In dev mode (is_dev=True), preview fallback is permitted
    app_dev = {
        "bot_token": "123:abc",
        "admin_ids": [55555],
        "is_dev": True,
    }
    req_dev = make_mocked_request("GET", "/api/user/me", app=app_dev)
    user_dev = get_authenticated_user(req_dev)
    assert user_dev is not None
    assert user_dev["id"] == 55555

    req_dev_custom = make_mocked_request("GET", "/api/user/me?user_id=88888", app=app_dev)
    user_custom = get_authenticated_user(req_dev_custom)
    assert user_custom is not None
    assert user_custom["id"] == 88888


@pytest.mark.anyio
async def test_user_me_dashboard_with_panel_user():
    from bot.web.routes_user import get_user_me
    from aiohttp.test_utils import make_mocked_request
    from unittest.mock import AsyncMock

    mock_remnawave = AsyncMock()
    mock_remnawave.get_users_by_telegram_id.return_value = [
        {
            "id": 101,
            "username": "client_vpn",
            "status": "ACTIVE",
            "trafficLimitBytes": 10 * 1024 * 1024 * 1024,
            "usedTrafficBytes": 2 * 1024 * 1024 * 1024,
            "expireAt": "2026-11-20T10:00:00.000Z",
            "subscriptionUrl": "https://sub.domain/xyz",
        }
    ]
    mock_remnawave.get_user_today_usage.return_value = (500 * 1024 * 1024, [])
    mock_remnawave.get_user_hwid_devices.return_value = [{"hwid": "hwid1", "platform": "android"}]

    mock_db_user = MagicMock()
    mock_db_user.created_at = None

    class MockUserRepo:
        def __init__(self, s): pass
        async def get_or_create(self, tid, username): return mock_db_user

    class MockSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def execute(self, stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = None
            m.scalar_one.return_value = 0
            m.scalars.return_value.all.return_value = []
            return m

    def session_factory():
        return MockSession()

    from unittest.mock import patch
    with patch("bot.web.routes_user.UserRepository", MockUserRepo):
        app = {
            "bot_token": "123:abc",
            "admin_ids": [55555],
            "is_dev": True,
            "remnawave": mock_remnawave,
            "session_factory": session_factory,
            "settings": MagicMock(TIMEZONE="Asia/Tehran"),
            "cache": FastCache(redis_client=None),
        }

        req = make_mocked_request("GET", "/api/user/me?user_id=77777", app=app)
        resp = await get_user_me(req)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["ok"] is True
        assert data["data"]["has_active_sub"] is True
        sub = data["data"]["active_sub"]
        assert sub["traffic_total_gb"] == 10.0
        assert sub["traffic_used_gb"] == 2.0
        assert sub["traffic_remaining_gb"] == 8.0
        assert sub["devices_count"] == 1
        assert sub["subscription_url"] == "https://sub.domain/xyz"


@pytest.mark.anyio
async def test_user_validate_coupon_endpoint():
    from bot.web.routes_user import post_user_validate_coupon
    from aiohttp.test_utils import make_mocked_request
    from unittest.mock import AsyncMock, patch

    mock_coupon = MagicMock(code="OFF20", discount_percent=20, discount_amount=0)
    mock_coupon_repo = MagicMock()
    mock_coupon_repo.validate_coupon = AsyncMock(return_value=(True, None, 20))
    mock_coupon_repo.get_by_code = AsyncMock(return_value=mock_coupon)

    class MockSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

    def session_factory():
        return MockSession()

    with patch("bot.db.repositories.coupon_repo.CouponRepository", return_value=mock_coupon_repo):
        app = {
            "bot_token": "123:abc",
            "is_dev": True,
            "session_factory": session_factory,
            "cache": FastCache(redis_client=None),
        }
        req = make_mocked_request(
            "POST",
            "/api/user/validate_coupon?user_id=77777",
            headers={"Content-Type": "application/json"},
            app=app,
        )
        req.json = AsyncMock(return_value={"code": "OFF20"})
        resp = await post_user_validate_coupon(req)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["ok"] is True
        assert data["data"]["code"] == "OFF20"
        assert data["data"]["discount_percent"] == 20


@pytest.mark.anyio
async def test_user_topup_info_endpoint():
    from bot.web.routes_user import get_user_topup_info
    from aiohttp.test_utils import make_mocked_request
    from unittest.mock import AsyncMock, patch

    mock_store = MagicMock(
        topup_min_amount=50000,
        card_enabled=True,
        card_number="6037991823456789",
        card_holder="John Doe",
        crypto_enabled=True,
        ton_wallet_address="EQB...",
        ton_rate_toman=600000,
    )

    class MockSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

    def session_factory():
        return MockSession()

    with patch("bot.services.app_settings.get_store_settings", AsyncMock(return_value=mock_store)):
        app = {
            "is_dev": True,
            "session_factory": session_factory,
        }
        req = make_mocked_request("GET", "/api/user/topup_info?user_id=77777", app=app)
        resp = await get_user_topup_info(req)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["ok"] is True
        assert data["card_enabled"] is True
        assert data["card_number"] == "6037991823456789"
        assert data["ton_rate_toman"] == 600000


