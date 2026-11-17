import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from bot.services.error_reporter import TelegramErrorLogHandler, report_error
from bot.web.cache import FastCache
from bot.web.user_subscription import get_user_subscription_configs


@pytest.mark.anyio
async def test_get_user_subscription_configs_cached():
    app = web.Application()
    cache = FastCache(redis_client=None)
    await cache.set("tma:user:12345:configs:def", [{"id": 1, "name": "Cached Config", "protocol": "vless", "flag": "🇩🇪", "country_name": "آلمان", "uri": "vless://test"}])
    app["cache"] = cache
    app["remnawave"] = AsyncMock()
    app["session_factory"] = MagicMock()

    request = MagicMock(spec=web.Request)
    request.app = app
    request.query = {}
    request.get = lambda k, default=None: {"id": 12345, "username": "testuser"} if k == "user" else default

    resp = await get_user_subscription_configs(request)
    assert resp.status == 200
    import json
    data = json.loads(resp.text)
    assert data["ok"] is True
    assert data["cached"] is True
    assert len(data["configs"]) == 1
    assert data["configs"][0]["name"] == "Cached Config"


@pytest.mark.anyio
async def test_get_user_subscription_configs_priority1_connection_keys():
    import base64
    import json
    app = web.Application()
    cache = FastCache(redis_client=None)
    app["cache"] = cache
    mock_remnawave = AsyncMock()
    mock_remnawave.get_users_by_telegram_id.return_value = [
        {"id": "user-42", "telegramId": 12345, "uuid": "uuid-42", "shortUuid": "su-42", "subscriptionUrl": "https://sub.example.com/sub/su-42"}
    ]
    vmess_payload = base64.b64encode(json.dumps({"v": "2", "ps": "🇳🇱 Amsterdam", "add": "server2.com"}).encode()).decode()
    mock_remnawave.get_user_connection_keys.return_value = [
        "vless://user@server1.com:443?type=tcp#🇩🇪%20Frankfurt",
        f"vmess://{vmess_payload}",
    ]
    app["remnawave"] = mock_remnawave
    session_factory = MagicMock()
    app["session_factory"] = session_factory

    request = MagicMock(spec=web.Request)
    request.app = app
    request.query = {"account_id": "user-42"}
    request.get = lambda k, default=None: {"id": 12345, "username": "testuser"} if k == "user" else default

    resp = await get_user_subscription_configs(request)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["ok"] is True
    assert len(data["configs"]) == 2
    assert data["configs"][0]["flag"] == "🇩🇪"
    assert data["configs"][1]["flag"] == "🇳🇱"
    mock_remnawave.get_user_connection_keys.assert_called_once()


@pytest.mark.anyio
async def test_get_user_subscription_configs_empty_when_no_keys():
    app = web.Application()
    cache = FastCache(redis_client=None)
    app["cache"] = cache
    mock_remnawave = AsyncMock()
    mock_remnawave.get_users_by_telegram_id.return_value = [{"id": "user-1", "telegramId": 12345, "subscriptionUrl": "https://sub.example.com/sub/abc"}]
    mock_remnawave.get_user_connection_keys.return_value = None
    app["remnawave"] = mock_remnawave
    session_factory = MagicMock()
    app["session_factory"] = session_factory

    request = MagicMock(spec=web.Request)
    request.app = app
    request.query = {"account_id": "user-1"}
    request.get = lambda k, default=None: {"id": 12345, "username": "testuser"} if k == "user" else default

    resp = await get_user_subscription_configs(request)
    assert resp.status == 200
    import json
    data = json.loads(resp.text)
    assert data["ok"] is True
    assert data["configs"] == []
    assert "یافت نشد" in data["message"]


@pytest.mark.anyio
async def test_get_user_subscription_configs_panel_unreachable_503():
    """Verify HTTP 503 is returned when Remnawave panel is unreachable."""
    import json
    app = web.Application()
    cache = FastCache(redis_client=None)
    app["cache"] = cache
    mock_remnawave = AsyncMock()
    # Panel unreachable returns None
    mock_remnawave.get_users_by_telegram_id.return_value = None
    app["remnawave"] = mock_remnawave
    app["session_factory"] = MagicMock()

    request = MagicMock(spec=web.Request)
    request.app = app
    request.query = {}
    request.get = lambda k, default=None: {"id": 12345, "username": "testuser"} if k == "user" else default

    resp = await get_user_subscription_configs(request)
    assert resp.status == 503
    data = json.loads(resp.text)
    assert data["ok"] is False
    assert "موقتاً برقرار نشد" in data["error"]


@pytest.mark.anyio
async def test_get_user_subscription_configs_panel_timeout_503():
    """Verify HTTP 503 is returned when fetching panel users times out or fails with exception."""
    import json
    app = web.Application()
    cache = FastCache(redis_client=None)
    app["cache"] = cache
    mock_remnawave = AsyncMock()
    mock_remnawave.get_users_by_telegram_id.side_effect = TimeoutError("Connection timed out")
    app["remnawave"] = mock_remnawave
    app["session_factory"] = MagicMock()

    request = MagicMock(spec=web.Request)
    request.app = app
    request.query = {}
    request.get = lambda k, default=None: {"id": 12345, "username": "testuser"} if k == "user" else default

    resp = await get_user_subscription_configs(request)
    assert resp.status == 503
    data = json.loads(resp.text)
    assert data["ok"] is False
    assert "موقتاً برقرار نشد" in data["error"]


@pytest.mark.anyio
async def test_get_user_subscription_configs_prevents_cross_user_leak():
    """Verify accounts belonging to a different telegramId are strictly ignored."""
    import json
    app = web.Application()
    cache = FastCache(redis_client=None)
    app["cache"] = cache
    mock_remnawave = AsyncMock()
    # Return user belonging to a DIFFERENT telegramId (999999 vs 12345)
    mock_remnawave.get_users_by_telegram_id.return_value = [
        {"id": "user-other", "telegramId": 999999, "subscriptionUrl": "https://sub.example.com/sub/other"}
    ]
    app["remnawave"] = mock_remnawave
    app["session_factory"] = MagicMock()

    request = MagicMock(spec=web.Request)
    request.app = app
    request.query = {}
    request.get = lambda k, default=None: {"id": 12345, "username": "testuser"} if k == "user" else default

    resp = await get_user_subscription_configs(request)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["ok"] is True
    assert data["configs"] == []
    assert "اشتراک فعالی برای این حساب در پنل یافت نشد." in data["message"]


@pytest.mark.anyio
async def test_error_reporter_filters_telegram_conflict_error():
    bot = AsyncMock()
    session_factory = MagicMock()

    # Test report_error ignores TelegramConflictError when from dispatcher
    await report_error(
        bot=bot,
        session_factory=session_factory,
        exc="Conflict: terminated by other getUpdates request",
        context="Logger: aiogram.dispatcher (dispatcher.py:226)",
    )
    bot.send_message.assert_not_called()

    # Test TelegramErrorLogHandler ignores conflict record
    handler = TelegramErrorLogHandler(bot, session_factory)
    record = MagicMock()
    record.name = "aiogram.dispatcher"
    record.lineno = 226
    record.filename = "dispatcher.py"
    record.exc_info = None
    record.getMessage.return_value = "Failed to fetch updates - TelegramConflictError: Telegram server says - Conflict: terminated by other getUpdates request"

    with patch("asyncio.get_running_loop") as mock_loop:
        handler.emit(record)
        # Should return early without calling loop.create_task
        mock_loop.assert_not_called()


@pytest.mark.anyio
async def test_error_reporter_filters_bad_gateway_and_polling_errors():
    bot = AsyncMock()
    session_factory = MagicMock()

    # 1. Test report_error ignores TelegramServerError Bad Gateway
    await report_error(
        bot=bot,
        session_factory=session_factory,
        exc="Failed to fetch updates - TelegramServerError: Telegram server says - Bad Gateway",
        context="Logger: aiogram.dispatcher (dispatcher.py:226)",
    )
    bot.send_message.assert_not_called()

    # 2. Test report_error ignores when exc is an Exception object
    class FakeTelegramServerError(Exception):
        pass

    await report_error(
        bot=bot,
        session_factory=session_factory,
        exc=FakeTelegramServerError("Telegram server says - Bad Gateway"),
        context="aiogram.dispatcher",
    )
    bot.send_message.assert_not_called()

    # 3. Test TelegramErrorLogHandler ignores Bad Gateway update failure
    handler = TelegramErrorLogHandler(bot, session_factory)
    record = MagicMock()
    record.name = "aiogram.dispatcher"
    record.lineno = 226
    record.filename = "dispatcher.py"
    record.exc_info = None
    record.getMessage.return_value = "Failed to fetch updates - TelegramServerError: Telegram server says - Bad Gateway"

    with patch("asyncio.get_running_loop") as mock_loop:
        handler.emit(record)
        mock_loop.assert_not_called()

    # 4. Test handler ignores with exc_info set
    record2 = MagicMock()
    record2.name = "aiogram.dispatcher"
    record2.lineno = 226
    record2.filename = "dispatcher.py"
    record2.exc_info = (FakeTelegramServerError, FakeTelegramServerError("Bad Gateway"), None)
    record2.getMessage.return_value = "Failed to fetch updates"

    with patch("asyncio.get_running_loop") as mock_loop:
        handler.emit(record2)
        mock_loop.assert_not_called()


@pytest.mark.anyio
async def test_error_reporter_topic_isolation_and_no_pv_leak():
    bot = AsyncMock()
    session_factory = MagicMock()

    mock_settings = MagicMock()
    mock_settings.ADMIN_CHAT_ID = -100987654321
    mock_settings.ADMIN_IDS = [777888]
    mock_settings.ADMIN_TOPIC_ERRORS = 55
    mock_settings.TIMEZONE = "Asia/Tehran"

    # Make send_message fail with an exception to simulate network/Telegram failure
    bot.send_message.side_effect = RuntimeError("Connection dropped")

    with patch("bot.services.error_reporter.get_settings", return_value=mock_settings), \
         patch("bot.services.error_reporter._cached_topic_errors", 55):
        await report_error(
            bot=bot,
            session_factory=session_factory,
            exc=ValueError("Real application bug"),
            context="handlers/user.py:42",
        )

    # Verify calls:
    # It must have tried sending to ADMIN_CHAT_ID WITH message_thread_id=55
    # It must NEVER have sent without message_thread_id (which would land in General topic)
    # It must NEVER have sent to 777888 (admin PV) because ADMIN_CHAT_ID was configured!
    assert bot.send_message.call_count >= 1
    for call in bot.send_message.call_args_list:
        args, kwargs = call
        # Target chat must always be ADMIN_CHAT_ID, never the admin PV
        assert args[0] == -100987654321
        # Thread kwargs must be present and point to topic 55
        assert kwargs.get("message_thread_id") == 55

