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
    def __init__(self, id, telegram_id, currency="POL", status="pending", pay_address="0x123", nanotons=100, created_at=None, amount_toman=50000):
        self.id = id
        self.telegram_id = telegram_id
        self.currency = currency
        self.status = status
        self.pay_address = pay_address
        self.nanotons = nanotons
        self.created_at = created_at or datetime.now(timezone.utc)
        self.amount_toman = amount_toman


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
        mock_crypto_repo.create_invoice = AsyncMock(return_value=created_inv)
        mock_crypto_cls.return_value = mock_crypto_repo

        resp = await post_user_topup_pol(request)
        assert resp.status == 200
        import json
        data = json.loads(resp.text)
        assert data["ok"] is True
        assert data["invoice"]["id"] == 101
        assert data["invoice"]["currency"] == "POL"
        assert data["invoice"]["amount_pol"] == "1.0000"
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
