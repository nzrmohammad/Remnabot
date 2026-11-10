"""Tests for Polygon (POL) cryptocurrency payment gateway and transaction layout."""
import math
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from bot.db.models import CryptoInvoice, User, Wallet
from bot.services.crypto.pol import (
    fetch_pol_rate,
    verify_and_credit_pol_invoice,
    verify_polygon_transaction,
)
from bot.web.user_topup import (
    get_user_topup_info,
    post_user_topup_pol,
    post_user_topup_pol_verify,
)


@pytest.mark.anyio
async def test_fetch_pol_rate_uses_configured_store_rate():
    rate = await fetch_pol_rate(store_rate=45000)
    assert rate == 45000


@pytest.mark.anyio
async def test_verify_polygon_transaction_invalid_hash():
    ok, reason, _ = await verify_polygon_transaction("invalid_hash", "0x123", 1000)
    assert not ok
    assert "شناسه تراکنش نامعتبر است" in reason


@pytest.mark.anyio
async def test_verify_polygon_transaction_success():
    expected_addr = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
    tx_hash = "0x" + "a" * 64

    # 1 POL = 10^18 Wei
    val_wei = 10**18
    val_hex = hex(val_wei)

    mock_resp_tx = MagicMock()
    mock_resp_tx.status = 200
    mock_resp_tx.json = AsyncMock(return_value={"result": {"to": expected_addr.lower(), "value": val_hex}})

    mock_resp_receipt = MagicMock()
    mock_resp_receipt.status = 200
    mock_resp_receipt.json = AsyncMock(return_value={"result": {"status": "0x1"}})

    class MockClientSession:
        def __init__(self, *args, **kwargs):
            self.call_count = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def post(self, url, json=None, headers=None):
            self.call_count += 1
            cm = MagicMock()
            if json and json.get("method") == "eth_getTransactionByHash":
                cm.__aenter__ = AsyncMock(return_value=mock_resp_tx)
            else:
                cm.__aenter__ = AsyncMock(return_value=mock_resp_receipt)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

    with patch("aiohttp.ClientSession", MockClientSession):
        ok, reason, confirmed_wei = await verify_polygon_transaction(
            tx_hash=tx_hash,
            expected_address=expected_addr,
            min_wei=val_wei,
        )
        assert ok is True
        assert reason == "SUCCESS"
        assert confirmed_wei == val_wei


@pytest.mark.anyio
async def test_verify_and_credit_pol_invoice_replay_prevention():
    session = AsyncMock()
    invoice = SimpleInvoice(
        id=10,
        telegram_id=12345,
        currency="POL",
        status="pending",
        pay_address="0x123",
        nanotons=10**18,
    )

    with patch("bot.services.crypto.pol.CryptoRepository") as mock_crypto_cls:
        mock_crypto = MagicMock()
        mock_crypto_cls.return_value = mock_crypto
        # Existing transaction with another invoice id
        mock_crypto.get_by_tx_hash = AsyncMock(return_value=SimpleInvoice(id=99, telegram_id=999))

        ok, bal, msg = await verify_and_credit_pol_invoice(session, invoice, "0x" + "b" * 64)
        assert ok is False
        assert "قبلاً برای فاکتور دیگری ثبت و استفاده شده است" in msg


class SimpleInvoice:
    def __init__(self, id, telegram_id, currency="POL", status="pending", pay_address="0x123", nanotons=100, created_at=None, amount_toman=50000, amount_ton="1.0", comment="12345", **kwargs):
        self.id = id
        self.telegram_id = telegram_id
        self.currency = currency
        self.status = status
        self.pay_address = pay_address
        self.nanotons = nanotons
        self.created_at = created_at or datetime.now(timezone.utc)
        self.amount_toman = amount_toman
        self.amount_ton = amount_ton
        self.comment = comment
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.mark.anyio
async def test_post_user_topup_pol_flow():
    app = web.Application()
    app["session_factory"] = MagicMock()

    request = MagicMock()
    request.app = app
    request.json = AsyncMock(return_value={"amount": 50000})

    mock_store = MagicMock()
    mock_store.pol_enabled = True
    mock_store.pol_wallet_address = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
    mock_store.pol_rate_toman = 50000
    mock_store.topup_min_amount = 10000
    mock_store.topup_max_amount = 10000000

    created_inv = SimpleInvoice(id=101, telegram_id=555, currency="POL", pay_address=mock_store.pol_wallet_address)
    created_inv.comment = "POL-101"

    with patch("bot.web.user_topup.require_user", return_value=({"id": 555}, None)), \
         patch("bot.web.user_topup.db_session") as mock_session_ctx, \
         patch("bot.web.user_topup.get_store_settings", AsyncMock(return_value=mock_store)), \
         patch("bot.web.user_topup.CryptoRepository") as mock_crypto_cls, \
         patch("bot.db.repositories.card_auto_repo.CardAutoRepository") as mock_card_cls:

        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        mock_card_repo = MagicMock()
        mock_card_repo.get_active_invoice_by_user = AsyncMock(return_value=None)
        mock_card_cls.return_value = mock_card_repo

        mock_crypto_repo = MagicMock()
        mock_crypto_repo.get_pending_by_user = AsyncMock(return_value=None)
        mock_crypto_repo.allocate_unique_crypto_units = AsyncMock(return_value=10**18 + 42 * 10**14)
        mock_crypto_repo.create_invoice = AsyncMock(return_value=created_inv)
        mock_crypto_cls.return_value = mock_crypto_repo

        resp = await post_user_topup_pol(request)
        assert resp.status == 200
        import json
        data = json.loads(resp.text)
        assert data["ok"] is True
        assert data["invoice"]["id"] == 101
        assert data["invoice"]["currency"] == "POL"
        assert data["invoice"]["amount_pol"] == "1.0042"
        assert data["invoice"]["wei"] == str(10**18 + 42 * 10**14)
        assert data["invoice"]["pay_address"] == mock_store.pol_wallet_address



@pytest.mark.anyio
async def test_get_user_topup_info_includes_pol():
    app = web.Application()
    app["session_factory"] = MagicMock()
    app["cache"] = None

    request = MagicMock()
    request.app = app

    mock_store = MagicMock()
    mock_store.pol_enabled = True
    mock_store.pol_wallet_address = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
    mock_store.pol_rate_toman = 48000
    mock_store.card_enabled = False
    mock_store.card_number = ""
    mock_store.card_holder = ""
    mock_store.card_auto_enabled = False
    mock_store.card_require_phone_verification = False
    mock_store.card_blubank_color = "blue"
    mock_store.card_graphical_view_enabled = True
    mock_store.card_template = "blubank"
    mock_store.crypto_enabled = False
    mock_store.ton_wallet_address = ""
    mock_store.ton_rate_toman = 0
    mock_store.trx_enabled = False
    mock_store.trx_wallet_address = ""
    mock_store.trx_rate_toman = 0
    mock_store.stars_enabled = False
    mock_store.stars_rate_toman = 0
    mock_store.usdt_rate_toman = 100000
    mock_store.topup_min_amount = 10000
    mock_store.topup_max_amount = 50000000
    mock_store.history_page_size = 15

    with patch("bot.web.user_topup.require_user", return_value=({"id": 123}, None)), \
         patch("bot.web.user_topup.db_session") as mock_session_ctx, \
         patch("bot.services.app_settings.get_store_settings", AsyncMock(return_value=mock_store)):

        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        resp = await get_user_topup_info(request)
        assert resp.status == 200
        import json
        data = json.loads(resp.text)
        assert data["ok"] is True
        assert data["pol_enabled"] is True
        assert data["pol_wallet_address"] == mock_store.pol_wallet_address
        assert data["pol_rate_toman"] == 48000


@pytest.mark.anyio
async def test_post_user_topup_pol_verify_success():
    app = web.Application()
    app["session_factory"] = MagicMock()
    app["cache"] = None
    app["bot"] = AsyncMock()

    request = MagicMock()
    request.app = app
    request.json = AsyncMock(return_value={"invoice_id": 101, "tx_hash": "0x" + "c" * 64})

    inv = SimpleInvoice(id=101, telegram_id=888, currency="POL", status="pending")

    with patch("bot.web.user_topup.require_user", return_value=({"id": 888}, None)), \
         patch("bot.web.user_topup.db_session") as mock_session_ctx, \
         patch("bot.web.user_topup.CryptoRepository") as mock_crypto_cls, \
         patch("bot.services.crypto.pol.verify_and_credit_pol_invoice", AsyncMock(return_value=(True, 250000, "OK"))):

        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        mock_crypto_repo = MagicMock()
        mock_crypto_repo.get_by_id = AsyncMock(return_value=inv)
        mock_crypto_cls.return_value = mock_crypto_repo

        resp = await post_user_topup_pol_verify(request)
        assert resp.status == 200
        import json
        data = json.loads(resp.text)
        assert data["ok"] is True
        assert data["paid"] is True
        assert data["new_balance"] == 250000
import json
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
from bot.db.base import Base
from bot.db.models import CryptoInvoice
from bot.web.user_topup import get_user_topup_crypto_active, _format_crypto_curr_name


@pytest.mark.anyio
async def test_crypto_invoice_supports_large_wei_values():
    """Verify CryptoInvoice can store and fetch 18-decimal wei > int64 max without overflow."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        # 21.2576 POL = 21,257,600,000,000,000,000 wei (> 2^63 - 1 = 9,223,372,036,854,775,807)
        large_wei = 21257600000000000000
        inv = CryptoInvoice(
            id=1,
            telegram_id=265455450,
            amount_toman=500000,
            amount_ton="21.2576",
            nanotons=large_wei,
            currency="POL",
            comment="62103",
            pay_address="0x343B7C64c6a62eE6815e6E7589fB4F06b0cA8F42",
            status="pending",
            expires_at=datetime.now(timezone.utc),
        )
        session.add(inv)
        await session.commit()

        res = await session.execute(select(CryptoInvoice).where(CryptoInvoice.id == 1))
        fetched = res.scalar_one()
        assert fetched.nanotons == large_wei
        assert isinstance(fetched.nanotons, int)


@pytest.mark.anyio
async def test_get_user_topup_crypto_active_returns_pol_details():
    """Verify get_user_topup_crypto_active includes amount_pol and wei for POL invoices."""
    request = MagicMock()
    now = datetime.now(timezone.utc)
    future = now.replace(year=now.year + 1)
    inv = SimpleInvoice(
        id=77,
        telegram_id=999,
        amount_toman=500000,
        amount_ton="21.2576",
        nanotons=21257600000000000000,
        currency="POL",
        comment="98765",
        pay_address="0xABC123",
        status="pending",
        expires_at=future,
    )

    with patch("bot.web.user_topup.require_user", return_value=({"id": 999}, None)), \
         patch("bot.web.user_topup.db_session") as mock_session_ctx, \
         patch("bot.web.user_topup.CryptoRepository") as mock_crypto_cls:

        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        mock_crypto_repo = MagicMock()
        mock_crypto_repo.get_pending_by_user = AsyncMock(return_value=inv)
        mock_crypto_cls.return_value = mock_crypto_repo

        resp = await get_user_topup_crypto_active(request)
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["ok"] is True
        assert data["has_active"] is True
        assert data["invoice"]["currency"] == "POL"
        assert data["invoice"]["amount_pol"] == "21.2576"
        assert data["invoice"]["wei"] == "21257600000000000000"


def test_format_crypto_curr_name():
    assert _format_crypto_curr_name("POL") == "پلیگان (POL)"
    assert _format_crypto_curr_name("pol") == "پلیگان (POL)"
    assert _format_crypto_curr_name("TRX") == "ترون (TRX)"
    assert _format_crypto_curr_name("TON") == "تون (TON)"
    assert _format_crypto_curr_name(None) == "تون (TON)"


@pytest.mark.anyio
async def test_verify_polygon_transaction_timestamp_guard():
    """Verify verify_polygon_transaction rejects pre-invoice transactions and accepts newer ones."""
    expected_addr = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
    tx_hash = "0x" + "d" * 64
    val_wei = 10**18
    val_hex = hex(val_wei)

    inv_created_ms = 1_750_000_000_000
    old_block_sec = (inv_created_ms // 1000) - 600   # 10 minutes before invoice
    new_block_sec = (inv_created_ms // 1000) + 120   # 2 minutes after invoice

    def make_mock_session(block_ts_sec: int):
        mock_tx = MagicMock(status=200)
        mock_tx.json = AsyncMock(return_value={"result": {"to": expected_addr.lower(), "value": val_hex}})

        mock_receipt = MagicMock(status=200)
        mock_receipt.json = AsyncMock(return_value={"result": {"status": "0x1", "blockNumber": "0x12345"}})

        mock_block = MagicMock(status=200)
        mock_block.json = AsyncMock(return_value={"result": {"timestamp": hex(block_ts_sec)}})

        class _Session:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def post(self, url, json=None, headers=None):
                method = (json or {}).get("method")
                cm = MagicMock()
                if method == "eth_getTransactionByHash":
                    cm.__aenter__ = AsyncMock(return_value=mock_tx)
                elif method == "eth_getTransactionReceipt":
                    cm.__aenter__ = AsyncMock(return_value=mock_receipt)
                else:
                    cm.__aenter__ = AsyncMock(return_value=mock_block)
                cm.__aexit__ = AsyncMock(return_value=None)
                return cm

        return _Session

    # 1. Old transaction before min_timestamp_ms must be rejected
    with patch("aiohttp.ClientSession", make_mock_session(old_block_sec)):
        ok, reason, _ = await verify_polygon_transaction(
            tx_hash=tx_hash,
            expected_address=expected_addr,
            min_wei=val_wei,
            min_timestamp_ms=inv_created_ms,
        )
        assert ok is False
        assert "قبل از زمان ایجاد فاکتور" in reason

    # 2. Fresh transaction after min_timestamp_ms must succeed
    with patch("aiohttp.ClientSession", make_mock_session(new_block_sec)):
        ok, reason, confirmed_wei = await verify_polygon_transaction(
            tx_hash=tx_hash,
            expected_address=expected_addr,
            min_wei=val_wei,
            min_timestamp_ms=inv_created_ms,
        )
        assert ok is True
        assert reason == "SUCCESS"
        assert confirmed_wei == val_wei

