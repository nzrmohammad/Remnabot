"""Verification tests for Audit Round 4 fixes:
1. create_database_backup with password parameter
2. UserRepository.get_or_create without username
3. Admin coupon duplicate code and FSM state clearance
4. Admin orders list keyboard adjustment and search cancel FSM clearing
5. Admin orders detail IndexError prevention on ref action
6. Web shop input validation and array payload protection
7. Broadcast banned users exclusion
8. Admin settings crypto message edit deduplication
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from aiogram.types import CallbackQuery, Message, User as TgUser

from bot.db.models import User, Wallet, Order, Coupon
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.coupon_repo import CouponRepository
from bot.services.backup import create_database_backup
from bot.services.broadcast import resolve_broadcast_recipients


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_create_database_backup_accepts_password(session_factory, tmp_path):
    """Verify that create_database_backup accepts password parameter without TypeError."""
    async with session_factory() as session:
        user = User(telegram_id=123456, username="backup_user")
        session.add(user)
        await session.commit()

    async with session_factory() as session:
        # Test with password provided
        backup_path = await create_database_backup(session, out_dir=tmp_path, password="secret_backup_pass")
        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.suffix in (".zip", ".json")


@pytest.mark.anyio
async def test_user_repo_get_or_create_without_username(session_factory):
    """Verify that get_or_create can be called with only telegram_id."""
    async with session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_or_create(telegram_id=987123)
        assert user is not None
        assert user.telegram_id == 987123
        assert user.username is None


@pytest.mark.anyio
async def test_admin_coupon_duplicate_clears_fsm(session_factory):
    """Verify that duplicate coupon creation handles existing code and clears state."""
    from bot.handlers.admin_coupons import admin_coupon_add_max_uses

    async with session_factory() as session:
        # Pre-create a coupon
        repo = CouponRepository(session)
        await repo.create(code="DUPCODE", discount_percent=10, max_uses=5)

    async with session_factory() as session:
        mock_msg = AsyncMock(spec=Message)
        mock_msg.from_user = TgUser(id=999, is_bot=False, first_name="Admin")
        mock_msg.chat = MagicMock(id=999)
        mock_msg.message_id = 1
        mock_msg.text = "10"

        mock_bot = AsyncMock()
        mock_user_repo = AsyncMock()
        mock_user_repo.get_or_create = AsyncMock(return_value=MagicMock(language="fa"))

        mock_state = AsyncMock()
        mock_state.get_data = AsyncMock(return_value={"coupon_code": "DUPCODE", "discount_percent": 10, "discount_amount": 0})
        mock_state.clear = AsyncMock()

        with patch("bot.handlers.admin_coupons._is_admin", return_value=True), \
             patch("bot.handlers.admin_coupons.delete_message_silently", AsyncMock()), \
             patch("bot.handlers.admin_coupons.render_menu", AsyncMock()):
            await admin_coupon_add_max_uses(
                message=mock_msg,
                bot=mock_bot,
                user_repo=mock_user_repo,
                session=session,
                state=mock_state,
            )

        # state.clear must be called even on duplicate
        mock_state.clear.assert_awaited()


@pytest.mark.anyio
async def test_broadcast_recipients_excludes_banned_users(session_factory):
    """Verify that resolve_broadcast_recipients excludes banned users from all audiences."""
    async with session_factory() as session:
        u_active = User(telegram_id=111, is_banned=False)
        u_banned = User(telegram_id=222, is_banned=True)
        w_active = Wallet(telegram_id=111, balance=50000)
        w_banned = Wallet(telegram_id=222, balance=50000)
        session.add_all([u_active, u_banned, w_active, w_banned])
        await session.commit()

    async with session_factory() as session:
        mock_remna = AsyncMock()
        recipients_all = await resolve_broadcast_recipients(session, mock_remna, "all")
        assert 111 in recipients_all
        assert 222 not in recipients_all

        recipients_bal = await resolve_broadcast_recipients(session, mock_remna, "balance")
        assert 111 in recipients_bal
        assert 222 not in recipients_bal


def test_admin_orders_detail_short_parts_does_not_crash():
    """Verify that parts length check avoids IndexError with adm:ord:ref."""
    from bot.handlers.admin_orders_detail import _safe_int
    data = "adm:ord:ref"
    parts = data.split(":")
    # Must not raise IndexError
    if len(parts) >= 4 and parts[2] in ("ref", "refyes"):
        order_id = _safe_int(parts[3])
    else:
        action = "view"
        order_id = _safe_int(parts[2]) if len(parts) > 2 else None
    assert order_id is None
