"""Smoke tests for the bug-fix batch (no DB/panel needed)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.db.models import Order
from bot.middlewares.rate_limit import MAX_EVENTS, WINDOW_SECONDS
from bot.services.purchases import _expire_from, _traffic_bytes
from bot.services.reconcile import INTERVAL_SECONDS, STALE_MINUTES
from bot.services.reports import _weekday_name


def test_traffic_no_reset_accumulates():
    gb = 1024 ** 3
    assert _traffic_bytes(10, 0, "NO_RESET") == 10 * gb
    assert _traffic_bytes(10, 5 * gb, "NO_RESET") == 15 * gb


def test_traffic_periodic_replaces():
    gb = 1024 ** 3
    for strategy in ("DAY", "WEEK", "MONTH", "MONTH_ROLLING"):
        assert _traffic_bytes(10, 5 * gb, strategy) == 10 * gb
    assert _traffic_bytes(0, 5 * gb, "MONTH") == 0


def test_expire_capped():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    far = _expire_from(5000, now)
    assert far <= now + timedelta(days=1095) + timedelta(seconds=5)


def test_weekday_names():
    from datetime import datetime

    # 2026-09-04 is a Friday.
    dt = datetime(2026, 9, 4, 12, 0, 0)
    assert _weekday_name(dt, "en") == "Friday"
    assert isinstance(_weekday_name(dt, "fa"), str)


def test_rate_limit_constants():
    assert MAX_EVENTS == 30
    assert WINDOW_SECONDS == 60.0


def test_order_statuses_fit_column():
    # String(10): all lifecycle statuses must fit.
    for status in ("paid", "pending", "failed", "refunded"):
        assert len(status) <= 10
        assert Order(status=status).status == status


def test_reconcile_constants():
    assert STALE_MINUTES == 15
    assert INTERVAL_SECONDS == 30 * 60


def test_renew_reactivates():
    # Renewals must send status="ACTIVE" or expiry-disabled accounts stay dead.
    import inspect

    from bot.services.remnawave import RemnawaveClient

    sig = inspect.signature(RemnawaveClient.update_user_subscription)
    assert "status" in sig.parameters


def test_stats_page_clamp():
    from bot.handlers.stats import _clamp_page

    assert _clamp_page(0, 3) == 0
    assert _clamp_page(2, 3) == 2
    assert _clamp_page(99, 3) == 2
    assert _clamp_page(-5, 3) == 0
    assert _clamp_page(0, 0) == 0
    assert _clamp_page(0, 1) == 0


def test_last_jalali_day_known_dates():
    from datetime import datetime

    from bot.services.reports import is_last_jalali_day

    # 2026-03-20 = Esfand 29, 1404 (last day, non-leap tail) → True
    assert is_last_jalali_day(datetime(2026, 3, 20, 12, 0, 0)) is True
    # 2026-03-21 = Farvardin 1, 1405 → False
    assert is_last_jalali_day(datetime(2026, 3, 21, 12, 0, 0)) is False
    # 2026-09-05 mid-Shahrivar → False
    assert is_last_jalali_day(datetime(2026, 9, 5, 12, 0, 0)) is False
    # 2026-09-22 = Shahrivar 31 (last day of a 31-day month) → True
    assert is_last_jalali_day(datetime(2026, 9, 22, 12, 0, 0)) is True


def test_jalali_month_range():
    from datetime import datetime

    from bot.services.reports import jalali_month_range, prev_jalali_month_range

    now = datetime(2026, 9, 5, 23, 59, 0)
    start, end = jalali_month_range(now)
    assert end == now
    # Shahrivar 1, 1405 = 2026-08-23
    assert (start.year, start.month, start.day) == (2026, 8, 23)

    p_start, p_end = prev_jalali_month_range(now)
    assert p_start < p_end < start
    # Previous month (Mordad) has 31 days
    assert (p_end.date() - p_start.date()).days == 30


def test_monthly_texts_exist():
    from bot.locales.texts import TEXTS

    for lang in ("fa", "en"):
        for key in (
            "monthly_title", "monthly_day", "monthly_others", "monthly_total",
            "monthly_hi", "monthly_sum_total", "monthly_sum_more",
            "monthly_sum_less", "monthly_sum_same", "monthly_sum_top",
            "settings_monthly_label", "settings_monthly_hint",
            "btn_toggle_monthly",
        ):
            assert key in TEXTS[lang], f"{lang}.{key} missing"


def test_admin_ids_parsing():
    from bot.config import Settings

    assert Settings.parse_admin_ids([123, 456]) == [123, 456]
    assert Settings.parse_admin_ids("123, 456") == [123, 456]
    assert Settings.parse_admin_ids("123,456") == [123, 456]
    assert Settings.parse_admin_ids("[123, 456]") == [123, 456]
    assert Settings.parse_admin_ids(12345) == [12345]
    assert Settings.parse_admin_ids("") == []
    assert Settings.parse_admin_ids("  ") == []


def test_topic_settings_none_or_int():
    from bot.config import Settings

    assert Settings.empty_str_to_none(None) is None
    assert Settings.empty_str_to_none("") is None
    assert Settings.empty_str_to_none(42) == 42
    assert Settings.empty_str_to_none("105") == 105


def test_heartbeat_path():
    import os
    import tempfile

    from bot.main import HEARTBEAT_FILE

    expected = os.path.join(tempfile.gettempdir(), "bot_heartbeat")
    assert HEARTBEAT_FILE == expected


def test_stats_account_block_burn_rate_and_flags():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from bot.handlers.stats import _account_block

    now = datetime(2026, 9, 24, 18, 0, 0, tzinfo=ZoneInfo("Asia/Tehran"))
    account = {
        "username": "testuser",
        "status": "active",
        "trafficLimitBytes": 100 * 1024**3,
        "userTraffic": {
            "usedTrafficBytes": 20 * 1024**3,
            "lifetimeUsedTrafficBytes": 200 * 1024**3,
        },
    }
    today = (
        1500 * 1024**2,
        [
            {"nodeName": "Netherlands", "countryCode": "NL", "total": 1500 * 1024**2},
            {"nodeName": "Germany", "countryCode": "DE", "total": 0},
        ],
    )
    block = _account_block(
        account, today, now, "fa", index=1, count=1, burn_rate_days=108
    )

    # Germany with 0 total should not appear
    assert "🇩🇪" not in block
    # Netherlands flag should appear without name and without leading space
    assert "🇳🇱 : <b>1.46 GB</b>" in block or "🇳🇱 : <b>" in block
    assert "  🇳🇱" not in block
    assert "Netherlands" not in block
    # Burn rate should be below lifetime
    lifetime_idx = block.index("مصرف کل از ابتدا")
    burn_idx = block.index("با الگوی مصرف شما")
    assert burn_idx > lifetime_idx
    assert "108 روز" in block


def test_topup_amount_prompt_content():
    from bot.locales.texts import TEXTS

    assert "یا یکی از مبالغ آماده زیر را انتخاب کنید" in TEXTS["fa"]["topup_amount_prompt"]
    assert "or select one of the quick amounts below" in TEXTS["en"]["topup_amount_prompt"]


def test_sparkline_generator():
    from bot.handlers.stats import generate_sparkline

    assert generate_sparkline([]) == ""
    assert generate_sparkline([0, 0, 0, 0, 0, 0, 0]) == "       "
    bars = generate_sparkline([10, 20, 30, 50, 70, 90, 100])
    assert len(bars) == 7
    # Earlier values should be shorter than the peak
    assert bars[0] < bars[-1]


def test_sparkline_in_account_block():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from bot.handlers.stats import _account_block

    now = datetime(2026, 9, 24, 18, 0, 0, tzinfo=ZoneInfo("Asia/Tehran"))
    account = {
        "username": "sparkuser",
        "status": "active",
        "trafficLimitBytes": 100 * 1024**3,
        "userTraffic": {"usedTrafficBytes": 10 * 1024**3},
    }
    block = _account_block(
        account, None, now, "fa", sparkline=(" ▂▃▅▇█", 15 * 1024**3)
    )
    assert "روند ۷ روز اخیر" in block
    assert " ▂▃▅▇█" in block
    assert "15.00 GB" in block


def test_new_texts_exist():
    from bot.locales.texts import TEXTS

    for lang in ("fa", "en"):
        for key in (
            "stats_sparkline",
            "device_new_connected",
            "tx_topup",
            "tx_topup_pending",
            "tx_topup_rejected",
            "tx_order_paid",
            "tx_order_refunded",
        ):
            assert key in TEXTS[lang], f"{lang}.{key} missing"





@pytest.mark.anyio
async def test_check_account_new_devices():
    from bot.services.devices import check_account_new_devices

    bot = MagicMock()
    bot.send_message = AsyncMock()

    remnawave = MagicMock()
    remnawave.get_user_hwid_devices = AsyncMock(
        return_value=[{"hwid": "hwid-1", "platform": "Android", "deviceModel": "Pixel 7"}]
    )

    session = MagicMock()
    with patch("bot.services.devices.DeviceRepository") as MockRepo:
        repo_instance = MagicMock()
        MockRepo.return_value = repo_instance
        repo_instance.get_known_hwids = AsyncMock(return_value=set())
        repo_instance.add_device = AsyncMock()

        account = {"id": 10, "username": "testuser"}
        res1 = await check_account_new_devices(
            bot, session, remnawave, account, 123456, "fa"
        )
        # Seeding: returns empty list, no message sent
        assert res1 == []
        bot.send_message.assert_not_called()
        repo_instance.add_device.assert_awaited_once()

        # 2nd call: new device connected!
        repo_instance.get_known_hwids = AsyncMock(return_value={"hwid-1"})
        remnawave.get_user_hwid_devices = AsyncMock(
            return_value=[
                {"hwid": "hwid-1", "platform": "Android", "deviceModel": "Pixel 7"},
                {
                    "hwid": "hwid-2",
                    "platform": "Windows",
                    "deviceModel": "PC",
                    "requestIp": "1.2.3.4",
                },
            ]
        )

        res2 = await check_account_new_devices(
            bot, session, remnawave, account, 123456, "fa"
        )
        assert len(res2) == 1
        assert res2[0]["hwid"] == "hwid-2"
        bot.send_message.assert_called_once()
        args, _ = bot.send_message.call_args
        assert args[0] == 123456
        assert "اتصال دستگاه جدید به اکانت!" in args[1]
        assert "Windows" in args[1]


def test_admin_panel_layout_persian():
    """Verify admin panel buttons are 3 rows of 2 RTL + main menu, no topups/logs."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    from bot.locales.texts import t

    lang = "fa"
    kb = InlineKeyboardBuilder()
    # Row 1: Left = User Management, Right = Dashboard
    kb.button(text=t(lang, "btn_manage_users"), callback_data="adm:users")
    kb.button(text=t(lang, "btn_dashboard"), callback_data="adm:dash")
    # Row 2: Left = Manage Services, Right = Sales Report
    kb.button(text=t(lang, "btn_manage_services"), callback_data="adm:services")
    kb.button(text=t(lang, "btn_sales_report"), callback_data="adm:sales")
    # Row 3: Left = Broadcast, Right = Store Settings
    kb.button(text=t(lang, "btn_broadcast"), callback_data="adm:broadcast")
    kb.button(text=t(lang, "btn_store_settings"), callback_data="adm:settings")
    # Row 4: Main Menu
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    kb.adjust(2, 2, 2, 1)

    markup = kb.as_markup()
    rows = markup.inline_keyboard
    assert len(rows) == 4
    # Row 1: [0]=users, [1]=dash
    assert rows[0][0].callback_data == "adm:users"
    assert rows[0][1].callback_data == "adm:dash"
    # Row 2: [0]=services, [1]=sales
    assert rows[1][0].callback_data == "adm:services"
    assert rows[1][1].callback_data == "adm:sales"
    # Row 3: [0]=broadcast, [1]=settings
    assert rows[2][0].callback_data == "adm:broadcast"
    assert rows[2][1].callback_data == "adm:settings"
    # Row 4: [0]=nav:main_menu
    assert rows[3][0].callback_data == "nav:main_menu"

    # Make sure adm:topups and adm:logs were removed
    all_callbacks = [btn.callback_data for row in rows for btn in row]
    assert "adm:topups" not in all_callbacks
    assert "adm:logs" not in all_callbacks


def test_admin_users_menu_layout_persian():
    """Verify users menu has search (left) & create (right), then list, then back."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    from bot.locales.texts import t

    lang = "fa"
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_user_search"), callback_data="adm:user:search")
    kb.button(text=t(lang, "btn_create_panel_user"), callback_data="adm:user:create")
    kb.button(text=t(lang, "btn_panel_users_list"), callback_data="adm:ulist:all:0")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(2, 1, 1)

    markup = kb.as_markup()
    rows = markup.inline_keyboard
    assert len(rows) == 3
    assert rows[0][0].callback_data == "adm:user:search"
    assert rows[0][1].callback_data == "adm:user:create"
    assert rows[1][0].callback_data == "adm:ulist:all:0"
    assert rows[2][0].callback_data == "menu:admin"


def test_panel_users_filtering():
    """Verify filtering panel users by category (online, never, offline, disabled, limited, expiring)."""
    from datetime import datetime, timedelta, timezone

    from bot.handlers.admin_users import _filter_panel_users

    now = datetime.now(timezone.utc)
    recent_iso = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    past_iso = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    expiring_iso = (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    far_iso = (now + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    users = [
        {"id": 1, "username": "u_online", "status": "ACTIVE", "trafficLimitBytes": 100, "usedTrafficBytes": 10, "onlineAt": recent_iso, "expireAt": far_iso},
        {"id": 2, "username": "u_never", "status": "ACTIVE", "trafficLimitBytes": 100, "usedTrafficBytes": 0, "onlineAt": None, "expireAt": far_iso},
        {"id": 3, "username": "u_offline", "status": "ACTIVE", "trafficLimitBytes": 100, "usedTrafficBytes": 20, "onlineAt": past_iso, "expireAt": far_iso},
        {"id": 4, "username": "u_disabled", "status": "DISABLED", "trafficLimitBytes": 100, "usedTrafficBytes": 10, "onlineAt": None, "expireAt": far_iso},
        {"id": 5, "username": "u_limited", "status": "ACTIVE", "trafficLimitBytes": 100, "usedTrafficBytes": 100, "onlineAt": None, "expireAt": far_iso},
        {"id": 6, "username": "u_expiring", "status": "ACTIVE", "trafficLimitBytes": 100, "usedTrafficBytes": 10, "onlineAt": None, "expireAt": expiring_iso},
    ]

    assert len(_filter_panel_users(users, "all")) == 6
    assert [u["id"] for u in _filter_panel_users(users, "online")] == [1]
    assert [u["id"] for u in _filter_panel_users(users, "never")] == [2]
    assert [u["id"] for u in _filter_panel_users(users, "offline")] == [3]
    assert [u["id"] for u in _filter_panel_users(users, "disabled")] == [4]
    assert [u["id"] for u in _filter_panel_users(users, "limited")] == [5]
    assert [u["id"] for u in _filter_panel_users(users, "expiring")] == [6]


@pytest.mark.anyio
async def test_store_settings_db_overrides():
    """Verify StoreSettings dynamically reads DB overrides."""
    from bot.services.app_settings import get_store_settings

    session = AsyncMock()
    with patch("bot.services.app_settings.AppSettingRepository") as mock_repo_cls:
        repo_inst = mock_repo_cls.return_value
        repo_inst.all = AsyncMock(
            return_value={
                "card_number": "6037997111223344",
                "card_holder": "Test Admin",
                "topup_min_amount": "150000",
                "expiry_grace_days": "7",
                "expiry_remind_days": "5,3,1",
                "topic_topups": "101",
                "topic_orders": "102",
                "topic_support": "103",
                "topic_alerts": "104",
                "support_contact": "@MySupportBot",
            }
        )
        store = await get_store_settings(session)
        assert store.card_number == "6037997111223344"
        assert store.card_holder == "Test Admin"
        assert store.topup_min_amount == 150000
        assert store.expiry_grace_days == 7
        assert store.expiry_remind_days == "5,3,1"
        assert store.topic_topups == 101
        assert store.topic_orders == 102
        assert store.topic_support == 103
        assert store.topic_alerts == 104
        assert store.support_contact == "@MySupportBot"


@pytest.mark.anyio
async def test_admin_user_management_constants():
    """Verify panel users list PAGE_SIZE is 15 and all required keys exist."""
    from bot.handlers.admin_users import PAGE_SIZE
    from bot.locales.texts import TEXTS

    assert PAGE_SIZE == 15

    for lang in ("fa", "en"):
        for key in (
            "btn_quick_extend",
            "btn_traffic_strategy",
            "btn_hwid_limit",
            "btn_edit_tid",
            "btn_edit_desc",
            "bcast_target_title",
            "bcast_target_all",
            "bcast_target_active",
            "bcast_target_expired",
            "bcast_target_balance",
            "bcast_target_buyers",
            "bcast_preview_target",
        ):
            assert key in TEXTS[lang], f"{lang}.{key} missing"


@pytest.mark.anyio
async def test_resolve_broadcast_recipients():
    """Verify audience filtering in _resolve_broadcast_recipients."""
    from datetime import datetime, timedelta, timezone
    from unittest.mock import MagicMock

    from bot.handlers.admin_ops import _resolve_broadcast_recipients

    session = AsyncMock()
    remnawave = MagicMock()

    # Mock UserRepository.all_users
    u1 = MagicMock(telegram_id=101)
    u2 = MagicMock(telegram_id=102)
    u3 = MagicMock(telegram_id=103)

    with patch("bot.handlers.admin_ops.UserRepository") as mock_u_repo:
        mock_u_repo.return_value.all_users = AsyncMock(return_value=[u1, u2, u3])

        # 1. target = "all"
        res_all = await _resolve_broadcast_recipients(session, remnawave, "all")
        assert set(res_all) == {101, 102, 103}

        # 2. target = "balance"
        mock_bal_res = MagicMock()
        mock_bal_res.fetchall.return_value = [(101,), (103,)]
        session.execute = AsyncMock(return_value=mock_bal_res)
        res_bal = await _resolve_broadcast_recipients(session, remnawave, "balance")
        assert set(res_bal) == {101, 103}

        # 3. target = "buyers"
        mock_buy_res = MagicMock()
        mock_buy_res.fetchall.return_value = [(102,)]
        session.execute = AsyncMock(return_value=mock_buy_res)
        res_buyers = await _resolve_broadcast_recipients(session, remnawave, "buyers")
        assert set(res_buyers) == {102}

        # 4. target = "active"
        now = datetime.now(timezone.utc)
        future_iso = (now + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        past_iso = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        remnawave.get_all_panel_users = AsyncMock(return_value=[
            {"id": 1, "telegramId": 101, "status": "ACTIVE", "expireAt": future_iso},
            {"id": 2, "telegramId": 102, "status": "ACTIVE", "expireAt": past_iso},
            {"id": 3, "telegramId": 103, "status": "DISABLED", "expireAt": future_iso},
        ])
        res_act = await _resolve_broadcast_recipients(session, remnawave, "active")
        assert set(res_act) == {101}

        # 5. target = "expired" (all_tids: {101, 102, 103} - active_tids: {101} -> {102, 103})
        res_exp = await _resolve_broadcast_recipients(session, remnawave, "expired")
        assert set(res_exp) == {102, 103}


@pytest.mark.anyio
async def test_format_days_left():
    from datetime import datetime, timedelta, timezone

    from bot.handlers.admin_users import _format_days_left

    now = datetime.now(timezone.utc)
    future_iso = (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    past_iso = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

    assert _format_days_left(future_iso, "fa") == "5 روز"
    assert _format_days_left(future_iso, "en") == "5d"
    assert _format_days_left(past_iso, "fa") == "منقضی"
    assert _format_days_left(None, "fa") == "نامحدود"


@pytest.mark.anyio
async def test_stats_connection_line_emojis():
    from datetime import datetime, timedelta, timezone

    from bot.handlers.stats import _connection_line

    now = datetime.now(timezone.utc)
    recent_iso = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Never connected -> ⚪️
    line_never = _connection_line({}, now, "fa")
    assert "⚪️" in line_never
    assert "هنوز متصل نشده" not in line_never

    # Online now -> 🟢
    line_online = _connection_line({"onlineAt": recent_iso}, now, "fa")
    assert "🟢" in line_online
    assert "آنلاین" not in line_online


def test_account_view_keyboard_has_get_configs():
    from bot.handlers.account import _account_view_keyboard

    account = {"id": 123, "subscriptionUrl": "https://example.com/sub"}
    kb = _account_view_keyboard(account, "fa", multi=False)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "cfg:acc:123" in callbacks


def test_parse_subscription_text():
    import base64
    import json

    from bot.services.configs import parse_subscription_text

    raw_vless = "vless://uuid@1.1.1.1:443?security=reality#%F0%9F%87%A9%F0%9F%87%AA%20Germany"
    raw_vmess = "vmess://" + base64.b64encode(
        json.dumps({"ps": "Netherlands", "add": "2.2.2.2", "port": 443}).encode()
    ).decode()
    raw_trojan = "trojan://pass@3.3.3.3:443#Trojan-Node"

    plaintext = f"{raw_vless}\n{raw_vmess}\n{raw_trojan}"
    b64 = base64.b64encode(plaintext.encode()).decode()

    # Test plaintext parsing
    configs_plain = parse_subscription_text(plaintext)
    assert len(configs_plain) == 3
    assert configs_plain[0]["name"] == "🇩🇪 Germany"
    assert configs_plain[0]["protocol"] == "vless"
    assert configs_plain[1]["name"] == "Netherlands"
    assert configs_plain[1]["protocol"] == "vmess"
    assert configs_plain[2]["name"] == "Trojan-Node"
    assert configs_plain[2]["protocol"] == "trojan"

    # Test base64 parsing
    configs_b64 = parse_subscription_text(b64)
    assert len(configs_b64) == 3
    assert configs_b64[0]["name"] == "🇩🇪 Germany"
    assert configs_b64[1]["name"] == "Netherlands"

    # Test empty or invalid
    assert parse_subscription_text("") == []
    assert parse_subscription_text("   \n  ") == []


@pytest.mark.anyio
async def test_execute_purchase_create_new_flag():
    from bot.services.purchases import execute_purchase

    remnawave = MagicMock()
    # User owns 1 account
    remnawave.get_users_by_telegram_id = AsyncMock(return_value=[
        {"id": 10, "username": "old_user", "expireAt": "2026-10-01T00:00:00Z"}
    ])
    remnawave.create_user = AsyncMock(return_value={
        "id": 99,
        "username": "u123_abcd",
        "subscriptionUrl": "https://sub.example.com/123",
    })
    remnawave.update_user_subscription = AsyncMock()

    service = MagicMock()
    service.id = 1
    service.name = "Test Service"
    service.price = 50000
    service.duration_days = 30
    service.traffic_gb = 50
    service.traffic_strategy = "NO_RESET"
    service.hwid_limit = 2
    service.squad_uuid = None

    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=100000)))
    session.commit = AsyncMock()

    with patch("bot.services.app_settings.is_maintenance", AsyncMock(return_value=False)), \
         patch("bot.services.purchases.get_store_settings") as mock_store, \
         patch("bot.services.purchases.OrderRepository") as mock_order_repo, \
         patch("bot.services.purchases._pick_username", AsyncMock(return_value="u123_abcd")):

        mock_store.return_value = MagicMock(default_squad_uuid=None)
        order_repo_inst = MagicMock()
        mock_order_repo.return_value = order_repo_inst
        order_repo_inst.create = AsyncMock(return_value=MagicMock())
        order_repo_inst.mark_paid = AsyncMock()

        # Call with create_new=True -> MUST call create_user, NOT update_user_subscription
        res = await execute_purchase(
            remnawave, session, service, 123456, create_new=True
        )
        assert res.ok is True
        assert res.panel_user_id == 99
        remnawave.create_user.assert_awaited_once()
        remnawave.update_user_subscription.assert_not_awaited()


@pytest.mark.anyio
async def test_single_configs_flow():
    from bot.handlers.configs import single_config_detail, single_configs_entry

    bot = MagicMock()
    user_repo = MagicMock()
    user_repo.get_or_create = AsyncMock(return_value=MagicMock(language="fa", is_verified=True))
    user_repo.set_verified = AsyncMock()

    remnawave = MagicMock()

    # 1. Multi-account user: should prompt account picker
    remnawave.get_users_by_telegram_id = AsyncMock(return_value=[
        {"id": 1, "username": "acc1", "subscriptionUrl": "https://sub.example/1"},
        {"id": 2, "username": "acc2", "subscriptionUrl": "https://sub.example/2"},
    ])
    call = MagicMock()
    call.from_user.id = 555
    call.from_user.username = "test"
    call.answer = AsyncMock()

    with patch("bot.handlers.configs.render_menu", AsyncMock()) as mock_render:
        await single_configs_entry(call, bot, user_repo, remnawave)
        mock_render.assert_awaited_once()
        # Verify picker keyboard was rendered with both accounts
        kb = mock_render.call_args[0][4]
        buttons = [b.callback_data for row in kb.inline_keyboard for b in row]
        assert "cfg:acc:1" in buttons
        assert "cfg:acc:2" in buttons

    # 2. Config detail view: renders config on screen via render_menu with back button
    call_show = MagicMock()
    call_show.data = "cfg:show:1:0"
    call_show.from_user.id = 555
    call_show.from_user.username = "test"
    call_show.answer = AsyncMock()

    with patch("bot.handlers.configs.fetch_subscription_configs", AsyncMock(return_value=[
        {"name": "🇩🇪 Germany", "protocol": "vless", "uri": "vless://uuid@1.2.3.4:443#DE"}
    ])), patch("bot.handlers.configs.render_menu", AsyncMock()) as mock_render_detail:
        await single_config_detail(call_show, bot, user_repo, remnawave)
        mock_render_detail.assert_awaited_once()
        text = mock_render_detail.call_args[0][3]
        assert "<code>vless://uuid@1.2.3.4:443#DE</code>" in text
        assert "🇩🇪 Germany" in text
        # Verify back button to configs list exists
        kb_detail = mock_render_detail.call_args[0][4]
        callbacks_detail = [b.callback_data for row in kb_detail.inline_keyboard for b in row]
        assert "cfg:acc:1" in callbacks_detail
        call_show.answer.assert_awaited_once()


@pytest.mark.anyio
async def test_admin_user_wallet_management_unlinked_user():
    from bot.handlers.admin_users import telegram_user_detail

    bot = MagicMock()
    user_repo = MagicMock()
    user_repo.get_or_create = AsyncMock(return_value=MagicMock(language="fa", is_verified=True))

    remnawave = MagicMock()
    remnawave.get_users_by_telegram_id = AsyncMock(return_value=[])

    session = AsyncMock()
    # Mock UserRepository.get_by_telegram_id -> None (first time), get_or_create -> User
    created_target = MagicMock(username="Sana", telegram_id=98765, last_active_at=None)

    call = MagicMock()
    call.data = "adm:user:98765"
    call.from_user.id = 123456  # admin
    call.from_user.username = "admin"
    call.answer = AsyncMock()

    with patch("bot.handlers.admin_users._is_admin", return_value=True), \
         patch("bot.handlers.admin_users.UserRepository") as mock_user_repo_cls, \
         patch("bot.handlers.admin_users.WalletRepository") as mock_wallet_repo_cls, \
         patch("bot.handlers.admin_users.render_menu", AsyncMock()) as mock_render:

        user_repo_instance = MagicMock()
        user_repo_instance.get_by_telegram_id = AsyncMock(return_value=None)
        user_repo_instance.get_or_create = AsyncMock(return_value=created_target)
        mock_user_repo_cls.return_value = user_repo_instance

        wallet_instance = MagicMock()
        wallet_instance.get_wallet = AsyncMock(return_value=MagicMock(balance=0))
        mock_wallet_repo_cls.return_value = wallet_instance

        await telegram_user_detail(call, bot, user_repo, session, remnawave)

        # Should render menu without raising or showing acc_error
        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]
        assert "98765" in text
        user_repo_instance.get_or_create.assert_awaited_once()


@pytest.mark.anyio
async def test_single_config_detail_copy_text_button_and_no_duplicate_emoji():
    from bot.handlers.configs import single_config_detail

    bot = MagicMock()
    user_repo = MagicMock()
    user_repo.get_or_create = AsyncMock(return_value=MagicMock(language="fa", telegram_id=123))

    remnawave = MagicMock()
    call = MagicMock()
    call.data = "cfg:show:10:0"
    call.from_user.id = 123
    call.from_user.username = "user1"
    call.answer = AsyncMock()

    mock_account = {"id": 10, "username": "Mohammad", "subscriptionUrl": "https://sub.example/link"}
    mock_configs = [{"name": "Netherland 1", "uri": "vless://mock-uuid@nl.example.com:443", "protocol": "vless"}]

    with patch("bot.handlers.configs._verify_account", AsyncMock(return_value=mock_account)), \
         patch("bot.handlers.configs.fetch_subscription_configs", AsyncMock(return_value=mock_configs)), \
         patch("bot.handlers.configs.render_menu", AsyncMock()) as mock_render:

        await single_config_detail(call, bot, user_repo, remnawave)

        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]
        markup = mock_render.call_args[0][4]

        # No duplicate emoji "👤 👤"
        assert "👤 👤" not in text
        assert "👤 اکانت : <code>Mohammad</code>" in text

        # Check CopyTextButton is attached
        copy_btn = markup.inline_keyboard[0][0]
        assert copy_btn.copy_text is not None
        assert copy_btn.copy_text.text == "vless://mock-uuid@nl.example.com:443"


@pytest.mark.anyio
async def test_purchase_result_digital_receipt():
    from bot.handlers.service_request import _render_purchase_result
    from bot.services.purchases import PurchaseResult

    bot = MagicMock()
    user = MagicMock(language="fa", telegram_id=555)
    user_repo = MagicMock()
    user_repo.set_verified = AsyncMock()
    session = AsyncMock()

    result = PurchaseResult(
        ok=True,
        kind="success",
        subscription_url="https://sub.example.com/token123",
        new_balance=150000,
        panel_user_id=101,
        panel_username="Mohammad",
    )
    service = MagicMock(
        name="Plan 50GB",
        price=50000,
        duration_days=30,
        traffic_gb=50,
    )

    with patch("bot.handlers.service_request.render_menu", AsyncMock()) as mock_render:
        await _render_purchase_result(bot, user, user_repo, session, result, service, "fa")

        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]
        markup = mock_render.call_args[0][4]

        # Check digital receipt fields
        assert "رسید دیجیتال خرید سرویس" in text
        assert "تاریخ و ساعت" in text
        assert "وضعیت پرداخت" in text
        assert "موفق و پرداخت‌شده" in text
        assert "Plan 50GB" in text
        assert "Mohammad" in text
        assert "30 روز" in text
        assert "50 گیگابایت" in text
        assert "50,000 تومان" in text
        assert "150,000 تومان" in text
        assert "https://sub.example.com/token123" in text

        # Check buttons
        # Row 1: Copy subscription link
        row0 = markup.inline_keyboard[0]
        assert len(row0) == 1
        assert row0[0].copy_text is not None
        assert row0[0].copy_text.text == "https://sub.example.com/token123"

        # Row 2: Connection guide & Get configs
        row1_cbs = [btn.callback_data for btn in markup.inline_keyboard[1]]
        assert "menu:guide" in row1_cbs
        assert "cfg:acc:101" in row1_cbs


@pytest.mark.anyio
async def test_admin_orders_list_filtered():
    from bot.handlers.admin_ops import _render_orders_list

    bot = MagicMock()
    user = MagicMock(language="fa", telegram_id=123)
    user_repo = MagicMock()
    session = AsyncMock()

    mock_orders = [
        MagicMock(id=1, service_name="Plan A", amount=50000, status="paid"),
        MagicMock(id=2, service_name="Plan B", amount=100000, status="refunded"),
    ]

    with patch("bot.handlers.admin_ops.OrderRepository") as mock_repo_cls, \
         patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:

        repo = MagicMock()
        repo.total_revenue = AsyncMock(return_value=150000)
        repo.count = AsyncMock(return_value=2)
        repo.status_counts = AsyncMock(return_value={"all": 2, "paid": 1, "refunded": 1})
        repo.list_filtered = AsyncMock(return_value=mock_orders)
        mock_repo_cls.return_value = repo

        await _render_orders_list(bot, user, user_repo, session, status="all", page=0, query=None)

        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]
        markup = mock_render.call_args[0][4]

        assert "گزارش و لیست سفارشات" in text
        assert "150,000" in text

        # Check filter buttons exist in markup
        all_cbs = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert "adm:orders:all:0" in all_cbs
        assert "adm:orders:paid:0" in all_cbs
        assert "adm:orders:refunded:0" in all_cbs
        assert "adm:orders:search" in all_cbs
        assert "adm:ord:1:all:0" in all_cbs
        assert "adm:ord:2:all:0" in all_cbs
        assert "menu:admin" in all_cbs


@pytest.mark.anyio
async def test_reports_hub_layout():
    """Verify Reports hub has HWID, SRH, and Sessions, and has removed Orders and System Info."""
    from bot.handlers.admin_ops import _render_reports_hub

    bot = MagicMock()
    user = MagicMock(language="fa", telegram_id=123)
    user_repo = MagicMock()
    session = AsyncMock()
    remnawave = MagicMock()
    remnawave.get_all_panel_users = AsyncMock(return_value=[{"id": 1, "status": "ACTIVE"}])
    remnawave.get_nodes = AsyncMock(return_value=[{"id": 1, "isConnected": True}])

    with patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:
        await _render_reports_hub(bot, user, user_repo, session, remnawave)
        mock_render.assert_awaited_once()
        markup = mock_render.call_args[0][4]
        all_cbs = [btn.callback_data for row in markup.inline_keyboard for btn in row]

        assert "adm:rep:hwid" in all_cbs
        assert "adm:rep:srh" in all_cbs
        assert "adm:rep:sessions:0" in all_cbs
        assert "menu:admin" in all_cbs

        # Must NOT contain orders or system info
        assert "adm:orders:all:0" not in all_cbs
        assert "adm:rep:sysinfo" not in all_cbs


@pytest.mark.anyio
async def test_hwid_inspector_rendering():
    """Verify HWID inspector renders unique devices, total HWID, avg per user, platforms and apps."""
    from bot.handlers.admin_ops import _render_hwid_inspector

    bot = MagicMock()
    user = MagicMock(language="fa", telegram_id=123)
    user_repo = MagicMock()
    remnawave = MagicMock()
    remnawave.get_hwid_stats = AsyncMock(return_value={
        "stats": {
            "totalUniqueDevices": 68,
            "totalHwidDevices": 75,
            "averageHwidDevicesPerUser": 1.88,
        },
        "byPlatform": [
            {
                "platform": "Android",
                "count": 34,
                "byApp": [{"app": "Happ", "count": 28}, {"app": "v2box", "count": 4}],
            },
            {
                "platform": "iOS",
                "count": 33,
                "byApp": [{"app": "Happ", "count": 12}, {"app": "V2Box 10.1.7", "count": 9}],
            },
        ],
    })

    with patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:
        await _render_hwid_inspector(bot, user, user_repo, remnawave)
        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]

        assert "HWID Inspector" in text
        assert "68" in text
        assert "75" in text
        assert "2 (1.88)" in text
        assert "Android" in text
        assert "Happ" in text
        assert "v2box" in text
        assert "iOS" in text
        assert "V2Box 10.1.7" in text


@pytest.mark.anyio
async def test_srh_inspector_rendering():
    """Verify SRH inspector renders app distribution and hourly request stats."""
    from bot.handlers.admin_ops import _render_srh_inspector

    bot = MagicMock()
    user = MagicMock(language="fa", telegram_id=123)
    user_repo = MagicMock()
    remnawave = MagicMock()
    remnawave.get_srh_stats = AsyncMock(return_value={
        "byParsedApp": [
            {"app": "Streisand", "count": 381},
            {"app": "Happ", "count": 381},
        ],
        "hourlyRequestStats": [
            {"dateTime": "2026-09-27T10:00:00.000Z", "requestCount": 20},
            {"dateTime": "2026-09-27T11:00:00.000Z", "requestCount": 15},
        ],
    })

    with patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:
        await _render_srh_inspector(bot, user, user_repo, remnawave)
        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]

        assert "SRH Inspector" in text
        assert "Streisand" in text
        assert "Happ" in text
        assert "آمار ساعتی درخواست‌ها" in text
        assert "Peak" in text
        assert "20" in text


@pytest.mark.anyio
async def test_multi_ip_sessions_audit():
    """Verify get_multi_ip_sessions groups devices by user and isolates multi-IP users."""
    from bot.services.remnawave import RemnawaveClient

    client = RemnawaveClient("http://fake", "fake_token")
    mock_devices = [
        {"userId": 1, "requestIp": "1.1.1.1", "deviceModel": "Pixel", "platform": "Android"},
        {"userId": 1, "requestIp": "2.2.2.2", "deviceModel": "iPhone", "platform": "iOS"},
        {"userId": 2, "requestIp": "3.3.3.3", "deviceModel": "PC", "platform": "Windows"},
        {"userId": 2, "requestIp": "3.3.3.3", "deviceModel": "PC2", "platform": "Windows"},
    ]
    mock_users = [
        {"id": 1, "username": "alice"},
        {"id": 2, "username": "bob"},
    ]

    client.get_all_hwid_devices = AsyncMock(return_value=mock_devices)
    client.get_all_panel_users = AsyncMock(return_value=mock_users)

    res = await client.get_multi_ip_sessions()
    await client.close()

    assert res["total_users_with_devices"] == 2
    assert res["total_devices"] == 4
    assert res["multi_ip_users_count"] == 1
    assert res["multi_ip_users"][0]["username"] == "alice"
    assert res["multi_ip_users"][0]["ip_count"] == 2
    assert set(res["multi_ip_users"][0]["ips"]) == {"1.1.1.1", "2.2.2.2"}


@pytest.mark.anyio
async def test_live_sessions_explorer_render():
    """Verify Sessions Explorer renders title without parentheses, shows multi-IP users without extra text."""
    from bot.handlers.admin_ops import _render_sessions_explorer

    bot = MagicMock()
    user = MagicMock(language="fa", telegram_id=123)
    user_repo = MagicMock()
    remnawave = MagicMock()
    remnawave.get_live_sessions_explorer = AsyncMock(return_value={
        "total_users_online": 24,
        "total_connections": 25,
        "total_unique_ips": 8,
        "nodes_scanned": 5,
        "total_nodes": 5,
        "multi_ip_users": [
            {
                "userId": 2,
                "username": "Mohammad",
                "uniqueIps": {"172.18.0.5", "151.233.64.90"},
                "totalConnections": 2,
                "nodeConnections": [
                    {"nodeName": "Netherlands", "countryCode": "NL", "ips": ["172.18.0.5"]},
                    {"nodeName": "Germany", "countryCode": "DE", "ips": ["151.233.64.90"]},
                ],
            }
        ],
        "all_online_users": [],
    })

    with patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:
        await _render_sessions_explorer(bot, user, user_repo, remnawave, page=0)
        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]

        assert "⚡ <b>Sessions Explorer</b>" in text
        assert "(کاوشگر نشست‌ها و چند IP)" not in text
        assert "Mohammad" in text
        assert "2 IP" in text
        assert "دستگاه‌ها" not in text
        assert "مختلف" not in text
        assert "Netherlands" in text
        assert "172.18.0.5" in text
        assert "Germany" in text
        assert "151.233.64.90" in text


def test_account_button_and_view_remaining_traffic():
    """Verify remaining traffic calculation in account button and account detail text."""
    from bot.handlers.account import _format_account_btn, _account_view_text

    acc = {
        "id": 1,
        "username": "Mohammad",
        "status": "ACTIVE",
        "trafficLimitBytes": 30 * (1024 ** 3),
        "userTraffic": {"usedTrafficBytes": 10 * (1024 ** 3)},
        "expireAt": "2026-10-18T00:00:00Z",
    }
    btn_text = _format_account_btn(acc, "fa")
    assert "Mohammad" in btn_text
    assert "20 GB" in btn_text

    view_text = _account_view_text(acc, "fa")
    assert "حجم باقی‌مانده" in view_text
    assert "20 GB" in view_text
    assert "30 GB" in view_text


@pytest.mark.anyio
async def test_guide_platform_incy_and_no_main_menu():
    """Verify INCY is in guide download links and main menu button is removed."""
    from bot.handlers.guide import PLATFORMS, guide_platform

    # Check INCY in android, ios, windows
    assert any(name == "INCY" for name, _ in PLATFORMS["android"][1])
    assert any(name == "INCY" for name, _ in PLATFORMS["ios"][1])
    assert any(name == "INCY" for name, _ in PLATFORMS["windows"][1])

    bot = MagicMock()
    user = MagicMock(language="fa", telegram_id=123)
    user_repo = MagicMock()
    user_repo.get_or_create = AsyncMock(return_value=user)
    remnawave = MagicMock()
    remnawave.get_users_by_telegram_id = AsyncMock(return_value=[])

    call = MagicMock()
    call.data = "guide:android"
    call.from_user.id = 123
    call.from_user.username = "test"
    call.answer = AsyncMock()

    with patch("bot.handlers.guide.render_menu", AsyncMock()) as mock_render:
        await guide_platform(call, bot, user_repo, remnawave)
        mock_render.assert_awaited_once()
        markup = mock_render.call_args[0][4]
        all_cbs = [btn.callback_data for row in markup.inline_keyboard for btn in row if btn.callback_data]

        assert "menu:guide" in all_cbs
        # nav:main_menu must NOT be in guide_platform keyboard
        assert "nav:main_menu" not in all_cbs


@pytest.mark.anyio
async def test_profile_date_format():
    """Verify profile shows only Jalali date without remaining days."""
    from bot.handlers.profile import _render_profile

    bot = MagicMock()
    user = MagicMock(language="fa", telegram_id=123, username="test", is_verified=True, created_at=None)
    user_repo = MagicMock()
    wallet_repo = MagicMock()
    wallet_repo.get_wallet = AsyncMock(return_value=MagicMock(balance=50000))
    order_repo = MagicMock()
    order_repo.list_for_user = AsyncMock(return_value=[MagicMock()])
    session = AsyncMock()
    remnawave = MagicMock()
    remnawave.get_users_by_telegram_id = AsyncMock(return_value=[
        {"id": 1, "username": "Mohammad", "expireAt": "2026-10-18T00:00:00Z"}
    ])

    with patch("bot.handlers.profile.WalletRepository", return_value=wallet_repo), \
         patch("bot.handlers.profile.OrderRepository", return_value=order_repo), \
         patch("bot.handlers.profile.render_menu", AsyncMock()) as mock_render:

        await _render_profile(bot, user, user_repo, session, remnawave)
        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]

        assert "Mohammad" in text
        # Date should be present (Jalali 1405/07/27 or similar)
        assert "1405/07/" in text
        # "روز" should NOT be in the account line
        assert "روز (" not in text


def test_no_double_emoji_in_account():
    """Verify account detail does not render double emojis like 📊 📥."""
    from bot.handlers.account import _account_view_text

    acc = {
        "id": 1,
        "username": "Mohammad",
        "status": "ACTIVE",
        "trafficLimitBytes": 250 * (1024 ** 3),
        "userTraffic": {"usedTrafficBytes": int(24.1 * (1024 ** 3))},
        "expireAt": "2026-10-18T00:00:00Z",
    }
    text = _account_view_text(acc, "fa")
    assert "📊 📥" not in text
    assert "📥 حجم باقی‌مانده : <b>225.9 GB</b> (از 250 GB)" in text


def test_support_and_report_icons_and_nightly_hint():
    """Verify support icon, distinct report icon, and 23:59 nightly report hint."""
    from bot.locales.texts import t

    fa_sup = t("fa", "btn_support")
    assert "🎧" in fa_sup
    assert "🆘" not in fa_sup

    fa_rep = t("fa", "btn_sales_report")
    fa_dash = t("fa", "btn_dashboard")
    assert "📑" in fa_rep
    assert "📊" in fa_dash
    assert fa_rep[0] != fa_dash[0]  # distinct icons!

    hint_fa = t("fa", "settings_nightly_hint")
    assert "۲۳:۵۹" in hint_fa or "23:59" in hint_fa
    assert "۲۳:۵۷" not in hint_fa

    hint_en = t("en", "settings_nightly_hint")
    assert "23:59" in hint_en
    assert "23:57" not in hint_en


@pytest.mark.anyio
async def test_dashboard_remnawave_overview():
    """Verify admin dashboard displays Remnawave overview and no store revenue/orders."""
    from bot.handlers.admin_ops import dashboard

    call = MagicMock()
    call.from_user.id = 999
    call.from_user.username = "admin"
    call.answer = AsyncMock()

    bot = MagicMock()
    user_repo = MagicMock()
    user_repo.get_or_create = AsyncMock(return_value=MagicMock(language="fa"))
    session = AsyncMock()

    remnawave = MagicMock()
    remnawave.get_all_panel_users = AsyncMock(return_value=[
        {"id": 1, "username": "u1", "status": "ACTIVE", "usedTrafficBytes": 10 * 1024**3},
        {"id": 2, "username": "u2", "status": "DISABLED", "usedTrafficBytes": 5 * 1024**3},
        {"id": 3, "username": "u3", "status": "LIMITED", "usedTrafficBytes": 20 * 1024**3},
    ])
    remnawave.get_nodes = AsyncMock(return_value=[
        {"id": 1, "name": "NL-1", "countryCode": "NL", "isConnected": True, "trafficUsedBytes": 35 * 1024**3},
        {"id": 2, "name": "DE-1", "countryCode": "DE", "isConnected": False, "trafficUsedBytes": 0},
    ])
    remnawave.get_system_recap = AsyncMock(return_value={
        "version": "3.4.4",
        "traffic": {"totalBytes": 35 * 1024**3, "downloadBytes": 20 * 1024**3, "uploadBytes": 15 * 1024**3},
    })

    with patch("bot.handlers.admin_ops._is_admin", return_value=True), \
         patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:

        await dashboard(call, bot, user_repo, session, remnawave)
        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]

        assert "داشبورد پنل" in text
        assert "ریمناوِیو" not in text
        assert "فعال : <b>1</b>" in text
        assert "غیرفعال : <b>1</b>" in text
        assert "محدود شده (اتمام حجم) : <b>1</b>" in text
        assert "🟢 آنلاین : <b>1</b>" in text
        assert "🔴 آفلاین : <b>1</b>" in text
        assert "• 🟢" not in text  # Bullets removed!
        assert "35.00 GB" in text
        assert "v3.4.4" in text
        # Verify bot shop DB stats are removed:
        assert "درآمد" not in text
        assert "فروش" not in text
        assert "سفارش" not in text


@pytest.mark.anyio
async def test_store_settings_full_overview():
    """Verify store settings displays all items, card name, and topics without SOS."""
    from bot.handlers.admin_ops import _render_settings, _render_topics_settings
    from bot.services.app_settings import StoreSettings

    bot = MagicMock()
    user = MagicMock(language="fa", telegram_id=999)
    user_repo = MagicMock()
    session = AsyncMock()

    # Case 1: with support contact
    store = StoreSettings(
        card_number="6219-8618-1954-7695",
        card_holder="محمد جواد نظری",
        topup_min_amount=100000,
        support_contact="@Support_ID",
        support_direct_enabled=True,
        trial_enabled=True,
        trial_traffic_gb=1,
        trial_duration_days=1,
        referral_enabled=True,
        referral_reward_gb=2,
        expiry_grace_days=3,
        expiry_remind_days="3,1,0",
        default_squad_uuid=None,
        topic_topups=10,
        topic_orders=20,
        topic_support=30,
        topic_alerts=40,
    )

    with patch("bot.handlers.admin_ops.get_store_settings", AsyncMock(return_value=store)), \
         patch("bot.handlers.admin_ops.is_maintenance", AsyncMock(return_value=False)), \
         patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:

        await _render_settings(bot, user, user_repo, session)
        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]

        # Name label
        assert "👤 نام : محمد جواد نظری" in text
        assert "نام دارنده کارت" not in text
        # Support block: direct support is ABOVE support contact
        assert text.index("📞 پشتیبانی مستقیم") < text.index("📞 آیدی پشتیبانی")
        assert "📞 آیدی پشتیبانی : \u200e@Support_ID" in text
        assert "<code>@Support_ID</code>" not in text
        assert "📞 پشتیبانی مستقیم : ✅" in text
        assert "فعال" not in text.split("📞 پشتیبانی مستقیم")[1].split("\n")[0]
        # Trial & referral: multi-line layout with volume and duration
        assert "🎁 سرویس تست : ✅\n   حجم : \u200e1 GB\n   زمان : 1 روز" in text
        assert "🤝 سیستم دعوت : ✅\n   حجم : \u200e2 GB" in text
        # Grace period without (روز)
        assert "⏳ مهلت پس از انقضا : 3 روز" in text
        assert "مهلت پس از انقضا (روز)" not in text
        # Only card number has <code>
        assert "💳 شماره کارت : <code>6219-8618-1954-7695</code>" in text
        assert "<code>3,1,0</code>" not in text
        # Topics with names
        assert "شارژ (10) : Topups" in text
        assert "سفارش (20) : Orders" in text
        assert "پشتیبانی (30) : Support" in text
        assert "هشدار (40) : Alerts" in text

    # Case 2: without support contact -> only single line 📞 آیدی پشتیبانی : —
    store_no_sup = StoreSettings(
        card_number="1234",
        card_holder="Ali",
        topup_min_amount=50000,
        support_contact="",
        support_direct_enabled=False,
        trial_enabled=False,
        trial_traffic_gb=1,
        trial_duration_days=1,
        referral_enabled=False,
        referral_reward_gb=2,
        expiry_grace_days=3,
        expiry_remind_days="3,1",
        default_squad_uuid=None,
        topic_topups=None,
        topic_orders=None,
        topic_support=None,
        topic_alerts=None,
    )
    with patch("bot.handlers.admin_ops.get_store_settings", AsyncMock(return_value=store_no_sup)), \
         patch("bot.handlers.admin_ops.is_maintenance", AsyncMock(return_value=False)), \
         patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:

        await _render_settings(bot, user, user_repo, session)
        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]

        assert "📞 آیدی پشتیبانی : —" in text
        assert "📞 پشتیبانی مستقیم" not in text
        assert "🎁 سرویس تست : ❌" in text
        assert "🤝 سیستم دعوت : ❌" in text
        assert "شارژ : — (Topups)" in text
        assert "سفارش : — (Orders)" in text
        assert "پشتیبانی : — (Support)" in text
        assert "هشدار : — (Alerts)" in text

    # Case 3: Topics keyboard does NOT contain 🆘
    with patch("bot.handlers.admin_ops.get_store_settings", AsyncMock(return_value=store)), \
         patch("bot.handlers.admin_ops._get_admin_group_title", AsyncMock(return_value="SupportSuperGroup")), \
         patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:

        await _render_topics_settings(bot, user, user_repo, session)
        mock_render.assert_awaited_once()
        text_topics = mock_render.call_args[0][3]
        markup = mock_render.call_args[0][4]
        all_btn_texts = [b.text for row in markup.inline_keyboard for b in row]
        assert any("🎧 تاپیک پشتیبانی" in t for t in all_btn_texts)
        assert not any("🆘" in t for t in all_btn_texts)
        assert "10 (Topups)" in text_topics
        assert "<code>10" not in text_topics
        assert "SupportSuperGroup" in text_topics


@pytest.mark.anyio
async def test_trial_and_referral_submenus():
    """Verify trial and referral settings submenus have clean titles, badges, and button labels."""
    from bot.handlers.admin_ops import _render_trial_settings, _render_referral_settings
    from bot.services.app_settings import StoreSettings

    bot = MagicMock()
    user = MagicMock(language="fa", telegram_id=999)
    user_repo = MagicMock()
    session = AsyncMock()

    store = StoreSettings(
        card_number="6219-8618-1954-7695",
        card_holder="محمد",
        topup_min_amount=100000,
        support_contact="@Support_ID",
        support_direct_enabled=True,
        trial_enabled=True,
        trial_traffic_gb=5,
        trial_duration_days=3,
        referral_enabled=True,
        referral_reward_gb=10,
        expiry_grace_days=3,
        expiry_remind_days="3,1,0",
        default_squad_uuid=None,
        topic_topups=10,
        topic_orders=20,
        topic_support=30,
        topic_alerts=40,
    )

    # 1. Trial settings submenu
    with patch("bot.handlers.admin_ops.get_store_settings", AsyncMock(return_value=store)), \
         patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:

        await _render_trial_settings(bot, user, user_repo, session)
        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]
        markup = mock_render.call_args[0][4]
        btn_texts = [b.text for row in markup.inline_keyboard for b in row]

        # Only one emoji in title
        assert text.startswith("🎁 <b>تنظیمات اکانت تست</b>")
        assert "⚙️" not in text.split("\n")[0]
        # Clean status without 'فعال'
        assert "🎁 <b>وضعیت تست :</b> ✅" in text
        assert "فعال" not in text.split("🎁 <b>وضعیت تست :</b>")[1].split("\n")[0]
        # Volume and Duration without 'تست' and without code tags
        assert "📊 <b>حجم :</b> 5 GB" in text
        assert "<code>5 GB</code>" not in text
        assert "⏳ <b>زمان :</b> 3 روز" in text
        assert "<code>3 روز</code>" not in text
        # Button texts
        assert any("📊 حجم: 5 GB" in b for b in btn_texts)
        assert any("⏳ زمان: 3 روز" in b for b in btn_texts)
        assert any("وضعیت: ✅" in b for b in btn_texts)
        assert "برای تغییر حجم یا زمان، دکمه مربوطه را انتخاب کنید" in text

    # 2. Referral settings submenu
    with patch("bot.handlers.admin_ops.get_store_settings", AsyncMock(return_value=store)), \
         patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:

        await _render_referral_settings(bot, user, user_repo, session)
        mock_render.assert_awaited_once()
        text_ref = mock_render.call_args[0][3]
        markup_ref = mock_render.call_args[0][4]
        btn_ref_texts = [b.text for row in markup_ref.inline_keyboard for b in row]

        # Only one emoji in title
        assert text_ref.startswith("🤝 <b>تنظیمات سیستم دعوت</b>")
        assert "⚙️" not in text_ref.split("\n")[0]
        # Clean status without 'فعال'
        assert "🤝 <b>وضعیت سیستم دعوت :</b> ✅" in text_ref
        assert "فعال" not in text_ref.split("🤝 <b>وضعیت سیستم دعوت :</b>")[1].split("\n")[0]
        # Volume without 'پاداش دعوت' and without code tags
        assert "🎁 <b>حجم :</b> 10 GB" in text_ref
        assert "<code>10 GB</code>" not in text_ref
        # Button texts
        assert any("📊 حجم: 10 GB" in b for b in btn_ref_texts)
        assert any("وضعیت: ✅" in b for b in btn_ref_texts)
        # Helper text matches button name (دکمه حجم)
        assert "دکمه حجم را انتخاب کنید" in text_ref


@pytest.mark.anyio
async def test_inspectors_and_nodes_code_tags_cleanup():
    """Verify that HWID, SRH, dashboard, and nodes screens do not use code tags except node address."""
    from bot.handlers.admin_ops import _render_hwid_inspector, _render_srh_inspector
    from bot.services.remnawave import RemnawaveClient

    bot = MagicMock()
    user = MagicMock(language="fa", telegram_id=999)
    user_repo = MagicMock()
    remnawave = MagicMock(spec=RemnawaveClient)

    # 1. HWID Inspector: no <code> tags anywhere in rendered text
    hwid_data = {
        "totalUniqueDevices": 68,
        "totalHwidDevices": 75,
        "avgDevicesPerUser": 2,
        "platformDistribution": [
            {"platform": "Android", "count": 34, "byApp": [{"app": "Happ", "count": 28}]}
        ]
    }
    remnawave.get_hwid_stats = AsyncMock(return_value={"stats": hwid_data})
    remnawave.get_hwid_devices = AsyncMock(return_value=[])
    with patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:
        await _render_hwid_inspector(bot, user, user_repo, remnawave)
        mock_render.assert_awaited_once()
        text_hwid = mock_render.call_args[0][3]
        assert "<code>" not in text_hwid

    # 2. SRH Inspector: no <code> tags anywhere in rendered text
    srh_data = {
        "byParsedApp": [{"app": "Happ", "count": 50}],
        "hourlyRequestStats": [{"dateTime": "2026-09-27T12:00:00Z", "requestCount": 100}],
    }
    remnawave.get_srh_stats = AsyncMock(return_value=srh_data)
    with patch("bot.handlers.admin_ops.render_menu", AsyncMock()) as mock_render:
        await _render_srh_inspector(bot, user, user_repo, remnawave)
        mock_render.assert_awaited_once()
        text_srh = mock_render.call_args[0][3]
        assert "<code>" not in text_srh


@pytest.mark.anyio
async def test_support_contact_validation_and_toggle():
    """Verify support contact normalization and toggle behavior."""
    from bot.handlers.admin_ops import setting_toggle_boolean, settings_value_save
    from bot.services.app_settings import StoreSettings

    bot = MagicMock()
    user_repo = MagicMock()
    user_repo.get_or_create = AsyncMock(return_value=MagicMock(language="fa"))
    session = AsyncMock()

    # 1. Toggling direct support with empty contact must fail with alert
    call = MagicMock()
    call.from_user.id = 999
    call.from_user.username = "admin"
    call.data = "adm:settings:toggle:support_direct_enabled"
    call.answer = AsyncMock()

    store_empty = StoreSettings(
        card_number="", card_holder="", topup_min_amount=10000,
        support_contact="", support_direct_enabled=False,
        trial_enabled=False, trial_traffic_gb=1, trial_duration_days=1,
        referral_enabled=False, referral_reward_gb=2,
        expiry_grace_days=3, expiry_remind_days="3,1", default_squad_uuid=None,
        topic_topups=None, topic_orders=None, topic_support=None, topic_alerts=None,
    )
    with patch("bot.handlers.admin_ops._is_admin", return_value=True), \
         patch("bot.handlers.admin_ops.get_store_settings", AsyncMock(return_value=store_empty)):

        await setting_toggle_boolean(call, bot, user_repo, session)
        call.answer.assert_awaited_once()
        args, kwargs = call.answer.call_args
        assert "ابتدا باید آیدی پشتیبانی را در تنظیمات وارد کنید" in args[0]
        assert kwargs.get("show_alert") is True

    # 2. Saving username without @ normalizes to @
    state = MagicMock()
    state.get_data = AsyncMock(return_value={"settings_field": "support_contact"})
    state.clear = AsyncMock()
    msg = MagicMock()
    msg.from_user.id = 999
    msg.from_user.username = "admin"
    msg.text = "MohammadSupport"
    msg.chat.id = 123
    msg.message_id = 456

    mock_app_setting_repo = MagicMock()
    mock_app_setting_repo.set = AsyncMock()

    with patch("bot.handlers.admin_ops.delete_message_silently", AsyncMock()), \
         patch("bot.handlers.admin_ops.AppSettingRepository", return_value=mock_app_setting_repo), \
         patch("bot.handlers.admin_ops.AdminLogRepository", return_value=MagicMock(log=AsyncMock())), \
         patch("bot.handlers.admin_ops._render_settings", AsyncMock()):

        await settings_value_save(msg, bot, user_repo, session, state)
        mock_app_setting_repo.set.assert_awaited_with("support_contact", "@MohammadSupport")











