"""Regression tests for PostgreSQL support chat history, affiliate wallet cashback,
1-click expiry renewal, smart OS installer routing, and multi-stage Docker build.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import make_mocked_request
from sqlalchemy import delete, select


@pytest.mark.anyio
async def test_support_chat_postgres_persistence_and_cold_cache_fallback(session_factory):
    from bot.db.models import SupportChatMessage
    from bot.services.support_chat import (
        append_support_message,
        get_active_thread_ids,
        get_support_messages,
    )
    from bot.web.cache import FastCache

    warm_cache = FastCache(redis_client=None)
    tid = 90011

    msg1 = await append_support_message(
        tid,
        sender="user",
        text="سلام مشکل اتصال دارم",
        msg_id="u_1",
        cache=warm_cache,
        session_factory=session_factory,
    )
    msg2 = await append_support_message(
        tid,
        sender="admin",
        text="لطفاً لینک جدید را آپدیت کنید",
        msg_id="a_2",
        cache=warm_cache,
        session_factory=session_factory,
    )
    assert msg1["text"] == "سلام مشکل اتصال دارم"
    assert msg2["sender"] == "admin"

    async with session_factory() as session:
        db_rows = (
            await session.execute(
                select(SupportChatMessage)
                .where(SupportChatMessage.telegram_id == tid)
                .order_by(SupportChatMessage.id.asc())
            )
        ).scalars().all()
        assert [r.external_msg_id for r in db_rows] == ["u_1", "a_2"]

        # Simulate cold Redis after container restart
        cold_cache = FastCache(redis_client=None)
        loaded_msgs = await get_support_messages(tid, cache=cold_cache, session=session)
        loaded_threads = await get_active_thread_ids(cache=cold_cache, session=session)

        assert [m["text"] for m in loaded_msgs] == [
            "سلام مشکل اتصال دارم",
            "لطفاً لینک جدید را آپدیت کنید",
        ]
        assert tid in loaded_threads
        # Confirm cold cache was warmed cleanly from PostgreSQL
        assert len(await cold_cache.get(f"support:chat:{tid}") or []) == 2


@pytest.mark.anyio
async def test_support_chat_backup_roundtrip_and_alembic_0002(session_factory, tmp_path):
    import sqlite3

    from alembic.config import Config

    from alembic import command
    from bot.db.models import SupportChatMessage
    from bot.services.backup import create_database_backup, restore_database_backup

    tid = 90022
    async with session_factory() as session:
        session.add(
            SupportChatMessage(
                telegram_id=tid,
                external_msg_id="bak_1",
                sender="user",
                text="پیام تستی بکاپ",
            )
        )
        await session.commit()

        bak_path = await create_database_backup(session, out_dir=tmp_path)
        payload = json.loads(Path(bak_path).read_text(encoding="utf-8"))
        assert any(m["external_msg_id"] == "bak_1" for m in payload["support_chat_messages"])

        await session.execute(delete(SupportChatMessage).where(SupportChatMessage.telegram_id == tid))
        await session.commit()

        stats = await restore_database_backup(session, bak_path)
        assert stats["support_chat_messages"] >= 1
        restored = (
            await session.execute(
                select(SupportChatMessage).where(SupportChatMessage.telegram_id == tid)
            )
        ).scalars().all()
        assert len(restored) == 1
        assert restored[0].text == "پیام تستی بکاپ"

    # Verify Alembic 0002 upgrade & downgrade cleanly manage support_chat_messages
    db_file = tmp_path / "alembic_support.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{str(db_file).replace(chr(92), '/')}")
    await asyncio.to_thread(command.upgrade, cfg, "head")

    con = sqlite3.connect(db_file)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        con.close()
    assert "support_chat_messages" in tables

    await asyncio.to_thread(command.downgrade, cfg, "0001_baseline")
    con = sqlite3.connect(db_file)
    try:
        tables_after_down = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        con.close()
    assert "support_chat_messages" not in tables_after_down

    await asyncio.to_thread(command.upgrade, cfg, "head")


@pytest.mark.anyio
async def test_affiliate_commission_first_purchase_and_renewal_toggle(session_factory):
    from bot.db.models import User, Wallet
    from bot.services.purchases import maybe_reward_referrer
    from bot.web.cache import FastCache

    async with session_factory() as session:
        inviter = User(telegram_id=91001, username="inviter", language="fa", spin_tickets=0)
        referee = User(telegram_id=91002, username="referee", language="fa", referred_by_id=91001)
        session.add_all([inviter, referee, Wallet(telegram_id=91001, balance=0)])
        await session.commit()

        bot = MagicMock()
        bot.send_message = AsyncMock()
        remnawave = MagicMock()
        remnawave.get_users_by_telegram_id = AsyncMock(return_value=[])
        cache = FastCache(redis_client=None)

        store_first = SimpleNamespace(
            referral_enabled=True,
            referral_reward_gb=5,
            referral_commission_percent=10,
            referral_renew_commission_enabled=False,
        )
        with patch("bot.services.purchases.get_store_settings", AsyncMock(return_value=store_first)):
            await maybe_reward_referrer(bot, session, remnawave, referee, paid_amount=100_000, cache=cache)

        w = (await session.execute(select(Wallet).where(Wallet.telegram_id == 91001))).scalar_one()
        await session.refresh(w)
        assert w.balance == 10_000
        bot.send_message.assert_awaited()

        # Repeat purchase when renewal commission disabled -> zero extra commission
        bot.send_message.reset_mock()
        with patch("bot.services.purchases.get_store_settings", AsyncMock(return_value=store_first)):
            await maybe_reward_referrer(bot, session, remnawave, referee, paid_amount=100_000, cache=cache)
        await session.refresh(w)
        assert w.balance == 10_000

        # Enable renewal commission -> inviter receives 10% on renewal purchase too
        store_renew = SimpleNamespace(
            referral_enabled=True,
            referral_reward_gb=5,
            referral_commission_percent=10,
            referral_renew_commission_enabled=True,
        )
        with patch("bot.services.purchases.get_store_settings", AsyncMock(return_value=store_renew)):
            await maybe_reward_referrer(bot, session, remnawave, referee, paid_amount=200_000, cache=cache)
        await session.refresh(w)
        assert w.balance == 30_000


@pytest.mark.anyio
async def test_admin_settings_affiliate_clamping_and_roundtrip(session_factory):
    from bot.web.admin_settings_api import get_admin_settings, post_admin_settings

    app = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
    }

    req_high = make_mocked_request("POST", "/api/admin/settings?user_id=99999", app=app)
    req_high.json = AsyncMock(return_value={
        "referral_commission_percent": 99,
        "referral_renew_commission_enabled": True,
    })
    resp_high = await post_admin_settings(req_high)
    assert resp_high.status == 200

    req_get = make_mocked_request("GET", "/api/admin/settings?user_id=99999", app=app)
    data_high = json.loads((await get_admin_settings(req_get)).text)
    assert data_high["settings"]["referral_commission_percent"] == 50
    assert data_high["settings"]["referral_renew_commission_enabled"] is True

    req_neg = make_mocked_request("POST", "/api/admin/settings?user_id=99999", app=app)
    req_neg.json = AsyncMock(return_value={"referral_commission_percent": -12})
    assert (await post_admin_settings(req_neg)).status == 200
    data_neg = json.loads((await get_admin_settings(make_mocked_request("GET", "/api/admin/settings?user_id=99999", app=app))).text)
    assert data_neg["settings"]["referral_commission_percent"] == 0


@pytest.mark.anyio
async def test_one_click_expiry_renewal_handler_and_fallback(session_factory):
    from bot.db.models import Order, OrderStatus, Service, User, Wallet
    from bot.db.repositories.user_repo import UserRepository
    from bot.handlers.shop_renew import quick_renew_account
    from bot.services.expiry import _renew_keyboard

    kb = _renew_keyboard("fa", 42)
    flat_cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert flat_cbs[:2] == ["renquick:42", "svc:renacc:42"]

    async with session_factory() as session:
        user = User(telegram_id=92001, username="renewer", language="fa")
        svc = Service(name="VIP 50GB", price=120_000, duration_days=30, traffic_gb=50, is_active=True)
        session.add_all([user, svc, Wallet(telegram_id=92001, balance=250_000)])
        await session.flush()
        session.add(
            Order(
                telegram_id=92001,
                service_id=svc.id,
                service_name=svc.name,
                amount=svc.price,
                duration_days=30,
                traffic_gb=50,
                panel_user_id=42,
                panel_username="acc_42",
                status=OrderStatus.PAID.value,
            )
        )
        await session.commit()
        svc_id = svc.id

        bot = MagicMock()
        user_repo = UserRepository(session)
        remnawave = MagicMock()
        remnawave.get_users_by_telegram_id = AsyncMock(return_value=[
            {"id": 42, "username": "acc_42"},
            {"id": 99, "username": "acc_trial"},
        ])
        call = MagicMock()
        call.from_user = SimpleNamespace(id=92001, username="renewer")
        call.answer = AsyncMock()
        call.data = "renquick:42"

        with (
            patch("bot.handlers.shop_renew._ensure_can_buy", AsyncMock(return_value=True)),
            patch("bot.handlers.shop_renew.is_maintenance", AsyncMock(return_value=False)),
            patch("bot.handlers.shop_renew._render_buy_confirm", AsyncMock()) as mock_confirm,
            patch("bot.handlers.shop_renew.render_services", AsyncMock()) as mock_services,
        ):
            await quick_renew_account(call, bot, user_repo, session, remnawave)
            mock_confirm.assert_awaited_once()
            assert mock_confirm.await_args.kwargs["confirm_callback"] == f"svc:confirma:{svc_id}:42"
            assert mock_confirm.await_args.kwargs["target_id"] == "42"
            mock_services.assert_not_awaited()

            # Account 99 without paid order falls back to plan selection
            mock_confirm.reset_mock()
            call.data = "renquick:99"
            await quick_renew_account(call, bot, user_repo, session, remnawave)
            mock_confirm.assert_not_awaited()
            mock_services.assert_awaited_once()
            assert mock_services.await_args.kwargs["renew_account_id"] == "99"


@pytest.mark.anyio
async def test_smart_open_client_os_detection_receipt_button_and_dockerfile(session_factory):
    from bot.db.models import Service, User
    from bot.db.repositories.user_repo import UserRepository
    from bot.handlers.shop_purchase_views import _render_purchase_result
    from bot.services.purchases import PurchaseResult
    from bot.web.server import serve_open_client

    sub = "https://sub.example.com/u/abc123"
    ios_req = make_mocked_request(
        "GET", f"/open-client?url={sub}",
        headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"},
    )
    android_req = make_mocked_request(
        "GET", f"/open-client?url={sub}",
        headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8)"},
    )
    win_req = make_mocked_request(
        "GET", f"/open-client?url={sub}",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    bad_req = make_mocked_request("GET", "/open-client?scheme=javascript:alert(1)")

    assert "streisand://import/" in (await serve_open_client(ios_req)).text
    assert "v2rayng://install-config?url=" in (await serve_open_client(android_req)).text
    assert "hiddify://install-config?url=" in (await serve_open_client(win_req)).text
    assert (await serve_open_client(bad_req)).status == 400

    async with session_factory() as session:
        user = User(telegram_id=93001, username="smartbtn", language="fa")
        session.add(user)
        await session.commit()
        user_repo = UserRepository(session)
        svc = Service(name="Pro 1M", price=90_000, duration_days=30, traffic_gb=50)
        res = PurchaseResult(
            ok=True,
            kind="success",
            subscription_url=sub,
            new_balance=10_000,
            panel_user_id=77,
            panel_username="u77",
        )
        fake_settings = SimpleNamespace(TIMEZONE="Asia/Tehran", WEB_APP_URL="https://mini.example.com")
        with (
            patch("bot.handlers.shop_purchase_views.get_settings", return_value=fake_settings),
            patch("bot.handlers.shop_purchase_views.resolve_squad_name", AsyncMock(return_value="Main")),
            patch("bot.handlers.shop_purchase_views.render_menu", AsyncMock()) as mock_menu,
        ):
            await _render_purchase_result(MagicMock(), user, user_repo, session, res, svc, "fa")
            markup = mock_menu.await_args.args[4]
            urls = [btn.url for row in markup.inline_keyboard for btn in row if getattr(btn, "url", None)]
            assert any(u.startswith("https://mini.example.com/open-client?url=") for u in urls)

    dockerfile_txt = Path("Dockerfile").read_text(encoding="utf-8")
    assert "AS assets" in dockerfile_txt
    assert "tailwind.config.js" in dockerfile_txt
    assert "npm run build:css && npm run build:js" in dockerfile_txt
    assert "COPY --from=assets" in dockerfile_txt
    assert "python -m bot.db.migrate" in dockerfile_txt


@pytest.mark.anyio
async def test_ensure_schema_migrated_fresh_and_legacy_db(tmp_path):
    import sqlite3

    from alembic.config import Config

    from alembic import command
    from bot.db.migrate import ensure_schema_migrated

    # 1. Fresh empty DB upgrades directly to head
    fresh_db = tmp_path / "fresh_mig.db"
    fresh_url = f"sqlite+aiosqlite:///{str(fresh_db).replace(chr(92), '/')}"
    res_fresh = await ensure_schema_migrated(fresh_url)
    assert res_fresh == "upgraded"

    con = sqlite3.connect(fresh_db)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        con.close()
    assert {"users", "support_chat_messages", "alembic_version"} <= tables

    # 2. Pre-Alembic legacy DB (created at 0001 tables, but missing alembic_version) auto-stamps baseline then upgrades
    legacy_db = tmp_path / "legacy_mig.db"
    legacy_url = f"sqlite+aiosqlite:///{str(legacy_db).replace(chr(92), '/')}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", legacy_url)
    await asyncio.to_thread(command.upgrade, cfg, "0001_baseline")

    con = sqlite3.connect(legacy_db)
    try:
        con.execute("DROP TABLE alembic_version")
        con.commit()
    finally:
        con.close()

    res_legacy = await ensure_schema_migrated(legacy_url)
    assert res_legacy == "stamped_and_upgraded"

    con = sqlite3.connect(legacy_db)
    try:
        tables_legacy = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        rev = con.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        con.close()
    assert "support_chat_messages" in tables_legacy
    assert rev == ("0003_referral_commission_total",)
    con_cols = sqlite3.connect(legacy_db)
    try:
        ref_cols_legacy = {r[1] for r in con_cols.execute("PRAGMA table_info(referral_rewards)").fetchall()}
    finally:
        con_cols.close()
    assert "commission_toman" in ref_cols_legacy

    # 3. Existing DB created via create_all (has BOTH users and support_chat_messages, no alembic_version) must NOT crash
    pre_existing_db = tmp_path / "pre_existing_all.db"
    pre_existing_url = f"sqlite+aiosqlite:///{str(pre_existing_db).replace(chr(92), '/')}"
    from sqlalchemy.ext.asyncio import create_async_engine

    from bot.db.base import init_db

    eng = create_async_engine(pre_existing_url)
    await init_db(eng)
    await eng.dispose()

    res_existing = await ensure_schema_migrated(pre_existing_url)
    assert res_existing == "stamped_head"
    con = sqlite3.connect(pre_existing_db)
    try:
        rev_existing = con.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        con.close()
    assert rev_existing == ("0003_referral_commission_total",)


@pytest.mark.anyio
async def test_affiliate_commission_records_marker_when_reward_gb_zero(session_factory):
    """When referral_reward_gb == 0 and commission > 0, first purchase records a 0 GB marker so renewals don't double-pay."""
    from bot.db.models import User, Wallet
    from bot.db.repositories.referral_repo import ReferralRepository
    from bot.services.purchases import maybe_reward_referrer
    from bot.web.cache import FastCache

    async with session_factory() as session:
        inviter = User(telegram_id=92001, username="inviter_zero", language="fa", spin_tickets=0)
        referee = User(telegram_id=92002, username="referee_zero", language="fa", referred_by_id=92001)
        session.add_all([inviter, referee, Wallet(telegram_id=92001, balance=0)])
        await session.commit()

        bot = MagicMock()
        bot.send_message = AsyncMock()
        remnawave = MagicMock()
        remnawave.get_users_by_telegram_id = AsyncMock(return_value=[])
        cache = FastCache(redis_client=None)

        store_zero_gb = SimpleNamespace(
            referral_enabled=True,
            referral_reward_gb=0,
            referral_commission_percent=10,
            referral_renew_commission_enabled=False,
        )
        with patch("bot.services.purchases.get_store_settings", AsyncMock(return_value=store_zero_gb)):
            await maybe_reward_referrer(bot, session, remnawave, referee, paid_amount=100_000, cache=cache)

        w = (await session.execute(select(Wallet).where(Wallet.telegram_id == 92001))).scalar_one()
        await session.refresh(w)
        assert w.balance == 10_000

        ref_repo = ReferralRepository(session)
        assert await ref_repo.has_rewarded(92002) is True
        assert await ref_repo.get_total_commission_earned(92001) == 10_000

        # Second purchase with renew commission disabled must NOT pay again
        with patch("bot.services.purchases.get_store_settings", AsyncMock(return_value=store_zero_gb)):
            await maybe_reward_referrer(bot, session, remnawave, referee, paid_amount=100_000, cache=cache)
        await session.refresh(w)
        assert w.balance == 10_000
        assert await ref_repo.get_total_commission_earned(92001) == 10_000

        # With renewal commission enabled, second purchase credits another commission onto ReferralReward
        store_zero_gb_renew = SimpleNamespace(
            referral_enabled=True,
            referral_reward_gb=0,
            referral_commission_percent=10,
            referral_renew_commission_enabled=True,
        )
        with patch("bot.services.purchases.get_store_settings", AsyncMock(return_value=store_zero_gb_renew)):
            await maybe_reward_referrer(bot, session, remnawave, referee, paid_amount=200_000, cache=cache)
        await session.refresh(w)
        assert w.balance == 30_000
        assert await ref_repo.get_total_commission_earned(92001) == 30_000


@pytest.mark.anyio
async def test_referral_entry_shows_cash_commission_details(session_factory):
    """Bot menu:referral handler includes percentage cash commission, earned total & respects trial_enabled."""
    from urllib.parse import unquote_plus

    from bot.db.models import User
    from bot.db.repositories.app_setting_repo import AppSettingRepository
    from bot.db.repositories.referral_repo import ReferralRepository
    from bot.db.repositories.user_repo import UserRepository
    from bot.handlers.referral import referral_entry

    async with session_factory() as session:
        session.add(User(telegram_id=93001, username="bot_inviter", language="fa"))
        srepo = AppSettingRepository(session)
        await srepo.set("referral_enabled", "1")
        await srepo.set("referral_reward_gb", "5")
        await srepo.set("referral_commission_percent", "12")
        await srepo.set("referral_renew_commission_enabled", "1")
        await srepo.set("trial_enabled", "0")
        await ReferralRepository(session).record_reward(93001, 93002, reward_gb=5, commission_toman=24000)
        await session.commit()

        user_repo = UserRepository(session)
        bot = MagicMock()
        bot.get_me = AsyncMock(return_value=SimpleNamespace(username="TestVpnBot"))
        bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=501))

        call = MagicMock()
        call.from_user = SimpleNamespace(id=93001, username="bot_inviter")
        call.answer = AsyncMock()
        call.message = MagicMock()

        await referral_entry(call, bot, user_repo, session)

        bot.send_message.assert_awaited_once()
        rendered_text = bot.send_message.await_args.kwargs["text"]
        assert "12%" in rendered_text
        assert "5" in rendered_text
        assert "تمدید" in rendered_text
        assert "24,000" in rendered_text
        markup = bot.send_message.await_args.kwargs["reply_markup"]
        share_url = unquote_plus(markup.inline_keyboard[0][0].url)
        assert "اکانت تست رایگان" not in share_url

