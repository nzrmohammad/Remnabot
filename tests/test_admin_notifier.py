"""Tests for centralized admin_notifier service and DRY notification delivery."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.services.admin_notifier import resolve_admin_topic_id, send_admin_topic_notification


@pytest.mark.anyio
async def test_resolve_admin_topic_id_from_store():
    mock_store = MagicMock()
    mock_store.topic_orders = 101
    mock_store.topic_alerts = 202

    mock_session = MagicMock()
    with patch("bot.services.admin_notifier.get_store_settings", AsyncMock(return_value=mock_store)):
        topic_orders = await resolve_admin_topic_id(session=mock_session, kind="orders")
        assert topic_orders == 101

        topic_alerts = await resolve_admin_topic_id(session=mock_session, kind="alerts")
        assert topic_alerts == 202


@pytest.mark.anyio
async def test_resolve_admin_topic_id_fallback_to_env():
    mock_settings = MagicMock()
    mock_settings.ADMIN_TOPIC_ORDERS = 303
    mock_settings.ADMIN_TOPIC_ALERTS = 404

    with patch("bot.services.admin_notifier.get_settings", return_value=mock_settings):
        # When store has None or DB call fails, fallback to settings
        topic = await resolve_admin_topic_id(session=None, kind="orders")
        assert topic == 303


@pytest.mark.anyio
async def test_send_admin_topic_notification_uses_thread_kwargs():
    bot = AsyncMock()
    mock_msg = MagicMock()
    bot.send_message.return_value = mock_msg

    mock_settings = MagicMock()
    mock_settings.ADMIN_CHAT_ID = -100999888
    mock_settings.ADMIN_IDS = [12345]

    with patch("bot.services.admin_notifier.get_settings", return_value=mock_settings), \
         patch("bot.services.admin_notifier.resolve_admin_topic_id", AsyncMock(return_value=77)):

        res = await send_admin_topic_notification(
            bot=bot,
            text="<b>Order placed</b>",
            kind="orders",
        )

        assert res == mock_msg
        bot.send_message.assert_called_once()
        args, kwargs = bot.send_message.call_args
        assert args[0] == -100999888
        assert args[1] == "<b>Order placed</b>"
        assert kwargs.get("message_thread_id") == 77
        assert kwargs.get("parse_mode") == "HTML"


@pytest.mark.anyio
async def test_send_admin_topic_notification_never_spams_pv_when_chat_configured():
    bot = AsyncMock()
    # Simulate network or Telegram error
    bot.send_message.side_effect = RuntimeError("Telegram Network Timeout")

    mock_settings = MagicMock()
    mock_settings.ADMIN_CHAT_ID = -100999888
    mock_settings.ADMIN_IDS = [12345, 67890]

    with patch("bot.services.admin_notifier.get_settings", return_value=mock_settings), \
         patch("bot.services.admin_notifier.resolve_admin_topic_id", AsyncMock(return_value=88)):

        res = await send_admin_topic_notification(
            bot=bot,
            text="Alert text",
            kind="alerts",
        )

        assert res is None
        # It must only have called ADMIN_CHAT_ID (with HTML and plaintext retry)
        # It must NEVER have called bot.send_message(12345, ...) or bot.send_message(67890, ...)
        for call in bot.send_message.call_args_list:
            args, _ = call
            assert args[0] == -100999888


@pytest.mark.anyio
async def test_send_admin_topic_notification_falls_back_to_admins_only_without_group():
    bot = AsyncMock()
    mock_msg = MagicMock()
    bot.send_message.return_value = mock_msg

    mock_settings = MagicMock()
    mock_settings.ADMIN_CHAT_ID = None  # No admin group
    mock_settings.ADMIN_IDS = [111, 222]

    with patch("bot.services.admin_notifier.get_settings", return_value=mock_settings):
        res = await send_admin_topic_notification(
            bot=bot,
            text="Direct alert",
            kind="alerts",
        )

        assert res == mock_msg
        assert bot.send_message.call_count == 2
        calls = [c[0][0] for c in bot.send_message.call_args_list]
        assert calls == [111, 222]


@pytest.mark.anyio
async def test_resolve_admin_topic_id_nodes_falls_back_to_alerts_and_ignores_nonpositive():
    mock_store = MagicMock()
    mock_store.topic_nodes = 0
    mock_store.topic_alerts = 505

    mock_session = MagicMock()
    with patch("bot.services.admin_notifier.get_store_settings", AsyncMock(return_value=mock_store)):
        assert await resolve_admin_topic_id(session=mock_session, kind="nodes") == 505

    mock_store.topic_nodes = 707
    with patch("bot.services.admin_notifier.get_store_settings", AsyncMock(return_value=mock_store)):
        assert await resolve_admin_topic_id(session=mock_session, kind="nodes") == 707
