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
async def test_get_user_subscription_configs_fetches_sub_url():
    app = web.Application()
    cache = FastCache(redis_client=None)
    app["cache"] = cache
    mock_remnawave = AsyncMock()
    mock_remnawave.get_users_by_telegram_id.return_value = [{"id": "user-1", "subscriptionUrl": "https://sub.example.com/sub/abc"}]
    app["remnawave"] = mock_remnawave
    session_factory = MagicMock()
    app["session_factory"] = session_factory

    request = MagicMock(spec=web.Request)
    request.app = app
    request.query = {"sub_url": "https://sub.example.com/sub/abc"}
    request.get = lambda k, default=None: {"id": 12345, "username": "testuser"} if k == "user" else default

    mock_cfgs = [
        {"name": "DE-Frankfurt", "protocol": "vless", "uri": "vless://frankfurt"},
        {"name": "NL-Amsterdam", "protocol": "vmess", "uri": "vmess://amsterdam"},
    ]

    with patch("bot.web.user_subscription.fetch_subscription_configs", AsyncMock(return_value=mock_cfgs)):
        resp = await get_user_subscription_configs(request)
        assert resp.status == 200
        import json
        data = json.loads(resp.text)
        assert data["ok"] is True
        assert len(data["configs"]) == 2
        assert data["configs"][0]["flag"] == "🇩🇪"
        assert data["configs"][1]["flag"] == "🇳🇱"


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
