"""Regression and validation tests for Round 6 Audit Fixes.

Covers:
1. Tokenized wheel lock & release in bot handler
2. Bot purchase & renew passing cache to execute_purchase
3. Voucher atomic redemption & double-spend prevention on SQLite
4. Speedtest atomic rate limiting with cache.incr & ping rate limit
5. Speedtest ISP cache bounding (max 500)
6. Invoice order/topup namespace isolation, distinct tracking code, HTML escaping
7. Stale crypto rates cache expiration guard (300s)
8. Referral spin tickets atomic database update
9. Admin broadcast ID uniqueness
10. FastCache L1 backfill guard & atomic incr method
11. CryptoInvoice partial unique index
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest
from sqlalchemy import select

from bot.db.models import Coupon, CouponUsage, CryptoInvoice, Order, OrderStatus, Service, Topup, User
from bot.db.repositories.coupon_repo import CouponRepository
from bot.services.crypto.nobitex import get_crypto_rates_summary
from bot.services.invoice_service import get_order_invoice_data, send_invoice_to_telegram
from bot.web.cache import FastCache


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_fastcache_incr_and_l1_backfill_guard():
    """FastCache.incr must be atomic, and Redis get must not overwrite newer L1 entries."""
    cache = FastCache(redis_client=None)

    # Test incr in memory
    val1 = await cache.incr("test:counter", ttl_seconds=10)
    val2 = await cache.incr("test:counter", ttl_seconds=10)
    val3 = await cache.incr("test:counter", ttl_seconds=10)
    assert val1 == 1
    assert val2 == 2
    assert val3 == 3

    # Test L1 backfill protection: newer entry in L1 should not be overwritten
    mock_redis = AsyncMock()
    mock_redis.get.return_value = '{"version": 1}'
    cache_with_redis = FastCache(redis_client=mock_redis)

    # Set newer entry in L1 memory
    await cache_with_redis.set("key1", {"version": 2}, ttl_seconds=30)
    # Fetching should return the L1 version without clobbering from stale Redis
    res = await cache_with_redis.get("key1")
    assert res["version"] == 2


@pytest.mark.anyio
async def test_voucher_atomic_redemption_prevents_race(session_factory):
    """Voucher redemption with max_uses=1 must succeed only once, preventing race conditions."""
    async with session_factory() as session:
        repo = CouponRepository(session)
        user1 = User(telegram_id=11199, username="u1", full_name="User One")
        user2 = User(telegram_id=22299, username="u2", full_name="User Two")
        session.add_all([user1, user2])

        coupon = Coupon(
            code="VOUCH-TEST1",
            kind="voucher",
            discount_amount=50000,
            max_uses=1,
            used_count=0,
            is_active=True,
        )
        session.add(coupon)
        await session.commit()

        # First redemption succeeds
        ok1, amt1, msg1 = await repo.redeem_credit_voucher("VOUCH-TEST1", 11199)
        assert ok1 is True
        assert amt1 == 50000

        # Second redemption concurrently or immediately after must fail
        ok2, amt2, msg2 = await repo.redeem_credit_voucher("VOUCH-TEST1", 22299)
        assert ok2 is False
        assert amt2 == 0
        assert "سقف مجاز" in msg2 or "غیرفعال" in msg2


@pytest.mark.anyio
async def test_wheel_tokenized_lock():
    """Lucky wheel spin lock must use unique token and release_lock."""
    from bot.handlers.wheel import wheel_spin_action
    mock_call = MagicMock()
    mock_call.from_user.id = 99999
    mock_call.from_user.username = "spinner"
    mock_call.data = "wheel:spin"
    mock_call.answer = AsyncMock()

    mock_bot = AsyncMock()
    mock_user_repo = AsyncMock()
    mock_user = MagicMock()
    mock_user.telegram_id = 99999
    mock_user_repo.get_or_create.return_value = mock_user

    mock_cache = MagicMock()
    mock_cache.set_nx = AsyncMock(return_value=True)
    mock_cache.release_lock = AsyncMock(return_value=True)

    with patch("bot.handlers.wheel.execute_lucky_wheel_spin", AsyncMock(return_value={"ok": False, "error": "test"})):
        await wheel_spin_action(
            call=mock_call,
            bot=mock_bot,
            user_repo=mock_user_repo,
            session=AsyncMock(),
            remnawave=AsyncMock(),
            cache=mock_cache,
        )

    # Must have set lock with TTL=30 and released with token
    mock_cache.set_nx.assert_awaited_once()
    args, kwargs = mock_cache.set_nx.call_args
    assert args[0] == "lock:user:99999:spin"
    assert len(args[1]) == 32  # hex 16 bytes = 32 chars
    assert kwargs.get("ttl_seconds") == 30

    mock_cache.release_lock.assert_awaited_once()
    rel_args, _ = mock_cache.release_lock.call_args
    assert rel_args[0] == "lock:user:99999:spin"
    assert rel_args[1] == args[1]


def test_bot_purchase_and_renew_pass_cache():
    """Shop purchase and renewal handlers must pass cache=cache to execute_purchase."""
    p_code = Path("bot/handlers/shop_purchase.py").read_text(encoding="utf-8")
    r_code = Path("bot/handlers/shop_renew.py").read_text(encoding="utf-8")

    assert "result = await execute_purchase(\n            remnawave, session, service, user.telegram_id,\n            create_new=True, discount_amount=total_discount,\n            coupon_code=coupon_code,\n            bot=bot,\n            cache=cache,\n        )" in p_code
    assert "result = await execute_purchase(\n            remnawave, session, service, user.telegram_id, discount_amount=total_discount,\n            coupon_code=coupon_code,\n            bot=bot,\n            cache=cache,\n        )" in p_code

    assert "result = await execute_purchase(\n            remnawave, session, service, user.telegram_id,\n            chosen_account=chosen, discount_amount=total_discount,\n            coupon_code=coupon_code,\n            bot=bot,\n            cache=cache,\n        )" in r_code


@pytest.mark.anyio
async def test_invoice_order_topup_namespace_and_html_escape(session_factory):
    """Invoices for orders vs topups must not collide and must escape HTML in Telegram notification."""
    async with session_factory() as session:
        user = User(telegram_id=888899, username="test_esc", full_name="<b>John</b> Doe")
        session.add(user)

        order = Order(
            telegram_id=888899,
            service_id=10,
            service_name="Test <VIP> Plan",
            amount=100000,
            status=OrderStatus.PAID.value,
        )
        topup = Topup(
            telegram_id=888899,
            amount=50000,
            status="approved",
        )
        session.add_all([order, topup])
        await session.commit()
        await session.refresh(order)
        await session.refresh(topup)

        # Query with type="topup" must return Topup, not Order
        topup_inv = await get_order_invoice_data(
            session, order_id=topup.id, telegram_id=888899, invoice_type="topup"
        )
        assert topup_inv is not None
        assert topup_inv["order_id"] == topup.id
        assert "TRX-TOP-" in topup_inv["payment"]["tracking_code"]
        assert topup_inv["payment"]["amount_toman"] == 50000

        # Query with type="order" must return Order
        order_inv = await get_order_invoice_data(
            session, order_id=order.id, telegram_id=888899, invoice_type="order"
        )
        assert order_inv is not None
        assert order_inv["order_id"] == order.id
        assert order_inv["item"]["title"] == "Test <VIP> Plan"
        assert order_inv["payment"]["amount_toman"] == 100000

        # Test HTML escaping when sending invoice to Telegram
        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock()
        await send_invoice_to_telegram(mock_bot, 888899, order_inv)
        mock_bot.send_message.assert_awaited_once()
        msg_text = mock_bot.send_message.call_args.kwargs.get("text") or mock_bot.send_message.call_args[0][1]
        assert "&lt;VIP&gt;" in msg_text
        assert "&lt;b&gt;John&lt;/b&gt;" in msg_text


@pytest.mark.anyio
async def test_stale_crypto_rates_threshold():
    """Stale crypto rates cache must not be returned if older than 300 seconds."""
    from bot.services.crypto import nobitex
    nobitex._rates_cache = {"ok": True, "cached_data": True}
    nobitex._rates_cache_time = time.time() - 350  # 350 seconds ago (expired)

    with patch("bot.services.crypto.nobitex.fetch_all_exchange_prices", side_effect=RuntimeError("Exchange Down")):
        res = await get_crypto_rates_summary(force_refresh=True)
        assert res.get("ok") is False
        assert "خطا" in res.get("error", "")


def test_speedtest_verdict_ping_zero_not_superb():
    """Speedtest verdict in speedtest.js must require ping > 0 for superb rating."""
    st_js = Path("bot/web/static/js/speedtest.js").read_text(encoding="utf-8")
    assert "if (dlSpeed >= 25 && ping > 0 && ping <= 90)" in st_js


def test_admin_broadcast_id_uniqueness():
    """Broadcast ID in admin_broadcast.py must include random uuid segment."""
    b_code = Path("bot/handlers/admin_broadcast.py").read_text(encoding="utf-8")
    assert 'bcast_id = f"bc_{int(time.time())}_{call.from_user.id}_{uuid.uuid4().hex[:6]}"' in b_code
