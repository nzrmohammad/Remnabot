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




