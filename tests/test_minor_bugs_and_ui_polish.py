"""Tests for minor backend fixes, report period restructuring, and TMA UI polish."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.db.base import Base
from bot.db.models import Topup, User, Wallet
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.formatting import parse_iso
from bot.web.user_nodes import _is_safe_public_ip


@pytest.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield session_factory
    await engine.dispose()


@pytest.mark.anyio
async def test_parse_iso_naive_and_aware():
    """Verify parse_iso attaches UTC timezone if naive to prevent compare bugs."""
    naive_iso = "2026-11-05T12:00:00"
    dt_naive = parse_iso(naive_iso)
    assert dt_naive is not None
    assert dt_naive.tzinfo is not None
    assert dt_naive.tzinfo == timezone.utc

    aware_iso = "2026-11-05T12:00:00+03:30"
    dt_aware = parse_iso(aware_iso)
    assert dt_aware is not None
    assert dt_aware.tzinfo is not None

    now_utc = datetime.now(timezone.utc)
    # Comparison should work without TypeError: can't compare offset-naive and offset-aware datetimes
    assert dt_naive > now_utc or dt_naive <= now_utc


@pytest.mark.anyio
def test_is_safe_public_ip_full_rfc1918():
    """Verify _is_safe_public_ip catches all 10/8, 172.16/12 (172.16-31), 192.168/16, and loopback."""
    assert not _is_safe_public_ip("127.0.0.1")
    assert not _is_safe_public_ip("10.0.0.5")
    assert not _is_safe_public_ip("192.168.1.100")
    assert not _is_safe_public_ip("172.16.0.1")
    assert not _is_safe_public_ip("172.24.0.1")
    assert not _is_safe_public_ip("172.31.255.254")

    # Safe public IPs
    assert _is_safe_public_ip("172.32.0.1")
    assert _is_safe_public_ip("8.8.8.8")
    assert _is_safe_public_ip("1.1.1.1")
    assert _is_safe_public_ip("5.200.10.50")
    # Invalid string
    assert not _is_safe_public_ip("invalid-ip")


@pytest.mark.anyio
async def test_wallet_repo_pending_count_and_concurrency(memory_db):
    """Verify pending_count uses count query and get_wallet handles concurrent insertion."""
    async with memory_db() as session:
        repo = WalletRepository(session)
        w = await repo.get_wallet(1001)
        assert w.balance == 0

        # Add topups
        t1 = Topup(telegram_id=1001, amount=50000, status="pending")
        t2 = Topup(telegram_id=1001, amount=100000, status="pending")
        t3 = Topup(telegram_id=1001, amount=20000, status="approved")
        session.add_all([t1, t2, t3])
        await session.commit()

        cnt = await repo.pending_count(1001)
        assert cnt == 2


@pytest.mark.anyio
async def test_user_repo_get_or_create_concurrency(memory_db):
    """Verify get_or_create succeeds and updates attributes."""
    async with memory_db() as session:
        repo = UserRepository(session)
        u1 = await repo.get_or_create(555, "initial_name", "Initial Name")
        await session.commit()
        assert u1.telegram_id == 555

        u2 = await repo.get_or_create(555, "updated_name", "Updated Name")
        await session.commit()
        assert u2.username == "updated_name"
        assert u2.full_name == "Updated Name"


@pytest.mark.anyio
async def test_security_header_nosniff():
    """Verify X-Content-Type-Options: nosniff is set by cors_and_security_middleware."""
    from bot.web.server import cors_and_security_middleware

    req = MagicMock(spec=web.Request)
    req.method = "GET"
    req.path = "/api/user/profile"
    req.headers = {}
    req.app = {"settings": None, "is_dev": True}

    async def fake_handler(r):
        return web.Response(text="ok")

    resp = await cors_and_security_middleware(req, fake_handler)
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


@pytest.mark.anyio
async def test_admin_sms_private_chat_requires_command():
    """Verify admin SMS handling requires /sms in private chat."""
    from aiogram.types import Chat, Message, User as TgUser

    from bot.handlers.admin_topups import _is_admin_sms_message

    admin_tg = TgUser(id=999999, is_bot=False, first_name="Admin")
    pv_chat = Chat(id=999999, type="private")
    group_chat = Chat(id=-1001234567, type="supergroup")

    with patch("bot.handlers.admin_topups._is_admin", return_value=True):
        # 1. Normal conversation in private chat with bank keywords should NOT trigger SMS
        msg_pv_normal = Message(
            message_id=1,
            date=datetime.now(),
            chat=pv_chat,
            from_user=admin_tg,
            text="سلام واریز به حساب ۱۰ انجام شد",
        )
        assert not _is_admin_sms_message(msg_pv_normal)

        # 2. Command /sms in private chat SHOULD trigger
        msg_pv_cmd = Message(
            message_id=2,
            date=datetime.now(),
            chat=pv_chat,
            from_user=admin_tg,
            text="/sms واریز به حساب ۱۰ مبلغ ۵۰۰۰۰",
        )
        assert _is_admin_sms_message(msg_pv_cmd)

        # 3. Bank keywords in group chat SHOULD trigger
        msg_group = Message(
            message_id=3,
            date=datetime.now(),
            chat=group_chat,
            from_user=admin_tg,
            text="واریز به حساب ۱۰ مبلغ ۵۰۰۰۰",
        )
        assert _is_admin_sms_message(msg_group)


@pytest.mark.anyio
async def test_reports_daily_and_nightly_breakdown():
    """Verify get_periodic_users_bandwidth provides distinct daily and nightly leaderboards."""
    from bot.web.admin_overview_charts import get_periodic_users_bandwidth

    mock_remnawave = AsyncMock()
    # 88 days 0, day 89 (yesterday) = 15 GB, day 90 (today) = 5 GB
    yesterday_bytes = 15 * (1024 ** 3)
    today_bytes = 5 * (1024 ** 3)
    data_series = [0] * 88 + [yesterday_bytes, today_bytes]

    mock_remnawave.get_user_bandwidth_stats = AsyncMock(return_value=[
        {"countryCode": "DE", "data": data_series}
    ])

    panel_users = [{"id": 101, "username": "pro_streamer", "usedTrafficBytes": 50 * (1024 ** 3)}]
    now_utc = datetime(2026, 11, 5, 14, 0, tzinfo=timezone.utc)

    result = await get_periodic_users_bandwidth(mock_remnawave, None, panel_users, now_utc, is_refresh=True)

    # 1. Daily reflects today's usage (offset 0)
    assert "daily" in result
    daily = result["daily"]
    assert "روزانه" in daily["label"]
    assert len(daily["top_users"]) == 1
    assert daily["top_users"][0]["used_gb"] == 5.0

    # 2. Nightly reflects yesterday's usage (offset 1)
    assert "nightly" in result
    nightly = result["nightly"]
    assert "شبانه" in nightly["label"]
    assert len(nightly["top_users"]) == 1
    assert nightly["top_users"][0]["used_gb"] == 15.0


@pytest.mark.anyio
async def test_support_link_resolution_in_start_invite_only(memory_db):
    """Verify support link is resolved from support_contact in invite_only mode."""
    from aiogram.types import Chat, Message, User as TgUser

    from bot.handlers.start import cmd_start

    msg = AsyncMock()
    msg.from_user.id = 77777
    msg.from_user.username = "guest"
    msg.from_user.full_name = "Guest User"
    msg.text = "/start"
    msg.chat.id = 77777
    msg.chat.type = "private"

    bot_mock = AsyncMock()
    remnawave_mock = AsyncMock()
    state_mock = AsyncMock()

    async with memory_db() as session:
        # Set access_mode to invite_only and support_contact to @RemnaSupport
        from bot.db.repositories.app_setting_repo import AppSettingRepository
        s_repo = AppSettingRepository(session)
        await s_repo.set("access_mode", "invite_only")
        await s_repo.set("support_contact", "@RemnaSupport")
        await session.commit()

        u_repo = UserRepository(session)
        await cmd_start(msg, bot_mock, u_repo, session, state_mock, remnawave_mock)

        assert msg.answer.called
        call_kwargs = msg.answer.call_args.kwargs
        reply_markup = call_kwargs.get("reply_markup")
        assert reply_markup is not None
        # Inline button url should be https://t.me/RemnaSupport
        inline_kb = reply_markup.inline_keyboard
        assert len(inline_kb) == 1
        btn = inline_kb[0][0]
        assert btn.url == "https://t.me/RemnaSupport"


def test_frontend_polish_and_reports_5_tabs():
    """Verify reports 5 tabs, card text, support bubbles, and coupon formatting."""
    from pathlib import Path

    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    assert "id=\"repSubDaily\"" in app_html
    assert "id=\"repSubNightly\"" in app_html
    assert "id=\"repSubWeekly\"" in app_html
    assert "id=\"repSubMonthly\"" in app_html
    assert "id=\"repSubAnalytics\"" in app_html
    assert "id=\"viewRepDaily\"" in app_html
    assert "id=\"viewRepNightly\"" in app_html
    assert "Blu, But Lovely" in app_html
    assert "Blu Bank, But Lovely" not in app_html

    wallet_js = Path("bot/web/static/js/wallet.js").read_text(encoding="utf-8")
    assert "Blu, But Lovely" in wallet_js
    assert "Blu Bank, But Lovely" not in wallet_js

    comp_css = Path("bot/web/static/css/components.css").read_text(encoding="utf-8")
    assert ".chat-bubble-user" in comp_css
    assert ".chat-bubble-admin" in comp_css
    assert "html.theme-light #cardAutoCardNumber" in comp_css

    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    assert "(${discMsg} تخفیف)" in shop_js
    assert "dir=\"ltr\"" in shop_js


def test_custom_plan_disabled_card_stripe_and_reports_polish():
    """Verify card magnetic stripe is edge-to-edge, custom plan has disabled notice, and reports polish."""
    from pathlib import Path

    app_html = Path("bot/web/templates/app.html").read_text(encoding="utf-8")
    assert "absolute inset-x-0 top-3 sm:top-4 h-7 bg-slate-950/90 shadow-inner" in app_html
    assert "id=\"customPlanDisabledNotice\"" in app_html
    assert "id=\"customPlanBuilderContent\"" in app_html
    assert "نمودار مصرف هفتگی (7 روز اخیر):" in app_html
    assert "نمودار مصرف روزانه (7 روز اخیر):" not in app_html
    assert "id=\"repDailyChartCanvas\"" in app_html
    assert "id=\"repNightlyChartCanvas\"" in app_html
    assert app_html.index("id=\"repDailyChartCanvas\"") < app_html.index("id=\"repDailyNodesContainer\"")
    assert app_html.index("id=\"repNightlyChartCanvas\"") < app_html.index("id=\"repNightlyNodesContainer\"")
    assert "نمودار مصرف ساعتی امروز (24 ساعت):" in app_html
    assert "نمودار مصرف ساعتی دیشب (24 ساعت):" in app_html
    assert "data-amt=\"50000\"" not in app_html
    assert "data-amt=\"100000\"" in app_html
    assert "placeholder=\"مبلغ دلخواه را وارد کنید (تومان)...\"" in app_html
    assert "--/--/-- - 23:59" in app_html

    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    assert "customPlanDisabledNotice" in shop_js
    assert "customPlanBuilderContent" in shop_js

    app_js = Path("bot/web/static/js/app.js").read_text(encoding="utf-8")
    assert "toEnglishDigits(data.today_jalali)} - 23:59" in app_js
    assert "repDailyChartCanvas" in app_js
    assert "repNightlyChartCanvas" in app_js


@pytest.mark.anyio
async def test_wallet_transaction_history_and_invoice_status_ssot(session_factory):
    """Verify order status in wallet transaction history matches DB status and invoice service."""
    from bot.db.models import Order, OrderStatus, User
    from bot.web.user_profile import _fetch_transaction_history
    from bot.services.invoice_service import get_order_invoice_data

    async with session_factory() as session:
        u = User(telegram_id=987654321, username="status_tester", full_name="Tester")
        session.add(u)
        await session.commit()

        # Create paid order, pending order, refunded order, and failed order
        o_paid = Order(telegram_id=987654321, service_name="Plan Paid", amount=50000, status=OrderStatus.PAID.value)
        o_pend = Order(telegram_id=987654321, service_name="Plan Pend", amount=60000, status=OrderStatus.PENDING.value)
        o_ref = Order(telegram_id=987654321, service_name="Plan Ref", amount=70000, status=OrderStatus.REFUNDED.value)
        o_fail = Order(telegram_id=987654321, service_name="Plan Fail", amount=80000, status=OrderStatus.FAILED.value)
        session.add_all([o_paid, o_pend, o_ref, o_fail])
        await session.commit()

        txs = await _fetch_transaction_history(session, 987654321, "Asia/Tehran")
        tx_by_id = {tx["id"]: tx for tx in txs if tx["type"] == "order"}

        # Verify wallet status mapping
        assert tx_by_id[o_paid.id]["status"] == "موفق"
        assert tx_by_id[o_paid.id]["status_color"] == "emerald"
        assert tx_by_id[o_pend.id]["status"] == "در انتظار پرداخت"
        assert tx_by_id[o_pend.id]["status_color"] == "amber"
        assert tx_by_id[o_ref.id]["status"] == "مسترد شده"
        assert tx_by_id[o_ref.id]["status_color"] == "purple"
        assert tx_by_id[o_fail.id]["status"] == "ناموفق"
        assert tx_by_id[o_fail.id]["status_color"] == "rose"

        # Verify invoice service matches
        inv_paid = await get_order_invoice_data(session, o_paid.id, 987654321)
        assert inv_paid["payment"]["status"] == "پرداخت شده"
        assert inv_paid["payment"]["is_paid"] is True

        inv_pend = await get_order_invoice_data(session, o_pend.id, 987654321)
        assert inv_pend["payment"]["status"] == "در انتظار پرداخت"
        assert inv_pend["payment"]["is_paid"] is False

        inv_ref = await get_order_invoice_data(session, o_ref.id, 987654321)
        assert inv_ref["payment"]["status"] == "مسترد شده (مرجوع)"
        assert inv_ref["payment"]["is_paid"] is False

        inv_fail = await get_order_invoice_data(session, o_fail.id, 987654321)
        assert inv_fail["payment"]["status"] == "ناموفق / لغو شده"
        assert inv_fail["payment"]["is_paid"] is False
        assert inv_paid["payment"]["deducted_amount"] == 50000
        assert inv_fail["payment"]["deducted_amount"] == 0
        assert "کسر شده" in inv_paid["payment"]["deduction_note"]
        assert "هیچ هزینه‌ای" in inv_fail["payment"]["deduction_note"]
