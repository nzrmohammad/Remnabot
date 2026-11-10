import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.db.models import CryptoInvoice


@pytest.mark.anyio
async def test_ton_verification_rejects_non_ton_currency():
    from bot.services.crypto.ton import verify_and_credit_ton_invoice

    session = AsyncMock()
    # Create TRX invoice
    inv = CryptoInvoice(
        id=101,
        telegram_id=123456,
        currency="TRX",
        amount_toman=500_000,
        nanotons=17_000_000,  # 17 TRX in SUN
        status="pending",
        comment="123456",
        pay_address="T...",
    )
    txs = [{
        "comment": "123456",
        "nanotons": 17_000_000,  # 0.017 TON in nanotons!
        "tx_hash": "ton_hash_123",
        "utime": int(datetime.now(timezone.utc).timestamp()),
    }]

    # Should reject because inv.currency is TRX, not TON
    is_paid, new_bal, tx_hash = await verify_and_credit_ton_invoice(session, inv, txs)
    assert is_paid is False
    assert new_bal == 0
    assert tx_hash == ""


@pytest.mark.anyio
async def test_trx_verification_rejects_non_trx_currency():
    from bot.services.crypto.trx import verify_and_credit_trx_invoice

    session = AsyncMock()
    # Create TON invoice
    inv = CryptoInvoice(
        id=202,
        telegram_id=123456,
        currency="TON",
        amount_toman=500_000,
        nanotons=1_000_000_000,  # 1 TON in nanotons
        status="pending",
        comment="test_memo",
        pay_address="EQ...",
    )

    # Should reject because inv.currency is TON, not TRX
    ok, new_bal, msg = await verify_and_credit_trx_invoice(session, inv, "a" * 64)
    assert ok is False
    assert "TRX" in msg


@pytest.mark.anyio
async def test_trx_verification_rejects_smart_contract_and_requires_transfer_contract():
    from bot.services.crypto.trx import verify_tron_transaction

    mock_resp = {
        "ret": [{"contractRet": "SUCCESS"}],
        "raw_data": {
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "contract": [
                {
                    # TriggerSmartContract (e.g. TRC20 transfer) should be rejected for native TRX
                    "type": "TriggerSmartContract",
                    "parameter": {
                        "value": {
                            "amount": 50_000_000,
                            "to_address": "4185ac60505b38f8cf5db2c5547dd59e97c6ff1d29",
                        }
                    },
                }
            ],
        },
    }

    mock_scan_resp = {"contractRet": "SUCCESS", "contractType": 31}

    with patch("aiohttp.ClientSession.post") as mock_post, patch("aiohttp.ClientSession.get") as mock_get:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value.status = 200
        mock_ctx.__aenter__.return_value.json = AsyncMock(return_value=mock_resp)
        mock_post.return_value = mock_ctx

        mock_scan_ctx = AsyncMock()
        mock_scan_ctx.__aenter__.return_value.status = 200
        mock_scan_ctx.__aenter__.return_value.json = AsyncMock(return_value=mock_scan_resp)
        mock_get.return_value = mock_scan_ctx

        ok, reason, sun = await verify_tron_transaction("a" * 64, "4185ac60505b38f8cf5db2c5547dd59e97c6ff1d29", 10_000_000)
        assert ok is False


@pytest.mark.anyio
async def test_trx_verification_rejects_old_timestamp():
    from bot.services.crypto.trx import verify_tron_transaction

    old_ts_ms = int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp() * 1000)
    mock_resp = {
        "ret": [{"contractRet": "SUCCESS"}],
        "raw_data": {
            "timestamp": old_ts_ms,  # 2 days ago
            "contract": [
                {
                    "type": "TransferContract",
                    "parameter": {
                        "value": {
                            "amount": 50_000_000,
                            "to_address": "4185ac60505b38f8cf5db2c5547dd59e97c6ff1d29",
                        }
                    },
                }
            ],
        },
    }

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value.status = 200
        mock_ctx.__aenter__.return_value.json = AsyncMock(return_value=mock_resp)
        mock_post.return_value = mock_ctx

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        ok, reason, sun = await verify_tron_transaction(
            "a" * 64,
            "4185ac60505b38f8cf5db2c5547dd59e97c6ff1d29",
            10_000_000,
            min_timestamp_ms=now_ms - 60_000,
        )
        assert ok is False
        assert "قبل از زمان ایجاد فاکتور" in reason


@pytest.mark.anyio
async def test_admin_bulk_user_delete_fail_closed():
    from bot.web.admin_users_list import post_admin_users_bulk_action

    req = MagicMock()
    req.app = {
        "remnawave": AsyncMock(),
        "admin_ids": [12345],
        "admin_id": 12345,
    }
    req.app["remnawave"].get_all_panel_users = AsyncMock(return_value=[
        {"id": 1, "username": "user1", "status": "ACTIVE"},
        {"id": 2, "username": "user2", "status": "DISABLED"},
    ])

    with patch("bot.web.admin_users_list._check_admin", return_value=({"id": 12345}, None)):
        # 1. Unknown target must fail-closed with 400
        req.json = AsyncMock(return_value={
            "action_type": "delete_users",
            "target": "unknown_typo_target",
            "confirm": "DELETE",
        })
        resp = await post_admin_users_bulk_action(req)
        assert resp.status == 400
        data = json.loads(resp.text)
        assert "نامعتبر است" in data["error"]

        # 2. Case-insensitive "All" / "ALL" must be rejected
        req.json = AsyncMock(return_value={
            "action_type": "delete_users",
            "target": "All",
            "confirm": "DELETE",
        })
        resp2 = await post_admin_users_bulk_action(req)
        assert resp2.status == 400
        data2 = json.loads(resp2.text)
        assert "حذف همگانی تمام کاربران پنل از این بخش مجاز نیست" in data2["error"]


@pytest.mark.anyio
async def test_trx_redirect_xss_and_input_validation():
    from bot.web.user_topup import get_user_topup_trx_redirect

    valid_tron_addr = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # USDT contract on Tron (valid Base58)

    req = MagicMock()
    # 1. Invalid address with XSS attempt
    req.query = {
        "address": 'T123"><script>alert(1)</script>',
        "amount": "10",
    }
    resp1 = await get_user_topup_trx_redirect(req)
    assert resp1.status == 400
    assert "آدرس کیف پول ترون نامعتبر است" in resp1.text

    # 2. Invalid non-numeric amount with injection attempt
    req.query = {
        "address": valid_tron_addr,
        "amount": '10" onclick="alert(1)',
    }
    resp2 = await get_user_topup_trx_redirect(req)
    assert resp2.status == 400
    assert "مبلغ ترون نامعتبر است" in resp2.text

    # 3. Valid address and amount should render escaped HTML
    req.query = {
        "address": valid_tron_addr,
        "amount": "15.5",
    }
    req.url = "https://example.com/redirect"
    resp3 = await get_user_topup_trx_redirect(req)
    assert resp3.status == 200
    assert valid_tron_addr in resp3.text
    assert "15.5 TRX" in resp3.text


@pytest.mark.anyio
async def test_stars_payment_mismatch_alerts_admin_with_charge_id():
    from bot.handlers.payment_stars import stars_successful_payment_handler

    message = MagicMock()
    message.from_user.id = 99999  # Payer is different user
    sp = MagicMock()
    sp.telegram_payment_charge_id = "test_charge_123"
    sp.currency = "XTR"
    sp.total_amount = 50
    # Payload indicates recipient is user 11111
    sp.invoice_payload = "stars_topup:11111:50000:50"
    message.successful_payment = sp

    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res

    bot = AsyncMock()

    with patch("bot.services.error_reporter.report_error", new_callable=AsyncMock) as mock_report:
        await stars_successful_payment_handler(message, bot, session)
        mock_report.assert_called_once()
        context = mock_report.call_args[1].get("exc", "")
        assert "test_charge_123" in str(context)
        assert "99999" in str(context)


@pytest.mark.anyio
async def test_auto_renew_detects_nested_user_traffic_exhaustion():
    from bot.common.helpers import get_used_bytes

    # Panel user has traffic exhausted ONLY in nested userTraffic!
    acc = {
        "id": 10,
        "trafficLimitBytes": 10_000_000_000,
        "usedTrafficBytes": 0,  # Top level is 0
        "userTraffic": {
            "usedTrafficBytes": 10_000_000_000,  # Nested shows 100% used!
        },
    }
    used_bytes = get_used_bytes(acc)
    limit_bytes = int(acc.get("trafficLimitBytes") or 0)
    traffic_exhausted = (limit_bytes > 0 and used_bytes >= limit_bytes)
    assert traffic_exhausted is True
