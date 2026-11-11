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


@pytest.mark.anyio
async def test_card_auto_destination_mismatch(async_session: AsyncSession):
    store = StoreSettings(
        card_number="6037991234567890",  # last 4 = 7890
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

    # SMS is for a different card (e.g. 1111)
    sms_other_card = """بانک ملی
واریز به ۶۰۳۷۹۹******۱۱۱۱
مبلغ: ۵۵۹,۳۷۰ ریال
مانده: ۱,۴۲۰,۰۰۰ ریال"""

    res = await process_incoming_sms(
        session=async_session,
        bot=None,
        settings=None,
        store=store,
        sender="Melli",
        raw_message=sms_other_card,
    )

    assert res["ok"] is True
    assert res["action"] == "card_mismatch"


@pytest.mark.anyio
async def test_topic_sms_logs_notifications(async_session: AsyncSession):
    """Verify topic_sms_logs receives notifications with bot decisions for all SMS actions."""
    store = StoreSettings(
        card_number="6037991234567890",
        card_holder="مدیریت",
        topup_min_amount=10000,
        default_squad_uuid="",
        expiry_grace_days=3,
        expiry_remind_days="3,1,0",
        topic_topups=101,
        topic_orders=None,
        topic_support=None,
        topic_alerts=None,
        topic_sms_logs=999,
        support_contact="",
        card_auto_enabled=True,
    )

    mock_bot = AsyncMock()
    mock_settings = MagicMock(ADMIN_CHAT_ID=-100123456789)

    # 1. Ignored non-deposit SMS
    sms_non_deposit = "برداشت از کارت ۶۰۳۷... مبلغ ۵۰,۰۰۰ ریال"
    res1 = await process_incoming_sms(
        session=async_session,
        bot=mock_bot,
        settings=mock_settings,
        store=store,
        sender="BankMelli",
        raw_message=sms_non_deposit,
    )
    assert res1["action"] == "ignored_non_deposit"
    assert "Not recognized" not in res1["reason"]
    assert mock_bot.send_message.called
    call_args1 = mock_bot.send_message.call_args
    assert call_args1.kwargs.get("message_thread_id") == 999
    msg_text1 = call_args1.kwargs.get("text", "")
    assert "پیامک غیرواریزی" in msg_text1
    assert "Not recognized as deposit" not in msg_text1
    assert "تراکنش برداشت، خرید یا انتقال خروجی از حساب است" in msg_text1

    # 2. Card mismatch SMS
    mock_bot.reset_mock()
    sms_mismatch = "بانک مسکن واریز: ۵۰,۰۰۰ ریال به کارت ۶۲۸۰...۱۱۱۱"
    res2 = await process_incoming_sms(
        session=async_session,
        bot=mock_bot,
        settings=mock_settings,
        store=store,
        sender="Masken",
        raw_message=sms_mismatch,
    )
    assert res2["action"] == "card_mismatch"
    assert mock_bot.send_message.called
    call_args2 = mock_bot.send_message.call_args
    assert call_args2.kwargs.get("message_thread_id") == 999
    assert "عدم تطابق شماره کارت مقصد" in call_args2.kwargs.get("text", "")


@pytest.mark.anyio
async def test_card_auto_messages_history_and_duplicate_guards(async_session: AsyncSession):
    """Verify user/admin card-auto message polish, wallet transaction history inclusion, and topup_info duplicate guards."""
    import json
    from types import SimpleNamespace
    from bot.db.models import CryptoInvoice, User
    from bot.web.user_profile import _fetch_transaction_history
    from bot.web.user_topup import get_user_topup_info

    tg_id = 991122
    user_repo = UserRepository(async_session)
    await user_repo.get_or_create(tg_id, username="ali_dev", full_name="Ali Dev")
    wallet_repo = WalletRepository(async_session)
    await wallet_repo.get_wallet(tg_id)

    repo = CardAutoRepository(async_session)
    inv = await repo.create_invoice(
        telegram_id=tg_id,
        base_amount=300000,
        exact_amount=300710,
        card_number="6219861012345678",
        card_holder="مدیر سیستم",
    )
    await async_session.commit()

    store = StoreSettings(
        card_number="6219861012345678",
        card_holder="مدیر سیستم",
        topup_min_amount=10000,
        default_squad_uuid="",
        expiry_grace_days=3,
        expiry_remind_days="",
        topic_topups=None,
        topic_orders=None,
        topic_support=None,
        topic_alerts=None,
        topic_sms_logs=888,
        support_contact="",
        card_auto_enabled=True,
    )
    mock_bot = AsyncMock()
    mock_settings = MagicMock(ADMIN_CHAT_ID=-100123456789)

    # 1. Unmatched SMS alert has no italic tags
    await process_incoming_sms(
        session=async_session,
        bot=mock_bot,
        settings=mock_settings,
        store=store,
        sender="SMS_Forwarder",
        raw_message="بلو\nواریز پول\nمحمدجواد عزیز، 9,111,000 ریال به حساب شما نشست.",
    )
    for call in mock_bot.send_message.call_args_list:
        assert "<i>" not in call.kwargs.get("text", "")

    mock_bot.reset_mock()

    # 2. Matched SMS credits wallet and formats user & admin messages accurately
    res = await process_incoming_sms(
        session=async_session,
        bot=mock_bot,
        settings=mock_settings,
        store=store,
        sender="SMS_Forwarder",
        raw_message="بلو\nواریز پول\nمحمدجواد عزیز،3,007,100 ریال به حساب شما نشست.\nموجودی: 818,342,497 ریال",
    )
    await async_session.commit()
    assert res["ok"] is True
    assert res["action"] == "credited"
    assert res["telegram_id"] == tg_id

    sent_texts = [call.kwargs.get("text", "") for call in mock_bot.send_message.call_args_list]
    user_msgs = [t for t in sent_texts if "شارژ خودکار کارت‌به‌کارت با موفقیت تأیید شد" in t]
    admin_logs = [t for t in sent_texts if "تأیید و شارژ خودکار کیف پول" in t]
    assert len(user_msgs) == 1
    assert "🏦 بانک:" not in user_msgs[0]
    assert len(admin_logs) == 1
    assert "@ali_dev" in admin_logs[0]
    assert f"\u2066<code>#{inv.invoice_uuid}</code>\u2069" in admin_logs[0]
    assert "<i>" not in admin_logs[0]

    # 3. Also add a paid CryptoInvoice and verify both appear in transaction history
    async_session.add(CryptoInvoice(
        telegram_id=tg_id,
        amount_toman=250000,
        amount_ton="1.5",
        nanotons=1500000000,
        currency="TON",
        comment=f"c_{tg_id}",
        pay_address="UQTest",
        status="paid",
        expires_at=datetime.now(timezone.utc),
        paid_at=datetime.now(timezone.utc),
    ))
    await async_session.commit()

    txs = await _fetch_transaction_history(async_session, tg_id, "Asia/Tehran")
    tx_types = {item["type"]: item for item in txs}
    assert "card_auto" in tx_types
    assert tx_types["card_auto"]["amount"] == 300710
    assert tx_types["card_auto"]["status"] == "تایید خودکار"
    assert "crypto" in tx_types
    assert tx_types["crypto"]["amount"] == 250000

    # 4. get_user_topup_info includes recent_paid_auto_amounts and recent_receipt_hashes
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_db_session(_req):
        yield async_session

    fake_req = SimpleNamespace(app={"cache": None}, query={}, headers={})
    with patch("bot.web.user_topup.require_user", return_value=({"id": tg_id, "is_preview": False}, None)), \
         patch("bot.web.user_topup.enforce_invite_only", AsyncMock(return_value=None)), \
         patch("bot.web.user_topup.db_session", side_effect=_fake_db_session), \
         patch("bot.web.user_topup.get_store_settings", AsyncMock(return_value=store)):
        resp = await get_user_topup_info(fake_req)
        payload = json.loads(resp.text)
        assert payload["ok"] is True
        assert 300710 in payload["recent_paid_auto_amounts"]
        assert isinstance(payload["recent_receipt_hashes"], list)

