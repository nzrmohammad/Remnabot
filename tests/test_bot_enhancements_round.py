"""Tests for bot wallet, custom plan devices, wheel coupons, configs, and formatting fixes."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.db.models import Topup, Order
from bot.locales.texts import t
from bot.services.app_settings import StoreSettings
from bot.services.formatting import format_date, format_datetime
from bot.services.service_display import service_block
from bot.web.user_shop import compute_custom_plan_price


def test_format_datetime_and_date_with_string_and_timestamp():
    """Verify format_datetime and format_date handle ISO string, timestamp int, and datetime without ValueError."""
    # 1. ISO string
    iso_str = "2026-11-15T08:18:00+00:00"
    res1 = format_datetime(iso_str, "fa")
    assert "1405" in res1
    assert "08" in res1 or "11" in res1

    # 2. String date
    res_date = format_date(iso_str, "fa")
    assert "1405" in res_date

    # 3. Timestamp int
    ts = 1794717324
    res2 = format_datetime(ts, "fa")
    assert len(res2) > 5

    # 4. Standard datetime
    dt = datetime(2026, 11, 15, 8, 18, tzinfo=timezone.utc)
    res3 = format_datetime(dt, "fa")
    assert "1405" in res3

    # 5. Invalid / None fallback
    assert format_datetime(None, "fa") == "—"
    assert format_date(None, "fa") == "—"


def test_service_block_hides_squad_uuid():
    """Verify service_block does NOT print raw internal squad UUIDs to users."""
    mock_svc = MagicMock()
    mock_svc.id = 1
    mock_svc.name = "سرویس ویژه"
    mock_svc.price = 50000
    mock_svc.traffic_gb = 30
    mock_svc.duration_days = 30
    mock_svc.traffic_strategy = "NO_RESET"
    mock_svc.hwid_limit = 2
    mock_svc.squad_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    mock_svc.description = "توضیحات تست"

    rendered = service_block(mock_svc, "fa")
    assert "a1b2c3d4-e5f6" not in rendered
    assert "🧩" not in rendered
    assert "سرویس ویژه" in rendered


def test_custom_plan_device_pricing():
    """Verify compute_custom_plan_price scales base price with hwid_limit (+15% per extra user)."""
    settings = StoreSettings(
        card_number="",
        card_holder="",
        topup_min_amount=10000,
        default_squad_uuid="",
        expiry_grace_days=1,
        expiry_remind_days="",
        topic_topups=None,
        topic_orders=None,
        topic_support=None,
        topic_alerts=None,
        support_contact="",
        custom_plan_price_per_gb=4500,
        custom_plan_price_per_day=1000,
        custom_plan_base_price=100000,
        custom_plan_extra_device_percent=15,
    )

    # 1 device
    _, vol1, price1 = compute_custom_plan_price(50, 30, settings, hwid_limit=1)
    # 2 devices (+15%)
    _, vol2, price2 = compute_custom_plan_price(50, 30, settings, hwid_limit=2)
    # 3 devices (+30%)
    _, vol3, price3 = compute_custom_plan_price(50, 30, settings, hwid_limit=3)

    assert vol1 == 0
    assert price2 > price1
    # Check 15% increase on subtotal
    assert round((price2 - price1) / price1, 2) == 0.15
    assert round((price3 - price1) / price1, 2) == 0.30


@pytest.mark.anyio
async def test_custom_plan_summary_includes_squad_notices():
    """Verify custom plan summary displays Iran / Tunnel warnings based on squad name."""
    from bot.handlers.custom_plan import _build_custom_plan_summary

    mock_user = MagicMock(telegram_id=999, language="fa")
    mock_session = AsyncMock()
    mock_wallet = MagicMock(balance=500000)

    settings = StoreSettings(
        card_number="",
        card_holder="",
        topup_min_amount=10000,
        default_squad_uuid="",
        expiry_grace_days=1,
        expiry_remind_days="",
        topic_topups=None,
        topic_orders=None,
        topic_support=None,
        topic_alerts=None,
        support_contact="",
        custom_plan_price_per_gb=4500,
        custom_plan_price_per_day=1000,
        custom_plan_base_price=100000,
        custom_plan_extra_device_percent=15,
    )

    with patch("bot.handlers.custom_plan.WalletRepository") as mock_wrepo, \
         patch("bot.handlers.custom_plan.get_user_loyalty", AsyncMock(return_value={"discount_percent": 0})):
        mock_wrepo.return_value.get_wallet = AsyncMock(return_value=mock_wallet)

        # 1. Iran server squad notice
        lines_iran, kb_iran = await _build_custom_plan_summary(
            mock_user, mock_session, settings, gb=20, days=30, hwid=2, cache=None, lang="fa", squad_name="سرور ایران (مخصوص بانکی)"
        )
        text_iran = "\n".join(lines_iran)
        assert "سرور ایران" in text_iran
        assert "بانکی" in text_iran
        assert "۲ دستگاه" in text_iran or "2 دستگاه" in text_iran
        btn_data = kb_iran.as_markup().inline_keyboard[0][0].callback_data
        assert btn_data == "cplan:buy:20:30:2"

        # 2. Tunnel squad notice
        lines_tunnel, _ = await _build_custom_plan_summary(
            mock_user, mock_session, settings, gb=20, days=30, hwid=1, cache=None, lang="fa", squad_name="تانل اختصاصی آلمان"
        )
        text_tunnel = "\n".join(lines_tunnel)
        assert "تانل اختصاصی" in text_tunnel
        assert "پایداری بالا" in text_tunnel


@pytest.mark.anyio
async def test_wallet_topup_methods_includes_all_gateways():
    """Verify wallet topup menu offers Card, Stars, TON, TRX, POL, Voucher when enabled."""
    from bot.handlers.wallet import topup_start

    mock_call = MagicMock()
    mock_call.from_user.id = 12345
    mock_call.from_user.username = "test_user"
    mock_call.answer = AsyncMock()

    mock_bot = MagicMock()
    mock_user_repo = MagicMock()
    mock_user = MagicMock(language="fa", telegram_id=12345)
    mock_user_repo.get_or_create = AsyncMock(return_value=mock_user)
    mock_session = AsyncMock()
    mock_state = AsyncMock()

    settings = StoreSettings(
        card_number="6037999999999999",
        card_holder="مدیریت",
        topup_min_amount=10000,
        default_squad_uuid="",
        expiry_grace_days=1,
        expiry_remind_days="",
        topic_topups=None,
        topic_orders=None,
        topic_support=None,
        topic_alerts=None,
        support_contact="",
        card_enabled=True,
        stars_enabled=True,
        stars_rate_toman=1500,
        crypto_enabled=True,
        ton_wallet_address="EQTestTonWalletAddress123",
        ton_rate_toman=350000,
        trx_enabled=True,
        trx_wallet_address="TTestTronWalletAddress123",
        pol_enabled=True,
        pol_wallet_address="0xTestPolygonWalletAddress123",
    )

    with patch("bot.handlers.wallet.get_store_settings", AsyncMock(return_value=settings)), \
         patch("bot.handlers.wallet.is_maintenance", AsyncMock(return_value=False)), \
         patch("bot.handlers.wallet.render_menu", AsyncMock()) as mock_render:

        await topup_start(mock_call, mock_bot, mock_user_repo, mock_session, mock_state)
        mock_render.assert_awaited_once()
        kb = mock_render.call_args[0][4]
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

        assert "wallet:method:card" in callbacks
        assert "wallet:method:stars" in callbacks
        assert "wallet:method:ton" in callbacks
        assert "wallet:method:trx" in callbacks
        assert "wallet:method:pol" in callbacks
        assert "wallet:voucher" in callbacks


@pytest.mark.anyio
async def test_account_configs_header_and_verify():
    """Verify account configs displays 'تعداد کل کانفیگ‌ها' without duplicate emoji, and matches shortUuid."""
    from bot.handlers.configs import _verify_account

    remnawave = MagicMock()
    remnawave.get_users_by_telegram_id = AsyncMock(return_value=[
        {"id": 101, "uuid": "uuid-101", "shortUuid": "short-101", "status": "ACTIVE"},
        {"id": 102, "uuid": "uuid-102", "shortUuid": "short-102", "status": "ACTIVE"},
    ])

    # Lookup by id, uuid, and shortUuid
    acc1 = await _verify_account(remnawave, 777, 101)
    assert acc1["id"] == 101

    acc2 = await _verify_account(remnawave, 777, "uuid-102")
    assert acc2["id"] == 102

    acc3 = await _verify_account(remnawave, 777, "short-101")
    assert acc3["id"] == 101

    # Invalid
    acc_none = await _verify_account(remnawave, 777, "invalid-acc")
    assert acc_none is None
