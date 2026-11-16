"""Tests for SMS Webhook Hardening (rate limiting alerts, query token removal) and ForApp integration."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from bot.db.models import User, Wallet
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.card_auto_repo import CardAutoRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.app_settings import get_store_settings
from bot.web.cache import FastCache
from bot.web.user_topup import post_webhook_sms


@pytest.fixture
async def async_session(session_factory):
    async with session_factory() as session:
        yield session


def _create_mock_request(
    session_factory,
    headers: dict | None = None,
    query: dict | None = None,
    body_dict: dict | None = None,
    raw_body_bytes: bytes | None = None,
    peer_ip: str = "1.2.3.4",
    bot_mock=None,
    settings_mock=None,
    cache=None,
) -> MagicMock:
    req = MagicMock(spec=web.Request)
    req.headers = headers or {}
    req.query = query or {}
    req.remote = peer_ip

    if raw_body_bytes is not None:
        payload_bytes = raw_body_bytes
    elif body_dict is not None:
        payload_bytes = json.dumps(body_dict).encode("utf-8")
    else:
        payload_bytes = b""

    req.read = AsyncMock(return_value=payload_bytes)
    req.text = AsyncMock(return_value=payload_bytes.decode("utf-8", errors="replace"))
    req.json = AsyncMock(return_value=body_dict if body_dict is not None else {})

    app_dict = {
        "session_factory": session_factory,
        "bot": bot_mock,
        "settings": settings_mock,
        "cache": cache or FastCache(),
    }
    req.app = app_dict
    return req


@pytest.mark.anyio
async def test_sms_webhook_rejects_query_token_security_hardening(session_factory):
    """Verify query token ?token=... is rejected (401) to prevent URL secret leakage."""
    secret = "secure_sms_token_456"
    async with session_factory() as s:
        repo = AppSettingRepository(s)
        await repo.set("sms_webhook_secret", secret)
        await s.commit()

    # Request with token only in query string
    req = _create_mock_request(
        session_factory=session_factory,
        headers={},
        query={"token": secret},
        body_dict={"sender": "Bank", "body": "واریز 100,000 ریال"},
        peer_ip="192.168.1.50",
    )
    resp = await post_webhook_sms(req)
    assert resp.status == 401
    resp_data = json.loads(resp.text)
    assert resp_data["ok"] is False


@pytest.mark.anyio
async def test_sms_webhook_accepts_header_tokens(session_factory):
    """Verify X-SMS-Token, X-API-Key (ForApp), and Bearer auth headers are accepted."""
    secret = "header_secret_789"
    async with session_factory() as s:
        repo = AppSettingRepository(s)
        await repo.set("sms_webhook_secret", secret)
        await s.commit()

    # 1. Test X-SMS-Token
    req1 = _create_mock_request(
        session_factory=session_factory,
        headers={"X-SMS-Token": secret},
        body_dict={"sender": "Melli", "message": "برداشت 50,000 ریال"},
    )
    resp1 = await post_webhook_sms(req1)
    assert resp1.status == 200

    # 2. Test X-API-Key (ForApp default header)
    req2 = _create_mock_request(
        session_factory=session_factory,
        headers={"X-API-Key": secret},
        body_dict={"sender": "Mellat", "body": "برداشت 20,000 ریال"},
    )
    resp2 = await post_webhook_sms(req2)
    assert resp2.status == 200

    # 3. Test Authorization: Bearer
    req3 = _create_mock_request(
        session_factory=session_factory,
        headers={"Authorization": f"Bearer {secret}"},
        body_dict={"sender": "Sepah", "body": "برداشت 30,000 ریال"},
    )
    resp3 = await post_webhook_sms(req3)
    assert resp3.status == 200


@pytest.mark.anyio
async def test_sms_webhook_unauthorized_alert_rate_limiting(session_factory):
    """Verify Telegram alerts for unauthorized webhook requests are rate-limited per IP (max 1 per 10m)."""
    secret = "correct_secret_999"
    async with session_factory() as s:
        repo = AppSettingRepository(s)
        await repo.set("sms_webhook_secret", secret)
        await repo.set("topic_sms_logs", "100")
        await s.commit()

    bot_mock = MagicMock()
    bot_mock.send_message = AsyncMock()

    settings_mock = MagicMock()
    settings_mock.ADMIN_CHAT_ID = -1001234567890
    settings_mock.ADMIN_TOPIC_SMS_LOGS = 100

    cache = FastCache()
    peer_ip = "185.220.101.5"

    # Send 5 unauthorized requests with wrong token from the same IP
    for i in range(5):
        req = _create_mock_request(
            session_factory=session_factory,
            headers={"X-SMS-Token": f"wrong_token_{i}"},
            body_dict={"sender": "Hacker", "body": "Flood attempt"},
            peer_ip=peer_ip,
            bot_mock=bot_mock,
            settings_mock=settings_mock,
            cache=cache,
        )
        resp = await post_webhook_sms(req)
        assert resp.status == 401

    # bot.send_message should have been called EXACTLY ONCE to prevent Telegram 429 FloodWait
    assert bot_mock.send_message.call_count == 1
    sent_text = bot_mock.send_message.call_args.kwargs["text"]
    assert "درخواست نامعتبر به وب‌هوک پیامک" in sent_text
    assert peer_ip in sent_text


@pytest.mark.anyio
async def test_sms_webhook_endpoint_rate_limiting(session_factory):
    """Verify endpoint rate limits abusive clients (>60 requests per minute) with 429 status."""
    secret = "rate_limit_secret_111"
    async with session_factory() as s:
        repo = AppSettingRepository(s)
        await repo.set("sms_webhook_secret", secret)
        await s.commit()

    cache = FastCache()
    peer_ip = "194.225.10.12"

    # Pre-fill request count to 60 in cache
    await cache.set(f"rl:sms_webhook_req:{peer_ip}", 60, ttl_seconds=60)

    # The 61st request should be rejected with 429 Too Many Requests
    req = _create_mock_request(
        session_factory=session_factory,
        headers={"X-SMS-Token": secret},
        body_dict={"sender": "Melli", "body": "برداشت 10,000 ریال"},
        peer_ip=peer_ip,
        cache=cache,
    )
    resp = await post_webhook_sms(req)
    assert resp.status == 429
    resp_data = json.loads(resp.text)
    assert resp_data["ok"] is False
    assert "Too many requests" in resp_data["message"]


@pytest.mark.anyio
async def test_forapp_test_ping_event(session_factory):
    """Verify ForApp test ping (test: true) returns 200 OK without processing as financial transaction."""
    secret = "forapp_test_secret"
    async with session_factory() as s:
        repo = AppSettingRepository(s)
        await repo.set("sms_webhook_secret", secret)
        await repo.set("topic_sms_logs", "100")
        await s.commit()

    bot_mock = MagicMock()
    bot_mock.send_message = AsyncMock()

    settings_mock = MagicMock()
    settings_mock.ADMIN_CHAT_ID = -1001234567890
    settings_mock.ADMIN_TOPIC_SMS_LOGS = 100

    cache = FastCache()

    # ForApp sample test payload
    forapp_test_payload = {
        "id": "test-uuid-12345",
        "test": True,
        "sender": "ForApp",
        "bank": "آزمایشی",
        "body": "پیامک آزمایشی ForApp\nواریز: 1,000,123 ریال",
        "amount": 1000123,
        "code": 123,
        "unit": "rial",
        "is_deposit": True,
    }

    req = _create_mock_request(
        session_factory=session_factory,
        headers={"X-API-Key": secret, "Idempotency-Key": "test-uuid-12345"},
        body_dict=forapp_test_payload,
        peer_ip="10.0.0.1",
        bot_mock=bot_mock,
        settings_mock=settings_mock,
        cache=cache,
    )

    resp = await post_webhook_sms(req)
    assert resp.status == 200
    resp_data = json.loads(resp.text)
    assert resp_data["ok"] is True
    assert resp_data["action"] == "test_successful"

    # Admin topic notified of successful test
    assert bot_mock.send_message.call_count == 1
    sent_text = bot_mock.send_message.call_args.kwargs["text"]
    assert "تست موفق وب‌هوک پیامک" in sent_text


@pytest.mark.anyio
async def test_forapp_payload_credits_wallet(session_factory):
    """Verify ForApp JSON payload (using 'body' instead of 'message') credits user wallet seamlessly."""
    secret = "forapp_prod_secret"
    tid = 777888999

    async with session_factory() as s:
        repo = AppSettingRepository(s)
        await repo.set("sms_webhook_secret", secret)
        await repo.set("card_auto_enabled", "1")
        await repo.set("card_number", "6037991234567890")

        # Create user & wallet
        s.add(User(telegram_id=tid, username="test_forapp_user"))
        s.add(Wallet(telegram_id=tid, balance=0))
        await s.commit()

        # Create pending invoice for 100,050 Tomans (1,000,500 Rials)
        card_repo = CardAutoRepository(s)
        inv = await card_repo.create_invoice(
            telegram_id=tid,
            base_amount=100000,
            exact_amount=100050,
            card_number="6037991234567890",
            card_holder="مدیریت سیستم",
            ttl_minutes=60,
        )
        inv_uuid = inv.invoice_uuid
        await s.commit()

    bot_mock = MagicMock()
    bot_mock.send_message = AsyncMock()

    cache = FastCache()

    # ForApp real deposit payload
    forapp_deposit_payload = {
        "id": "forapp-msg-uuid-987",
        "test": False,
        "sender": "بانک ملت",
        "bank": "ملت",
        "body": "بانک ملت\nواریز: 1,000,500 ریال\nبه کارت: 603799***7890\nمانده: 15,200,000 ریال",
        "amount": 1000500,
        "code": 50,
        "unit": "rial",
        "is_deposit": True,
    }

    req = _create_mock_request(
        session_factory=session_factory,
        headers={"X-API-Key": secret, "Idempotency-Key": "forapp-msg-uuid-987"},
        body_dict=forapp_deposit_payload,
        peer_ip="10.0.0.2",
        bot_mock=bot_mock,
        cache=cache,
    )

    resp = await post_webhook_sms(req)
    assert resp.status == 200
    resp_data = json.loads(resp.text)
    assert resp_data["ok"] is True
    assert resp_data["action"] == "credited"
    assert resp_data["telegram_id"] == tid
    assert resp_data["amount_toman"] == 100050

    # Verify wallet balance in DB
    async with session_factory() as s:
        w_repo = WalletRepository(s)
        bal = await w_repo.get_balance(tid)
        assert bal == 100050

        # Invoice marked as paid
        inv_db = await CardAutoRepository(s).get_invoice_by_uuid(inv_uuid)
        assert inv_db.status == "paid"


@pytest.mark.anyio
async def test_admin_settings_sms_forwarder_app_configuration(session_factory):
    """Verify sms_forwarder_app option is stored and retrieved in StoreSettings and Settings API."""
    async with session_factory() as s:
        repo = AppSettingRepository(s)
        await repo.set("sms_forwarder_app", "forapp")
        await s.commit()

        store = await get_store_settings(s)
        assert store.sms_forwarder_app == "forapp"

        await repo.set("sms_forwarder_app", "sms_forwarder")
        await s.commit()

        store2 = await get_store_settings(s)
        assert store2.sms_forwarder_app == "sms_forwarder"
