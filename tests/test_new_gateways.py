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
