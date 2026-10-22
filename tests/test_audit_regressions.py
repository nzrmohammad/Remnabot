"""Regression tests for audit findings and critical fixes.

Covers:
1. TMA Coupon rollback/safety on purchase failure.
2. TON verification replay attack & clock skew protection.
3. Purchase concurrency locking (double-tap protection).
4. Purchase failure compensation (panel renewal state rollback).
5. Reconcile auto-disabling uncharged panel accounts after crash.
6. Database receipt_hash deduplication and unique index safety.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from bot.db.models import Coupon, CryptoInvoice, Order, Service, Topup, User, Wallet
from bot.db.repositories.crypto_repo import CryptoRepository
from bot.db.repositories.order_repo import OrderRepository
from bot.services.crypto.ton import verify_and_credit_ton_invoice
from bot.services.purchases import PurchaseResult, execute_purchase
from bot.services.reconcile import run_reconcile


@pytest.mark.anyio
async def test_purchase_concurrency_lock_rejects_concurrent_requests():
    """Verify concurrent purchase attempts on the same telegram_id are rejected with kind='conflict'."""
    remnawave = MagicMock()
    session = AsyncMock()
    service = MagicMock()
    service.id = 1
    service.name = "Plan A"
    service.price = 10000

    tid = 987654321

    # Simulate an acquired lock
    from bot.services.purchases import _get_purchase_lock
    lock = _get_purchase_lock(tid)
    await lock.acquire()
    try:
        res = await execute_purchase(remnawave, session, service, tid)
        assert res.ok is False
        assert res.kind == "conflict"
    finally:
        lock.release()


@pytest.mark.anyio
async def test_renewal_balance_race_triggers_compensation():
    """Verify that if balance deduction fails after renewal, compensation reverts panel changes."""
    remnawave = MagicMock()
    tid = 11223344

    existing_account = {
        "id": 55,
        "username": "user_55",
        "expireAt": "2026-11-01T00:00:00Z",
        "trafficLimitBytes": 10 * 1024**3,
        "status": "ACTIVE",
    }
    remnawave.get_users_by_telegram_id = AsyncMock(return_value=[existing_account])
    remnawave.update_user_subscription = AsyncMock(return_value={"id": 55, "username": "user_55"})

    service = MagicMock()
    service.id = 2
    service.name = "30 Days Renewal"
    service.price = 50000
    service.duration_days = 30
    service.traffic_gb = 20
    service.traffic_strategy = "NO_RESET"
    service.hwid_limit = 2
    service.squad_uuid = None

    session = AsyncMock()
    # 1st call: SELECT wallet.balance -> 100000 (passes initial check)
    # 2nd call: UPDATE wallets SET balance = balance - price -> None (simulates race/double-spend)
    res_mock1 = MagicMock(scalar_one_or_none=MagicMock(return_value=100000))
    res_mock2 = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    session.execute = AsyncMock(side_effect=[res_mock1, res_mock2])
    session.commit = AsyncMock()

    with patch("bot.services.app_settings.is_maintenance", AsyncMock(return_value=False)), \
         patch("bot.services.purchases.get_store_settings", AsyncMock(return_value=MagicMock(default_squad_uuid=None))), \
         patch("bot.services.purchases.OrderRepository") as mock_order_repo:

        mock_repo_inst = MagicMock()
        mock_order_repo.return_value = mock_repo_inst
        mock_repo_inst.create = AsyncMock(return_value=MagicMock())
        mock_repo_inst.mark_failed = AsyncMock()

        res = await execute_purchase(remnawave, session, service, tid)
        assert res.ok is False
        assert res.kind == "failed"

        # Verify update_user_subscription was called twice:
        # 1. Renewal update
        # 2. Compensation revert back to old values
        assert remnawave.update_user_subscription.call_count == 2
        revert_call = remnawave.update_user_subscription.call_args_list[1]
        assert revert_call[0][0] == 55
        assert revert_call[0][1] == "2026-11-01T00:00:00Z"
        assert revert_call[0][2] == 10 * 1024**3
        mock_repo_inst.mark_failed.assert_awaited_once()


@pytest.mark.anyio
async def test_reconcile_disables_stale_pending_panel_accounts(session_factory):
    """Verify that run_reconcile marks stale orders failed and disables panel accounts via remnawave."""
    tid = 55667788
    async with session_factory() as session:
        user = User(telegram_id=tid, username="stale_user", full_name="Stale")
        session.add(user)
        # Create a stale order older than 20 minutes
        stale_order = Order(
            telegram_id=tid,
            service_name="Stale Plan",
            amount=50000,
            status="pending",
            panel_user_id=999,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=25),
        )
        session.add(stale_order)
        await session.commit()

    remnawave = MagicMock()
    remnawave.set_user_status = AsyncMock(return_value={"id": 999, "status": "DISABLED"})
    bot = MagicMock()
    bot.send_message = AsyncMock()

    closed = await run_reconcile(bot, session_factory, remnawave=remnawave)
    assert closed == 1

    remnawave.set_user_status.assert_awaited_once_with(999, "DISABLED")

    async with session_factory() as session:
        repo = OrderRepository(session)
        orders = await repo.list_for_user(tid)
        assert len(orders) == 1
        assert orders[0].status == "failed"


@pytest.mark.anyio
async def test_ton_verification_clock_skew_and_replay_protection(session_factory):
    """Verify TON verification rejects transactions older than invoice creation and duplicate hashes."""
    tid = 998877
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        user = User(telegram_id=tid, username="ton_user", full_name="Ton")
        wallet = Wallet(telegram_id=tid, balance=0)
        session.add_all([user, wallet])

        invoice = CryptoInvoice(
            id=101,
            telegram_id=tid,
            amount_toman=150000,
            amount_ton="1.5",
            nanotons=1500000000,
            comment="REMNA-TON-1",
            pay_address="EQB_test_address",
            status="pending",
            created_at=now,
            expires_at=now + timedelta(minutes=30),
        )
        session.add(invoice)
        await session.commit()

    # Case 1: Clock skew older than invoice creation - 60s
    old_tx = {
        "comment": "REMNA-TON-1",
        "nanotons": 1500000000,
        "tx_hash": "tx_skew_old_hash",
        "utime": int((now - timedelta(seconds=120)).timestamp()),
    }
    async with session_factory() as session:
        repo = CryptoRepository(session)
        inv = await repo.get_by_id(101)
        assert inv is not None
        is_paid, new_bal, tx = await verify_and_credit_ton_invoice(session, inv, [old_tx])
        assert is_paid is False
        assert new_bal == 0

    # Case 2: Valid transaction timestamp -> success
    valid_tx = {
        "comment": "REMNA-TON-1",
        "nanotons": 1500000000,
        "tx_hash": "tx_valid_first_time",
        "utime": int((now + timedelta(seconds=10)).timestamp()),
    }
    async with session_factory() as session:
        repo = CryptoRepository(session)
        inv = await repo.get_by_id(101)
        assert inv is not None
        is_paid, new_bal, tx = await verify_and_credit_ton_invoice(session, inv, [valid_tx])
        assert is_paid is True
        assert new_bal == 150000
        assert tx == "tx_valid_first_time"
        await session.commit()

    # Case 3: Replay attack (same tx_hash used again for another invoice)
    async with session_factory() as session:
        invoice2 = CryptoInvoice(
            id=102,
            telegram_id=tid,
            amount_toman=150000,
            amount_ton="1.5",
            nanotons=1500000000,
            comment="REMNA-TON-2",
            pay_address="EQB_test_address",
            status="pending",
            created_at=now,
            expires_at=now + timedelta(minutes=30),
        )
        session.add(invoice2)
        await session.commit()

    replay_tx = {
        "comment": "REMNA-TON-2",
        "nanotons": 1500000000,
        "tx_hash": "tx_valid_first_time",  # Same tx_hash already used in Case 2
        "utime": int((now + timedelta(seconds=15)).timestamp()),
    }
    async with session_factory() as session:
        repo = CryptoRepository(session)
        inv2 = await repo.get_by_id(102)
        assert inv2 is not None
        is_paid, new_bal, tx = await verify_and_credit_ton_invoice(session, inv2, [replay_tx])
        assert is_paid is False
        assert new_bal == 0


@pytest.mark.anyio
async def test_topups_receipt_hash_deduplication_migration():
    """Verify receipt_hash deduplication query works cleanly on tables with duplicates."""
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE test_topups (id INTEGER PRIMARY KEY, receipt_hash TEXT)"))
        await conn.execute(text("INSERT INTO test_topups (id, receipt_hash) VALUES (1, 'hash_abc'), (2, 'hash_abc'), (3, 'hash_xyz')"))
        dedup_sql = text("""
            UPDATE test_topups
            SET receipt_hash = receipt_hash || '_dup_' || id
            WHERE id NOT IN (
                SELECT min_id FROM (
                    SELECT MIN(id) AS min_id
                    FROM test_topups
                    WHERE receipt_hash IS NOT NULL
                    GROUP BY receipt_hash
                ) t
            )
            AND receipt_hash IS NOT NULL
        """)
        await conn.execute(dedup_sql)
        rows = (await conn.execute(text("SELECT id, receipt_hash FROM test_topups ORDER BY id"))).all()
        assert rows[0][1] == "hash_abc"
        assert rows[1][1] == "hash_abc_dup_2"
        assert rows[2][1] == "hash_xyz"
        assert len(set(r[1] for r in rows)) == 3
    await engine.dispose()


@pytest.mark.anyio
async def test_coupon_not_consumed_on_purchase_failure(session_factory):
    """Verify that in TMA shop, if purchase execution fails, coupon usage is NOT recorded."""
    from bot.web.user_shop import post_user_purchase
    from aiohttp.test_utils import make_mocked_request

    tid = 776655
    async with session_factory() as session:
        user = User(telegram_id=tid, username="coupon_buyer", full_name="Buyer")
        wallet = Wallet(telegram_id=tid, balance=50000)
        service = Service(id=99, name="Test Svc", price=40000, duration_days=30, traffic_gb=20, is_active=True)
        coupon = Coupon(code="FAIL_SAVE", discount_percent=20, max_uses=5, is_active=True)
        session.add_all([user, wallet, service, coupon])
        await session.commit()

    rem_mock = MagicMock()
    rem_mock.get_users_by_telegram_id = AsyncMock(return_value=[])
    app = {
        "session_factory": session_factory,
        "remnawave": rem_mock,
        "bot": MagicMock(),
        "settings": MagicMock(),
        "cache": MagicMock(get=AsyncMock(return_value=None), set=AsyncMock()),
    }

    # Simulate execute_purchase failing (e.g. panel unreachable)
    with patch("bot.web.user_shop.execute_purchase", AsyncMock(return_value=PurchaseResult(ok=False, kind="failed"))):
        req = make_mocked_request(
            "POST",
            "/api/user/purchase",
            headers={"Content-Type": "application/json"},
            app=app,
        )
        req.json = AsyncMock(return_value={"service_id": 99, "coupon_code": "FAIL_SAVE"})
        req["user"] = {"id": tid, "username": "coupon_buyer"}

        resp = await post_user_purchase(req)
        assert resp.status == 500

    # Verify coupon usage was NOT recorded and coupon remains valid
    async with session_factory() as session:
        from bot.db.repositories.coupon_repo import CouponRepository
        c_repo = CouponRepository(session)
        is_valid, _, _ = await c_repo.validate_coupon("FAIL_SAVE", tid, price=40000)
        assert is_valid is True
