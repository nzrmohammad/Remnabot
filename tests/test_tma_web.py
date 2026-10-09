"""Tests for Telegram Mini App (TMA) Web Service and HMAC Auth."""
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

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
    # Regular menu without web app buttons
    kb_no_web = main_menu_keyboard(lang="fa", is_admin=False, web_app_url="")
    all_buttons = [btn.text for row in kb_no_web.inline_keyboard for btn in row]
    assert not any("مینی‌اپ" in b for b in all_buttons)

    # Even with web_app_url, main menu should not have TMA buttons per design
    kb_web = main_menu_keyboard(lang="fa", is_admin=False, web_app_url="https://app.test.com")
    all_web_buttons = [btn.text for row in kb_web.inline_keyboard for btn in row]
    assert not any("مینی‌اپ" in b for b in all_web_buttons)
    assert not any("پنل وب کلاستر" in b for b in all_web_buttons)

    # Admin menu has bot admin panel button
    kb_admin = main_menu_keyboard(lang="fa", is_admin=True, web_app_url="https://app.test.com")
    admin_buttons = [btn.text for row in kb_admin.inline_keyboard for btn in row]
    assert any("مدیریت" in b for b in admin_buttons)
    assert not any("پنل وب کلاستر" in b for b in admin_buttons)


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
    assert "/api/admin/broadcast/status" in registered_paths
    assert "/api/admin/user/reset_trial" in registered_paths


@pytest.mark.anyio
async def test_auth_browser_preview_fallback():
    from aiohttp.test_utils import make_mocked_request

    from bot.web.auth import get_authenticated_user

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
    from aiohttp.test_utils import make_mocked_request

    from bot.web.routes_user import get_user_me

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
    from unittest.mock import patch

    from aiohttp.test_utils import make_mocked_request

    from bot.web.routes_user import post_user_validate_coupon

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
    from unittest.mock import patch

    from aiohttp.test_utils import make_mocked_request

    from bot.web.routes_user import get_user_topup_info

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


@pytest.mark.anyio
async def test_user_topup_card_validation_and_duplicate_prevention():
    from unittest.mock import patch

    from aiohttp.test_utils import make_mocked_request

    from bot.web.user_topup import post_user_topup_card

    mock_store = MagicMock(
        topup_min_amount=10000,
        card_enabled=True,
        topic_topups=None,
    )

    existing_hashes = set()

    class MockWalletRepo:
        def __init__(self, session):
            pass

        async def pending_count(self, telegram_id):
            return 0

        async def receipt_exists(self, receipt_hash):
            return receipt_hash in existing_hashes

        async def create_topup(self, telegram_id, amount, receipt_hash):
            existing_hashes.add(receipt_hash)
            return MagicMock(id=999)

    class MockSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def commit(self): pass

    def session_factory():
        return MockSession()

    mock_bot = AsyncMock()
    mock_settings = MagicMock(ADMIN_CHAT_ID=12345, ADMIN_TOPIC_TOPUPS=None)

    app = {
        "is_dev": True,
        "session_factory": session_factory,
        "bot": mock_bot,
        "settings": mock_settings,
    }

    with patch("bot.web.user_topup.get_store_settings", AsyncMock(return_value=mock_store)), \
         patch("bot.web.user_topup.WalletRepository", MockWalletRepo):
        # 1. Missing receipt text -> 400
        req_empty = make_mocked_request(
            "POST", "/api/user/topup/card?user_id=77777",
            headers={"Content-Type": "application/json"},
            app=app,
        )
        req_empty.json = AsyncMock(return_value={"amount": 20000, "receipt_text": "   "})
        resp = await post_user_topup_card(req_empty)
        assert resp.status == 400
        assert "شماره پیگیری" in json.loads(resp.text)["message"]

        # 2. First submission -> 200 OK
        req_valid = make_mocked_request(
            "POST", "/api/user/topup/card?user_id=77777",
            headers={"Content-Type": "application/json"},
            app=app,
        )
        req_valid.json = AsyncMock(return_value={"amount": 20000, "receipt_text": "TRX-123456789"})
        resp1 = await post_user_topup_card(req_valid)
        assert resp1.status == 200
        assert json.loads(resp1.text)["ok"] is True

        # 3. Duplicate submission with same receipt -> 400 Rejected
        req_dup = make_mocked_request(
            "POST", "/api/user/topup/card?user_id=77777",
            headers={"Content-Type": "application/json"},
            app=app,
        )
        req_dup.json = AsyncMock(return_value={"amount": 20000, "receipt_text": "  TRX-123456789  "})
        resp2 = await post_user_topup_card(req_dup)
        assert resp2.status == 400
        data2 = json.loads(resp2.text)
        assert data2["ok"] is False
        assert "قبلاً ثبت شده است" in data2["message"]


@pytest.mark.anyio
async def test_user_settings_persistence():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base
    from bot.web.user_nodes import post_user_settings
    from bot.web.routes_user import get_user_me

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = {
        "bot_token": "123:abc",
        "admin_ids": [55555],
        "is_dev": True,
        "session_factory": session_factory,
        "cache": FastCache(redis_client=None),
        "remnawave": AsyncMock(get_users_by_telegram_id=AsyncMock(return_value=[])),
        "settings": MagicMock(TIMEZONE="Asia/Tehran"),
    }

    # 1. Update settings: toggle nightly=False
    req = make_mocked_request("POST", "/api/user/settings?user_id=88888", app=app)
    req.json = AsyncMock(return_value={"key": "nightly", "value": False})
    resp = await post_user_settings(req)
    assert resp.status == 200
    res_data = json.loads(resp.text)
    assert res_data["ok"] is True
    assert res_data["settings"]["nightly"] is False

    # 2. Get user me and check settings are persisted
    req_me = make_mocked_request("GET", "/api/user/me?user_id=88888", app=app)
    resp_me = await get_user_me(req_me)
    assert resp_me.status == 200
    me_data = json.loads(resp_me.text)["data"]
    assert "settings" in me_data
    assert me_data["settings"]["nightly"] is False
    assert me_data["settings"]["weekly"] is True

    await engine.dispose()


@pytest.mark.anyio
async def test_lucky_wheel_active_sub_and_24h_timer():
    from aiohttp.test_utils import make_mocked_request
    from bot.web.user_shop import post_user_spin

    mock_remnawave = AsyncMock()
    # 1. User without active subscription
    mock_remnawave.get_users_by_telegram_id.return_value = [{"status": "DISABLED", "id": 1}]
    cache = FastCache(redis_client=None)

    app = {
        "bot_token": "123:abc",
        "admin_ids": [55555],
        "is_dev": True,
        "remnawave": mock_remnawave,
        "cache": cache,
    }

    # Request without active sub -> rejected 400
    req_no_sub = make_mocked_request("POST", "/api/user/spin?user_id=12345", app=app)
    resp_no_sub = await post_user_spin(req_no_sub)
    assert resp_no_sub.status == 400
    assert "داشتن یک اشتراک فعال" in json.loads(resp_no_sub.text)["error"]

    # 2. User with active sub -> first spin succeeds
    mock_remnawave.get_users_by_telegram_id.return_value = [{"status": "ACTIVE", "id": 1}]
    req_spin1 = make_mocked_request("POST", "/api/user/spin?user_id=12345", app=app)
    resp_spin1 = await post_user_spin(req_spin1)
    assert resp_spin1.status == 200
    data_spin1 = json.loads(resp_spin1.text)
    assert data_spin1["ok"] is True
    assert "prize" in data_spin1

    # 3. If prize wasn't "again", spin immediately again -> rejected due to 24h cooldown
    if data_spin1["prize"]["id"] != "again":
        req_spin2 = make_mocked_request("POST", "/api/user/spin?user_id=12345", app=app)
        resp_spin2 = await post_user_spin(req_spin2)
        assert resp_spin2.status == 400
        data_spin2 = json.loads(resp_spin2.text)
        assert data_spin2["ok"] is False
        assert "۲۴ ساعت" in data_spin2["error"]
        assert data_spin2["next_spin_seconds"] > 0


@pytest.mark.anyio
async def test_lucky_wheel_prize_application_traffic_and_days():
    from unittest.mock import patch
    from aiohttp.test_utils import make_mocked_request
    from bot.web.user_shop import post_user_spin

    mock_remnawave = AsyncMock()
    mock_remnawave.get_users_by_telegram_id.return_value = [
        {"status": "ACTIVE", "id": 101, "trafficLimitBytes": 10 * 1024**3, "expireAt": "2026-12-01T00:00:00Z"}
    ]
    mock_remnawave.update_user_subscription.return_value = {"id": 101}
    cache = FastCache(redis_client=None)

    app = {
        "bot_token": "123:abc",
        "admin_ids": [55555],
        "is_dev": True,
        "remnawave": mock_remnawave,
        "cache": cache,
    }

    # Force prize to traffic (1 GB)
    with patch("random.choice", return_value={"id": "1gb", "name": "1 GB", "icon": "🎁", "type": "traffic", "value": 1}):
        req = make_mocked_request("POST", "/api/user/spin?user_id=111222", app=app)
        resp = await post_user_spin(req)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["ok"] is True
        assert data["applied"] is True
        # Verify call arguments: id, expireAt, new_limit (10GB + 1GB = 11GB)
        mock_remnawave.update_user_subscription.assert_awaited_once_with(
            101, "2026-12-01T00:00:00Z", 11 * 1024**3
        )

    # Force prize to days (1 day)
    mock_remnawave.update_user_subscription.reset_mock()
    await cache.delete("tma:user:111222:wheel_last_spin")
    with patch("random.choice", return_value={"id": "1day", "name": "1 day", "icon": "💎", "type": "days", "value": 1}):
        req = make_mocked_request("POST", "/api/user/spin?user_id=111222", app=app)
        resp = await post_user_spin(req)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["ok"] is True
        assert data["applied"] is True
        mock_remnawave.update_user_subscription.assert_awaited_once()
        call_args = mock_remnawave.update_user_subscription.call_args[0]
        assert call_args[0] == 101
        assert "2026-12-02" in call_args[1]  # 2026-12-01 + 1 day = 2026-12-02
        assert call_args[2] == 10 * 1024**3



@pytest.mark.anyio
async def test_user_purchase_multi_account_fallback_and_payload():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base, Service, Wallet
    from bot.web.user_shop import post_user_purchase

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Create service and user wallet
        svc = Service(
            name="Gold 50GB",
            traffic_gb=50,
            duration_days=30,
            price=100000,
            is_active=True,
        )
        session.add(svc)
        wallet = Wallet(telegram_id=22222, balance=250000)
        session.add(wallet)
        await session.commit()
        svc_id = svc.id

    mock_remnawave = AsyncMock()
    # User has 2 panel accounts
    mock_remnawave.get_users_by_telegram_id.return_value = [
        {"id": 101, "username": "u22222_primary", "status": "ACTIVE", "subscriptionUrl": "https://sub/primary"},
        {"id": 102, "username": "u22222_secondary", "status": "ACTIVE", "subscriptionUrl": "https://sub/secondary"},
    ]
    mock_remnawave.update_user_subscription.return_value = {
        "id": 101, "username": "u22222_primary", "subscriptionUrl": "https://sub/primary"
    }

    app = {
        "bot_token": "123:abc",
        "admin_ids": [55555],
        "is_dev": True,
        "session_factory": session_factory,
        "cache": FastCache(redis_client=None),
        "remnawave": mock_remnawave,
    }

    # Purchase without account_id should gracefully renew primary account (101) instead of failing
    req = make_mocked_request("POST", "/api/user/purchase?user_id=22222", app=app)
    req.json = AsyncMock(return_value={"service_id": svc_id})

    resp = await post_user_purchase(req)
    assert resp.status == 200
    res_data = json.loads(resp.text)
    assert res_data["ok"] is True
    assert res_data["service_name"] == "Gold 50GB"
    assert res_data["traffic_gb"] == 50
    assert res_data["duration_days"] == 30
    assert res_data["new_balance"] == 150000
    assert res_data["subscription_url"] == "https://sub/primary"

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_overview_metrics_flags_and_devices():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base, User
    from bot.web.routes_admin import get_admin_overview

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(User(telegram_id=99999, username="admin_user"))
        await session.commit()

    mock_remnawave = AsyncMock()
    # Panel users with nested userTraffic and top-level usedTrafficBytes
    mock_remnawave.get_all_panel_users.return_value = [
        {"id": 1, "status": "ACTIVE", "userTraffic": {"usedTrafficBytes": 10 * (1024**3)}},
        {"id": 2, "status": "ACTIVE", "usedTrafficBytes": 5 * (1024**3)},
    ]
    # Nodes with countryCode, isConnected, usersOnline, and system info
    mock_remnawave.get_nodes.return_value = [
        {
            "id": 1,
            "name": "Germany Main",
            "countryCode": "DE",
            "isConnected": True,
            "usersOnline": 42,
            "system": {"cpu": 15, "ram": 55},
        },
        {
            "id": 2,
            "name": "Netherlands #2",
            "countryCode": "NL",
            "isConnected": False,
            "usersOnline": 0,
            "system": {"cpu": 5, "ram": 20},
        },
    ]
    mock_remnawave.get_hwid_stats.return_value = {"onlineDevices": 42}

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "cache": FastCache(redis_client=None),
        "remnawave": mock_remnawave,
    }

    req = make_mocked_request("GET", "/api/admin/overview?user_id=99999", app=app)
    resp = await get_admin_overview(req)
    assert resp.status == 200
    res_data = json.loads(resp.text)
    assert res_data["ok"] is True
    metrics = res_data["data"]["metrics"]
    assert metrics["month_traffic_gb"] == 15.0  # 10 + 5 GB
    assert metrics["online_devices"] == 42
    assert metrics["active_panel_users"] == 2
    assert metrics["offline_nodes"] == 1

    nodes = res_data["data"]["nodes"]
    assert len(nodes) == 2
    assert nodes[0]["flag"] == "🇩🇪"
    assert nodes[0]["status"] == "ONLINE"
    assert nodes[0]["connected_users"] == 42
    assert nodes[1]["flag"] == "🇳🇱"
    assert nodes[1]["status"] == "OFFLINE"

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_users_remaining_traffic_and_days():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base, User, Wallet
    from bot.web.routes_admin import get_admin_users

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(User(telegram_id=11111, username="test_client"))
        session.add(Wallet(telegram_id=11111, balance=50000))
        await session.commit()

    mock_remnawave = AsyncMock()
    # User with 50GB limit and 20GB used, expiring in 15 days
    mock_remnawave.get_users_by_telegram_id.return_value = [{
        "id": 505,
        "status": "ACTIVE",
        "trafficLimitBytes": 50 * (1024**3),
        "userTraffic": {"usedTrafficBytes": 20 * (1024**3)},
        "expireAt": "2099-01-01T00:00:00.000Z",
    }]

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "cache": FastCache(redis_client=None),
        "remnawave": mock_remnawave,
    }

    req = make_mocked_request("GET", "/api/admin/users?user_id=99999", app=app)
    resp = await get_admin_users(req)
    assert resp.status == 200
    res_data = json.loads(resp.text)
    assert res_data["ok"] is True
    users = res_data["users"]
    assert len(users) == 1
    u = users[0]
    assert u["telegram_id"] == 11111
    assert u["username"] == "test_client"
    assert u["avatar_url"] == "/api/user/avatar?user_id=11111"
    panel = u["panel_account"]
    assert panel["exists"] is True
    assert panel["used_traffic_gb"] == 20.0
    assert panel["limit_traffic_gb"] == 50.0
    assert panel["remaining_traffic_gb"] == 30.0  # 50 - 20 = 30 GB remaining
    assert panel["days_left"] is not None and panel["days_left"] > 0

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_broadcast_audience_targeting():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base, User
    from bot.web.routes_admin import post_admin_broadcast

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(User(telegram_id=101, username="u1"))
        session.add(User(telegram_id=102, username="u2"))
        await session.commit()

    mock_bot = AsyncMock()
    mock_remnawave = AsyncMock()
    mock_remnawave.get_all_panel_users.return_value = []

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "cache": FastCache(redis_client=None),
        "remnawave": mock_remnawave,
        "bot": mock_bot,
    }

    req = make_mocked_request("POST", "/api/admin/broadcast?user_id=99999", app=app)
    req.json = AsyncMock(return_value={"message": "سلام به همه کاربران", "target": "all"})

    resp = await post_admin_broadcast(req)
    assert resp.status == 200
    res_data = json.loads(resp.text)
    assert res_data["ok"] is True
    assert "همه کاربران" in res_data["message"]

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_reset_trial():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base, User
    from bot.web.routes_admin import post_admin_reset_trial

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        user = User(telegram_id=202, username="test_trial", has_claimed_trial=True)
        session.add(user)
        await session.commit()

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "cache": FastCache(redis_client=None),
        "bot": AsyncMock(),
    }

    # Reset trial for user 202
    req = make_mocked_request("POST", "/api/admin/user/reset_trial?user_id=99999", app=app)
    req.json = AsyncMock(return_value={"telegram_id": 202})

    resp = await post_admin_reset_trial(req)
    assert resp.status == 200
    res_data = json.loads(resp.text)
    assert res_data["ok"] is True
    assert "با موفقیت فعال شد" in res_data["message"]

    # Verify in DB that has_claimed_trial is now False
    async with session_factory() as session:
        u = await session.scalar(select(User).where(User.telegram_id == 202))
        assert u.has_claimed_trial is False

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_broadcast_status():
    from aiohttp.test_utils import make_mocked_request
    from bot.web.routes_admin import _BROADCAST_STATUSES, get_admin_broadcast_status

    _BROADCAST_STATUSES["test-task-123"] = {
        "broadcast_id": "test-task-123",
        "target": "all",
        "total": 10,
        "sent": 7,
        "failed": 1,
        "is_completed": False,
    }

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
    }

    req = make_mocked_request("GET", "/api/admin/broadcast/status?user_id=99999&id=test-task-123", app=app)
    resp = await get_admin_broadcast_status(req)
    assert resp.status == 200
    res_data = json.loads(resp.text)
    assert res_data["ok"] is True
    assert res_data["stats"]["sent"] == 7
    assert res_data["stats"]["failed"] == 1
    assert res_data["stats"]["is_completed"] is False


@pytest.mark.anyio
async def test_admin_modify_user_traffic_and_days():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base
    from bot.web.routes_admin import post_admin_modify_user

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    mock_remnawave = AsyncMock()
    mock_remnawave.get_users_by_telegram_id.return_value = [{
        "id": "user-uuid-1",
        "trafficLimitBytes": 20 * (1024**3),
        "expireAt": "2026-11-01T00:00:00Z",
    }]
    mock_remnawave.update_user_subscription.return_value = {"id": "user-uuid-1"}

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "remnawave": mock_remnawave,
        "cache": FastCache(redis_client=None),
    }

    # 1. Modify Traffic
    req_traffic = make_mocked_request("POST", "/api/admin/user/modify?user_id=99999", app=app)
    req_traffic.json = AsyncMock(return_value={"telegram_id": 555, "action": "traffic", "amount": 10})
    resp_traffic = await post_admin_modify_user(req_traffic)
    assert resp_traffic.status == 200
    res_json = json.loads(resp_traffic.text)
    assert res_json["ok"] is True
    assert "افزایش 10 GB ترافیک" in res_json["message"]

    # Verify update_user_subscription was called with the increased limit: 20GB + 10GB = 30GB
    mock_remnawave.update_user_subscription.assert_called_with(
        "user-uuid-1",
        expire_at_iso="2026-11-01T00:00:00Z",
        traffic_limit_bytes=30 * (1024**3),
        status="ACTIVE",
    )

    # 2. Modify Days
    req_days = make_mocked_request("POST", "/api/admin/user/modify?user_id=99999", app=app)
    req_days.json = AsyncMock(return_value={"telegram_id": 555, "action": "days", "amount": 30})
    resp_days = await post_admin_modify_user(req_days)
    assert resp_days.status == 200
    res_days_json = json.loads(resp_days.text)
    assert res_days_json["ok"] is True
    assert "تمدید 30 روز" in res_days_json["message"]

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_settings_full():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base
    from bot.web.routes_admin import get_admin_settings, post_admin_settings

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
    }

    # Save settings
    post_req = make_mocked_request("POST", "/api/admin/settings?user_id=99999", app=app)
    post_req.json = AsyncMock(return_value={
        "card_number": "6037991823456789",
        "card_holder": "محمد رضایی",
        "topup_min_amount": 50000,
        "usdt_rate_toman": 105000,
        "trial_enabled": True,
        "trial_traffic_gb": 2,
        "trial_duration_days": 3,
        "referral_reward_gb": 10,
        "support_contact": "@MySupportBot",
    })
    post_resp = await post_admin_settings(post_req)
    assert post_resp.status == 200

    # Retrieve and verify settings
    get_req = make_mocked_request("GET", "/api/admin/settings?user_id=99999", app=app)
    get_resp = await get_admin_settings(get_req)
    assert get_resp.status == 200
    data = json.loads(get_resp.text)["settings"]
    assert data["card_number"] == "6037991823456789"
    assert data["card_holder"] == "محمد رضایی"
    assert data["topup_min_amount"] == 50000
    assert data["usdt_rate_toman"] == 105000
    assert data["trial_enabled"] is True
    assert data["trial_traffic_gb"] == 2
    assert data["trial_duration_days"] == 3
    assert data["referral_reward_gb"] == 10
    assert data["support_contact"] == "@MySupportBot"

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_user_wallet_modify():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base, Wallet
    from bot.web.routes_admin import post_admin_user_wallet

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(Wallet(telegram_id=12345, balance=50000))
        await session.commit()

    mock_bot = AsyncMock()
    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "cache": FastCache(redis_client=None),
        "bot": mock_bot,
    }

    # Add 25,000 Toman
    req_add = make_mocked_request("POST", "/api/admin/user/wallet?user_id=99999", app=app)
    req_add.json = AsyncMock(return_value={"telegram_id": 12345, "amount": 25000, "reason": "هدیه ادمین"})
    resp_add = await post_admin_user_wallet(req_add)
    assert resp_add.status == 200
    data_add = json.loads(resp_add.text)
    assert data_add["ok"] is True
    assert data_add["new_balance"] == 75000
    mock_bot.send_message.assert_called_once()

    # Deduct 15,000 Toman
    req_sub = make_mocked_request("POST", "/api/admin/user/wallet?user_id=99999", app=app)
    req_sub.json = AsyncMock(return_value={"telegram_id": 12345, "amount": -15000, "reason": "اصلاح موجودی"})
    resp_sub = await post_admin_user_wallet(req_sub)
    assert resp_sub.status == 200
    data_sub = json.loads(resp_sub.text)
    assert data_sub["ok"] is True
    assert data_sub["new_balance"] == 60000

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_user_revoke_sub():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base
    from bot.web.routes_admin import post_admin_user_revoke_sub

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    mock_remnawave = AsyncMock()
    mock_remnawave.get_users_by_telegram_id.return_value = [{"id": "user-uuid-1"}]
    mock_remnawave.revoke_user_subscription.return_value = {
        "id": "user-uuid-1",
        "subscriptionUrl": "https://remna.test/sub/new-token-123",
    }

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "cache": FastCache(redis_client=None),
        "remnawave": mock_remnawave,
    }

    req = make_mocked_request("POST", "/api/admin/user/revoke_sub?user_id=99999", app=app)
    req.json = AsyncMock(return_value={"telegram_id": 777})
    resp = await post_admin_user_revoke_sub(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["ok"] is True
    assert data["subscription_url"] == "https://remna.test/sub/new-token-123"
    mock_remnawave.revoke_user_subscription.assert_called_with("user-uuid-1")

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_user_hwid_devices():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base
    from bot.web.routes_admin import get_admin_user_hwid_devices, post_admin_user_delete_hwid

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    mock_remnawave = AsyncMock()
    mock_remnawave.get_users_by_telegram_id.return_value = [{"id": "user-uuid-hwid"}]
    mock_remnawave.get_user_hwid_devices.return_value = [
        {"hwid": "hwid-abc-1", "os": "iOS 17.4", "ip": "1.2.3.4"}
    ]
    mock_remnawave.delete_hwid_device.return_value = True

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "remnawave": mock_remnawave,
    }

    # 1. Get devices
    req_get = make_mocked_request("GET", "/api/admin/user/hwid_devices?telegram_id=888&user_id=99999", app=app)
    resp_get = await get_admin_user_hwid_devices(req_get)
    assert resp_get.status == 200
    data_get = json.loads(resp_get.text)
    assert data_get["ok"] is True
    assert len(data_get["devices"]) == 1
    assert data_get["devices"][0]["hwid"] == "hwid-abc-1"

    # 2. Delete device
    req_del = make_mocked_request("POST", "/api/admin/user/delete_hwid?user_id=99999", app=app)
    req_del.json = AsyncMock(return_value={"telegram_id": 888, "hwid": "hwid-abc-1"})
    resp_del = await post_admin_user_delete_hwid(req_del)
    assert resp_del.status == 200
    data_del = json.loads(resp_del.text)
    assert data_del["ok"] is True
    mock_remnawave.delete_hwid_device.assert_called_with("user-uuid-hwid", "hwid-abc-1")

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_plans_crud():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base
    from bot.web.routes_admin import (
        get_admin_plans,
        post_admin_plan_save,
        post_admin_plan_toggle,
        post_admin_plan_delete,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
    }

    # 1. Create plan
    req_save = make_mocked_request("POST", "/api/admin/plan/save?user_id=99999", app=app)
    req_save.json = AsyncMock(return_value={
        "name": "پلن پرسرعت 50 گیگ",
        "price": 120000,
        "traffic_gb": 50,
        "duration_days": 30,
        "hwid_limit": 2,
        "description": "مناسب ترید و گیم",
        "is_active": True,
    })
    resp_save = await post_admin_plan_save(req_save)
    assert resp_save.status == 200
    assert json.loads(resp_save.text)["ok"] is True

    # 2. Get plans
    req_list = make_mocked_request("GET", "/api/admin/plans?user_id=99999", app=app)
    resp_list = await get_admin_plans(req_list)
    assert resp_list.status == 200
    plans = json.loads(resp_list.text)["plans"]
    assert len(plans) == 1
    plan_id = plans[0]["id"]
    assert plans[0]["name"] == "پلن پرسرعت 50 گیگ"
    assert plans[0]["hwid_limit"] == 2

    # 3. Toggle status
    req_toggle = make_mocked_request("POST", "/api/admin/plan/toggle?user_id=99999", app=app)
    req_toggle.json = AsyncMock(return_value={"id": plan_id, "is_active": False})
    resp_toggle = await post_admin_plan_toggle(req_toggle)
    assert resp_toggle.status == 200
    assert json.loads(resp_toggle.text)["is_active"] is False

    # 4. Delete plan
    req_del = make_mocked_request("POST", "/api/admin/plan/delete?user_id=99999", app=app)
    req_del.json = AsyncMock(return_value={"id": plan_id})
    resp_del = await post_admin_plan_delete(req_del)
    assert resp_del.status == 200
    assert json.loads(resp_del.text)["ok"] is True

    # 5. Verify empty
    resp_empty = await get_admin_plans(req_list)
    assert len(json.loads(resp_empty.text)["plans"]) == 0

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_coupons_crud():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base
    from bot.web.routes_admin import (
        get_admin_coupons,
        post_admin_coupon_save,
        post_admin_coupon_toggle,
        post_admin_coupon_delete,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
    }

    # 1. Create coupon
    req_save = make_mocked_request("POST", "/api/admin/coupon/save?user_id=99999", app=app)
    req_save.json = AsyncMock(return_value={
        "code": "NOROOZ1403",
        "discount_percent": 20,
        "discount_amount": 0,
        "max_uses": 50,
        "expires_days": 10,
        "is_active": True,
    })
    resp_save = await post_admin_coupon_save(req_save)
    assert resp_save.status == 200
    assert json.loads(resp_save.text)["ok"] is True

    # 2. Get coupons
    req_list = make_mocked_request("GET", "/api/admin/coupons?user_id=99999", app=app)
    resp_list = await get_admin_coupons(req_list)
    assert resp_list.status == 200
    coupons = json.loads(resp_list.text)["coupons"]
    assert len(coupons) == 1
    coupon_id = coupons[0]["id"]
    assert coupons[0]["code"] == "NOROOZ1403"
    assert coupons[0]["discount_percent"] == 20

    # 3. Toggle status
    req_toggle = make_mocked_request("POST", "/api/admin/coupon/toggle?user_id=99999", app=app)
    req_toggle.json = AsyncMock(return_value={"id": coupon_id, "is_active": False})
    resp_toggle = await post_admin_coupon_toggle(req_toggle)
    assert resp_toggle.status == 200
    assert json.loads(resp_toggle.text)["is_active"] is False

    # 4. Delete coupon
    req_del = make_mocked_request("POST", "/api/admin/coupon/delete?user_id=99999", app=app)
    req_del.json = AsyncMock(return_value={"id": coupon_id})
    resp_del = await post_admin_coupon_delete(req_del)
    assert resp_del.status == 200
    assert json.loads(resp_del.text)["ok"] is True

    # 5. Verify empty
    resp_empty = await get_admin_coupons(req_list)
    assert len(json.loads(resp_empty.text)["coupons"]) == 0

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_users_filter_online_and_expiring():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base, User
    from bot.web.routes_admin import get_admin_users

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(User(telegram_id=99999, username="admin_user"))
        session.add(User(telegram_id=11111, username="online_user"))
        session.add(User(telegram_id=22222, username="expiring_user"))
        await session.commit()

    mock_remnawave = AsyncMock()
    user_11 = {"username": "tg_11111", "status": "ACTIVE", "trafficLimitBytes": 50 * (1024**3), "userTraffic": {"usedTrafficBytes": 10 * (1024**3)}}
    user_22 = {"username": "tg_22222", "status": "ACTIVE", "trafficLimitBytes": 10 * (1024**3), "userTraffic": {"usedTrafficBytes": 9 * (1024**3)}}

    async def mock_get_by_tg(tg_id):
        if tg_id == 11111:
            return [user_11]
        elif tg_id == 22222:
            return [user_22]
        return []

    mock_remnawave.get_users_by_telegram_id.side_effect = mock_get_by_tg
    mock_remnawave.get_all_panel_users.return_value = [user_11, user_22]
    mock_remnawave.get_active_sessions.return_value = [
        {"user": {"username": "tg_11111"}}
    ]
    mock_remnawave.get_active_hwid_devices.return_value = []

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "remnawave": mock_remnawave,
    }

    # Test all users
    req_all = make_mocked_request("GET", "/api/admin/users?user_id=99999", app=app)
    resp_all = await get_admin_users(req_all)
    assert resp_all.status == 200
    users_all = json.loads(resp_all.text)["users"]
    assert len(users_all) == 3

    # Check is_online & is_expiring flags
    u_online = next(u for u in users_all if u["telegram_id"] == 11111)
    assert u_online["is_online"] is True
    assert u_online["is_expiring"] is False

    u_expiring = next(u for u in users_all if u["telegram_id"] == 22222)
    assert u_expiring["is_online"] is False
    assert u_expiring["is_expiring"] is True

    # Test online filter
    req_online = make_mocked_request("GET", "/api/admin/users?user_id=99999&filter=online", app=app)
    resp_online = await get_admin_users(req_online)
    assert resp_online.status == 200
    users_online = json.loads(resp_online.text)["users"]
    assert len(users_online) == 1
    assert users_online[0]["telegram_id"] == 11111

    # Test expiring filter
    req_exp = make_mocked_request("GET", "/api/admin/users?user_id=99999&filter=expiring", app=app)
    resp_exp = await get_admin_users(req_exp)
    assert resp_exp.status == 200
    users_exp = json.loads(resp_exp.text)["users"]
    assert len(users_exp) == 1
    assert users_exp[0]["telegram_id"] == 22222

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_topups_listing():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base, User
    from bot.db.repositories.wallet_repo import WalletRepository
    from bot.web.routes_admin import get_admin_topups

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(User(telegram_id=55555, username="payer_user"))
        wallet_repo = WalletRepository(session)
        await wallet_repo.create_topup(telegram_id=55555, amount=75000, receipt_hash="hash-receipt-123")
        await session.commit()

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
    }

    req = make_mocked_request("GET", "/api/admin/topups?user_id=99999", app=app)
    resp = await get_admin_topups(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["ok"] is True
    assert len(data["topups"]) == 1
    t = data["topups"][0]
    assert t["telegram_id"] == 55555
    assert t["amount"] == 75000
    assert t["username"] == "payer_user"
    assert t["receipt_hash"] == "hash-receipt-123"

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_coupon_usages():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base, User
    from bot.db.repositories.coupon_repo import CouponRepository
    from bot.web.routes_admin import get_admin_coupon_usages

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(User(telegram_id=77777, username="lucky_user"))
        coupon_repo = CouponRepository(session)
        coupon = await coupon_repo.create(code="DISCOUNT50", discount_percent=50, max_uses=10)
        await coupon_repo.record_usage(coupon=coupon, telegram_id=77777, discount_applied=25000)
        await session.commit()
        coupon_id = coupon.id

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
    }

    req = make_mocked_request("GET", f"/api/admin/coupons/{coupon_id}/usages?user_id=99999", match_info={"id": str(coupon_id)}, app=app)
    resp = await get_admin_coupon_usages(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["ok"] is True
    assert data["coupon"]["code"] == "DISCOUNT50"
    assert len(data["usages"]) == 1
    u = data["usages"][0]
    assert u["telegram_id"] == 77777
    assert u["username"] == "lucky_user"
    assert u["discount_applied"] == 25000

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_topup_action_syncs_with_supergroup():
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base, Topup, Wallet
    from bot.web.routes_admin import post_admin_topup_action

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        t = Topup(telegram_id=12345, amount=50000, status="pending", admin_message_id=888)
        w = Wallet(telegram_id=12345, balance=10000)
        session.add_all([t, w])
        await session.commit()
        topup_id = t.id

    mock_bot = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.ADMIN_CHAT_ID = -100123456789
    mock_settings.TOPIC_TOPUPS = None

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "bot": mock_bot,
        "settings": mock_settings,
        "cache": FastCache(redis_client=None),
    }

    req = make_mocked_request("POST", "/api/admin/topup/action?user_id=99999", app=app)
    req.json = AsyncMock(return_value={"topup_id": topup_id, "approved": True})

    resp = await post_admin_topup_action(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["ok"] is True

    # Check that reply markup on supergroup message 888 was removed
    mock_bot.edit_message_reply_markup.assert_called_once_with(
        chat_id=-100123456789,
        message_id=888,
        reply_markup=None,
    )
    # Check that notification was sent to user and announcement to admin chat
    assert mock_bot.send_message.call_count >= 2
    user_call = mock_bot.send_message.call_args_list[0]
    assert user_call.kwargs["chat_id"] == 12345
    assert "واریز شما تایید شد!" in user_call.kwargs["text"]
    assert user_call.kwargs["reply_markup"] is not None
    button_callbacks = [
        btn.callback_data for row in user_call.kwargs["reply_markup"].inline_keyboard for btn in row
    ]
    assert "menu:services" in button_callbacks
    assert "menu:wallet" in button_callbacks

    admin_call = mock_bot.send_message.call_args_list[1]
    assert f"تعیین وضعیت فیش {topup_id}" in admin_call.kwargs["text"]
    assert f"#{topup_id}" not in admin_call.kwargs["text"]

    await engine.dispose()


@pytest.mark.anyio
async def test_post_user_purchase_commits_session_without_coupon():
    """Verify that purchase without a coupon permanently commits wallet deduction and order."""
    from aiohttp.test_utils import make_mocked_request
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select
    from bot.db.models import Base, Service, Wallet, Order
    from bot.web.user_shop import post_user_purchase

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        svc = Service(name="Plan Test", traffic_gb=20, duration_days=30, price=50000, is_active=True)
        session.add(svc)
        wallet = Wallet(telegram_id=33333, balance=100000)
        session.add(wallet)
        await session.commit()
        svc_id = svc.id

    mock_remnawave = AsyncMock()
    mock_remnawave.get_users_by_telegram_id.return_value = [
        {"id": 555, "username": "u33333_acc", "status": "ACTIVE", "subscriptionUrl": "https://sub/555"}
    ]
    mock_remnawave.update_user_subscription.return_value = {
        "id": 555, "username": "u33333_acc", "subscriptionUrl": "https://sub/555"
    }

    app = {
        "bot_token": "123:abc",
        "admin_ids": [55555],
        "is_dev": True,
        "session_factory": session_factory,
        "cache": FastCache(redis_client=None),
        "remnawave": mock_remnawave,
    }

    req = make_mocked_request("POST", "/api/user/purchase?user_id=33333", app=app)
    req.json = AsyncMock(return_value={"service_id": svc_id})

    resp = await post_user_purchase(req)
    assert resp.status == 200
    res_data = json.loads(resp.text)
    assert res_data["ok"] is True
    assert res_data["new_balance"] == 50000

    # In a brand new session, verify the wallet balance and order actually persisted in DB!
    async with session_factory() as verify_session:
        w = (await verify_session.execute(select(Wallet).where(Wallet.telegram_id == 33333))).scalar_one()
        assert w.balance == 50000

        ord_row = (await verify_session.execute(select(Order).where(Order.telegram_id == 33333))).scalar_one()
        assert ord_row.status == "paid"
        assert ord_row.amount == 50000

    await engine.dispose()


@pytest.mark.anyio
async def test_api_rate_limit_middleware_blocks_excessive_requests():
    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request
    from bot.web.server import api_rate_limit_middleware, _api_buckets

    _api_buckets.clear()

    async def mock_handler(request):
        return web.json_response({"ok": True})

    app = web.Application()
    app["is_dev"] = False

    # Simulate 21 sensitive requests from same IP (limit is 20)
    for i in range(20):
        req = make_mocked_request(
            "POST", "/api/user/validate_coupon",
            headers={"X-Real-IP": "198.51.100.1"},
            app=app,
        )
        res = await api_rate_limit_middleware(req, mock_handler)
        assert res.status == 200

    # 21st request should be rate-limited (HTTP 429)
    req_excess = make_mocked_request(
        "POST", "/api/user/validate_coupon",
        headers={"X-Real-IP": "198.51.100.1"},
        app=app,
    )
    res_excess = await api_rate_limit_middleware(req_excess, mock_handler)
    assert res_excess.status == 429
    data = json.loads(res_excess.text)
    assert data["ok"] is False
    assert data["code"] == "rate_limited"


@pytest.mark.anyio
async def test_crypto_mark_paid_atomic():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from bot.db.models import Base
    from bot.db.repositories.crypto_repo import CryptoRepository

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        repo = CryptoRepository(session)
        inv = await repo.create_invoice(
            telegram_id=44444,
            amount_toman=100000,
            amount_ton="1.5000",
            nanotons=1500000000,
            pay_address="EQB_test_addr",
        )
        inv_id = inv.id
        await session.commit()

    # First mark_paid should succeed
    async with session_factory() as session:
        repo = CryptoRepository(session)
        paid = await repo.mark_paid(inv_id, "tx_hash_123")
        assert paid is not None
        assert paid.status == "paid"
        assert paid.tx_hash == "tx_hash_123"
        await session.commit()

    # Second mark_paid with same invoice should return None (already paid, no double crediting)
    async with session_factory() as session:
        repo = CryptoRepository(session)
        second = await repo.mark_paid(inv_id, "tx_hash_duplicate")
        assert second is None

    await engine.dispose()




