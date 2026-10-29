"""Integration tests for Automated Card-to-Card (SMS Forwarder) payment system."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import CardAutoInvoice, User
from bot.db.repositories.card_auto_repo import CardAutoRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.app_settings import StoreSettings
from bot.services.payment.card_auto_service import (
    generate_card_auto_invoice,
    process_incoming_sms,
)


@pytest.fixture
async def async_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest.mark.anyio
async def test_generate_card_auto_invoice_unique_suffix(async_session: AsyncSession):
    store = StoreSettings(
        card_number="6037991234567890",
        card_holder="مدیریت سیستم",
        topup_min_amount=10000,
        default_squad_uuid="",
        expiry_grace_days=3,
        expiry_remind_days="3,1,0",
        topic_topups=None,
        topic_orders=None,
        topic_support=None,
        topic_alerts=None,
        support_contact="",
        card_auto_enabled=True,
    )

    # User 1 creates invoice for 50,000 Tomans
    inv1 = await generate_card_auto_invoice(
        session=async_session,
        telegram_id=111,
        base_amount=50000,
        store=store,
    )
    assert inv1.base_amount == 50000
    assert inv1.exact_amount > 50000
    assert inv1.exact_rial == inv1.exact_amount * 10
    assert inv1.status == "pending"

    # User 2 creates invoice for same base amount (50,000 Tomans)
    inv2 = await generate_card_auto_invoice(
        session=async_session,
        telegram_id=222,
        base_amount=50000,
        store=store,
    )
    assert inv2.base_amount == 50000
    # Must have different exact amount to prevent collision!
    assert inv2.exact_amount != inv1.exact_amount


@pytest.mark.anyio
async def test_process_incoming_sms_and_credit_wallet(async_session: AsyncSession):
    tg_id = 777888
    user_repo = UserRepository(async_session)
    await user_repo.get_or_create(tg_id, username="c2c_user", full_name="C2C User")
    wallet_repo = WalletRepository(async_session)
    await wallet_repo.get_wallet(tg_id)

    store = StoreSettings(
        card_number="6280231574054762",
        card_holder="فاطمه شاکری",
        topup_min_amount=10000,
        default_squad_uuid="",
        expiry_grace_days=3,
        expiry_remind_days="3,1,0",
        topic_topups=None,
        topic_orders=None,
        topic_support=None,
        topic_alerts=None,
        support_contact="",
        card_auto_enabled=True,
        sms_webhook_secret="supersecret123",
    )

    # Create pending invoice for 55,937 Tomans (559,370 Rials)
    repo = CardAutoRepository(async_session)
    inv = await repo.create_invoice(
        telegram_id=tg_id,
        base_amount=55000,
        exact_amount=55937,
        card_number="6280231574054762",
        card_holder="فاطمه شاکری",
    )
    await async_session.commit()

    mock_bot = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.ADMIN_CHAT_ID = None

    # Incoming SMS from Bank Masken
    sms_text = """بانک مسکن
واریز: 559,370 ریال
به کارت 6280***4762
ارجاع: 11223344"""

    res = await process_incoming_sms(
        session=async_session,
        bot=mock_bot,
        settings=mock_settings,
        store=store,
        sender="+98200033",
        raw_message=sms_text,
    )
    await async_session.commit()

    assert res["ok"] is True
    assert res["action"] == "credited"
    assert res["amount_toman"] == 55937
    assert res["invoice_uuid"] == inv.invoice_uuid

    # Check updated wallet balance
    bal = await wallet_repo.get_balance(tg_id)
    assert bal == 55937

    # Check invoice status is paid
    updated_inv = await repo.get_invoice_by_uuid(inv.invoice_uuid)
    assert updated_inv.status == "paid"
    assert updated_inv.paid_at is not None

    # Mock bot should have sent user notification
    assert mock_bot.send_message.called


@pytest.mark.anyio
async def test_process_incoming_sms_unmatched_alert(async_session: AsyncSession):
    store = StoreSettings(
        card_number="6280231574054762",
        card_holder="مدیریت",
        topup_min_amount=10000,
        default_squad_uuid="",
        expiry_grace_days=3,
        expiry_remind_days="",
        topic_topups=None,
        topic_orders=None,
        topic_support=None,
        topic_alerts=None,
        support_contact="",
    )

    mock_bot = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.ADMIN_CHAT_ID = -100123456789
    mock_settings.ADMIN_TOPIC_TOPUPS = None

    # Unmatched deposit SMS
    sms_text = "بانک ملت واریز مبلغ 999,990 ریال به حساب شما"
    res = await process_incoming_sms(
        session=async_session,
        bot=mock_bot,
        settings=mock_settings,
        store=store,
        sender="BankMellat",
        raw_message=sms_text,
    )

    assert res["ok"] is True
    assert res["action"] == "unmatched_deposit"
    assert res["amount_toman"] == 99999
    # Admin alert should be triggered
    assert mock_bot.send_message.called


@pytest.mark.anyio
async def test_webhook_sms_authorization(session_factory):
    from bot.web.server import create_web_app
    from bot.web.user_topup import post_webhook_sms
    from bot.db.repositories.app_setting_repo import AppSettingRepository

    # Configure secret token in db
    async with session_factory() as s:
        repo = AppSettingRepository(s)
        await repo.set("sms_webhook_secret", "my_token_xyz")
        await s.commit()

    # Mock request without token
    req_unauth = MagicMock()
    req_unauth.headers = {}
    req_unauth.query = {}
    req_unauth.json = AsyncMock(return_value={})
    req_unauth.post = AsyncMock(return_value={})
    req_unauth.text = AsyncMock(return_value="")
    req_unauth.app = {"session_factory": session_factory}

    resp = await post_webhook_sms(req_unauth)
    assert resp.status == 401

    # Mock request with valid header
    req_auth = MagicMock()
    req_auth.headers = {"X-SMS-Token": "my_token_xyz"}
    req_auth.query = {}
    req_auth.json = AsyncMock(return_value={"from": "Melli", "text": "برداشت 50,000 ریال"})
    req_auth.app = {"session_factory": session_factory, "bot": None, "settings": None, "cache": None}

    resp_auth = await post_webhook_sms(req_auth)
    assert resp_auth.status == 200
