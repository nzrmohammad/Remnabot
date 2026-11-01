"""Tests for TRX, TON Connect, and xRocket payment gateways."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.repositories.crypto_repo import CryptoRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.crypto.trx import (
    fetch_trx_rate,
    hex_to_tron_address,
    verify_and_credit_trx_invoice,
    verify_tron_transaction,
)
from bot.services.crypto.xrocket import XRocketClient


@pytest.fixture
async def async_session(session_factory):
    async with session_factory() as session:
        yield session


def test_hex_to_tron_address_conversion():
    # Known Tron address conversion
    hex_addr = "418840e6c55b9ada326d211d8307b38f9e51600e0d"
    b58 = hex_to_tron_address(hex_addr)
    assert b58.startswith("T")
    assert b58 == "TNPeeaaFB7K9cmo4uXyyTC47YfBJxtVNgQ"

    # Already base58 address should be untouched
    assert hex_to_tron_address("TLyqzVGLV1srkB7dToTAnY9QVeqxBe5YoH") == "TLyqzVGLV1srkB7dToTAnY9QVeqxBe5YoH"


@pytest.mark.anyio
async def test_fetch_trx_rate_prefers_store_setting():
    rate = await fetch_trx_rate(store_rate=95000)
    assert rate == 95000


@pytest.mark.anyio
async def test_verify_tron_transaction_success():
    expected_addr = "TNPeeaaFB7K9cmo4uXyyTC47YfBJxtVNgQ"
    tx_hash = "a" * 64

    mock_resp = {
        "ret": [{"contractRet": "SUCCESS"}],
        "raw_data": {
            "contract": [
                {
                    "type": "TransferContract",
                    "parameter": {
                        "value": {
                            "amount": 25_000_000,  # 25 TRX (in SUN)
                            "to_address": "418840e6c55b9ada326d211d8307b38f9e51600e0d",
                        }
                    },
                }
            ]
        },
    }

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value.status = 200
        mock_cm.__aenter__.return_value.json = AsyncMock(return_value=mock_resp)
        mock_post.return_value = mock_cm

        ok, reason, sun = await verify_tron_transaction(tx_hash, expected_addr, min_sun=25_000_000)
        assert ok is True
        assert reason == "SUCCESS"
        assert sun == 25_000_000


@pytest.mark.anyio
async def test_verify_and_credit_trx_invoice(async_session: AsyncSession):
    tg_id = 987654
    user_repo = UserRepository(async_session)
    await user_repo.get_or_create(tg_id, username="trx_user", full_name="TRX")
    wallet_repo = WalletRepository(async_session)
    await wallet_repo.get_wallet(tg_id)

    crypto_repo = CryptoRepository(async_session)
    inv = await crypto_repo.create_invoice(
        telegram_id=tg_id,
        amount_toman=150_000,
        amount_ton="15.00",
        nanotons=15_000_000,
        pay_address="TNPeeaaFB7K9cmo4uXyyTC47YfBJxtVNgQ",
        currency="TRX",
    )
    await async_session.commit()

    tx_hash = "b" * 64
    with patch("bot.services.crypto.trx.verify_tron_transaction", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = (True, "SUCCESS", 15_000_000)

        ok, new_bal, msg = await verify_and_credit_trx_invoice(async_session, inv, tx_hash)
        assert ok is True
        assert new_bal == 150_000
        assert "موفقیت" in msg

        # Verify anti-replay
        inv2 = await crypto_repo.create_invoice(
            telegram_id=tg_id,
            amount_toman=50_000,
            amount_ton="5.00",
            nanotons=5_000_000,
            pay_address="TNPeeaaFB7K9cmo4uXyyTC47YfBJxtVNgQ",
            currency="TRX",
        )
        await async_session.commit()

        ok2, _, reason = await verify_and_credit_trx_invoice(async_session, inv2, tx_hash)
        assert ok2 is False
        assert "قبلاً" in reason


@pytest.mark.anyio
async def test_xrocket_client_create_invoice():
    client = XRocketClient(api_key="test_rocket_key")

    mock_resp = {
        "success": True,
        "data": {
            "id": 12345,
            "link": "https://t.me/xrocket?start=inv_abc",
            "status": "active",
        },
    }

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value.status = 200
        mock_cm.__aenter__.return_value.json = AsyncMock(return_value=mock_resp)
        mock_post.return_value = mock_cm

        data = await client.create_invoice(
            amount_usd=5.0,
            currency="USDT",
            payload="topup:123:500000",
        )
        assert data is not None
        assert data["id"] == 12345
        assert "t.me/xrocket" in data["link"]


@pytest.mark.anyio
async def test_xrocket_webhook_security(session_factory):
    from bot.web.user_topup import post_webhook_xrocket
    from bot.db.repositories.app_setting_repo import AppSettingRepository

    # Configure store settings
    async with session_factory() as s:
        repo = AppSettingRepository(s)
        await repo.set("xrocket_enabled", "true")
        await repo.set("xrocket_api_key", "sec_rocket_key")
        await repo.set("usdt_rate_toman", "100000")
        await s.commit()

    # 1. Reject missing payment id
    req_no_id = MagicMock()
    req_no_id.headers = {}
    req_no_id.remote = "127.0.0.1"
    req_no_id.json = AsyncMock(return_value={"status": "PAID", "payload": "topup:999:100000"})
    req_no_id.app = {"session_factory": session_factory}

    resp1 = await post_webhook_xrocket(req_no_id)
    assert resp1.status == 400

    # 2. Reject unverified / fake invoice that cannot be verified by xRocket API
    req_fake = MagicMock()
    req_fake.headers = {}
    req_fake.remote = "127.0.0.1"
    req_fake.json = AsyncMock(return_value={"id": "fake_inv_999", "status": "PAID", "payload": "topup:999:5000000"})
    req_fake.app = {"session_factory": session_factory}

    with patch("bot.services.crypto.xrocket.XRocketClient.get_invoice", AsyncMock(return_value=None)):
        resp2 = await post_webhook_xrocket(req_fake)
        assert resp2.status == 400

    # 3. Accept and credit authentic invoice verified with xRocket API
    verified_remote_inv = {
        "id": "legit_inv_123",
        "status": "PAID",
        "currency": "USDT",
        "amount": 5.0,  # 5 USDT = 500,000 Tomans
        "payload": "topup:888777:500000",
    }
    req_legit = MagicMock()
    req_legit.headers = {}
    req_legit.remote = "127.0.0.1"
    req_legit.json = AsyncMock(return_value={"id": "legit_inv_123", "status": "PAID"})
    req_legit.app = {"session_factory": session_factory}

    with patch("bot.services.crypto.xrocket.XRocketClient.get_invoice", AsyncMock(return_value=verified_remote_inv)):
        resp3 = await post_webhook_xrocket(req_legit)
        assert resp3.status == 200

        # Check user wallet balance credited
        async with session_factory() as s:
            w_repo = WalletRepository(s)
            bal = await w_repo.get_balance(888777)
            assert bal == 500000

