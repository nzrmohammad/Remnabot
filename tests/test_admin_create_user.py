import pytest
from unittest.mock import AsyncMock, MagicMock
from aiohttp import web
from bot.web.admin_users_actions import post_admin_create_user
from bot.db.models import User, AdminLog
from sqlalchemy import select


@pytest.mark.anyio
async def test_admin_create_user_endpoint(session_factory):
    # Mock Remnawave client
    mock_remnawave = MagicMock()
    mock_remnawave.create_user = AsyncMock(return_value={
        "id": 999,
        "username": "custom_user",
        "telegramId": 12345678,
        "subscriptionUrl": "https://sub.example.com/token123",
    })

    app = web.Application()
    app["session_factory"] = session_factory
    app["remnawave"] = mock_remnawave
    app["admin_id"] = 111111

    # 1. Test unauthorized request
    request_unauth = MagicMock()
    request_unauth.app = app
    request_unauth.headers = {}
    resp_unauth = await post_admin_create_user(request_unauth)
    assert resp_unauth.status == 403

    # 2. Test authorized request with invalid telegram_id
    request_invalid = MagicMock()
    request_invalid.app = app
    request_invalid.headers = {"X-Admin-Key": "test"}
    # mock _check_admin to return admin
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("bot.web.admin_users_actions._check_admin", lambda r: {"id": 111111, "name": "Admin"})
        
        request_invalid.json = AsyncMock(return_value={"telegram_id": ""})
        resp_invalid = await post_admin_create_user(request_invalid)
        assert resp_invalid.status == 400

        # 3. Test successful user creation
        request_valid = MagicMock()
        request_valid.app = app
        request_valid.json = AsyncMock(return_value={
            "telegram_id": 12345678,
            "username": "custom_user",
            "traffic_gb": 50,
            "duration_days": 30,
            "hwid_limit": 2,
        })
        resp_valid = await post_admin_create_user(request_valid)
        assert resp_valid.status == 200

        import json
        data = json.loads(resp_valid.text)
        assert data["ok"] is True
        assert data["user"]["username"] == "custom_user"

        # Verify Remnawave client was called with expected parameters
        mock_remnawave.create_user.assert_awaited_once_with(
            username="custom_user",
            expire_days=30,
            traffic_gb=50,
            telegram_id=12345678,
            hwid_device_limit=2,
        )

        # Verify DB user and AdminLog were created
        async with session_factory() as session:
            db_user = (await session.execute(select(User).where(User.telegram_id == 12345678))).scalar_one_or_none()
            assert db_user is not None
            assert db_user.username == "custom_user"
            assert db_user.is_verified is True

            log = (await session.execute(select(AdminLog).where(AdminLog.target_user_id == 12345678))).scalar_one_or_none()
            assert log is not None
            assert log.action == "create_user"
            assert "custom_user" in log.detail
