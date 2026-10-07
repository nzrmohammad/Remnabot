"""Unit and integration tests for the new Remnawave Bot features:
1. Free Trial Account (1 GB / 1 Day, username only, verified)
2. Referral System (deep linking, 5 GB traffic rewards, stats)
3. Discount Coupon System (percentage & fixed, max uses, one per user, validation)
4. Blacklist & Ban Management (BanCheckMiddleware)
5. Database Backup (JSON export)
6. Retention Loop & Retargeting (~7 day expired accounts)
7. Start command message preservation
"""
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.db.models import (
    Base,
    Order,
)
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.referral_repo import ReferralRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.middlewares.ban_check import BanCheckMiddleware
from bot.services.backup import create_database_backup


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.anyio
async def test_coupon_validation_and_usage(async_session: AsyncSession):
    repo = CouponRepository(async_session)

    # 1. Percentage discount coupon
    c_percent = await repo.create(
        code="SUMMER20",
        discount_percent=20,
        discount_amount=0,
        max_uses=2,
    )
    assert c_percent.code == "SUMMER20"
    assert c_percent.discount_percent == 20

    # Validate on 100,000 price
    valid, err, discount = await repo.validate_coupon("SUMMER20", telegram_id=111, price=100_000)
    assert valid is True
    assert err is None
    assert discount == 20_000

    # 2. Fixed discount coupon
    await repo.create(
        code="FIXED30",
        discount_percent=None,
        discount_amount=30_000,
        max_uses=10,
    )
    valid, err, discount = await repo.validate_coupon("FIXED30", telegram_id=111, price=50_000)
    assert valid is True
    assert discount == 30_000

    # Fixed discount greater than price caps at price
    valid, err, discount = await repo.validate_coupon("FIXED30", telegram_id=111, price=20_000)
    assert valid is True
    assert discount == 20_000

    # 3. Non-existent coupon
    valid, err, discount = await repo.validate_coupon("NONEXISTENT", telegram_id=111, price=50_000)
    assert valid is False
    assert err == "coupon_not_found"

    # 4. Inactive coupon
    await repo.toggle_active(c_percent.id)
    valid, err, discount = await repo.validate_coupon("SUMMER20", telegram_id=111, price=100_000)
    assert valid is False
    assert err == "coupon_inactive"
    await repo.toggle_active(c_percent.id)  # re-activate

    # 5. Usage tracking & per-user limit
    order = Order(
        telegram_id=111,
        service_id=1,
        service_name="Test Plan",
        amount=80_000,
        status="paid",
    )
    async_session.add(order)
    await async_session.flush()

    await repo.record_usage(c_percent.id, telegram_id=111, order_id=order.id, discount_applied=20_000)

    # Same user trying again should be rejected
    valid, err, discount = await repo.validate_coupon("SUMMER20", telegram_id=111, price=100_000)
    assert valid is False
    assert err == "coupon_already_used"

    # Another user can still use it (1 use left of max_uses=2)
    valid, err, discount = await repo.validate_coupon("SUMMER20", telegram_id=222, price=100_000)
    assert valid is True

    # Use up the remaining quota
    await repo.record_usage(c_percent.id, telegram_id=222, order_id=order.id, discount_applied=20_000)

    # Third user should hit limit
    valid, err, discount = await repo.validate_coupon("SUMMER20", telegram_id=333, price=100_000)
    assert valid is False
    assert err == "coupon_limit_reached"


@pytest.mark.anyio
async def test_referral_repository(async_session: AsyncSession):
    ref_repo = ReferralRepository(async_session)
    u_repo = UserRepository(async_session)

    referrer_id = 999
    friend_1 = 1001
    friend_2 = 1002

    await u_repo.get_or_create(referrer_id, "boss")

    assert await ref_repo.has_rewarded(friend_1) is False
    assert await ref_repo.get_invites_count(referrer_id) == 0
    assert await ref_repo.get_total_gb_earned(referrer_id) == 0

    # User 1 joins via referral
    await u_repo.get_or_create(friend_1, "f1")
    await u_repo.set_referrer(friend_1, referrer_id)
    # Record first reward: 5 GB
    await ref_repo.record_reward(referrer_id, friend_1, reward_gb=5)
    assert await ref_repo.has_rewarded(friend_1) is True
    assert await ref_repo.get_invites_count(referrer_id) == 1
    assert await ref_repo.get_total_gb_earned(referrer_id) == 5

    # User 2 joins via referral
    await u_repo.get_or_create(friend_2, "f2")
    await u_repo.set_referrer(friend_2, referrer_id)
    # Record second reward: 5 GB
    await ref_repo.record_reward(referrer_id, friend_2, reward_gb=5)
    assert await ref_repo.get_invites_count(referrer_id) == 2
    assert await ref_repo.get_total_gb_earned(referrer_id) == 10


@pytest.mark.anyio
async def test_user_ban_and_claimed_trial(async_session: AsyncSession):
    u_repo = UserRepository(async_session)

    user = await u_repo.get_or_create(telegram_id=55555, username="test_user")
    assert user.is_banned is False
    assert user.has_claimed_trial is False
    assert user.referred_by_id is None

    # Set referrer
    await u_repo.set_referrer(55555, referrer_id=999)
    updated = await u_repo.get_by_telegram_id(55555)
    assert updated.referred_by_id == 999

    # Set claimed trial
    await u_repo.set_claimed_trial(55555)
    updated = await u_repo.get_by_telegram_id(55555)
    assert updated.has_claimed_trial is True

    # Set banned
    await u_repo.set_banned(55555, banned=True)
    updated = await u_repo.get_by_telegram_id(55555)
    assert updated.is_banned is True

    banned_list = await u_repo.list_banned()
    assert len(banned_list) == 1
    assert banned_list[0].telegram_id == 55555

    # Unban
    await u_repo.set_banned(55555, banned=False)
    banned_list = await u_repo.list_banned()
    assert len(banned_list) == 0


@pytest.mark.anyio
async def test_ban_check_middleware(async_session: AsyncSession):
    u_repo = UserRepository(async_session)
    await u_repo.get_or_create(telegram_id=77777, username="banned_user")
    await u_repo.set_banned(77777, banned=True)

    middleware = BanCheckMiddleware()

    handler_mock = AsyncMock()

    # 1. Message from banned user
    banned_tg_user = MagicMock()
    banned_tg_user.id = 77777

    msg_event = MagicMock(spec=Message)
    msg_event.from_user = banned_tg_user
    msg_event.answer = AsyncMock()

    data = {"session": async_session}
    await middleware(handler_mock, msg_event, data)
    assert handler_mock.call_count == 0
    assert msg_event.answer.call_count == 1
    assert t("fa", "banned_user_notice") in msg_event.answer.call_args[0][0]

    # 2. CallbackQuery from banned user
    call_event = MagicMock(spec=CallbackQuery)
    call_event.from_user = banned_tg_user
    call_event.answer = AsyncMock()

    await middleware(handler_mock, call_event, data)
    assert handler_mock.call_count == 0
    assert call_event.answer.call_count == 1
    assert call_event.answer.call_args[1].get("show_alert") is True

    # 3. Message from non-banned user
    normal_tg_user = MagicMock()
    normal_tg_user.id = 88888
    normal_tg_user.username = "normal_guy"

    normal_msg = MagicMock(spec=Message)
    normal_msg.from_user = normal_tg_user

    await middleware(handler_mock, normal_msg, data)
    assert handler_mock.call_count == 1


@pytest.mark.anyio
async def test_database_backup_service(async_session: AsyncSession):
    # Seed sample records
    u_repo = UserRepository(async_session)
    await u_repo.get_or_create(123456, "alice")

    c_repo = CouponRepository(async_session)
    await c_repo.create("BACKUPCODE", discount_percent=15)

    path = await create_database_backup(async_session)
    filename = path.name
    try:
        assert os.path.exists(path)
        assert filename.startswith("remnabot_backup_")
        assert filename.endswith(".json")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        assert "users" in data
        assert "coupons" in data
        assert any(u["telegram_id"] == 123456 for u in data["users"])
        assert any(c["code"] == "BACKUPCODE" for c in data["coupons"])
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.mark.anyio
async def test_maybe_reward_referrer(async_session: AsyncSession):
    from bot.handlers.service_request import _maybe_reward_referrer
    from bot.services.app_settings import get_store_settings

    store = await get_store_settings(async_session)
    store.referral_enabled = True
    store.referral_reward_gb = 5

    u_repo = UserRepository(async_session)
    await u_repo.get_or_create(1111, "inviter")
    friend = await u_repo.get_or_create(2222, "friend")
    await u_repo.set_referrer(2222, 1111)

    # Reload friend
    friend = await u_repo.get_by_telegram_id(2222)

    remnawave = MagicMock()
    remnawave.get_users_by_telegram_id = AsyncMock(return_value=[
        {"id": 42, "trafficLimitBytes": 10 * (1024**3), "expireAt": "2026-10-01T00:00:00Z"}
    ])
    remnawave.update_user_subscription = AsyncMock()

    bot = MagicMock()
    bot.send_message = AsyncMock()

    await _maybe_reward_referrer(bot, async_session, remnawave, friend)

    # Inviter's panel user 42 should have received +5GB
    remnawave.update_user_subscription.assert_called_once()
    called_limit = remnawave.update_user_subscription.call_args[0][2]
    assert called_limit == 15 * (1024**3)

    # Inviter was notified
    bot.send_message.assert_called_once()
    assert bot.send_message.call_args[0][0] == 1111

    # Second reward attempt should do nothing
    remnawave.update_user_subscription.reset_mock()
    bot.send_message.reset_mock()
    await _maybe_reward_referrer(bot, async_session, remnawave, friend)
    assert remnawave.update_user_subscription.call_count == 0
    assert bot.send_message.call_count == 0


@pytest.mark.anyio
async def test_retention_check(async_session: AsyncSession):
    from bot.services.retention import _check_retention

    now = datetime.now(timezone.utc)
    expired_7_days = now - timedelta(days=7, hours=2)
    expired_iso = expired_7_days.strftime("%Y-%m-%dT%H:%M:%SZ")

    u_repo = UserRepository(async_session)
    await u_repo.get_or_create(3333, "lost_user")

    remnawave = MagicMock()
    remnawave.get_all_panel_users = AsyncMock(return_value=[
        {"id": 99, "telegramId": 3333, "expireAt": expired_iso, "username": "lost_panel_acc"}
    ])

    bot = MagicMock()
    bot.send_message = AsyncMock()

    await _check_retention(bot, async_session, remnawave)

    # Should have sent message with COMEBACK20 coupon
    assert bot.send_message.call_count == 1
    sent_text = bot.send_message.call_args[0][1]
    assert "COMEBACK20" in sent_text
    assert bot.send_message.call_args[0][0] == 3333

    # Retention state recorded in DB, second call won't notify again
    bot.send_message.reset_mock()
    await _check_retention(bot, async_session, remnawave)
    assert bot.send_message.call_count == 0


def test_auto_backup_schedule():
    from bot.services.backup import _seconds_until_backup

    seconds = _seconds_until_backup(1, 30)
    assert 0 < seconds <= 86400


@pytest.mark.anyio
async def test_renewal_traffic_rollover_vs_reset(async_session: AsyncSession):
    from bot.db.models import Service, Wallet
    from bot.services.purchases import execute_purchase

    # User with 500,000 balance
    w = Wallet(telegram_id=99001, balance=500_000)
    async_session.add(w)

    # 1. NO_RESET service
    svc_no_reset = Service(
        name="Rollover Plan",
        price=100_000,
        duration_days=30,
        traffic_gb=50,
        traffic_strategy="NO_RESET",
        is_active=True,
    )
    async_session.add(svc_no_reset)

    # 2. Reset (MONTH) service
    svc_month = Service(
        name="Monthly Reset Plan",
        price=100_000,
        duration_days=30,
        traffic_gb=50,
        traffic_strategy="MONTH",
        is_active=True,
    )
    async_session.add(svc_month)
    await async_session.flush()

    remnawave = MagicMock()
    remnawave.update_user_subscription = AsyncMock(
        return_value={"id": 12, "username": "acc12", "subscriptionUrl": "https://sub"}
    )
    remnawave.reset_user_traffic = AsyncMock(return_value=True)

    chosen_acc = {
        "id": 12,
        "username": "acc12",
        "trafficLimitBytes": 20 * (1024**3),  # already 20GB limit
        "expireAt": "2026-10-15T00:00:00Z",
    }

    # Test NO_RESET renewal: stacks traffic (20GB + 50GB = 70GB)
    res_rollover = await execute_purchase(
        remnawave, async_session, svc_no_reset, telegram_id=99001, chosen_account=chosen_acc
    )
    assert res_rollover.ok is True
    called_limit = remnawave.update_user_subscription.call_args[0][2]
    assert called_limit == 70 * (1024**3)
    assert remnawave.reset_user_traffic.call_count == 0

    # Test MONTH reset renewal: resets traffic to 50GB and calls reset_user_traffic
    remnawave.update_user_subscription.reset_mock()
    res_reset = await execute_purchase(
        remnawave, async_session, svc_month, telegram_id=99001, chosen_account=chosen_acc
    )
    assert res_reset.ok is True
    called_limit = remnawave.update_user_subscription.call_args[0][2]
    assert called_limit == 50 * (1024**3)
    assert remnawave.reset_user_traffic.call_count == 1


@pytest.mark.anyio
async def test_insufficient_balance_allows_service_view_and_coupon_flow(async_session: AsyncSession):
    from unittest.mock import AsyncMock, MagicMock, patch

    from bot.db.models import Service, Wallet
    from bot.handlers.service_request import _render_buy_confirm, service_view

    w = Wallet(telegram_id=99002, balance=0)
    async_session.add(w)

    svc = Service(name="Expensive Plan", price=100_000, duration_days=30, traffic_gb=50, is_active=True)
    async_session.add(svc)
    await async_session.flush()

    u_repo = UserRepository(async_session)
    user = await u_repo.get_or_create(99002, "poor_user")
    await u_repo.set_language(user, "fa")

    call = MagicMock(spec=CallbackQuery)
    user_mock = MagicMock()
    user_mock.id = 99002
    user_mock.username = "poor_user"
    call.from_user = user_mock
    call.data = f"svc:view:{svc.id}"
    call.answer = AsyncMock()

    bot = MagicMock()

    # 1. service_view allows viewing even with 0 balance
    with patch("bot.handlers.service_request.render_menu", AsyncMock()) as mock_render:
        await service_view(call, bot, u_repo, async_session)
        mock_render.assert_awaited_once()
        text = mock_render.call_args[0][3]
        markup = mock_render.call_args[0][4]
        assert "Expensive Plan" in text
        btn_texts = [b.text for row in markup.inline_keyboard for b in row]
        assert any("خرید" in b for b in btn_texts)

    # 2. _render_buy_confirm with 0 balance shows topup and apply_coupon
    with patch("bot.handlers.service_request.render_menu", AsyncMock()) as mock_render:
        await _render_buy_confirm(
            bot, user, u_repo, async_session, svc, balance=0,
            confirm_callback=f"svc:confirmn:{svc.id}", lang="fa",
        )
        markup = mock_render.call_args[0][4]
        btn_texts = [b.text for row in markup.inline_keyboard for b in row]
        assert any("شارژ" in b for b in btn_texts)
        assert any("کد تخفیف" in b for b in btn_texts)

    # 3. _render_buy_confirm with 100% coupon (discount_amount=100_000) enables confirm_pay even with 0 balance
    with patch("bot.handlers.service_request.render_menu", AsyncMock()) as mock_render:
        await _render_buy_confirm(
            bot, user, u_repo, async_session, svc, balance=0,
            confirm_callback=f"svc:confirmn:{svc.id}", lang="fa",
            coupon_code="FREE100", discount_amount=100_000,
        )
        markup = mock_render.call_args[0][4]
        btn_texts = [b.text for row in markup.inline_keyboard for b in row]
        assert any("پرداخت" in b for b in btn_texts)
        assert not any("شارژ" in b for b in btn_texts)


@pytest.mark.anyio
async def test_trial_referral_boolean_toggle(async_session: AsyncSession):
    from bot.handlers.admin_ops import setting_toggle_boolean
    from bot.services.app_settings import get_store_settings

    # Verify initial settings
    store = await get_store_settings(async_session)
    initial_trial = store.trial_enabled
    initial_ref = store.referral_enabled

    u_repo = UserRepository(async_session)
    bot = MagicMock()
    mock_msg = MagicMock()
    mock_msg.message_id = 123
    bot.send_message = AsyncMock(return_value=mock_msg)
    bot.edit_message_text = AsyncMock()

    # Toggle trial_enabled
    call = MagicMock(spec=CallbackQuery)
    user_mock = MagicMock()
    user_mock.id = 999999999  # admin ID
    user_mock.username = "admin"
    call.from_user = user_mock
    call.data = "adm:settings:toggle:trial_enabled"
    call.answer = AsyncMock()

    from bot.config import get_settings
    get_settings().ADMIN_IDS.append(999999999)

    await setting_toggle_boolean(call, bot, u_repo, async_session)

    store_after = await get_store_settings(async_session)
    assert store_after.trial_enabled == (not initial_trial)

    # Toggle referral_enabled
    call.data = "adm:settings:toggle:referral_enabled"
    await setting_toggle_boolean(call, bot, u_repo, async_session)

    store_after2 = await get_store_settings(async_session)
    assert store_after2.referral_enabled == (not initial_ref)


@pytest.mark.anyio
async def test_admin_services_detail_and_toggle(async_session: AsyncSession):
    from bot.db.models import Service
    from bot.handlers.admin import service_view_detail, toggle_service

    svc = Service(name="Test 100GB", price=150_000, duration_days=30, traffic_gb=100, is_active=True)
    async_session.add(svc)
    await async_session.flush()

    u_repo = UserRepository(async_session)
    bot = MagicMock()
    mock_msg = MagicMock()
    mock_msg.message_id = 124
    bot.send_message = AsyncMock(return_value=mock_msg)
    bot.edit_message_text = AsyncMock()

    call = MagicMock(spec=CallbackQuery)
    user_mock = MagicMock()
    user_mock.id = 999999999
    user_mock.username = "admin"
    call.from_user = user_mock
    call.data = f"adm:svc:view:{svc.id}"
    call.answer = AsyncMock()

    # View detail
    state = MagicMock()
    state.clear = AsyncMock()
    await service_view_detail(call, bot, u_repo, async_session, state)
    assert call.answer.call_count == 1

    # Toggle service active state
    call.data = f"adm:svc:toggle:{svc.id}"
    await toggle_service(call, bot, u_repo, async_session)
    await async_session.refresh(svc)
    assert svc.is_active is False


def test_node_flag_formatting_and_core_version():
    from bot.handlers.admin_ops import _extract_core_version, _format_node_title

    # 1. Country name replacement with flag
    node_nl = {"name": "Netherland 1", "countryCode": "NL"}
    assert _format_node_title(node_nl, 1) == "🇳🇱 1"

    node_de = {"name": "Germany", "countryCode": "DE"}
    assert _format_node_title(node_de, 2) == "🇩🇪"

    node_fr = {"name": "FR - Paris 01", "countryCode": "FR"}
    assert _format_node_title(node_fr, 3) == "🇫🇷 Paris 01"

    # Flag inference when countryCode is missing
    node_infer = {"name": "Netherland 2"}
    assert _format_node_title(node_infer, 4) == "🇳🇱 2"

    # Flag preservation when already in name
    node_has_flag = {"name": "🇳🇱 Netherland 3"}
    assert _format_node_title(node_has_flag, 5) == "🇳🇱 3"

    # 2. Core version extraction across schemas
    # Schema A: versions dict with xray and node
    n_a = {"versions": {"xray": "1.8.24", "node": "2.8.1"}}
    assert _extract_core_version(n_a) == "Xray 1.8.24 | Node 2.8.1"

    # Schema B: top-level xrayVersion
    n_b = {"xrayVersion": "1.8.24"}
    assert _extract_core_version(n_b) == "Xray 1.8.24"

    # Schema C: system.versions
    n_c = {"system": {"versions": {"xray": "1.8.20", "node": "2.7.0"}}}
    assert _extract_core_version(n_c) == "Xray 1.8.20 | Node 2.7.0"

    # Schema D: singbox
    n_d = {"singboxVersion": "1.10.0"}
    assert _extract_core_version(n_d) == "Sing-Box 1.10.0"

    # Schema E: None/empty
    assert _extract_core_version({}) is None


@pytest.mark.anyio
async def test_admin_services_rtl_2col(async_session: AsyncSession):
    from bot.db.models import Service
    from bot.handlers.admin import _render_admin_services

    s1 = Service(name="Plan A", price=100_000, duration_days=30, traffic_gb=50, is_active=True)
    s2 = Service(name="Plan B", price=200_000, duration_days=30, traffic_gb=100, is_active=False)
    async_session.add_all([s1, s2])
    await async_session.flush()

    u_repo = UserRepository(async_session)
    user = await u_repo.get_or_create(999999999, "admin")
    user.language = "fa"

    bot = MagicMock()
    mock_msg = MagicMock()
    mock_msg.message_id = 999
    bot.send_message = AsyncMock(return_value=mock_msg)
    bot.edit_message_text = AsyncMock()

    await _render_admin_services(bot, user, u_repo, async_session)

    # Verify menu rendered
    assert bot.send_message.call_count == 1
    call_args = bot.send_message.call_args[1]
    reply_markup = call_args["reply_markup"]

    # In Persian RTL: Row 1 should have Plan B on LEFT (idx 0) and Plan A on RIGHT (idx 1)
    row0 = reply_markup.inline_keyboard[0]
    assert len(row0) == 2
    assert "Plan B" in row0[0].text
    assert "Plan A" in row0[1].text


@pytest.mark.anyio
async def test_services_policy_hint_rendered(async_session: AsyncSession):
    from bot.db.models import Service
    from bot.handlers.service_request import _render_services

    s1 = Service(
        name="Rollover Plan",
        price=50_000,
        duration_days=30,
        traffic_gb=30,
        traffic_strategy="NO_RESET",
        is_active=True,
    )
    async_session.add(s1)
    await async_session.flush()

    u_repo = UserRepository(async_session)
    user = await u_repo.get_or_create(1234567, "buyer")
    user.language = "fa"

    bot = MagicMock()
    mock_msg = MagicMock()
    mock_msg.message_id = 1001
    bot.send_message = AsyncMock(return_value=mock_msg)

    await _render_services(bot, user, u_repo, async_session)

    assert bot.send_message.call_count == 1
    text = bot.send_message.call_args[1]["text"]
    assert "بدون ریست" in text
    assert "۱ روز" in text


@pytest.mark.anyio
async def test_admin_user_detail_back_to_search(async_session: AsyncSession):
    from bot.handlers.admin_users import _render_panel_user_detail

    u_repo = UserRepository(async_session)
    admin = await u_repo.get_or_create(999000111, "admin")
    admin.language = "fa"

    remnawave = MagicMock()
    remnawave.get_panel_user_by_id = AsyncMock(return_value={
        "id": 55,
        "username": "Mohammad",
        "status": "ACTIVE",
        "usedTraffic": 0,
        "trafficLimit": 10737418240,
        "trafficLimitStrategy": "NO_RESET",
        "expireAt": "2026-10-01T00:00:00Z",
    })
    remnawave.get_user_hwid_devices = AsyncMock(return_value=[])
    remnawave.get_internal_squads = AsyncMock(return_value=[])

    bot = MagicMock()
    mock_msg = MagicMock()
    mock_msg.message_id = 1002
    bot.send_message = AsyncMock(return_value=mock_msg)

    # Render with category="search"
    await _render_panel_user_detail(
        bot, admin, u_repo, remnawave,
        panel_user_id=55, category="search", page=0,
    )

    assert bot.send_message.call_count == 1
    reply_markup = bot.send_message.call_args[1]["reply_markup"]

    # Verify back button points to adm:user:search
    back_button = reply_markup.inline_keyboard[-1][0]
    assert back_button.callback_data == "adm:user:search"


@pytest.mark.anyio
async def test_decide_topup_notification_keyboards(async_session: AsyncSession):
    from bot.db.repositories.wallet_repo import WalletRepository
    from bot.services.topups import decide_topup

    u_repo = UserRepository(async_session)
    user = await u_repo.get_or_create(777001, "customer")
    user.language = "fa"

    w_repo = WalletRepository(async_session)
    # 1. Test Approval
    topup_ok = await w_repo.create_topup(777001, 500_000, "hash_ok_1")

    bot = MagicMock()
    bot.send_message = AsyncMock()

    changed, note = await decide_topup(bot, async_session, topup_ok.id, approved=True, admin_id=123)
    assert changed is True
    assert bot.send_message.call_count == 1

    call_kwargs = bot.send_message.call_args[1]
    reply_markup = call_kwargs["reply_markup"]
    btn_callbacks = [b.callback_data for row in reply_markup.inline_keyboard for b in row]
    assert "menu:wallet" in btn_callbacks
    assert "menu:services" in btn_callbacks

    # 2. Test Rejection
    topup_no = await w_repo.create_topup(777001, 300_000, "hash_no_1")
    bot.send_message.reset_mock()

    changed, note = await decide_topup(bot, async_session, topup_no.id, approved=False, admin_id=123)
    assert changed is True
    assert bot.send_message.call_count == 1

    call_kwargs = bot.send_message.call_args[1]
    reply_markup = call_kwargs["reply_markup"]
    btn_callbacks = [b.callback_data for row in reply_markup.inline_keyboard for b in row]
    assert "menu:support" in btn_callbacks


@pytest.mark.anyio
async def test_admin_nightly_summary(async_session: AsyncSession):
    from bot.services.reports import _send_admin_nightly_summary

    bot = MagicMock()
    bot.send_message = AsyncMock()

    remnawave = MagicMock()
    now = datetime.now(timezone.utc)
    in_2_days = (now + timedelta(days=2)).isoformat()
    yesterday = (now - timedelta(hours=12)).isoformat()

    remnawave.get_all_panel_users = AsyncMock(return_value=[
        {"id": 1, "username": "active_user", "status": "ACTIVE", "expireAt": in_2_days, "usedTrafficBytes": 1000},
        {"id": 2, "username": "expired_user", "status": "DISABLED", "expireAt": yesterday, "usedTrafficBytes": 0},
    ])
    remnawave.get_nodes = AsyncMock(return_value=[
        {"name": "Node DE", "countryCode": "DE", "isConnected": True, "todayTrafficBytes": 1024**3}
    ])
    remnawave.get_user_bandwidth_stats = AsyncMock(return_value=[
        {"name": "Node DE", "countryCode": "DE", "total": 1024**3, "data": [1024**3]}
    ])

    await _send_admin_nightly_summary(bot, async_session, remnawave, now)

    assert bot.send_message.call_count >= 1
    text = (
        bot.send_message.call_args[0][1]
        if bot.send_message.call_args[0] and len(bot.send_message.call_args[0]) > 1
        else bot.send_message.call_args[1].get("text", "")
    )
    assert "گزارش جامع" in text
    assert "خلاصه وضعیت کل پنل" in text
    assert "کاربران فعال امروز و مصرفشان" in text
    assert "کاربرانی که تا ۳ روز آینده منقضی می شوند" in text
    assert "کاربران منقضی (24 ساعت اخیر)" in text
    assert "هشدارهای ارسال شده امروز" in text
    assert "active_user" in text
    assert "expired_user" in text
    assert "🇩🇪" in text


@pytest.mark.anyio
async def test_admin_weekly_summary(async_session: AsyncSession):
    from bot.services.reports import _send_admin_weekly_summary

    bot = MagicMock()
    bot.send_message = AsyncMock()

    remnawave = MagicMock()
    remnawave.get_all_panel_users = AsyncMock(return_value=[
        {"id": 10, "username": "Farinaz", "usedTrafficBytes": 5000},
        {"id": 20, "username": "Benjamin", "usedTrafficBytes": 3000},
    ])
    # 7 days of traffic
    remnawave.get_user_bandwidth_stats = AsyncMock(side_effect=[
        [{"name": "DE", "countryCode": "DE", "total": 14 * 1024**3, "data": [14 * 1024**3, 0, 0, 0, 0, 0, 0]}],
        [{"name": "DE", "countryCode": "DE", "total": 10 * 1024**3, "data": [0, 0, 0, 0, 0, 0, 10 * 1024**3]}],
    ])

    now = datetime(2026, 3, 13, 23, 59, tzinfo=timezone.utc)  # Friday
    await _send_admin_weekly_summary(bot, async_session, remnawave, now)

    assert bot.send_message.call_count >= 1
    text = (
        bot.send_message.call_args[0][1]
        if bot.send_message.call_args[0] and len(bot.send_message.call_args[0]) > 1
        else bot.send_message.call_args[1].get("text", "")
    )
    assert "گزارش هفتگی پرمصرفترین کاربران" in text
    assert "۲۰ کاربر برتر این هفته:" in text
    assert "قهرمان هر روز هفته:" in text
    assert "Farinaz" in text
    assert "Benjamin" in text
    assert "جمعه" in text


def test_chunk_text():
    from bot.services.reports import SEPARATOR, _chunk_text

    short_text = "Hello world"
    assert _chunk_text(short_text, max_chars=100) == [short_text]

    long_block_1 = "A" * 50
    long_block_2 = "B" * 50
    joined = f"{long_block_1}\n{SEPARATOR}\n{long_block_2}"
    chunks = _chunk_text(joined, max_chars=80)
    assert len(chunks) == 2
    assert "A" in chunks[0]
    assert "B" in chunks[1]


@pytest.mark.anyio
async def test_backup_and_restore_json(async_session: AsyncSession, tmp_path):
    from bot.db.models import AppSetting, User, Wallet
    from bot.services.backup import create_database_backup, restore_database_backup

    # Insert test user and wallet
    user = User(telegram_id=987654321, username="backup_user")
    wallet = Wallet(telegram_id=987654321, balance=50000)
    setting = AppSetting(key="test_backup_key", value="test_backup_val")
    async_session.add_all([user, wallet, setting])
    await async_session.commit()

    # Create backup
    backup_file = await create_database_backup(async_session, out_dir=tmp_path)
    assert backup_file.is_file()

    # Clear user username and wallet balance to test restore
    wallet.balance = 0
    await async_session.commit()

    # Restore backup
    stats = await restore_database_backup(async_session, backup_file)
    assert stats["users"] >= 1
    assert stats["wallets"] >= 1

    # Verify restored balance
    restored_wallet = await async_session.get(Wallet, 987654321)
    assert restored_wallet.balance == 50000


@pytest.mark.anyio
async def test_nightly_reports_formatting(async_session: AsyncSession):
    """Verify nightly account report has no leading spaces and admin summary is sorted with separate lines."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from bot.services.reports import (
        _breakdown_lines,
        _nightly_account_block,
        _send_admin_nightly_summary,
    )

    # 1. Test _breakdown_lines has no leading 6 spaces
    sample_rows = [
        {"name": "Netherlands", "countryCode": "NL", "total": 18 * 1024**3},
        {"name": "Germany 2", "countryCode": "DE", "total": 27 * 1024**3},
    ]
    bd_lines = _breakdown_lines(sample_rows)
    for line in bd_lines:
        assert not line.startswith(" ")
        assert "🇳🇱" in line or "🇩🇪" in line

    # 2. Test _nightly_account_block
    now = datetime(2026, 9, 27, 23, 59, tzinfo=timezone.utc)
    mock_remnawave = MagicMock()
    mock_remnawave.get_user_bandwidth_stats = AsyncMock(return_value=[
        {"name": "Germany 2", "countryCode": "DE", "total": 27 * 1024**3, "data": [4 * 1024**3]}
    ])
    account = {
        "id": 101,
        "username": "Outbound",
        "trafficLimitBytes": 75 * 1024**3,
        "usedTrafficBytes": 27 * 1024**3,
        "expireAt": (now + timedelta(days=20)).isoformat(),
    }
    block = await _nightly_account_block(mock_remnawave, account, now, "fa")
    # Verify no line has leading spaces before country flags
    for line in block.split("\n"):
        if "🇩🇪 Germany 2" in line:
            assert not line.startswith(" ")
            assert line.startswith("🇩🇪 Germany 2")

    # 3. Test _send_admin_nightly_summary with multiple users sorted high to low
    bot = MagicMock()
    bot.send_message = AsyncMock()

    remnawave = MagicMock()
    remnawave.get_all_panel_users = AsyncMock(return_value=[
        {"id": 1, "username": "Mohadeseh3", "status": "ACTIVE", "usedTrafficBytes": 5000},
        {"id": 2, "username": "Sahba", "status": "ACTIVE", "usedTrafficBytes": 3000},
        {"id": 3, "username": "TopUser", "status": "ACTIVE", "usedTrafficBytes": 10000},
    ])
    remnawave.get_nodes = AsyncMock(return_value=[])

    async def mock_bandwidth_stats(uid, s_str, t_str):
        if uid == 1:
            return [{"countryCode": "NL", "data": [380 * 1024**2]}]
        elif uid == 2:
            return [{"countryCode": "NL", "data": [168 * 1024**2]}]
        elif uid == 3:
            return [{"countryCode": "DE", "data": [2 * 1024**3]}]
        return []

    remnawave.get_user_bandwidth_stats = AsyncMock(side_effect=mock_bandwidth_stats)

    with patch("bot.services.reports.get_store_settings") as mock_store:
        mock_store.return_value = MagicMock(topic_alerts=None)
        await _send_admin_nightly_summary(bot, async_session, remnawave, now)
    admin_text = bot.send_message.call_args[0][1]

    # Verify order: TopUser (2.00 GB) > Mohadeseh3 (380.00 MB) > Sahba (168.00 MB)
    pos_top = admin_text.find("👤 TopUser : \u200e2.00 GB")
    pos_moh = admin_text.find("👤 Mohadeseh3 : \u200e380.00 MB")
    pos_sah = admin_text.find("👤 Sahba : \u200e168.00 MB")

    assert pos_top != -1
    assert pos_moh != -1
    assert pos_sah != -1
    assert pos_top < pos_moh < pos_sah

    # Verify layout: username on top, breakdown on next line without leading space
    assert "👤 Mohadeseh3 : \u200e380.00 MB\n🇳🇱 \u200e380.00 MB" in admin_text
    assert "👤 Sahba : \u200e168.00 MB\n🇳🇱 \u200e168.00 MB" in admin_text
    # Verify blank line between users
    assert "👤 Mohadeseh3 : \u200e380.00 MB\n🇳🇱 \u200e380.00 MB\n\n👤 Sahba : \u200e168.00 MB" in admin_text


@pytest.mark.anyio
async def test_admin_monthly_summary(async_session: AsyncSession):
    from unittest.mock import patch
    from bot.services.reports import _send_admin_monthly_summary

    bot = MagicMock()
    bot.send_message = AsyncMock()

    remnawave = MagicMock()
    remnawave.get_all_panel_users = AsyncMock(return_value=[
        {"id": 10, "username": "Farinaz", "usedTrafficBytes": 5000},
        {"id": 20, "username": "Benjamin", "usedTrafficBytes": 3000},
    ])
    remnawave.get_user_bandwidth_stats = AsyncMock(return_value=[
        {"name": "DE", "countryCode": "DE", "total": 50 * 1024**3, "data": [10 * 1024**3] * 30}
    ])

    now = datetime(2026, 3, 20, 23, 59, tzinfo=timezone.utc)
    with patch("bot.services.reports.get_store_settings") as mock_store:
        mock_store.return_value = MagicMock(topic_alerts=None)
        await _send_admin_monthly_summary(bot, async_session, remnawave, now)

    assert bot.send_message.call_count >= 1
    text = bot.send_message.call_args[0][1]
    assert "گزارش جامع ماهانه پنل" in text
    assert "خلاصه وضعیت ماه" in text
    assert "مجموع مصرف کل ماه" in text


@pytest.mark.anyio
async def test_user_weekly_report_formatting_and_alignment():
    from bot.db.models import User
    from bot.services.reports.weekly import _weekly_text_for_user

    user = User(telegram_id=999888, username="ali", language="fa")
    remnawave = MagicMock()
    remnawave.get_users_by_telegram_id = AsyncMock(return_value=[
        {"id": 101, "username": "ali"}
    ])

    # 7 days: offsets 0..4 = 0, offset 5 (Thursday) = 6.35 GB, offset 6 (Friday) = 4 GB
    gb = 1024**3
    mb = 1024**2
    thursday_bytes = int(4.35 * gb)
    remnawave.get_user_bandwidth_stats = AsyncMock(side_effect=[
        # current week
        [
            {"name": "NL-Server", "countryCode": "NL", "total": 6 * gb, "data": [0, 0, 0, 0, 0, 2 * gb, 4 * gb]},
            {"name": "DE-Server-1", "countryCode": "DE", "total": 5 * gb, "data": [0, 0, 0, 0, 0, thursday_bytes, 0]},
        ],
        # previous week
        [],
    ])

    now = datetime(2026, 10, 2, 23, 59, tzinfo=timezone.utc)  # Friday (جمعه)
    text = await _weekly_text_for_user(user, remnawave, now)

    assert text is not None
    assert "گزارش هفتگی" in text
    # Check date and weekday formatting
    assert "📅 جمعه" in text
    assert "📅 پنج‌شنبه" in text
    # Check that countries show flags without country names
    assert "🇳🇱" in text
    assert "🇩🇪" in text
    assert "NL-Server" not in text
    assert "DE-Server" not in text
    assert "سایر" not in text
    # Thursday was peak with ~6.35 GB (2GB + 4.35GB)
    assert "پنج‌شنبه" in text
    assert "پرمصرف‌ترین روزت <b>پنج‌شنبه</b> بود" in text

