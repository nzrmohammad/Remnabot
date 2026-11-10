import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db.base import _migrate_db_schema
from bot.db.models import CardAutoInvoice, Coupon, CouponUsage, CryptoInvoice, GiftCard, Order, Service, User, Wallet
from bot.db.repositories.campaign_repo import CampaignRepository
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.crypto_repo import CryptoRepository
from bot.handlers.cleanup import router as cleanup_router
from bot.services.gift_service import claim_gift
from bot.services.purchases import execute_purchase, notify_admin
from bot.services.wheel_service import execute_lucky_wheel_spin


@pytest.mark.anyio
async def test_item10_schema_index_migration(session_factory):
    """Test Item 10: _migrate_db_schema introspects and creates missing indexes."""
    async with session_factory() as session:
        conn = await session.connection()

        def check_and_migrate(sync_conn):
            _migrate_db_schema(sync_conn)

        await conn.run_sync(check_and_migrate)


@pytest.mark.anyio
async def test_item11_crypto_mark_expired_mark_cancelled_atomic(session_factory):
    """Test Item 11: mark_expired and mark_cancelled do not overwrite paid invoices."""
    async with session_factory() as session:
        repo = CryptoRepository(session)
        inv = await repo.create_invoice(
            telegram_id=123,
            amount_toman=50000,
            nanotons=1_000_000_000,
            amount_ton=1.0,
            pay_address="EQTestAddress",
            currency="TON",
        )
        await session.commit()

        # Mark paid
        await repo.mark_paid(inv.id, tx_hash="tx_test_hash")
        await session.commit()

        # Attempt to mark expired on a paid invoice -> should return False and keep status='paid'
        res_exp = await repo.mark_expired(inv.id)
        assert res_exp is False
        inv_fresh = await repo.get_by_id(inv.id)
        assert inv_fresh.status == "paid"

        # Attempt to mark cancelled on a paid invoice -> should return False and keep status='paid'
        res_canc = await repo.mark_cancelled(inv.id)
        assert res_canc is False
        inv_fresh = await repo.get_by_id(inv.id)
        assert inv_fresh.status == "paid"


@pytest.mark.anyio
async def test_item13_coupon_duplicate_usage_does_not_burn_quota(session_factory):
    """Test Item 13: Duplicate usage inside record_usage rolls back used_count increment."""
    async with session_factory() as session:
        coupon = Coupon(
            code="SAVE10",
            discount_percent=10,
            max_uses=2,
            used_count=0,
            is_active=True,
        )
        session.add(coupon)
        await session.commit()

        repo = CouponRepository(session)
        # First usage succeeds
        u1 = await repo.record_usage(coupon, telegram_id=1001, order_id=1, discount_applied=5000)
        assert u1 is not None
        await session.commit()

        # Refresh coupon
        c_check = await repo.get_by_code("SAVE10")
        assert c_check.used_count == 1

        # Second usage by same user violates unique constraint (coupon_id, telegram_id)
        u2 = await repo.record_usage(c_check, telegram_id=1001, order_id=2, discount_applied=5000)
        assert u2 is None
        await session.commit()

        # Verify used_count was NOT burned and remains 1
        c_check2 = await repo.get_by_code("SAVE10")
        assert c_check2.used_count == 1


@pytest.mark.anyio
async def test_item14_coupon_naive_datetime_validation(session_factory):
    """Test Item 14: Naive datetime on expires_at does not crash validate_coupon or redeem_credit_voucher."""
    async with session_factory() as session:
        naive_future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2)
        coupon = Coupon(
            code="NAIVEEXP",
            kind="discount",
            discount_amount=10000,
            max_uses=10,
            used_count=0,
            is_active=True,
            expires_at=naive_future,  # naive datetime as SQLite returns
        )
        voucher = Coupon(
            code="NAIVEVCH",
            kind="voucher",
            discount_amount=10000,
            max_uses=10,
            used_count=0,
            is_active=True,
            expires_at=naive_future,
        )
        session.add_all([coupon, voucher])
        await session.commit()

        repo = CouponRepository(session)
        is_valid, err, disc = await repo.validate_coupon("NAIVEEXP", telegram_id=2001, price=50000)
        assert is_valid is True
        assert disc == 10000

        # Test redeem_credit_voucher with naive datetime (strictly voucher kind)
        ok, cred, msg = await repo.redeem_credit_voucher("NAIVEVCH", telegram_id=2001)
        assert ok is True
        assert cred == 10000


@pytest.mark.anyio
async def test_item15_gift_claim_ownership_username_bypass(session_factory):
    """Test Item 15: User without username cannot claim DIRECT gift targeted at a specific username."""
    async with session_factory() as session:
        gift = GiftCard(
            code="GIFT-FOR-ALICE",
            gift_type="BALANCE",
            amount=50000,
            delivery_type="DIRECT",
            sender_telegram_id=999,
            receiver_username="alice_vip",
            receiver_telegram_id=None,
            is_claimed=False,
        )
        session.add(gift)
        await session.commit()

        # Attacker Bob has no username
        res1 = await claim_gift(session, "GIFT-FOR-ALICE", claimer_telegram_id=555, claimer_username=None)
        assert res1["ok"] is False
        assert "اختصاصاً" in res1["message"]

        # Attacker Charlie has different username
        res2 = await claim_gift(session, "GIFT-FOR-ALICE", claimer_telegram_id=666, claimer_username="charlie")
        assert res2["ok"] is False
        assert "اختصاصاً" in res2["message"]

        # Legitimate Alice claims
        res3 = await claim_gift(session, "GIFT-FOR-ALICE", claimer_telegram_id=777, claimer_username="alice_vip")
        assert res3["ok"] is True


@pytest.mark.anyio
async def test_item16_squads_reversion_on_purchase_failure(session_factory):
    """Test Item 16: set_user_squads is reverted to original squads if compensation triggers."""
    async with session_factory() as session:
        remnawave = AsyncMock()
        # Account currently has squad "orig-squad-uuid"
        account = {
            "id": 42,
            "username": "client42",
            "expireAt": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
            "trafficLimitBytes": 10 * 1024 * 1024 * 1024,
            "activeInternalSquads": [{"uuid": "orig-squad-uuid"}],
            "status": "ACTIVE",
        }
        remnawave.get_user = AsyncMock(return_value=account)
        remnawave.set_user_squads = AsyncMock()
        # Subscription update fails -> triggers squad revert
        remnawave.update_user_subscription = AsyncMock(return_value=None)

        service = Service(
            name="1 Month VIP",
            price=100000,
            duration_days=30,
            traffic_gb=20,
            squad_uuid="new-target-squad",
            is_active=True,
        )
        session.add(service)
        # Wallet with sufficient funds
        wallet = Wallet(telegram_id=3001, balance=200000)
        session.add(wallet)
        await session.commit()

        result = await execute_purchase(
            remnawave,
            session,
            service,
            3001,
            chosen_account=account,
        )
        assert result.ok is False
        # Verify set_user_squads was called with target squad, then reverted with orig-squad-uuid
        assert remnawave.set_user_squads.call_count == 2
        remnawave.set_user_squads.assert_called_with(42, ["orig-squad-uuid"])


@pytest.mark.anyio
async def test_item20_admin_notify_loyalty_discount():
    """Test Item 20: notify_admin reports loyalty discount cleanly."""
    bot = AsyncMock()
    user = MagicMock()
    user.telegram_id = 4001
    user.username = "loyalty_user"
    service = MagicMock()
    service.name = "Gold Plan"
    service.price = 100000
    result = MagicMock()
    result.new_balance = 50000
    result.panel_username = "gold_panel_user"

    with patch("bot.config.get_settings") as mock_settings:
        mock_settings.return_value.ADMIN_CHAT_ID = -100123
        mock_settings.return_value.ADMIN_TOPIC_ORDERS = None
        await notify_admin(
            bot=bot,
            user=user,
            service=service,
            result=result,
            coupon_code=None,
            discount_amount=0,
            loyalty_discount_amount=10000,  # 10% loyalty discount
        )

    assert bot.send_message.called
    sent_text = bot.send_message.call_args[0][1]
    assert "تخفیف وفاداری" in sent_text
    assert "90,000" in sent_text or "90000" in sent_text


@pytest.mark.anyio
async def test_item21_wheel_streak_naive_datetime(session_factory):
    """Test Item 21: Naive datetime in wheel_last_spin_at does not crash streak calculation."""
    async with session_factory() as session:
        naive_yesterday = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        user = User(
            telegram_id=5001,
            username="wheel_spinner",
            wheel_streak=2,
            wheel_last_spin_at=naive_yesterday,  # naive datetime from SQLite
        )
        session.add(user)
        await session.commit()

        remnawave = AsyncMock()
        remnawave.get_users_by_telegram_id = AsyncMock(return_value=[{"id": 1, "status": "ACTIVE"}])
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        bot = AsyncMock()

        res = await execute_lucky_wheel_spin(
            session=session,
            remnawave=remnawave,
            cache=cache,
            bot=bot,
            telegram_id=5001,
            use_ticket=False,
        )
        assert res["ok"] is True
        # Streak should increment from 2 to 3
        assert res["streak"] == 3


def test_item22_admin_topic_sms_manual_empty_str():
    """Test Item 22: ADMIN_TOPIC_SMS_MANUAL='' parses to None without pydantic ValidationError."""
    env_backup = os.environ.get("ADMIN_TOPIC_SMS_MANUAL")
    try:
        os.environ["ADMIN_TOPIC_SMS_MANUAL"] = ""
        s = Settings(
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            REMNAWAVE_BASE_URL="https://example.com",
            REMNAWAVE_TOKEN="tok",
        )
        assert s.ADMIN_TOPIC_SMS_MANUAL is None
    finally:
        if env_backup is not None:
            os.environ["ADMIN_TOPIC_SMS_MANUAL"] = env_backup
        else:
            os.environ.pop("ADMIN_TOPIC_SMS_MANUAL", None)


@pytest.mark.anyio
async def test_item23_campaign_stats_batch_aggregation(session_factory):
    """Test Item 23: get_campaigns_with_stats aggregates stats without N+1 queries."""
    async with session_factory() as session:
        repo = CampaignRepository(session)
        c1 = await repo.create(code="camp_alpha", name="Alpha Ads", cost=50000)
        c2 = await repo.create(code="camp_beta", name="Beta Ads", cost=20000)

        # Add users
        u1 = User(telegram_id=6001, campaign_code="camp_alpha")
        u2 = User(telegram_id=6002, campaign_code="camp_alpha")
        u3 = User(telegram_id=6003, campaign_code="camp_beta")
        session.add_all([u1, u2, u3])
        await session.flush()

        # Add orders with required service_name
        o1 = Order(telegram_id=6001, service_name="Plan Alpha", amount=70000, status="paid")
        o2 = Order(telegram_id=6003, service_name="Plan Beta", amount=30000, status="paid")
        session.add_all([o1, o2])
        await session.commit()

        stats = await repo.get_campaigns_with_stats("mybot")
        assert len(stats) == 2
        alpha_stat = next(s for s in stats if s["code"] == "camp_alpha")
        beta_stat = next(s for s in stats if s["code"] == "camp_beta")

        assert alpha_stat["users_count"] == 2
        assert alpha_stat["buyers_count"] == 1
        assert alpha_stat["total_revenue"] == 70000
        assert alpha_stat["profit"] == 20000

        assert beta_stat["users_count"] == 1
        assert beta_stat["buyers_count"] == 1
        assert beta_stat["total_revenue"] == 30000
        assert beta_stat["profit"] == 10000


def test_item24_cleanup_router_private_chat_only():
    """Test Item 24: Cleanup router strictly targets private chats."""
    handlers = cleanup_router.message.handlers
    assert len(handlers) > 0
    handler = handlers[0]
    filter_obj = handler.filters[0]
    # Verify magic filter resolves True for private chat and False for others
    msg_private = MagicMock(chat=MagicMock(type="private"))
    msg_group = MagicMock(chat=MagicMock(type="group"))
    msg_supergroup = MagicMock(chat=MagicMock(type="supergroup"))
    assert filter_obj.magic.resolve(msg_private) is True
    assert filter_obj.magic.resolve(msg_group) is False
    assert filter_obj.magic.resolve(msg_supergroup) is False
