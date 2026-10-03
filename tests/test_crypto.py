"""Unit and integration tests for TON cryptocurrency payments and Nobitex integration."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.db.models import Base
from bot.db.repositories.crypto_repo import CryptoRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.handlers.admin_ops import apply_nobitex_rate
from bot.services.app_settings import StoreSettings
from bot.services.crypto.nobitex import (
    RATE_CHECK_HOURS,
    _seconds_until_next_target,
    format_rate_alert,
)
from bot.services.crypto.ton import (
    _extract_comment,
    verify_and_process_payments,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def session_factory():
    from sqlalchemy.pool import StaticPool
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest.fixture
async def async_session(session_factory):
    async with session_factory() as session:
        yield session


def test_nobitex_rate_alert_formatting():
    """Verify rate alert puts signs and percentage strictly on the left with \\u200e."""
    # 1. Higher price (increase)
    text_inc, kb_inc = format_rate_alert(nobitex_price=385000, current_rate=370000, hour_str="14:00")
    assert "14:00" in text_inc
    assert "385,000" in text_inc
    assert "370,000" in text_inc
    # Must contain LTR sign before +
    assert "\u200e+15,000" in text_inc
    assert "\u200e+4.1%" in text_inc
    # Button to apply rate directly
    apply_btn = kb_inc.inline_keyboard[0][0]
    assert apply_btn.callback_data == "adm:rate:apply:385000"
    assert "385,000" in apply_btn.text

    # 2. Lower price (decrease)
    text_dec, kb_dec = format_rate_alert(nobitex_price=350000, current_rate=370000, hour_str="22:00")
    assert "22:00" in text_dec
    assert "\u200e-20,000" in text_dec
    assert "\u200e-5.4%" in text_dec
    apply_btn_dec = kb_dec.inline_keyboard[0][0]
    assert apply_btn_dec.callback_data == "adm:rate:apply:350000"

    # 3. No change
    text_eq, kb_eq = format_rate_alert(nobitex_price=370000, current_rate=370000, hour_str="10:00")
    assert "0 تومان" in text_eq
    assert "(0%)" in text_eq


def test_multi_rate_alert_formatting():
    """Verify multi-exchange alert displays all domestic exchanges, USDT, and back button."""
    from bot.services.crypto.nobitex import format_multi_rate_alert

    market_data = {
        "ton": {"نوبیتکس": 387000, "بیت‌پین": 385000, "والکس": 388000},
        "usdt": {"نوبیتکس": 255000, "بیت‌پین": 254000, "والکس": 256000},
        "binance_usd": 1.55,
        "best_ton": (387000, "نوبیتکس"),
        "best_usdt": (255000, "نوبیتکس"),
    }
    text, kb = format_multi_rate_alert(market_data, current_ton_rate=400000, current_usdt_rate=250000, hour_str="10:00")
    assert "نوبیتکس" in text
    assert "بیت‌پین" in text
    assert "والکس" in text
    assert "387,000" in text
    assert "255,000" in text
    buttons = [b for row in kb.inline_keyboard for b in row]
    cb_datas = [b.callback_data for b in buttons]
    assert "adm:rate:apply:ton:387000" in cb_datas
    assert "adm:rate:apply:usdt:255000" in cb_datas
    assert "adm:settings:crypto" in cb_datas


def test_nobitex_scheduled_hours():
    """Verify target check hours are 10, 14, 18, 22."""
    assert RATE_CHECK_HOURS == (10, 14, 18, 22)
    wait_s, next_h = _seconds_until_next_target(RATE_CHECK_HOURS, "Asia/Tehran")
    assert next_h in RATE_CHECK_HOURS
    assert wait_s > 0


@pytest.mark.anyio
async def test_crypto_invoice_crud(async_session: AsyncSession):
    """Test creating, querying, and updating CryptoInvoice in repository."""
    repo = CryptoRepository(async_session)

    # Generate unique comment
    comment = await repo.generate_unique_comment()
    assert 5 <= len(comment) <= 6
    assert comment.isdigit()

    # Create invoice
    inv = await repo.create_invoice(
        telegram_id=12345678,
        amount_toman=100000,
        amount_ton="0.2500",
        nanotons=250000000,
        pay_address="EQD__________________________________________0vo",
        expires_minutes=30,
    )
    comment = inv.comment
    assert 5 <= len(comment) <= 6
    assert comment.isdigit()
    assert inv.id is not None
    assert inv.status == "pending"
    assert inv.telegram_id == 12345678
    assert inv.amount_toman == 100000
    assert inv.amount_ton == "0.2500"
    assert inv.nanotons == 250000000

    # Query by ID
    by_id = await repo.get_by_id(inv.id)
    assert by_id is not None
    assert by_id.comment == comment

    # Query by comment
    by_comment = await repo.get_by_comment(comment)
    assert by_comment is not None
    assert by_comment.id == inv.id

    # Pending invoice
    pending_user = await repo.get_pending_by_user(12345678)
    assert pending_user is not None
    assert pending_user.id == inv.id

    # Mark paid
    await repo.mark_paid(inv.id, tx_hash="tx_abc_123")
    paid_inv = await repo.get_by_id(inv.id)
    assert paid_inv.status == "paid"
    assert paid_inv.tx_hash == "tx_abc_123"
    assert paid_inv.paid_at is not None

    # Pending should now be None
    pending_after = await repo.get_pending_by_user(12345678)
    assert pending_after is None


def test_extract_comment_from_ton_tx():
    """Verify memo/comment extraction from standard text or base64."""
    # Plain message
    tx1 = {"message": "84729103"}
    assert _extract_comment(tx1) == "84729103"

    # Base64 encoded in msg_data
    import base64
    b64_str = base64.b64encode(b"12345678").decode("ascii")
    tx2 = {"msg_data": {"text": b64_str}}
    assert _extract_comment(tx2) == "12345678"

    # Empty
    assert _extract_comment({}) == ""


@pytest.mark.anyio
async def test_ton_payment_watcher_credit(session_factory):
    """Test verify_and_process_payments crediting user wallet when on-chain tx matches."""
    # Create user and invoice in initial session
    async with session_factory() as session:
        user_repo = UserRepository(session)
        await user_repo.get_or_create(telegram_id=999888, username="ton_user")

        wallet_repo = WalletRepository(session)
        wallet = await wallet_repo.get_wallet(999888)
        assert wallet.balance == 0

        crypto_repo = CryptoRepository(session)
        inv = await crypto_repo.create_invoice(
            telegram_id=999888,
            amount_toman=200000,
            amount_ton="0.5000",
            nanotons=500000000,
            pay_address="EQTestWalletAddress",
            expires_minutes=30,
        )
        inv_id = inv.id
        comment = inv.comment
        await session.commit()

    # Mock fetch_ton_transactions
    mock_txs = [
        {
            "tx_hash": "tx_ton_valid_hash_1",
            "nanotons": 500000000,
            "comment": comment,
            "utime": int(datetime.now(timezone.utc).timestamp()),
        }
    ]

    bot = MagicMock()
    bot.send_message = AsyncMock()

    with patch("bot.services.crypto.ton.fetch_ton_transactions", AsyncMock(return_value=mock_txs)):
        with patch("bot.services.crypto.ton.get_store_settings") as mock_settings:
            mock_settings.return_value = StoreSettings(
                card_number="",
                card_holder="",
                topup_min_amount=10000,
                default_squad_uuid="",
                expiry_grace_days=7,
                expiry_remind_days="3,1",
                topic_topups=None,
                topic_orders=None,
                topic_support=None,
                topic_alerts=None,
                support_contact="",
                topic_crypto=1234,
                ton_wallet_address="EQTestWalletAddress",
                ton_rate_toman=400000,
                crypto_enabled=True,
            )

            processed = await verify_and_process_payments(bot, session_factory)
            assert processed == 1

    # Verify invoice status & wallet balance in fresh session
    async with session_factory() as session:
        crypto_repo = CryptoRepository(session)
        wallet_repo = WalletRepository(session)

        updated_inv = await crypto_repo.get_by_id(inv_id)
        assert updated_inv.status == "paid"
        assert updated_inv.tx_hash == "tx_ton_valid_hash_1"

        updated_wallet = await wallet_repo.get_wallet(999888)
        assert updated_wallet.balance == 200000

    # Verify notifications sent
    assert bot.send_message.call_count >= 2  # one to user, one to admin


@pytest.mark.anyio
async def test_admin_apply_rate_callback(async_session: AsyncSession):
    """Test adm:rate:apply:<price> sets store TON rate in DB."""
    from bot.db.repositories.app_setting_repo import AppSettingRepository

    cb = MagicMock(spec=CallbackQuery)
    cb.data = "adm:rate:apply:390000"
    cb.answer = AsyncMock()
    cb.message = MagicMock(spec=Message)
    cb.message.edit_text = AsyncMock()
    cb.message.html_text = "Previous message text"
    cb.from_user = User(id=111, is_bot=False, first_name="Admin")

    bot = MagicMock()
    user_repo = UserRepository(async_session)

    with patch("bot.handlers.admin_ops._is_admin", return_value=True):
        await apply_nobitex_rate(cb, bot, user_repo, async_session)

    # Check that ton_rate_toman was saved in DB
    repo = AppSettingRepository(async_session)
    val = await repo.get("ton_rate_toman")
    assert val == "390000"
    cb.answer.assert_called_once()
    assert "390,000" in cb.answer.call_args[0][0]


@pytest.mark.anyio
async def test_crypto_settings_and_overview_ui(session_factory):
    """Verify crypto settings menu title has no (TON), no italics, and overview has 2 lines."""
    from bot.handlers.admin_ops import _render_crypto_settings, _render_settings

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create(telegram_id=111, username="admin_ui")
        bot = MagicMock()
        bot.send_message = AsyncMock()

        # Render crypto settings
        with patch("bot.handlers.admin_ops.render_menu") as mock_render:
            await _render_crypto_settings(bot, user, user_repo, session)
            call_args = mock_render.call_args
            text = call_args[0][3]
            kb = call_args[0][4]

            # Title must not contain (TON)
            assert "💎 <b>تنظیمات پرداخت کریپتو</b>" in text
            assert "(TON)" not in text
            # No italics in tip
            assert "<i>" not in text
            # Topic line removed from crypto settings
            assert "تاپیک اختصاصی" not in text

            # Buttons check
            all_buttons = [b.text for row in kb.inline_keyboard for b in row]
            assert any("آدرس والت" in b for b in all_buttons)
            assert any("نرخ تبدیل" in b for b in all_buttons)
            assert not any("تاپیک کریپتو" in b for b in all_buttons)

        # Render store settings overview
        with patch("bot.handlers.admin_ops.render_menu") as mock_render_ov:
            with patch("bot.handlers.admin_ops._get_admin_group_title", AsyncMock(return_value="Admin Group")):
                await _render_settings(bot, user, user_repo, session)
                ov_text = mock_render_ov.call_args[0][3]
                ov_kb = mock_render_ov.call_args[0][4]
                # Check two-line format
                assert "💎 پرداخت کریپتو :" in ov_text
                assert "قیمت تبدیل :" in ov_text
                assert "💎 پرداخت کریپتو (TON) :" not in ov_text
                # Check button
                ov_buttons = [b.text for row in ov_kb.inline_keyboard for b in row]
                assert any("💎 کریپتو" in b for b in ov_buttons)


@pytest.mark.anyio
async def test_profile_login_status_format(session_factory):
    """Verify profile view contains login status icon without 'وارد شده'."""
    from bot.handlers.profile import _render_profile

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create(telegram_id=222, username="norm_user")
        user.is_verified = True
        bot = MagicMock()
        remnawave = MagicMock()
        remnawave.get_users_by_telegram_id = AsyncMock(return_value=[])

        with patch("bot.handlers.profile.render_menu") as mock_render:
            await _render_profile(bot, user, user_repo, session, remnawave)
            text = mock_render.call_args[0][3]
            assert "وضعیت ورود : ✅" in text
            assert "وارد شده" not in text


@pytest.mark.anyio
async def test_global_binance_fallback():
    """Verify fetch_ton_market_price falls back to global Binance TON/USD * USDT rate."""
    from bot.services.crypto.nobitex import fetch_ton_market_price

    # Mock Binance response
    mock_binance_resp = MagicMock()
    mock_binance_resp.status = 200
    mock_binance_resp.json = AsyncMock(return_value={"symbol": "TONUSDT", "price": "5.4000"})

    class MockSession:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        def get(self, url, *args, **kwargs):
            class RequestContext:
                async def __aenter__(self):
                    if "binance" in url:
                        return mock_binance_resp
                    # Simulate failure on domestic Iranian APIs
                    err_resp = MagicMock()
                    err_resp.status = 403
                    return err_resp
                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass
            return RequestContext()

    with patch("aiohttp.ClientSession", MockSession):
        price, source = await fetch_ton_market_price(usdt_rate=100000)
        assert price == 540000
        assert "بایننس" in source


@pytest.mark.anyio
async def test_remind_and_grace_days_pickers(session_factory):
    from bot.handlers.admin_ops import (
        _render_remind_days_picker,
        _render_grace_days_picker,
        remind_days_toggle,
        grace_days_set,
    )
    from bot.db.repositories.app_setting_repo import AppSettingRepository
    from bot.services.app_settings import get_store_settings

    async with session_factory() as session:
        user_repo = UserRepository(session)
        admin = await user_repo.get_or_create(telegram_id=12345, username="admin")
        bot = MagicMock()
        bot.send_message = AsyncMock()
        bot.edit_message_text = AsyncMock()

        # Set initial settings
        app_repo = AppSettingRepository(session)
        await app_repo.set("expiry_remind_days", "3,1")
        await app_repo.set("expiry_grace_days", "5")
        await session.commit()

        # 1. Render remind days picker
        with patch("bot.handlers.admin_ops.render_menu") as mock_render:
            await _render_remind_days_picker(bot, admin, user_repo, session)
            mock_render.assert_awaited_once()
            text = mock_render.call_args[0][3]
            kb = mock_render.call_args[0][4]
            btn_texts = [b.text for row in kb.inline_keyboard for b in row]

            assert "روزهای انتخابی فعلی" in text
            assert any("3 روز ✅" in b for b in btn_texts)
            assert any("1 روز ✅" in b for b in btn_texts)
            assert any("5 روز" in b and "✅" not in b for b in btn_texts)

        # 2. Toggle remind day (add 5)
        call_mock = MagicMock()
        call_mock.from_user.id = 12345
        call_mock.from_user.username = "admin"
        call_mock.data = "adm:remind:toggle:5"
        call_mock.answer = AsyncMock()

        with patch("bot.handlers.admin_ops._is_admin", return_value=True), \
             patch("bot.handlers.admin_ops.render_menu"):
            await remind_days_toggle(call_mock, bot, user_repo, session)
            store = await get_store_settings(session)
            assert "5" in store.expiry_remind_days
            assert "3" in store.expiry_remind_days
            assert "1" in store.expiry_remind_days

        # 3. Render grace days picker
        with patch("bot.handlers.admin_ops.render_menu") as mock_render_grace:
            await _render_grace_days_picker(bot, admin, user_repo, session)
            mock_render_grace.assert_awaited_once()
            text_grace = mock_render_grace.call_args[0][3]
            kb_grace = mock_render_grace.call_args[0][4]
            grace_btns = [b.text for row in kb_grace.inline_keyboard for b in row]

            assert "مهلت فعلی: <b>5 روز</b>" in text_grace
            assert any("5 روز ✅" in b for b in grace_btns)
            assert any("0" in b for b in grace_btns)

        # 4. Set grace day to 0
        call_grace = MagicMock()
        call_grace.from_user.id = 12345
        call_grace.from_user.username = "admin"
        call_grace.data = "adm:grace:set:0"
        call_grace.answer = AsyncMock()

        with patch("bot.handlers.admin_ops._is_admin", return_value=True), \
             patch("bot.handlers.admin_ops.render_menu"):
            await grace_days_set(call_grace, bot, user_repo, session)
            store = await get_store_settings(session)
            assert store.expiry_grace_days == 0


@pytest.mark.anyio
async def test_card_enabled_toggle_and_wallet_guard(session_factory):
    from bot.handlers.admin_ops import setting_toggle_boolean
    from bot.services.app_settings import get_store_settings
    from bot.handlers.wallet import topup_start

    async with session_factory() as session:
        user_repo = UserRepository(session)
        admin = await user_repo.get_or_create(telegram_id=12345, username="admin")
        bot = MagicMock()
        bot.send_message = AsyncMock()
        bot.edit_message_text = AsyncMock()

        # Set card number
        from bot.db.repositories.app_setting_repo import AppSettingRepository
        app_repo = AppSettingRepository(session)
        await app_repo.set("card_number", "6037-9918-1234-5678")
        await app_repo.set("card_enabled", "1")
        await session.commit()

        # Toggle card_enabled off
        call_toggle = MagicMock()
        call_toggle.from_user.id = 12345
        call_toggle.from_user.username = "admin"
        call_toggle.data = "adm:settings:toggle:card_enabled"
        call_toggle.answer = AsyncMock()

        with patch("bot.handlers.admin_ops._is_admin", return_value=True), \
             patch("bot.handlers.admin_ops._render_settings", AsyncMock()):
            await setting_toggle_boolean(call_toggle, bot, user_repo, session)
            store = await get_store_settings(session)
            assert store.card_enabled is False

        # When card_enabled is False and crypto is off, topup should reject
        call_user = MagicMock()
        call_user.from_user.id = admin.telegram_id
        call_user.from_user.username = admin.username
        call_user.answer = AsyncMock()
        state = AsyncMock()

        with patch("bot.handlers.wallet.render_menu", AsyncMock()):
            await topup_start(call_user, bot, user_repo, session, state)
            call_user.answer.assert_awaited_once()
            assert "شارژ کیف پول فعلاً در دسترس نیست" in call_user.answer.call_args[0][0]


@pytest.mark.anyio
async def test_ton_unique_comment_and_replay_protection(session_factory):
    async with session_factory() as session:
        crypto_repo = CryptoRepository(session)
        # Create an initial invoice and mark it paid
        inv1 = await crypto_repo.create_invoice(
            telegram_id=111,
            amount_toman=100000,
            amount_ton="0.5",
            nanotons=500000000,
            pay_address="EQB...",
        )
        await crypto_repo.mark_paid(inv1.id, tx_hash="hash_abc_123")
        await session.commit()

        # Generate 20 new comments - none should match inv1.comment
        for _ in range(20):
            c = await crypto_repo.generate_unique_comment()
            assert c != inv1.comment

        # Verify get_by_tx_hash
        found_inv = await crypto_repo.get_by_tx_hash("hash_abc_123")
        assert found_inv is not None
        assert found_inv.id == inv1.id


@pytest.mark.anyio
async def test_ton_watcher_rejects_tx_replay_and_stale_utime(session_factory):
    from bot.db.repositories.app_setting_repo import AppSettingRepository
    from bot.services.crypto.ton import verify_and_process_payments

    async with session_factory() as session:
        # Setup store settings with TON wallet
        app_repo = AppSettingRepository(session)
        await app_repo.set("ton_wallet_address", "EQB_TEST_WALLET")
        await app_repo.set("crypto_enabled", "1")
        await app_repo.set("ton_rate_toman", "500000")

        crypto_repo = CryptoRepository(session)
        inv1 = await crypto_repo.create_invoice(
            telegram_id=222,
            amount_toman=50000,
            amount_ton="0.1",
            nanotons=100000000,
            pay_address="EQB_TEST_WALLET",
        )
        # Mark inv1 paid with tx_hash_1
        await crypto_repo.mark_paid(inv1.id, tx_hash="tx_hash_1")

        # Now create inv2 with different comment
        inv2 = await crypto_repo.create_invoice(
            telegram_id=333,
            amount_toman=50000,
            amount_ton="0.1",
            nanotons=100000000,
            pay_address="EQB_TEST_WALLET",
        )
        await session.commit()

    # Case 1: Replayed transaction with tx_hash_1 (already used)
    replayed_txs = [
        {
            "nanotons": 100000000,
            "comment": inv2.comment,
            "tx_hash": "tx_hash_1",  # already used by inv1!
            "utime": int(datetime.now(timezone.utc).timestamp()),
        }
    ]

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    with patch("bot.services.crypto.ton.fetch_ton_transactions", AsyncMock(return_value=replayed_txs)):
        processed = await verify_and_process_payments(mock_bot, session_factory)
        assert processed == 0

    # Case 2: Stale transaction with utime before invoice creation
    stale_txs = [
        {
            "nanotons": 100000000,
            "comment": inv2.comment,
            "tx_hash": "tx_hash_2",
            "utime": int(inv2.created_at.timestamp()) - 1000,  # 1000s in the past
        }
    ]

    with patch("bot.services.crypto.ton.fetch_ton_transactions", AsyncMock(return_value=stale_txs)):
        processed = await verify_and_process_payments(mock_bot, session_factory)
        assert processed == 0

    # Case 3: Legitimate matching transaction
    valid_txs = [
        {
            "nanotons": 100000000,
            "comment": inv2.comment,
            "tx_hash": "tx_hash_2",
            "utime": int(inv2.created_at.timestamp()) + 10,
        }
    ]

    with patch("bot.services.crypto.ton.fetch_ton_transactions", AsyncMock(return_value=valid_txs)):
        processed = await verify_and_process_payments(mock_bot, session_factory)
        assert processed == 1


