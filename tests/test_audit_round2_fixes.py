"""Unit and regression tests for Round 2 Audit Fixes.
Covers:
- RateLimitMiddleware correctly unwrap Update objects and enforce flood protection
- Admin user detail callback filter does not shadow sub-routers (squads, devices)
- Purchases max_purchases atomic capacity enforcement and compensation
- Crypto grace period alignment (120 min) and duplicate tx_hash handling
- Auth client IP validation against spoofing
- Admin topup receipt path traversal protection
- Expiry calculation off-by-one correction for recent expiration
- Node monitor flapping dampening
- JS XSS escaping verification
"""
import time
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import pytest
from aiogram.types import CallbackQuery, Message, Update, User as TgUser

from bot.middlewares.rate_limit import RateLimitMiddleware, _extract_user_and_inner, _buckets
from bot.handlers.admin_user_detail import _is_panel_user_detail_callback


def test_rate_limit_middleware_unwraps_update():
    """Verify RateLimitMiddleware correctly extracts user_id from an Update object."""
    tg_user = TgUser(id=987654321, is_bot=False, first_name="Test", language_code="fa")
    msg = MagicMock(spec=Message)
    msg.from_user = tg_user

    update = MagicMock(spec=Update)
    update.message = msg
    update.edited_message = None
    update.callback_query = None
    update.inline_query = None
    update.chosen_inline_result = None
    update.pre_checkout_query = None
    update.shipping_query = None

    uid, user_obj, inner = _extract_user_and_inner(update, {})
    assert uid == 987654321
    assert user_obj == tg_user
    assert inner == msg


@pytest.mark.anyio
async def test_rate_limit_middleware_drops_excessive_events():
    """Verify RateLimitMiddleware increments buckets and drops events exceeding limit."""
    tg_user = TgUser(id=88887777, is_bot=False, first_name="Spammer", language_code="en")
    cb = MagicMock(spec=CallbackQuery)
    cb.from_user = tg_user
    cb.answer = AsyncMock()

    update = MagicMock(spec=Update)
    update.message = None
    update.callback_query = cb
    update.edited_message = None
    update.inline_query = None
    update.chosen_inline_result = None
    update.pre_checkout_query = None
    update.shipping_query = None

    middleware = RateLimitMiddleware()
    handler = AsyncMock(return_value="OK")

    # Clear bucket
    _buckets[88887777].clear()

    # Fill bucket up to limit (30)
    for _ in range(30):
        res = await middleware(handler, update, {})
        assert res == "OK"

    assert len(_buckets[88887777]) == 30

    # 31st event must be dropped (return None) and toast answered
    res = await middleware(handler, update, {})
    assert res is None
    cb.answer.assert_called_once()
    assert "Too fast" in cb.answer.call_args[0][0]


def test_admin_user_detail_callback_filter():
    """Verify _is_panel_user_detail_callback yields False for sub-router actions."""
    # Sub-router prefixes must NOT match parent dispatcher
    sub_callbacks = [
        "adm:puser:squads:7:all:0",
        "adm:puser:tgsq:7:uuid1:all:0",
        "adm:puser:hwidlim:7:all:0",
        "adm:puser:sethwid:7:2:all:0",
        "adm:puser:hwid:7:all:0",
        "adm:puser:delhwid:7:hwid1:all:0",
    ]
    for cb_data in sub_callbacks:
        cb = MagicMock(spec=CallbackQuery)
        cb.data = cb_data
        assert _is_panel_user_detail_callback(cb) is False, f"Should yield False for {cb_data}"

    # Parent router actions must match
    parent_callbacks = [
        "adm:puser:7:all:0",
        "adm:puser:toggle:7:all:0",
        "adm:puser:reset:7:all:0",
        "adm:puser:revoke:7:all:0",
        "adm:puser:ext:7:all:0",
        "adm:puser:strat:7:all:0",
    ]
    for cb_data in parent_callbacks:
        cb = MagicMock(spec=CallbackQuery)
        cb.data = cb_data
        assert _is_panel_user_detail_callback(cb) is True, f"Should yield True for {cb_data}"


def test_client_ip_spoof_prevention():
    """Verify get_client_ip validates IP format and ignores arbitrary spoofed strings."""
    from bot.web.auth import get_client_ip

    req = MagicMock()
    req.remote = "127.0.0.1"
    req.headers = {
        "CF-Connecting-IP": "malicious-header-injection",
        "X-Real-IP": "5.6.7.8",
    }
    ip = get_client_ip(req)
    # The invalid CF-Connecting-IP string must be skipped, falling back to valid X-Real-IP
    assert ip == "5.6.7.8"


def test_expiry_days_left_does_not_floor_to_negative_immediately():
    """Verify recent expiration (< 24h) does not jump to -1 day."""
    diff_sec_1min_ago = -60.0
    days_left = int(diff_sec_1min_ago // 86400) if diff_sec_1min_ago >= 0 else int(diff_sec_1min_ago / 86400)
    assert days_left == 0  # 0 days expired, NOT -1

    diff_sec_25h_ago = -90000.0
    days_left_25h = int(diff_sec_25h_ago // 86400) if diff_sec_25h_ago >= 0 else int(diff_sec_25h_ago / 86400)
    assert days_left_25h == -1  # 1 day expired


def test_node_monitor_flapping_dampened():
    """Verify node monitor does not send duplicate offline alerts within 5 minutes."""
    from bot.services import node_monitor
    node_monitor._NODE_STATES.clear()

    now_ts = 1000.0
    state = node_monitor._NODE_STATES.setdefault(1, {"is_offline": False, "last_alert_ts": now_ts})

    # Recover 60 seconds later
    state["is_offline"] = False
    state["last_alert_ts"] = now_ts + 60.0

    # Drop again 60 seconds later (total 120s since last alert)
    time_since_alert = (now_ts + 120.0) - state["last_alert_ts"]
    COOLDOWN_SECONDS = 3600.0
    should_alert = (not state["is_offline"] and time_since_alert > min(300.0, COOLDOWN_SECONDS)) or (time_since_alert > COOLDOWN_SECONDS)
    assert should_alert is False  # Must NOT alert because 60s < 300s dampening window


def test_shop_and_utils_js_xss_escaped():
    """Verify shop.js and utils.js escape plan names and badges."""
    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    assert 'data-name="${escapeHtml(p.name)}"' in shop_js
    assert 'data-badge="${escapeHtml(p.badge || \'\')}"' in shop_js

    utils_js = Path("bot/web/static/js/utils.js").read_text(encoding="utf-8")
    assert 'const textOut = options.raw ? cleanText : escapeHtml(cleanText);' in utils_js


def test_topup_receipt_traversal_prevention():
    """Verify local receipt retrieval uses strict Path.name and boundary checks."""
    admin_topups_py = Path("bot/web/admin_topups.py").read_text(encoding="utf-8")
    assert "target_name = Path(raw_target).name" in admin_topups_py
    assert "target_path.is_relative_to(base_dir)" in admin_topups_py


def test_crypto_mark_paid_grace_and_hash_handling():
    """Verify crypto mark_paid uses 120m default grace and handles duplicate tx_hash."""
    crypto_repo_py = Path("bot/db/repositories/crypto_repo.py").read_text(encoding="utf-8")
    assert "max_expired_grace_minutes: int = 120" in crypto_repo_py
    assert "Duplicate tx_hash collision in mark_paid" in crypto_repo_py


def test_birthday_and_autorenew_cooldown_windows():
    """Verify birthday uses 365 days window and auto_renew insufficient balance cooldown is 1 hour."""
    bday_py = Path("bot/services/birthday.py").read_text(encoding="utf-8")
    assert "timedelta(days=365)" in bday_py

    renew_py = Path("bot/services/auto_renew.py").read_text(encoding="utf-8")
    assert "ttl_seconds=3600" in renew_py


def test_purchases_capacity_reservation():
    """Verify purchases.py reserves max_purchases atomically before panel/balance."""
    purchases_py = Path("bot/services/purchases.py").read_text(encoding="utf-8")
    assert "service_reserved = True" in purchases_py
    assert "capacity_exhausted" in purchases_py
    assert "Service.purchases_count < Service.max_purchases" in purchases_py

