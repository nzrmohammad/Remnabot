"""Tests for Remnashop-inspired features:
1. Telegram Stars & CryptoBot payments
2. Ad Campaigns and deep-link tracking
3. Access Modes (Invite-Only, Open, Closed)
4. Smart Broadcast with cancellation & message revocation
"""
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from bot.db.models import Base, User, Order, Campaign
from bot.db.repositories.campaign_repo import CampaignRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.services.app_settings import is_maintenance


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.mark.anyio
async def test_campaign_repository_and_stats(db_session_factory):
    """Test campaign creation, stats calculation (users, buyers, revenue, ROI), and deletion."""
    async with db_session_factory() as session:
        repo = CampaignRepository(session)
        user_repo = UserRepository(session)

        # 1. Create a campaign
        camp = await repo.create(code="promo_channel", name="کانال پروکسی", cost=100000)
        assert camp.id is not None
        assert camp.code == "promo_channel"
        assert camp.cost == 100000

        # 2. Add users with campaign
        u1 = await user_repo.get_or_create(telegram_id=101, username="user1", full_name="U1")
        await user_repo.set_campaign(u1, "promo_channel")

        u2 = await user_repo.get_or_create(telegram_id=102, username="user2", full_name="U2")
        await user_repo.set_campaign(u2, "promo_channel")

        # 3. Add order for u1 (buyer)
        order = Order(
            telegram_id=101,
            service_name="1 Month VIP",
            amount=250000,
            status="paid",
        )
        session.add(order)
        await session.commit()

        # 4. Fetch stats
        stats = await repo.get_campaigns_with_stats(bot_username="MyVpnBot")
        assert len(stats) == 1
        s = stats[0]
        assert s["code"] == "promo_channel"
        assert s["users_count"] == 2
        assert s["buyers_count"] == 1
        assert s["total_revenue"] == 250000
        assert s["deep_link"] == "https://t.me/MyVpnBot?start=ad_promo_channel"
        # ROI: (250000 - 100000) / 100000 * 100 = 150%
        assert s["roi"] == 150.0

        # 5. Delete campaign
        del_ok = await repo.delete(camp.id)
        assert del_ok is True
        empty_stats = await repo.get_campaigns_with_stats("MyVpnBot")
        assert len(empty_stats) == 0


@pytest.mark.anyio
async def test_access_mode_logic(db_session_factory):
    """Test access_mode ('open', 'invite_only', 'closed') in is_maintenance."""
    async with db_session_factory() as session:
        app_repo = AppSettingRepository(session)

        # Default open
        assert not await is_maintenance(session)

        # Closed mode activates maintenance
        await app_repo.set("access_mode", "closed")
        assert await is_maintenance(session)

        # Invite-only mode keeps system operational
        await app_repo.set("access_mode", "invite_only")
        assert not await is_maintenance(session)

        # Legacy maintenance flag
        await app_repo.set("maintenance", "1")
        assert await is_maintenance(session)


@pytest.mark.anyio
async def test_smart_broadcast_cancel_and_delete():
    """Test smart broadcast cancellation and message revocation tracking."""
    from bot.handlers.admin_broadcast import ACTIVE_BROADCASTS, broadcast_stop_handler, broadcast_revoke_handler

    bcast_id = "test_bcast_123"
    ACTIVE_BROADCASTS[bcast_id] = {
        "status": "running",
        "sent": [(101, 555), (102, 556)],
    }

    # 1. Stop broadcast
    call = AsyncMock()
    call.from_user.id = 999
    call.data = f"adm:bcast:stop:{bcast_id}"
    bot = AsyncMock()
    user_repo = AsyncMock()

    with patch("bot.handlers.admin_broadcast._is_admin", return_value=True):
        await broadcast_stop_handler(call, bot, user_repo)
        assert ACTIVE_BROADCASTS[bcast_id]["status"] == "stopped"
        call.answer.assert_called_with("🛑 دستور توقف ارسال همگانی صادر شد.", show_alert=True)

    # 2. Revoke / delete messages
    call.data = f"adm:bcast:del:{bcast_id}"
    with patch("bot.handlers.admin_broadcast._is_admin", return_value=True):
        with patch("bot.handlers.admin_broadcast.render_menu", new_callable=AsyncMock):
            await broadcast_revoke_handler(call, bot, user_repo)
            assert bot.delete_message.await_count == 2
            bot.delete_message.assert_any_await(chat_id=101, message_id=555)
            bot.delete_message.assert_any_await(chat_id=102, message_id=556)
            assert ACTIVE_BROADCASTS[bcast_id]["sent"] == []


@pytest.mark.anyio
async def test_payment_stars_precheckout():
    """Test pre-checkout query handler for Telegram Stars."""
    from bot.handlers.payment_stars import stars_pre_checkout_handler

    pre_checkout = AsyncMock()
    pre_checkout.id = "pq_123"
    bot = AsyncMock()

    await stars_pre_checkout_handler(pre_checkout, bot)
    bot.answer_pre_checkout_query.assert_called_once_with("pq_123", ok=True)
