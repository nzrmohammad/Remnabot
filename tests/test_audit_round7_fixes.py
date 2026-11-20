"""Regression tests for Round 7 audit findings and fixes."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.config import Settings
from bot.services.birthday import days_until_jalali_birthday, parse_and_validate_jalali_birthdate
from bot.services.configs import _mask_url
from bot.services.formatting import _human_bytes_plain, format_datetime, ltr_frag


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_settings_log_level_and_file_defaults():
    s = Settings(
        BOT_TOKEN="123:ABC",
        REMNAWAVE_URL="https://vpn.example.com",
        REMNAWAVE_TOKEN="secret_token",
        ADMIN_IDS=[111],
        LOG_LEVEL="DEBUG",
        LOG_FILE="test.log",
    )
    assert s.LOG_LEVEL == "DEBUG"
    assert s.LOG_FILE == "test.log"


def test_url_masking_in_configs():
    raw_url = "https://sub.panel.com/api/v1/sub/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token"
    masked = _mask_url(raw_url)
    assert "token" in masked or "..." in masked
    assert "..." in masked
    assert len(masked) < len(raw_url)


def test_stars_payload_masking():
    from bot.handlers.payment_stars import _mask_stars_payload
    payload = "stars:user:12345:svc:2:nonce_abcdef1234567890"
    masked = _mask_stars_payload(payload)
    assert "abcdef1234567890" not in masked
    assert "nonc***" in masked
    assert "12345" in masked


@pytest.mark.anyio
async def test_error_reporter_thread_safe_emit_and_dedup():
    from bot.services.error_reporter import TelegramErrorLogHandler, report_error

    loop = asyncio.get_running_loop()
    bot = MagicMock()
    bot.send_message = AsyncMock()

    handler = TelegramErrorLogHandler(bot=bot, session_factory=None, loop=loop)
    assert handler.loop is loop

    with patch("bot.services.error_reporter.get_settings") as mock_settings:
        mock_settings.return_value = Settings(
            BOT_TOKEN="123:ABC",
            REMNAWAVE_URL="https://vpn.example.com",
            REMNAWAVE_TOKEN="secret",
            ADMIN_IDS=[111],
            ERROR_NOTIFICATION_CHAT_ID=123,
        )
        sig1 = await report_error(bot, None, ValueError("test error deduplication"), context="ctx1")
        sig2 = await report_error(bot, None, ValueError("test error deduplication"), context="ctx2")
        assert sig1 == sig2
        assert bot.send_message.call_count == 1


def test_jalali_leap_year_validation():
    # 1403 is a Jalali leap year -> Esfand 30 is valid
    valid_leap, dt_str, err = parse_and_validate_jalali_birthdate("1403/12/30")
    assert valid_leap is True
    assert dt_str == "1403/12/30"
    assert err is None

    # 1402 is NOT a Jalali leap year -> Esfand 30 is invalid
    valid_non_leap, _, err2 = parse_and_validate_jalali_birthdate("1402/12/30")
    assert valid_non_leap is False
    assert err2 is not None

    # days_until_jalali_birthday handles month 12 day 30 safely
    remaining = days_until_jalali_birthday("1400/12/30")
    assert isinstance(remaining, int)
    assert remaining >= 0


def test_node_country_fallback_not_nl():
    from bot.web.admin_overview_nodes import extract_node_item

    node_data = {
        "id": 99,
        "name": "Node Unknown",
        "countryCode": "",
        "country": "",
        "isConnected": True,
    }
    extracted = extract_node_item(node_data, 1, {}, {}, datetime.now(timezone.utc))
    assert extracted["country_code"] == "XX"
    assert extracted["country_name"] == "نامشخص"
    assert extracted["flag"] == "🌐"


def test_human_bytes_plain_has_kb_tier():
    assert _human_bytes_plain(0) == "0 MB"
    assert _human_bytes_plain(None) == "0 MB"
    assert _human_bytes_plain(-100) == "0 MB"
    assert _human_bytes_plain(512) == "0.50 KB"
    assert _human_bytes_plain(1024) == "1.00 KB"
    assert _human_bytes_plain(1024 * 500) == "500.00 KB"
    assert _human_bytes_plain(1024 * 1024) == "1.00 MB"


def test_service_display_ltr_frag_isolation():
    from bot.db.models import Service
    from bot.services.service_display import service_block

    svc = Service(
        id=1,
        name="Test",
        price=50000,
        traffic_gb=10,
        duration_days=30,
        traffic_strategy="NO_RESET",
        hwid_limit=1,
        is_active=True,
    )
    block_text = service_block(svc, "fa")
    # BiDi isolation character exists around price
    assert "\u206650,000\u2069" in block_text


def test_dead_state_waiting_telegram_id_removed():
    from bot.states.admin import UserManagementStates
    assert not hasattr(UserManagementStates, "waiting_telegram_id")


@pytest.mark.anyio
async def test_admin_settings_views_clear_fsm_state():
    from bot.handlers.admin_settings_views import store_settings_view

    call = MagicMock()
    call.from_user.id = 111
    call.answer = AsyncMock()
    bot = MagicMock()
    user_repo = MagicMock()
    user_repo.get_or_create = AsyncMock(return_value=MagicMock(language="fa"))
    session = AsyncMock()

    state = MagicMock()
    state.clear = AsyncMock()
    with patch("bot.handlers.admin_settings_views.is_admin", return_value=True), \
         patch("bot.handlers.admin_settings_views._render_settings", AsyncMock()):
        await store_settings_view(call, bot, user_repo, session, state=state)
        state.clear.assert_awaited_once()


@pytest.mark.anyio
async def test_admin_user_detail_clears_fsm_state():
    from bot.handlers.admin_user_bans import telegram_user_detail

    call = MagicMock()
    call.from_user.id = 111
    call.from_user.username = "admin"
    call.data = "adm:user:12345"
    call.answer = AsyncMock()
    bot = MagicMock()
    user_repo = MagicMock()
    target_user = MagicMock(telegram_id=12345, username="target", is_banned=False, balance=100)
    user_repo.get_or_create = AsyncMock(return_value=MagicMock(language="fa", telegram_id=111))
    session = AsyncMock()
    remnawave = MagicMock()
    remnawave.get_users_by_telegram_id = AsyncMock(return_value=[])

    state = MagicMock()
    state.clear = AsyncMock()

    with patch("bot.handlers.admin_user_bans._is_admin", return_value=True), \
         patch("bot.handlers.admin_user_bans.UserRepository") as mock_urepo_cls, \
         patch("bot.handlers.admin_user_bans.render_menu", AsyncMock()), \
         patch("bot.db.repositories.wallet_repo.WalletRepository.get_wallet", AsyncMock(return_value=MagicMock(balance=100))):
        mock_urepo_cls.return_value.get_by_telegram_id = AsyncMock(return_value=target_user)
        await telegram_user_detail(call, bot, user_repo, session, remnawave, state=state)
        state.clear.assert_awaited_once()

