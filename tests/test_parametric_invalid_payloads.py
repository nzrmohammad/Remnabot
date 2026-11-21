"""Parametric test suite for invalid / non-dict JSON payloads across TMA endpoints.

Ensures that non-object payloads (e.g. [], "raw string", 123, None) never cause
uncaught 500 Internal Server Errors (such as AttributeError: 'list' object has no attribute 'get').
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import make_mocked_request

from bot.web.admin_infra_api import get_admin_tools_check_host
from bot.web.user_shop import (
    post_user_claim_gift,
    post_user_create_gift,
    post_user_kill_device,
    post_user_purchase,
    post_user_revoke_sub,
    post_user_spin,
    post_user_validate_coupon,
)
from bot.web.user_topup import (
    post_user_auto_renew,
    post_user_redeem_voucher,
    post_user_topup_card,
)


@pytest.fixture
def mock_app():
    mock_settings = MagicMock(
        ADMIN_CHAT_ID=12345,
        ADMIN_TOPIC_TOPUPS=None,
        TIMEZONE="Asia/Tehran",
    )
    mock_remnawave = AsyncMock()
    mock_remnawave.get_users_by_telegram_id.return_value = []
    
    mock_cache = AsyncMock()
    mock_cache.get.return_value = None
    mock_cache.set.return_value = True
    mock_cache.delete.return_value = True

    class MockSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def commit(self):
            pass
        async def rollback(self):
            pass
        async def execute(self, stmt):
            m = MagicMock()
            m.scalar_one_or_none.return_value = None
            m.scalars.return_value.all.return_value = []
            m.scalar_one.return_value = 0
            return m

    return {
        "is_dev": True,
        "admin_ids": [77777],
        "bot_token": "123:abc",
        "bot": AsyncMock(),
        "settings": mock_settings,
        "remnawave": mock_remnawave,
        "cache": mock_cache,
        "session_factory": lambda: MockSession(),
    }


@pytest.mark.anyio
@pytest.mark.parametrize("bad_payload", [[], "malicious_string", 12345, None])
async def test_topup_voucher_non_dict_payload(mock_app, bad_payload):
    req = make_mocked_request(
        "POST", "/api/user/voucher/redeem?user_id=77777",
        headers={"Content-Type": "application/json"},
        app=mock_app,
    )
    req.json = AsyncMock(return_value=bad_payload)
    resp = await post_user_redeem_voucher(req)
    assert resp.status in (400, 422)
    data = json.loads(resp.text)
    assert data.get("ok") is False


@pytest.mark.anyio
@pytest.mark.parametrize("bad_payload", [[], "malicious_string", 12345, None])
async def test_topup_auto_renew_non_dict_payload(mock_app, bad_payload):
    req = make_mocked_request(
        "POST", "/api/user/auto-renew?user_id=77777",
        headers={"Content-Type": "application/json"},
        app=mock_app,
    )
    req.json = AsyncMock(return_value=bad_payload)
    resp = await post_user_auto_renew(req)
    assert resp.status in (400, 422)
    data = json.loads(resp.text)
    assert data.get("ok") is False


@pytest.mark.anyio
@pytest.mark.parametrize("bad_payload", [[], "malicious_string", 12345, None])
async def test_topup_card_non_dict_payload(mock_app, bad_payload):
    req = make_mocked_request(
        "POST", "/api/user/topup/card?user_id=77777",
        headers={"Content-Type": "application/json"},
        app=mock_app,
    )
    req.json = AsyncMock(return_value=bad_payload)
    with patch("bot.web.user_topup.get_store_settings", AsyncMock(return_value=MagicMock(card_to_card_enabled=True))):
        resp = await post_user_topup_card(req)
        assert resp.status in (400, 422)
        data = json.loads(resp.text)
        assert data.get("ok") is False


@pytest.mark.anyio
@pytest.mark.parametrize("bad_payload", [[], "malicious_string", 12345, None])
async def test_shop_validate_coupon_non_dict_payload(mock_app, bad_payload):
    req = make_mocked_request(
        "POST", "/api/user/coupon/validate?user_id=77777",
        headers={"Content-Type": "application/json"},
        app=mock_app,
    )
    req.json = AsyncMock(return_value=bad_payload)
    resp = await post_user_validate_coupon(req)
    assert resp.status in (400, 422)
    data = json.loads(resp.text)
    assert data.get("ok") is False


@pytest.mark.anyio
@pytest.mark.parametrize("bad_payload", [[], "malicious_string", 12345, None])
async def test_shop_spin_wheel_non_dict_payload(mock_app, bad_payload):
    req = make_mocked_request(
        "POST", "/api/user/spin?user_id=77777",
        headers={"Content-Type": "application/json"},
        app=mock_app,
    )
    req.json = AsyncMock(return_value=bad_payload)
    with patch("bot.services.wheel_service.execute_lucky_wheel_spin", AsyncMock(return_value={"ok": False, "error": "test"})):
        resp = await post_user_spin(req)
        assert resp.status in (400, 403)
        data = json.loads(resp.text)
        assert data.get("ok") is False


@pytest.mark.anyio
@pytest.mark.parametrize("bad_payload", [[], "malicious_string", 12345, None])
async def test_shop_kill_device_non_dict_payload(mock_app, bad_payload):
    req = make_mocked_request(
        "POST", "/api/user/devices/kill?user_id=77777",
        headers={"Content-Type": "application/json"},
        app=mock_app,
    )
    req.json = AsyncMock(return_value=bad_payload)
    resp = await post_user_kill_device(req)
    assert resp.status in (400, 404)
    data = json.loads(resp.text)
    assert data.get("ok") is False


@pytest.mark.anyio
@pytest.mark.parametrize("bad_payload", [[], "malicious_string", 12345, None])
async def test_shop_claim_gift_non_dict_payload(mock_app, bad_payload):
    req = make_mocked_request(
        "POST", "/api/user/gift/claim?user_id=77777",
        headers={"Content-Type": "application/json"},
        app=mock_app,
    )
    req.json = AsyncMock(return_value=bad_payload)
    resp = await post_user_claim_gift(req)
    assert resp.status in (400, 404)
    data = json.loads(resp.text)
    assert data.get("ok") is False


@pytest.mark.anyio
@pytest.mark.parametrize("bad_payload", [[], "malicious_string", 12345, None])
async def test_admin_ping_host_non_dict_payload(mock_app, bad_payload):
    req = make_mocked_request(
        "POST", "/api/admin/infra/ping?user_id=77777",
        headers={"Content-Type": "application/json"},
        app=mock_app,
    )
    req.json = AsyncMock(return_value=bad_payload)
    resp = await get_admin_tools_check_host(req)
    assert resp.status in (200, 400)
    data = json.loads(resp.text)
    assert "ok" in data
