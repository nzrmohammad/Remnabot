"""Regression tests for Bot <-> Mini App parity (SSOT wallet history, DELETED filtering, create_new, settings)."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery
from aiogram.types import User as TgUser
from aiohttp.test_utils import make_mocked_request

from bot.db.models import (
    AdminLog,
    CardAutoInvoice,
    CryptoInvoice,
    Order,
    OrderStatus,
    Service,
    Topup,
    User,
    Wallet,
)
from bot.db.repositories.user_repo import UserRepository
from bot.services.purchases import filter_active_panel_users
from bot.services.wallet_history import classify_topup_method, fetch_user_transactions
from bot.web.cache import FastCache


@pytest.mark.anyio
async def test_wallet_history_ssot_bot_and_tma_parity(session_factory):
    """Both TMA _fetch_transaction_history and Bot wallet:history share Stars labels, CardAuto, Crypto, and AdminAdjust."""
    from bot.handlers.wallet import topup_history
    from bot.web.user_profile import _fetch_transaction_history

    tid = 774411
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add(User(telegram_id=tid, username="parity_user", language="fa"))
        await session.flush()
        session.add(Wallet(telegram_id=tid, balance=500_000))
        session.add_all([
            Topup(telegram_id=tid, amount=120_000, status="approved", receipt_hash="stars:chg_1"),
            CardAutoInvoice(
                invoice_uuid="ca-test-1",
                telegram_id=tid, base_amount=200_000, exact_amount=200_123, exact_rial=2_001_230,
                card_number="6219", card_holder="Admin", status="paid",
                expires_at=now, paid_at=now,
            ),
            CryptoInvoice(
                telegram_id=tid, amount_toman=350_000, amount_ton="2.0", nanotons=2_000_000_000,
                currency="TON", comment="c_1", pay_address="UQ1", status="paid",
                expires_at=now, paid_at=now,
            ),
            AdminLog(admin_id=1, target_user_id=tid, action="wallet_charge", detail="amount=75000"),
            Order(telegram_id=tid, service_name="Gold Plan", amount=90_000, status=OrderStatus.FAILED.value),
        ])
        await session.commit()

        assert classify_topup_method("stars:chg_1")[1] == "⭐️ تلگرام استارز"
        tma_txs = await _fetch_transaction_history(session, tid, "Asia/Tehran")
        stars_tx = next(tx for tx in tma_txs if tx["type"] == "topup")
        assert "تلگرام استارز" in stars_tx["title"]
        assert "کارت به کارت" not in stars_tx["title"]
        assert any(tx["type"] == "card_auto" for tx in tma_txs)
        assert any(tx["type"] == "crypto" for tx in tma_txs)
        assert any(tx["type"] == "admin_adjust" and tx["amount"] == 75_000 for tx in tma_txs)
        assert any(tx["type"] == "order" and tx["raw_status"] == "failed" for tx in tma_txs)

        bot_txs = await fetch_user_transactions(session, tid, "Asia/Tehran", include_failed_orders=False)
        assert not any(tx["type"] == "order" for tx in bot_txs)

        call = MagicMock(spec=CallbackQuery)
        call.from_user = TgUser(id=tid, is_bot=False, first_name="Parity", username="parity_user")
        call.data = "wallet:history"
        call.answer = AsyncMock()
        bot = MagicMock()
        u_repo = UserRepository(session)

        with patch("bot.handlers.wallet.render_menu", AsyncMock()) as mock_render:
            await topup_history(call, bot, u_repo, session)
            mock_render.assert_awaited_once()
            rendered = mock_render.call_args[0][3]
            assert "تلگرام استارز" in rendered
            assert "کارت‌به‌کارت آنی" in rendered
            assert "رمزارز TON" in rendered
            assert "شارژ دستی مدیریت" in rendered
            assert "Gold Plan" not in rendered


@pytest.mark.anyio
async def test_deleted_panel_accounts_ignored_and_create_new_works_in_tma(session_factory):
    """DELETED panel accounts are excluded from TMA & execute_purchase; create_new=True provisions a fresh account."""
    import json

    from bot.web.user_shop import post_user_custom_plan_purchase, post_user_purchase

    raw = [
        {"id": 10, "username": "old_del", "status": "DELETED"},
        {"id": 20, "username": "live_acc", "status": "ACTIVE", "expireAt": "2027-01-01T00:00:00Z"},
        {"id": 20, "username": "live_acc", "status": "ACTIVE", "expireAt": "2027-01-01T00:00:00Z"},
    ]
    filtered = filter_active_panel_users(raw)
    assert [a["id"] for a in filtered] == [20]

    tid = 665544
    async with session_factory() as session:
        session.add(User(telegram_id=tid, username="multi_shopper"))
        session.add(Wallet(telegram_id=tid, balance=900_000))
        svc = Service(id=505, name="VIP 30GB", price=100_000, duration_days=30, traffic_gb=30, is_active=True)
        session.add(svc)
        await session.commit()

    remnawave = AsyncMock()
    remnawave.get_users_by_telegram_id.return_value = [
        {"id": 10, "username": "deleted_user", "status": "DELETED"},
        {"id": 20, "username": "active_user", "status": "ACTIVE", "expireAt": "2027-01-01T00:00:00Z"},
    ]
    remnawave.update_user_subscription.return_value = {"id": 20, "username": "active_user", "subscriptionUrl": "https://sub/20"}
    remnawave.create_user.return_value = {"id": 30, "username": "new_user_30", "subscriptionUrl": "https://sub/30"}
    remnawave.get_internal_squads.return_value = []

    app = {
        "session_factory": session_factory,
        "remnawave": remnawave,
        "bot": None,
        "settings": SimpleNamespace(TIMEZONE="Asia/Tehran"),
        "cache": FastCache(redis_client=None),
    }

    # 1. Standard purchase without create_new picks ONLY the single active account (ignores DELETED)
    req1 = make_mocked_request("POST", "/api/user/purchase", app=app)
    req1.json = AsyncMock(return_value={"service_id": 505})
    req1["user"] = {"id": tid, "username": "multi_shopper"}
    resp1 = await post_user_purchase(req1)
    assert resp1.status == 200
    assert json.loads(resp1.text)["panel_username"] == "active_user"
    remnawave.update_user_subscription.assert_awaited_once()
    remnawave.create_user.assert_not_awaited()

    # 2. Standard purchase with create_new=True creates a brand-new panel account instead of renewing id=20
    remnawave.update_user_subscription.reset_mock()
    req2 = make_mocked_request("POST", "/api/user/purchase", app=app)
    req2.json = AsyncMock(return_value={"service_id": 505, "create_new": True})
    req2["user"] = {"id": tid, "username": "multi_shopper"}
    resp2 = await post_user_purchase(req2)
    assert resp2.status == 200
    assert json.loads(resp2.text)["subscription_url"] == "https://sub/30"
    remnawave.create_user.assert_awaited_once()
    remnawave.update_user_subscription.assert_not_awaited()

    # 3. Custom plan purchase with create_new=True also creates a fresh panel account
    remnawave.create_user.reset_mock()
    remnawave.create_user.return_value = {"id": 31, "username": "custom_31", "subscriptionUrl": "https://sub/31"}
    req3 = make_mocked_request("POST", "/api/user/custom-plan/purchase", app=app)
    req3.json = AsyncMock(return_value={"traffic_gb": 20, "duration_days": 30, "hwid_limit": 2, "create_new": True})
    req3["user"] = {"id": tid, "username": "multi_shopper"}
    resp3 = await post_user_custom_plan_purchase(req3)
    assert resp3.status == 200
    assert json.loads(resp3.text)["subscription_url"] == "https://sub/31"
    remnawave.create_user.assert_awaited_once()


@pytest.mark.anyio
async def test_bot_admin_settings_invalidate_fastcache_and_js_defaults_match(session_factory):
    from bot.config import get_settings
    from bot.handlers.admin_settings_views import maintenance_toggle

    cache = FastCache(redis_client=None)
    await cache.set("store_settings", {"maintenance": False}, ttl_seconds=60)
    await cache.set("tma:user:555:dashboard:default", {"ok": True}, ttl_seconds=60)

    admin_id = 888999
    get_settings().ADMIN_IDS.append(admin_id)
    try:
        bot = MagicMock()
        bot.cache = cache
        call = MagicMock(spec=CallbackQuery)
        call.from_user = TgUser(id=admin_id, is_bot=False, first_name="Adm", username="adm")
        call.answer = AsyncMock()
        async with session_factory() as async_session:
            u_repo = UserRepository(async_session)

            with patch("bot.handlers.admin_settings_views._render_settings", AsyncMock()):
                await maintenance_toggle(call, bot, u_repo, async_session)

        assert await cache.get("store_settings") is None
        assert await cache.get("tma:user:555:dashboard:default") is None
    finally:
        if admin_id in get_settings().ADMIN_IDS:
            get_settings().ADMIN_IDS.remove(admin_id)

    admin_js = Path("bot/web/static/js/admin_settings.js").read_text(encoding="utf-8")
    assert "settingCustomPlanPricePerGb')?.value || '4500'" in admin_js
    assert "settingCustomPlanPricePerDay')?.value || '1000'" in admin_js
    assert "settingCustomPlanBasePrice')?.value || '100000'" in admin_js
