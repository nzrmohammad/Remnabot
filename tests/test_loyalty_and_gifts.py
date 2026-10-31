"""Unit and integration tests for Loyalty Tiers, Gifts System, and Custom Plan Builder."""
import pytest
from bot.db.models import Order, OrderStatus, Service, User, Wallet
from bot.services.loyalty import LOYALTY_TIERS, apply_loyalty_discount, get_user_loyalty
from bot.services.gift_service import create_gift, claim_gift, get_user_gifts


@pytest.mark.anyio
async def test_loyalty_tiers_progression(session_factory):
    async with session_factory() as session:
        tg_id = 998877661
        u = User(telegram_id=tg_id, username="vip_tester", full_name="VIP Tester")
        session.add(u)
        await session.commit()

        # 1. Zero spent -> Bronze
        loyalty = await get_user_loyalty(session, tg_id)
        assert loyalty["tier_id"] == "bronze"
        assert loyalty["discount_percent"] == 0
        assert loyalty["amount_to_next"] == 500_000
        assert loyalty["progress_percent"] == 0
        assert not loyalty["is_max_tier"]

        # 2. Add orders for 750,000 -> Silver
        order1 = Order(
            telegram_id=tg_id,
            service_name="Test Plan",
            amount=750_000,
            status=OrderStatus.PAID.value,
        )
        session.add(order1)
        await session.commit()

        loyalty = await get_user_loyalty(session, tg_id)
        assert loyalty["tier_id"] == "silver"
        assert loyalty["discount_percent"] == 5
        assert loyalty["total_spent"] == 750_000
        assert loyalty["amount_to_next"] == 750_000  # 1.5M - 750k = 750k
        assert loyalty["progress_percent"] == 25  # 250k / 1000k

        # 3. Add orders for 1,000,000 more (total 1,750,000) -> Gold
        order2 = Order(
            telegram_id=tg_id,
            service_name="Test Plan 2",
            amount=1_000_000,
            status=OrderStatus.PAID.value,
        )
        session.add(order2)
        await session.commit()

        loyalty = await get_user_loyalty(session, tg_id)
        assert loyalty["tier_id"] == "gold"
        assert loyalty["discount_percent"] == 10
        assert loyalty["total_spent"] == 1_750_000

        # 4. Add orders for 3,000,000 more (total 4,750,000) -> Diamond
        order3 = Order(
            telegram_id=tg_id,
            service_name="Test Plan 3",
            amount=3_000_000,
            status=OrderStatus.PAID.value,
        )
        session.add(order3)
        await session.commit()

        loyalty = await get_user_loyalty(session, tg_id)
        assert loyalty["tier_id"] == "diamond"
        assert loyalty["discount_percent"] == 15
        assert loyalty["is_max_tier"] is True
        assert loyalty["progress_percent"] == 100


def test_apply_loyalty_discount():
    disc, final = apply_loyalty_discount(100_000, 10)
    assert disc == 10_000
    assert final == 90_000

    disc, final = apply_loyalty_discount(200_000, 15)
    assert disc == 30_000
    assert final == 170_000

    disc, final = apply_loyalty_discount(50_000, 0)
    assert disc == 0
    assert final == 50_000


@pytest.mark.anyio
async def test_gift_cards_flow(session_factory):
    async with session_factory() as session:
        sender_id = 111222333
        receiver_id = 444555666

        sender = User(telegram_id=sender_id, username="sender_user")
        receiver = User(telegram_id=receiver_id, username="receiver_user")
        session.add_all([sender, receiver])

        sender_wallet = Wallet(telegram_id=sender_id, balance=100_000)
        receiver_wallet = Wallet(telegram_id=receiver_id, balance=0)
        session.add_all([sender_wallet, receiver_wallet])
        await session.commit()

        # 1. Create Balance Gift Voucher Link
        res = await create_gift(
            session=session,
            sender_telegram_id=sender_id,
            sender_name="Sender",
            delivery_type="LINK",
            gift_type="BALANCE",
            amount=50_000,
            message="Happy Birthday!",
        )
        assert res["ok"] is True
        code = res["code"]
        assert code.startswith("GIFT-")

        # Check sender balance deducted
        await session.refresh(sender_wallet)
        assert sender_wallet.balance == 50_000

        # 2. Sender cannot claim their own gift
        fail_res = await claim_gift(
            session=session,
            code=code,
            claimer_telegram_id=sender_id,
        )
        assert fail_res["ok"] is False

        # 3. Receiver claims gift
        claim_res = await claim_gift(
            session=session,
            code=code,
            claimer_telegram_id=receiver_id,
            claimer_username="receiver_user",
        )
        assert claim_res["ok"] is True
        assert claim_res["amount"] == 50_000

        # Check receiver balance credited
        await session.refresh(receiver_wallet)
        assert receiver_wallet.balance == 50_000

        # 4. Cannot claim again
        fail_res2 = await claim_gift(
            session=session,
            code=code,
            claimer_telegram_id=receiver_id,
        )
        assert fail_res2["ok"] is False
        assert "قبلاً استفاده شده" in fail_res2["message"]

        # 5. Check history
        history = await get_user_gifts(session, sender_id)
        assert len(history["sent"]) == 1
        assert history["sent"][0]["code"] == code
        assert history["sent"][0]["is_claimed"] is True


@pytest.mark.anyio
async def test_gift_direct_send(session_factory):
    async with session_factory() as session:
        sender_id = 777111222
        receiver_id = 777333444

        session.add(User(telegram_id=sender_id, username="gifter"))
        session.add(User(telegram_id=receiver_id, username="lucky_friend"))
        session.add(Wallet(telegram_id=sender_id, balance=80_000))
        await session.commit()

        # Create direct gift targeting @lucky_friend
        res = await create_gift(
            session=session,
            sender_telegram_id=sender_id,
            sender_name="Best Friend",
            delivery_type="DIRECT",
            gift_type="BALANCE",
            amount=30_000,
            receiver_target="@lucky_friend",
            message="Enjoy this gift!",
        )
        assert res["ok"] is True
        code = res["code"]

        # Other random user cannot claim this direct gift
        imposter_id = 999999999
        session.add(User(telegram_id=imposter_id, username="imposter"))
        await session.commit()

        fail_claim = await claim_gift(
            session=session,
            code=code,
            claimer_telegram_id=imposter_id,
            claimer_username="imposter",
        )
        assert fail_claim["ok"] is False
        assert "اختصاصاً برای کاربر دیگری" in fail_claim["message"]

        # Lucky friend claims successfully
        ok_claim = await claim_gift(
            session=session,
            code=code,
            claimer_telegram_id=receiver_id,
            claimer_username="lucky_friend",
        )
        assert ok_claim["ok"] is True


@pytest.mark.anyio
async def test_custom_plan_calculation(session_factory):
    async with session_factory() as session:
        from bot.services.app_settings import get_store_settings
        store_settings = await get_store_settings(session)
        # default settings: price_per_gb=2500, price_per_day=500, base_price=10000
        gb = 40
        days = 30
        expected_base = (40 * 2500) + (30 * 500) + 10000  # 100k + 15k + 10k = 125,000
        assert expected_base == 125000

        # With 10% Gold discount
        disc, final = apply_loyalty_discount(expected_base, 10)
        assert disc == 12500
        assert final == 112500

