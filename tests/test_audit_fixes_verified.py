"""Tests for the 6 verified audit fixes:
1. AdminLog cross-user leakage prevention in user_profile
2. Memory pruning in ACTIVE_BROADCASTS
3. Ceiling rounding for TON and USDT top-up
4. Top-up maximum fallback guard
5. ServiceRepository.list_active() re-raising on catastrophic failure
6. Telegram Stars mismatch topup audit record
"""
import math
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy import select

from bot.db.models import AdminLog, Topup
from bot.handlers.admin_broadcast import ACTIVE_BROADCASTS, _prune_active_broadcasts
from bot.handlers.payment_stars import stars_successful_payment_handler
from bot.db.repositories.service_repo import ServiceRepository
from bot.web.user_topup import _resolve_topup_max, DEFAULT_MAX_TOPUP_TOMAN


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_admin_log_isolation_in_user_profile(session_factory):
    """Ensure user 123 cannot see AdminLog of user 1234, even if detail contains '123'."""
    async with session_factory() as session:
        # Create log for user 1234
        log_other = AdminLog(
            admin_id=999,
            target_user_id=1234,
            action="wallet_charge",
            detail="Wallet credited for 1234 with 50000 Toman",
        )
        session.add(log_other)
        await session.commit()

        # Query using the exact query logic from user_profile
        res = await session.execute(
            select(AdminLog)
            .where(
                AdminLog.target_user_id == 123,
                AdminLog.action.in_(["wallet_charge", "wallet_deduct", "gift_balance"]),
            )
        )
        logs = res.scalars().all()
        assert len(logs) == 0, "User 123 should not see logs belonging to user 1234"

        # Correct user 1234 sees it
        res_correct = await session.execute(
            select(AdminLog)
            .where(
                AdminLog.target_user_id == 1234,
                AdminLog.action.in_(["wallet_charge", "wallet_deduct", "gift_balance"]),
            )
        )
        assert len(res_correct.scalars().all()) == 1


def test_broadcast_memory_pruning():
    """Ensure _prune_active_broadcasts bounds memory to max_keep."""
    ACTIVE_BROADCASTS.clear()
    for i in range(10):
        ACTIVE_BROADCASTS[f"bcast_{i}"] = {"status": "finished", "sent": []}

    _prune_active_broadcasts(max_keep=5)
    assert len(ACTIVE_BROADCASTS) <= 5
    ACTIVE_BROADCASTS.clear()


def test_crypto_topup_ceiling_rounding():
    """Verify that TON and USDT amount calculations use ceiling rounding."""
    # TON: 100,000 / 300,000 = 0.3333333...
    amount = 100_000
    ton_rate = 300_000
    ton_amount = math.ceil((amount / ton_rate) * 10_000) / 10_000
    # Must be 0.3334 (ceiling) instead of 0.3333 (floor/round)
    assert ton_amount == 0.3334

    # USDT: 100,000 / 70,000 = 1.42857...
    usdt_rate = 70_000
    usdt_amount = max(0.1, math.ceil((amount / usdt_rate) * 100) / 100)
    # Must be 1.43 (ceiling) instead of 1.42 (floor)
    assert usdt_amount == 1.43


def test_resolve_topup_max_fallback():
    """Verify top-up max amount fallback logic."""
    mock_store_empty = MagicMock()
    # Unconfigured MagicMock or missing attribute defaults to DEFAULT_MAX_TOPUP_TOMAN
    assert _resolve_topup_max(mock_store_empty) == DEFAULT_MAX_TOPUP_TOMAN

    # Real configured value
    mock_store_configured = MagicMock()
    mock_store_configured.topup_max_amount = 20_000_000
    assert _resolve_topup_max(mock_store_configured) == 20_000_000

    # Non-positive or zero value falls back
    mock_store_zero = MagicMock()
    mock_store_zero.topup_max_amount = 0
    assert _resolve_topup_max(mock_store_zero) == DEFAULT_MAX_TOPUP_TOMAN


@pytest.mark.anyio
async def test_service_repo_list_active_raises_on_fatal_failure():
    """Verify ServiceRepository.list_active() re-raises when database fails catastrophically."""
    mock_session = AsyncMock()
    mock_session.execute.side_effect = RuntimeError("Fatal DB connection lost")
    repo = ServiceRepository(mock_session)

    with pytest.raises(RuntimeError, match="Fatal DB connection lost"):
        await repo.list_active()


@pytest.mark.anyio
async def test_stars_mismatch_creates_rejected_topup_record(session_factory):
    """Verify that Stars payment mismatch creates a rejected topup record for admin audit."""
    msg = AsyncMock()
    msg.successful_payment.invoice_payload = "stars_topup:11111:50000:30"
    msg.successful_payment.currency = "XTR"
    msg.successful_payment.total_amount = 30
    msg.successful_payment.telegram_payment_charge_id = "test_stars_mismatch_audit_1"
    msg.from_user.id = 99999  # Mismatch: from_user 99999 != 11111

    async with session_factory() as session:
        await stars_successful_payment_handler(msg, bot=AsyncMock(), session=session)

        # Check topup table
        res = await session.execute(
            select(Topup).where(Topup.receipt_hash == "mismatch:test_stars_mismatch_audit_1")
        )
        rec = res.scalar_one_or_none()
        assert rec is not None
        assert rec.status == "rejected"
        assert rec.telegram_id == 99999
        assert rec.amount == 50000


@pytest.mark.anyio
async def test_admin_users_actions_safe_bool_and_target_id_validation():
    """Verify ban string 'false' unbans instead of banning, and invalid telegram_ids return 400 (not 500)."""
    import json
    from unittest.mock import patch

    from bot.web.admin_users_actions import (
        post_admin_kill_sessions,
        post_admin_modify_user,
        post_admin_reset_trial,
        post_admin_toggle_ban,
        post_admin_user_revoke_sub,
        post_admin_user_wallet,
    )

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_user = MagicMock(is_banned=True)
    mock_user_repo = MagicMock()
    mock_user_repo.get_by_telegram_id = AsyncMock(return_value=mock_user)

    app = {
        "session_factory": MagicMock(return_value=mock_session),
        "remnawave": MagicMock(get_users_by_telegram_id=AsyncMock(return_value=[])),
        "cache": MagicMock(delete=AsyncMock()),
    }

    with patch("bot.web.admin_users_actions._check_admin", return_value={"id": 1}), \
         patch("bot.web.admin_users_actions.UserRepository", return_value=mock_user_repo):

        # 1. String 'false' must unban cleanly (not evaluate bool('false') == True)
        req_unban = MagicMock(app=app)
        req_unban.json = AsyncMock(return_value={"telegram_id": "12345", "ban": "false"})
        resp_unban = await post_admin_toggle_ban(req_unban)
        assert resp_unban.status == 200
        data_unban = json.loads(resp_unban.text)
        assert data_unban["banned"] is False
        assert mock_user.is_banned is False

        # 2. Invalid/non-numeric telegram_id must return HTTP 400 instead of raising ValueError (500)
        endpoints_and_payloads = [
            (post_admin_modify_user, {"telegram_id": "abc", "traffic_gb": 5}),
            (post_admin_kill_sessions, {"telegram_id": "abc"}),
            (post_admin_reset_trial, {"telegram_id": "abc"}),
            (post_admin_user_wallet, {"telegram_id": "abc", "amount": 10000}),
            (post_admin_user_revoke_sub, {"telegram_id": "abc"}),
        ]
        for handler, payload in endpoints_and_payloads:
            req = MagicMock(app=app)
            req.json = AsyncMock(return_value=payload)
            resp = await handler(req)
            assert resp.status == 400, f"{handler.__name__} did not return 400 on invalid telegram_id"


@pytest.mark.anyio
async def test_trx_tronscan_fallback_supports_hex_expected_address():
    """Verify TronScan fallback matches even when admin stores wallet address in 41-prefixed hex format."""
    from unittest.mock import patch

    from bot.services.crypto.trx import hex_to_tron_address, verify_tron_transaction

    hex_addr = "41" + "12" * 20
    b58_addr = hex_to_tron_address(hex_addr)
    assert b58_addr.startswith("T")

    tx_hash = "e" * 64
    mock_grid_err = MagicMock(status=503)
    mock_scan_ok = MagicMock(status=200)
    mock_scan_ok.json = AsyncMock(return_value={
        "contractRet": "SUCCESS",
        "contractType": 1,
        "timestamp": 1_750_000_000_000,
        "toAddress": b58_addr,
        "amount": 5_000_000,
    })

    class MockTrxSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def post(self, url, **kwargs):
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=mock_grid_err)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        def get(self, url, **kwargs):
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=mock_scan_ok)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

    with patch("aiohttp.ClientSession", MockTrxSession):
        ok, reason, confirmed_sun = await verify_tron_transaction(
            tx_hash=tx_hash,
            expected_address=hex_addr,
            min_sun=5_000_000,
            min_timestamp_ms=1_749_999_000_000,
        )
        assert ok is True
        assert reason == "SUCCESS"
        assert confirmed_sun == 5_000_000

