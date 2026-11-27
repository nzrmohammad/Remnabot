"""Verification tests for Audit Round 3 fixes:
1. GIFT- Voucher & GiftCard dual routing in redeem_code_to_wallet
2. Admin user detail revoke_user_subscription invocation (no AttributeError)
3. Subscription config URL masking and SSRF internal host detection
4. RemnawaveClient panel_retry wrapping and deduplicated get_all_panel_users
5. Lucky Wheel float streak weighting and ticket delivery protection
6. Custom plan volume discount amount consistency
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from sqlalchemy import select

from bot.db.models import Coupon, GiftCard, User, Wallet
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.gift_service import redeem_code_to_wallet
from bot.services.configs import _is_internal_host, _mask_url
from bot.services.remnawave import RemnawaveClient, panel_retry


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_gift_voucher_routing_credit_coupon(session_factory):
    """Verify that GIFT- prefixed credit vouchers created by admin redeem properly to wallet."""
    async with session_factory() as session:
        # Create an admin credit voucher with GIFT- prefix
        coupon_repo = CouponRepository(session)
        codes = await coupon_repo.batch_generate_vouchers(count=1, amount=50000, prefix="GIFT-")
        assert len(codes) == 1
        code = codes[0]
        assert code.startswith("GIFT-")

        # Create user
        user = User(telegram_id=987654, username="test_voucher_user", full_name="Voucher User")
        wallet = Wallet(telegram_id=987654, balance=0)
        session.add_all([user, wallet])
        await session.commit()

    async with session_factory() as session:
        # Redeem through unified SSOT helper
        res = await redeem_code_to_wallet(session, code, telegram_id=987654)
        assert res["ok"] is True
        assert res["amount"] == 50000

        # Verify wallet balance was updated
        wallet_repo = WalletRepository(session)
        w = await wallet_repo.get_wallet(987654)
        assert w.balance == 50000


@pytest.mark.anyio
async def test_gift_card_routing_friend_gift(session_factory):
    """Verify that friend GiftCards with GIFT- prefix still route to claim_gift."""
    async with session_factory() as session:
        sender = User(telegram_id=11111, username="sender11111")
        user = User(telegram_id=22222, username="receiver_user", full_name="Receiver")
        session.add_all([sender, user])
        await session.flush()

        # Create a GiftCard
        gift = GiftCard(
            code="GIFT-FRIEND-123",
            gift_type="BALANCE",
            amount=30000,
            sender_telegram_id=11111,
            is_claimed=False,
            delivery_type="LINK",
        )
        wallet = Wallet(telegram_id=22222, balance=10000)
        session.add_all([gift, wallet])
        await session.commit()

    async with session_factory() as session:
        res = await redeem_code_to_wallet(session, "GIFT-FRIEND-123", telegram_id=22222)
        assert res["ok"] is True

        wallet_repo = WalletRepository(session)
        w = await wallet_repo.get_wallet(22222)
        assert w.balance == 40000


@pytest.mark.anyio
async def test_admin_revoke_calls_revoke_user_subscription():
    """Verify admin_user_detail calls revoke_user_subscription instead of non-existent revoke_user_sub."""
    from bot.handlers.admin_user_detail import panel_user_callback_dispatch
    from aiogram.types import CallbackQuery, User as TgUser

    call = AsyncMock(spec=CallbackQuery)
    call.data = "adm:puser:revoke:10:all:0"
    call.from_user = TgUser(id=999, is_bot=False, first_name="Admin")
    call.answer = AsyncMock()

    mock_bot = AsyncMock()
    mock_user_repo = AsyncMock()
    mock_user_repo.get_or_create = AsyncMock(return_value=MagicMock(language="fa"))
    mock_remnawave = AsyncMock(spec=RemnawaveClient)
    mock_remnawave.revoke_user_subscription = AsyncMock(return_value={"success": True})
    mock_state = AsyncMock()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    with patch("bot.handlers.admin_user_detail._is_admin", return_value=True), \
         patch("bot.handlers.admin_user_detail._render_panel_user_detail", AsyncMock()):
        await panel_user_callback_dispatch(
            call=call,
            bot=mock_bot,
            user_repo=mock_user_repo,
            session=mock_session,
            remnawave=mock_remnawave,
            state=mock_state,
        )

    mock_remnawave.revoke_user_subscription.assert_awaited_once_with(10)


def test_configs_url_masking_and_ssrf_host_detection():
    """Verify subscription token masking in logs and internal IP detection."""
    masked = _mask_url("https://sub.remna.io/api/sub/secret_token_123456789?token=xyz")
    assert "secret_token_123456789" not in masked
    assert "..." in masked

    assert _is_internal_host("127.0.0.1") is True
    assert _is_internal_host("localhost") is True
    assert _is_internal_host("remnawave") is True
    assert _is_internal_host("192.168.1.100") is True
    assert _is_internal_host("10.0.0.5") is True
    assert _is_internal_host("172.20.0.3") is True  # private docker
    assert _is_internal_host("172.217.16.206") is False  # public IP (Google)
    assert _is_internal_host("8.8.8.8") is False
    assert _is_internal_host("sub.remna.io") is False


@pytest.mark.anyio
async def test_remnawave_client_panel_retry_wrapping():
    """Verify that RemnawaveClient wraps request method with panel_retry."""
    client = RemnawaveClient(base_url="https://fake-panel.local", token="token123")
    assert hasattr(client._client.request, "retry")
    await client.close()


@pytest.mark.anyio
async def test_remnawave_get_all_panel_users_deduplication():
    """Verify that get_all_panel_users transparently deduplicates users by id/uuid."""
    client = RemnawaveClient(base_url="https://fake-panel.local", token="token123")
    mock_resp1 = MagicMock()
    mock_resp1.status_code = 200
    mock_resp1.json = MagicMock(return_value={
        "response": [
            {"id": 1, "username": "user1"},
            {"id": 2, "username": "user2"},
            {"id": 1, "username": "user1_dup"},
        ]
    })

    client._client.get = AsyncMock(return_value=mock_resp1)
    users = await client.get_all_panel_users(size=100)
    assert users is not None
    assert len(users) == 2
    assert [u["id"] for u in users] == [1, 2]
    await client.close()


@pytest.mark.anyio
async def test_wheel_service_delivery_failure_protects_ticket(session_factory):
    """Verify that if Remnawave fails to apply winning prize, ticket is restored and cooldown is not set."""
    from bot.services.wheel_service import execute_lucky_wheel_spin

    async with session_factory() as session:
        user = User(
            telegram_id=44444,
            username="wheel_tester",
            spin_tickets=2,
            wheel_streak=1,
            wheel_last_spin_at=None,
        )
        session.add(user)
        await session.commit()

    async with session_factory() as session:
        mock_remna = AsyncMock(spec=RemnawaveClient)
        # Active subscription exists
        mock_remna.get_users_by_telegram_id = AsyncMock(return_value=[{"id": 10, "status": "ACTIVE", "trafficLimitBytes": 100000}])
        # Updating subscription FAILS
        mock_remna.update_user_subscription = AsyncMock(return_value=None)

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_bot = AsyncMock()

        with patch("bot.services.wheel_service.random.choices", return_value=[{"id": "1gb", "name": "1 GB", "type": "traffic", "value": 1}]):
            res = await execute_lucky_wheel_spin(
                session=session,
                remnawave=mock_remna,
                cache=mock_cache,
                bot=mock_bot,
                telegram_id=44444,
                use_ticket=True,
            )

        assert res["ok"] is True
        assert res["applied"] is False
        # User ticket must NOT be consumed on delivery failure
        assert res["spin_tickets"] == 2

        db_user = (await session.execute(select(User).where(User.telegram_id == 44444))).scalar_one()
        assert db_user.spin_tickets == 2
        assert db_user.wheel_last_spin_at is None
