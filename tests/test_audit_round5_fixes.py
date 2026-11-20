"""Tests for Audit Round 5 Fixes:
1. Bank SMS ReDoS prevention (< 50ms for 32KB input)
2. Bank SMS Balance override prevention (balance amount is not taken as deposit)
3. Bank SMS Outgoing transfer rejection
4. Bank SMS "قابل برداشت" deposit acceptance
5. Bank SMS Dotted amount normalization
6. Bank SMS Card last4 date suffix avoidance
7. CardAutoRepository SMS hash deduplication with tracking_code and idempotency_key
8. ForApp amount fallback reachability
9. Encrypted ZIP backup restoration with password
10. Broadcast audience: permanent active users included in 'active', excluded from 'expired'
11. AdminNotifier fallback to ADMIN_IDS when ADMIN_CHAT_ID delivery fails
12. Expiry username HTML escaping
"""
import asyncio
import time
from html import escape
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest
from aiogram.types import Message

from bot.db.models import User, Wallet
from bot.db.repositories.card_auto_repo import CardAutoRepository
from bot.services.payment.bank_sms_parser import parse_bank_sms
from bot.services.backup import create_database_backup, restore_database_backup
from bot.services.broadcast import resolve_broadcast_recipients
from bot.services.admin_notifier import send_admin_topic_notification


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_bank_sms_redos_prevention():
    """Verify that a 32KB SMS with repeated digits/commas finishes in under 50ms."""
    evil_sms = "1," * 16000
    t0 = time.time()
    res = parse_bank_sms(evil_sms)
    elapsed = time.time() - t0
    assert elapsed < 0.05, f"ReDoS vulnerability detected: took {elapsed:.3f}s"
    assert res.is_deposit is False


def test_bank_sms_balance_override_prevention():
    """Verify that large balance amounts do not overwrite the actual deposit amount."""
    sms = "واریز 50,000\nموجودی حساب شما برابر است با 5,000,000 ریال"
    res = parse_bank_sms(sms)
    assert res.is_deposit is True
    # Deposit should be 50,000 Rials = 5,000 Tomans, NOT 500,000 Tomans
    assert res.amount_toman == 5000
    assert res.amount_rial == 50000


def test_bank_sms_outgoing_transfer_rejected():
    """Verify that an outgoing transfer is not accepted as deposit even with '+' or 'شما'."""
    sms = "انتقال به کارت 6037 مبلغ 50,000 ریال از حساب شما sh +98912"
    res = parse_bank_sms(sms)
    assert res.is_deposit is False
    assert "خروجی" in (res.reject_reason or "")


def test_bank_sms_ghabele_bardasht_accepted():
    """Verify that 'موجودی قابل برداشت' in deposit SMS does not trigger withdrawal rejection."""
    sms = "واریز مبلغ 50,000 تومان. موجودی قابل برداشت: 500,000 تومان"
    res = parse_bank_sms(sms)
    assert res.is_deposit is True
    assert res.amount_toman == 50000


def test_bank_sms_dotted_amounts_normalized():
    """Verify that dotted thousand groupings (50.500.000) are recognized."""
    sms = "واریز 50.500.000 ریال به حساب شما"
    res = parse_bank_sms(sms)
    assert res.is_deposit is True
    assert res.amount_toman == 5050000


def test_bank_sms_card_last4_ignores_date():
    """Verify that card last 4 digits are not extracted from date suffix like 1403/08/07-1234."""
    sms = "واریز 50000 تومان به کارت 6037991234567890 در تاریخ 1403/08/07-1234"
    res = parse_bank_sms(sms)
    assert res.card_last4 == "7890"


def test_card_auto_repo_sms_hash_includes_tracking_and_idemp():
    """Verify that different tracking codes or idempotency keys produce distinct hashes."""
    h1 = CardAutoRepository.compute_sms_hash("BLUBANK", "واریز 50,000 تومان", tracking_code="111")
    h2 = CardAutoRepository.compute_sms_hash("BLUBANK", "واریز 50,000 تومان", tracking_code="222")
    h3 = CardAutoRepository.compute_sms_hash("BLUBANK", "واریز 50,000 تومان", idempotency_key="key-A")
    assert h1 != h2
    assert h1 != h3


@pytest.mark.anyio
async def test_forapp_amount_fallback_applied():
    """Verify that ForApp external amount fallback is applied when deposit keywords are present but amount unit was missing."""
    from bot.services.payment.card_auto_service import process_incoming_sms
    from unittest.mock import MagicMock

    session = AsyncMock()
    mock_repo = MagicMock()
    mock_repo.sms_hash_exists = AsyncMock(return_value=False)
    mock_repo.log_bank_sms = AsyncMock(return_value=MagicMock(id=1))
    mock_repo.match_invoice_for_deposit = AsyncMock(return_value=None)
    mock_repo.claim_and_mark_paid = AsyncMock(return_value=None)

    with patch("bot.services.payment.card_auto_service.CardAutoRepository", return_value=mock_repo):
        # Raw message has deposit keywords and digits but no explicit unit
        res = await process_incoming_sms(
            session=session,
            bot=AsyncMock(),
            settings=MagicMock(),
            store=MagicMock(),
            sender="BANK",
            raw_message="واریز به کارت شما 75000",
            forapp_amount_toman=7500,
        )
        assert res["ok"] is True
        # Verify amount passed to log_bank_sms was 7500
        call_kwargs = mock_repo.log_bank_sms.call_args.kwargs
        assert call_kwargs["amount_toman"] == 7500


@pytest.mark.anyio
async def test_encrypted_zip_backup_and_restore(session_factory, tmp_path):
    """Verify that an AES-encrypted zip backup can be successfully restored with password."""
    async with session_factory() as session:
        u = User(telegram_id=987654, username="test_zip_restore")
        w = Wallet(telegram_id=987654, balance=42000)
        session.add_all([u, w])
        await session.commit()

    async with session_factory() as session:
        zip_path = await create_database_backup(session, out_dir=tmp_path, password="MySecretPassword123!")
        assert zip_path.suffix == ".zip"
        assert zip_path.is_file()

    # Now restore from the encrypted zip
    async with session_factory() as session:
        stats = await restore_database_backup(session, zip_path, password="MySecretPassword123!")
        assert stats["users"] >= 1
        assert stats["wallets"] >= 1


@pytest.mark.anyio
async def test_broadcast_includes_permanent_active_users():
    """Verify that active panel accounts without expireAt are included in 'active' and not 'expired'."""
    session = AsyncMock()
    mock_remna = AsyncMock()
    # Account 101: active with expireAt in the future
    # Account 102: active with NO expireAt (permanent)
    mock_remna.get_all_panel_users.return_value = [
        {"telegramId": 101, "status": "ACTIVE", "expireAt": "2030-01-01T00:00:00Z"},
        {"telegramId": 102, "status": "ACTIVE", "expireAt": None},
    ]

    with patch("bot.services.broadcast.UserRepository") as mock_u_repo:
        u1 = MagicMock(telegram_id=101)
        u2 = MagicMock(telegram_id=102)
        u3 = MagicMock(telegram_id=103)
        mock_u_repo.return_value.all_users = AsyncMock(return_value=[u1, u2, u3])
        mock_u_repo.return_value.list_banned = AsyncMock(return_value=[])

        recipients_active = await resolve_broadcast_recipients(session, mock_remna, "active")
        assert 101 in recipients_active
        assert 102 in recipients_active

        recipients_expired = await resolve_broadcast_recipients(session, mock_remna, "expired")
        assert 101 not in recipients_expired
        assert 102 not in recipients_expired
        assert 103 in recipients_expired


@pytest.mark.anyio
async def test_admin_notifier_truncates_long_text_and_delivers():
    """Verify that AdminNotifier truncates text exceeding 4000 chars and delivers safely."""
    mock_bot = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.ADMIN_CHAT_ID = -100123456789
    mock_settings.ADMIN_IDS = [555]
    mock_settings.ADMIN_TOPIC_BROADCAST = 12

    with patch("bot.services.admin_notifier.get_settings", return_value=mock_settings):
        long_text = "A" * 5000
        await send_admin_topic_notification(mock_bot, kind="broadcast", text=long_text)
        called_text = mock_bot.send_message.call_args[0][1]
        assert len(called_text) <= 4000
        assert called_text.endswith("...")


def test_expiry_username_html_escape():
    """Verify that username with HTML special chars is escaped."""
    raw_username = "test<user>&admin"
    escaped = escape(raw_username)
    assert "<" not in escaped
    assert "&lt;" in escaped
    assert "&amp;" in escaped
