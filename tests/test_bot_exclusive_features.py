"""Unit and integration tests for Bot Exclusive Features:
1. Lucky Wheel (گردونه شانس)
2. Birthday Registration & VIP Gift (ثبت تاریخ تولد)
3. Connected HWID Devices Management (دستگاه‌های متصل)
4. Gift Cards (ارسال هدیه به دوستان)
5. Custom Plan Builder (بسته‌ساز دلخواه)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from aiogram.types import CallbackQuery, Message, User as TgUser

from bot.db.models import User, Wallet, Service
from bot.db.repositories.user_repo import UserRepository
from bot.services.birthday import days_until_jalali_birthday, parse_and_validate_jalali_birthdate
from bot.services.wheel_service import (
    execute_lucky_wheel_spin,
    get_wheel_status,
)
from bot.services.gift_service import create_gift, get_user_gifts
from bot.web.cache import FastCache
from bot.web.user_shop import compute_custom_plan_price
from types import SimpleNamespace


# -------------------------------------------------------------------------
# 1. Lucky Wheel Tests
# -------------------------------------------------------------------------
@pytest.mark.anyio
async def test_wheel_sub_required_and_cooldown(session_factory):
    async with session_factory() as session:
        tg_id = 9001
        u = User(telegram_id=tg_id, username="wheel_tester")
        session.add(u)
        await session.commit()

        cache = FastCache(redis_client=None)
        mock_remnawave = AsyncMock()

        # No active subscription -> rejected
        mock_remnawave.get_users_by_telegram_id.return_value = [{"status": "DISABLED", "id": 10}]
        res = await execute_lucky_wheel_spin(
            session=session,
            remnawave=mock_remnawave,
            cache=cache,
            bot=None,
            telegram_id=tg_id,
        )
        assert not res["ok"]
        assert res["code"] == "sub_required"

        # With active subscription -> can spin
        mock_remnawave.get_users_by_telegram_id.return_value = [
            {"status": "ACTIVE", "id": 10, "trafficLimitBytes": 10 * 1024**3, "expireAt": "2026-12-01T00:00:00Z"}
        ]
        mock_remnawave.update_user_subscription.return_value = {"id": 10}

        with patch("random.choices", return_value=[{"id": "1gb", "name": "1 GB", "icon": "🎁", "type": "traffic", "value": 1}]):
            res_spin1 = await execute_lucky_wheel_spin(
                session=session,
                remnawave=mock_remnawave,
                cache=cache,
                bot=None,
                telegram_id=tg_id,
            )
            assert res_spin1["ok"] is True
            assert res_spin1["streak"] == 1
            assert res_spin1["applied"] is True

        # Second spin within 24h -> cooldown
        res_spin2 = await execute_lucky_wheel_spin(
            session=session,
            remnawave=mock_remnawave,
            cache=cache,
            bot=None,
            telegram_id=tg_id,
        )
        assert not res_spin2["ok"]
        assert res_spin2["code"] == "cooldown"

        # Now give user a spin ticket -> bypasses cooldown
        u.spin_tickets = 1
        await session.commit()

        with patch("random.choices", return_value=[{"id": "blank_1", "name": "پوچ", "icon": "❌", "type": "blank", "value": 0}]):
            res_ticket = await execute_lucky_wheel_spin(
                session=session,
                remnawave=mock_remnawave,
                cache=cache,
                bot=None,
                telegram_id=tg_id,
                use_ticket=True,
            )
            assert res_ticket["ok"] is True
            assert res_ticket["used_ticket"] is True
            assert res_ticket["spin_tickets"] == 0


@pytest.mark.anyio
async def test_wheel_coupon_reward_generation(session_factory):
    async with session_factory() as session:
        tg_id = 9002
        u = User(telegram_id=tg_id, username="coupon_winner")
        session.add(u)
        await session.commit()

        cache = FastCache(redis_client=None)
        mock_remnawave = AsyncMock()
        mock_remnawave.get_users_by_telegram_id.return_value = [
            {"status": "ACTIVE", "id": 11, "trafficLimitBytes": 10 * 1024**3}
        ]

        with patch("random.choices", return_value=[{"id": "discount10", "name": "10% OFF", "icon": "🎟", "type": "coupon", "code": "OFF10"}]):
            res = await execute_lucky_wheel_spin(
                session=session,
                remnawave=mock_remnawave,
                cache=cache,
                bot=None,
                telegram_id=tg_id,
            )
            assert res["ok"] is True
            prize = res["prize"]
            assert prize["type"] == "coupon"
            assert "WHEEL10_" in prize["code"]
            assert res["applied"] is True


# -------------------------------------------------------------------------
# 2. Birthday Registration Tests
# -------------------------------------------------------------------------
def test_parse_and_validate_jalali_birthdate():
    # Standard YYYY/MM/DD
    ok, formatted, err = parse_and_validate_jalali_birthdate("1378/04/15")
    assert ok is True
    assert formatted == "1378/04/15"
    assert err is None

    # Delimiters -, ., space
    ok, formatted, err = parse_and_validate_jalali_birthdate("1380-05-20")
    assert ok is True
    assert formatted == "1380/05/20"

    # Persian digits
    ok, formatted, err = parse_and_validate_jalali_birthdate("۱۳۷۵/۰۷/۲۲")
    assert ok is True
    assert formatted == "1375/07/22"

    # MM/DD format
    ok, formatted, err = parse_and_validate_jalali_birthdate("06/10")
    assert ok is True
    assert formatted == "1380/06/10"

    # Invalid month
    ok, _, err = parse_and_validate_jalali_birthdate("1378/13/10")
    assert ok is False
    assert "ماه تولد" in err

    # Invalid day
    ok, _, err = parse_and_validate_jalali_birthdate("1378/08/31")
    assert ok is False
    assert "روز تولد" in err


def test_days_until_jalali_birthday():
    import jdatetime
    from zoneinfo import ZoneInfo
    now_tehran = datetime.now(ZoneInfo("Asia/Tehran"))
    today_j = jdatetime.date.fromgregorian(date=now_tehran.date())

    # Today is birthday -> 0 days
    today_bday_str = f"1380/{today_j.month:02d}/{today_j.day:02d}"
    assert days_until_jalali_birthday(today_bday_str) == 0

    # None or empty
    assert days_until_jalali_birthday(None) is None
    assert days_until_jalali_birthday("") is None


# -------------------------------------------------------------------------
# 3. Gift Cards Tests
# -------------------------------------------------------------------------
@pytest.mark.anyio
async def test_gift_cards_balance_and_service(session_factory):
    async with session_factory() as session:
        sender_id = 9010
        receiver_id = 9011

        u_sender = User(telegram_id=sender_id, username="sender_vip", full_name="Sender")
        w_sender = Wallet(telegram_id=sender_id, balance=300_000)
        u_recv = User(telegram_id=receiver_id, username="friend_tg", full_name="Friend")
        w_recv = Wallet(telegram_id=receiver_id, balance=0)
        session.add_all([u_sender, w_sender, u_recv, w_recv])
        await session.commit()

        # 1. Send balance gift of 100,000 to @friend_tg
        res = await create_gift(
            session=session,
            sender_telegram_id=sender_id,
            delivery_type="DIRECT",
            gift_type="BALANCE",
            amount=100_000,
            receiver_target="@friend_tg",
            bot_username="testvpn_bot",
        )
        assert res["ok"] is True
        assert res["code"].startswith("GIFT-")
        assert "start=gift_" in res["share_url"]

        # Sender balance deducted
        await session.refresh(w_sender)
        assert w_sender.balance == 200_000

        # 2. View sent gifts
        gifts_data = await get_user_gifts(session, sender_id, bot_username="testvpn_bot")
        gifts = gifts_data.get("sent", [])
        assert len(gifts) == 1
        assert gifts[0]["code"] == res["code"]
        assert gifts[0]["is_claimed"] is False


# -------------------------------------------------------------------------
# 4. Custom Plan Builder Tests
# -------------------------------------------------------------------------
def test_custom_plan_volume_tiered_pricing():
    store = SimpleNamespace(
        custom_plan_price_per_gb=4_000,
        custom_plan_price_per_day=500,
        custom_plan_base_price=10_000,
        custom_plan_volume_tiers_json="",
    )

    # 1. 30 GB (tier 1: 0% discount)
    raw, vol_pct, disc = compute_custom_plan_price(30, 30, store)
    # raw = 30*4000 (120,000) + 30*500 (15,000) + 10,000 = 145,000
    assert vol_pct == 0
    assert raw == 145_000
    assert disc == 145_000

    # 2. 80 GB (tier 2: 10% volume discount on traffic)
    # traffic_raw = 80*4000 = 320,000 -> 10% off = 288,000
    # time+base = 30*500 + 10,000 = 25,000
    # total = 313,000
    raw80, vol_pct80, disc80 = compute_custom_plan_price(80, 30, store)
    assert vol_pct80 == 10
    assert raw80 == 320_000 + 25_000
    assert disc80 == 288_000 + 25_000

    # 3. 150 GB (tier 3: 20% volume discount)
    raw150, vol_pct150, disc150 = compute_custom_plan_price(150, 30, store)
    assert vol_pct150 == 20

    # 4. 250 GB (tier 4: 30% volume discount)
    raw250, vol_pct250, disc250 = compute_custom_plan_price(250, 30, store)
    assert vol_pct250 == 30


# -------------------------------------------------------------------------
# 5. Connected Devices & Bot Menu Handlers
# -------------------------------------------------------------------------
@pytest.mark.anyio
async def test_bot_menu_devices_entry(session_factory):
    from bot.handlers.account import menu_devices_entry

    async with session_factory() as session:
        u_repo = UserRepository(session)
        user = await u_repo.get_or_create(9020, "device_tester")
        await u_repo.set_language(user, "fa")

        call = MagicMock(spec=CallbackQuery)
        call.from_user = TgUser(id=9020, is_bot=False, first_name="DevTester", username="device_tester")
        call.data = "menu:devices"
        call.answer = AsyncMock()

        bot = MagicMock()
        mock_remnawave = AsyncMock()

        # Case A: No accounts
        mock_remnawave.get_users_by_telegram_id.return_value = []
        with patch("bot.handlers.account.render_menu", AsyncMock()) as mock_render:
            await menu_devices_entry(call, bot, u_repo, mock_remnawave)
            mock_render.assert_awaited_once()
            assert "شما در حال حاضر سرویس فعالی ندارید" in mock_render.call_args[0][3]

        # Case B: 1 account with devices
        mock_remnawave.get_users_by_telegram_id.return_value = [
            {"id": 1001, "username": "acc_single", "status": "ACTIVE"}
        ]
        mock_remnawave.get_user_hwid_devices.return_value = [
            {"platform": "iOS", "deviceModel": "iPhone 15 Pro", "requestIp": "1.2.3.4"}
        ]
        with patch("bot.handlers.account.render_menu", AsyncMock()) as mock_render:
            await menu_devices_entry(call, bot, u_repo, mock_remnawave)
            mock_render.assert_awaited_once()
            text = mock_render.call_args[0][3]
            assert "دستگاه‌های متصل" in text or "iPhone" in text


# -------------------------------------------------------------------------
# 6. Handlers Integration (Wheel Hub, Birthday Input, Custom Plan Flow)
# -------------------------------------------------------------------------
@pytest.mark.anyio
async def test_bot_wheel_handlers(session_factory):
    from bot.handlers.wheel import wheel_hub, wheel_prizes_list, wheel_my_coupons

    async with session_factory() as session:
        u_repo = UserRepository(session)
        user = await u_repo.get_or_create(9030, "wheel_bot_tester")
        await u_repo.set_language(user, "fa")

        call = MagicMock(spec=CallbackQuery)
        call.from_user = TgUser(id=9030, is_bot=False, first_name="WheelTester", username="wheel_bot_tester")
        call.answer = AsyncMock()
        bot = MagicMock()
        cache = FastCache(redis_client=None)

        # 1. View Hub
        with patch("bot.handlers.wheel.render_menu", AsyncMock()) as mock_render:
            await wheel_hub(call, bot, u_repo, session, cache)
            mock_render.assert_awaited_once()
            assert "گردونه شانس" in mock_render.call_args[0][3]

        # 2. View Prizes List
        with patch("bot.handlers.wheel.render_menu", AsyncMock()) as mock_render:
            await wheel_prizes_list(call, bot, u_repo)
            mock_render.assert_awaited_once()
            assert "فهرست جوایز" in mock_render.call_args[0][3]

        # 3. View My Coupons
        with patch("bot.handlers.wheel.render_menu", AsyncMock()) as mock_render:
            await wheel_my_coupons(call, bot, u_repo, session, cache)
            mock_render.assert_awaited_once()
            assert "کدهای تخفیف" in mock_render.call_args[0][3]


@pytest.mark.anyio
async def test_bot_birthday_registration_flow(session_factory):
    from bot.handlers.profile import start_set_birthday, process_birthday_input
    from aiogram.fsm.context import FSMContext

    async with session_factory() as session:
        u_repo = UserRepository(session)
        user = await u_repo.get_or_create(9040, "birthday_user")
        await u_repo.set_language(user, "fa")

        call = MagicMock(spec=CallbackQuery)
        call.from_user = TgUser(id=9040, is_bot=False, first_name="BdayUser", username="birthday_user")
        call.answer = AsyncMock()

        bot = MagicMock()
        mock_state = AsyncMock(spec=FSMContext)

        # 1. Start birthday prompt
        with patch("bot.handlers.profile.render_menu", AsyncMock()) as mock_render:
            await start_set_birthday(call, bot, u_repo, mock_state)
            mock_render.assert_awaited_once()
            assert "ثبت تاریخ تولد" in mock_render.call_args[0][3]
            mock_state.set_state.assert_awaited_once()

        # 2. Invalid birthday input
        msg_invalid = MagicMock(spec=Message)
        msg_invalid.from_user = call.from_user
        msg_invalid.text = "1378/14/40"
        msg_invalid.reply = AsyncMock()

        await process_birthday_input(msg_invalid, bot, u_repo, session, mock_state)
        msg_invalid.reply.assert_awaited_once()
        assert "❌" in msg_invalid.reply.call_args[0][0]

        # 3. Valid birthday input
        msg_valid = MagicMock(spec=Message)
        msg_valid.from_user = call.from_user
        msg_valid.text = "1378/04/15"
        msg_valid.reply = AsyncMock()

        await process_birthday_input(msg_valid, bot, u_repo, session, mock_state)
        msg_valid.reply.assert_awaited_once()
        assert "با موفقیت ثبت شد" in msg_valid.reply.call_args[0][0]

        # Verify DB updated
        await session.refresh(user)
        assert user.birth_date == "1378/04/15"


@pytest.mark.anyio
async def test_bot_custom_plan_purchase_flow(session_factory):
    from bot.handlers.custom_plan import custom_plan_entry, custom_plan_execute_purchase
    from bot.db.models import AppSetting

    async with session_factory() as session:
        u_repo = UserRepository(session)
        user = await u_repo.get_or_create(9050, "custom_builder_user")
        await u_repo.set_language(user, "fa")
        wallet = Wallet(telegram_id=9050, balance=500_000)
        session.add(wallet)
        await session.commit()

        # Enable custom plan in store settings
        session.add_all([
            AppSetting(key="custom_plan_enabled", value="true"),
            AppSetting(key="custom_plan_price_per_gb", value="2000"),
            AppSetting(key="custom_plan_price_per_day", value="100"),
            AppSetting(key="custom_plan_base_price", value="5000"),
        ])
        await session.commit()

        call = MagicMock(spec=CallbackQuery)
        call.from_user = TgUser(id=9050, is_bot=False, first_name="Builder", username="custom_builder_user")
        call.data = "menu:custom_plan"
        call.answer = AsyncMock()
        bot = MagicMock()

        # 1. Entry point
        with patch("bot.handlers.custom_plan.render_menu", AsyncMock()) as mock_render:
            await custom_plan_entry(call, bot, u_repo, session)
            mock_render.assert_awaited_once()
            assert "طراحی بسته دلخواه" in mock_render.call_args[0][3]

        # 2. Purchase execution
        call.data = "cplan:buy:50:30"
        mock_remnawave = AsyncMock()
        mock_remnawave.create_user.return_value = {
            "id": 8888,
            "username": "custom_user_8888",
            "subscriptionUrl": "https://sub.domain.com/sub/custom8888",
        }

        with patch("bot.handlers.custom_plan.render_menu", AsyncMock()) as mock_render:
            await custom_plan_execute_purchase(call, bot, u_repo, session, mock_remnawave)
            mock_render.assert_awaited_once()
            text = mock_render.call_args[0][3]
            assert "با موفقیت فعال گردید" in text
            assert "https://sub.domain.com/sub/custom8888" in text
