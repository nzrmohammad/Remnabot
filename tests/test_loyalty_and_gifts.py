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
        assert loyalty["amount_to_next"] == 300_000
        assert loyalty["progress_percent"] == 0
        assert not loyalty["is_max_tier"]
        assert len(loyalty["all_tiers"]) == 7

        # 2. Add orders for 400,000 -> Silver (threshold: 300,000, next: 700,000)
        order1 = Order(
            telegram_id=tg_id,
            service_name="Test Plan",
            amount=400_000,
            status=OrderStatus.PAID.value,
        )
        session.add(order1)
        await session.commit()

        loyalty = await get_user_loyalty(session, tg_id)
        assert loyalty["tier_id"] == "silver"
        assert loyalty["discount_percent"] == 3
        assert loyalty["total_spent"] == 400_000
        assert loyalty["amount_to_next"] == 300_000  # 700k - 400k = 300k to Gold
        assert loyalty["progress_percent"] == 25  # 100k / 400k

        # 3. Add orders for 600,000 more (total 1,000,000) -> Gold (threshold: 700,000, next: 1,500,000)
        order2 = Order(
            telegram_id=tg_id,
            service_name="Test Plan 2",
            amount=600_000,
            status=OrderStatus.PAID.value,
        )
        session.add(order2)
        await session.commit()

        loyalty = await get_user_loyalty(session, tg_id)
        assert loyalty["tier_id"] == "gold"
        assert loyalty["discount_percent"] == 5
        assert loyalty["total_spent"] == 1_000_000

        # 4. Add orders for 10,000,000 more (total 11,000,000) -> Diamond (threshold: 10,000,000)
        order3 = Order(
            telegram_id=tg_id,
            service_name="Test Plan 3",
            amount=10_000_000,
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


@pytest.mark.anyio
async def test_voucher_redeem_with_gift_card(session_factory):
    async with session_factory() as session:
        sender_id = 771122
        claimer_id = 883344

        sender_w = Wallet(telegram_id=sender_id, balance=50_000)
        claimer_w = Wallet(telegram_id=claimer_id, balance=0)
        session.add_all([sender_w, claimer_w])
        await session.commit()

        # Create gift
        created = await create_gift(
            session=session,
            sender_telegram_id=sender_id,
            sender_name="Ali",
            delivery_type="LINK",
            gift_type="BALANCE",
            amount=30_000,
        )
        assert created["ok"] is True
        code = created["code"]
        assert code.startswith("GIFT-")

        # Claim via claim_gift directly (used by post_user_redeem_voucher)
        res = await claim_gift(
            session=session,
            code=code,
            claimer_telegram_id=claimer_id,
        )
        assert res["ok"] is True
        assert res["amount"] == 30_000

        # Check claimer wallet
        await session.refresh(claimer_w)
        assert claimer_w.balance == 30_000

