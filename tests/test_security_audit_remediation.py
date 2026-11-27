"""Regression tests verifying Critical & High security and logic fixes."""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pyzipper

from bot.db.models import Coupon, GiftCard, Order, Service, User, Wallet
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.user_repo import UserRepository
from bot.handlers.start import cmd_start
from bot.services.backup import create_encrypted_backup_archive
from bot.services.node_monitor import _NODE_STATES, check_nodes_health_once
from bot.services.purchases import execute_purchase
from bot.services.reconcile import run_reconcile
from bot.services.wheel_service import execute_lucky_wheel_spin, get_wheel_status
from bot.web.cache import FastCache


async def _seed_wallet_user(session, tid: int, balance: int = 0, username: str | None = None, **kwargs):
    user = User(telegram_id=tid, username=username or f"u_{tid}", full_name=f"User {tid}", **kwargs)
    session.add(user)
    session.add(Wallet(telegram_id=tid, balance=balance))
    await session.flush()
    return user


# ---------------------------------------------------------------------- #
# 1. Lucky Wheel Ticket + "again" Cooldown Bypass Guard
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_wheel_ticket_again_does_not_clear_daily_cooldown(session_factory):
    now = datetime.now(timezone.utc)
    future_iso = (now + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with session_factory() as session:
        await _seed_wallet_user(
            session,
            31001,
            spin_tickets=1,
            wheel_streak=1,
            wheel_last_spin_at=now - timedelta(hours=1),
        )
        await session.commit()

    cache = FastCache(redis_client=None)
    remnawave = AsyncMock()
    remnawave.get_users_by_telegram_id = AsyncMock(
        return_value=[{"id": 9101, "status": "ACTIVE", "expireAt": future_iso, "trafficLimitBytes": 10 * (1024**3)}]
    )

    again_prize = {"id": "again", "name": "دوباره", "icon": "🔄", "type": "again", "value": 0}
    store_open = SimpleNamespace(join_gate_enabled=False, join_gate_channel="")

    async with session_factory() as session:
        with (
            patch("bot.services.wheel_service.get_store_settings", AsyncMock(return_value=store_open)),
            patch("bot.services.wheel_service.random.choices", return_value=[again_prize]),
        ):
            res_ticket = await execute_lucky_wheel_spin(session, remnawave, cache, None, 31001, use_ticket=True)

        assert res_ticket["ok"] is True
        assert res_ticket["used_ticket"] is False
        assert res_ticket["spin_tickets"] == 1
        assert await cache.get("wheel:has_free_retry:31001") is None

        status = await get_wheel_status(session, cache, 31001)
        assert status["is_cooldown"] is True
        assert status["remaining_seconds"] > 0

        # Trying a daily free spin right after ticket-"again" MUST stay blocked on cooldown
        with patch("bot.services.wheel_service.get_store_settings", AsyncMock(return_value=store_open)):
            res_free = await execute_lucky_wheel_spin(session, remnawave, cache, None, 31001, use_ticket=False)
        assert res_free["ok"] is False
        assert res_free["code"] == "cooldown"

    # By contrast, a genuine daily (non-ticket) "again" still grants a 1-time free retry
    async with session_factory() as session:
        await _seed_wallet_user(session, 31002, spin_tickets=0, wheel_streak=1, wheel_last_spin_at=None)
        await session.commit()

    async with session_factory() as session:
        with (
            patch("bot.services.wheel_service.get_store_settings", AsyncMock(return_value=store_open)),
            patch("bot.services.wheel_service.random.choices", return_value=[again_prize]),
        ):
            res_daily = await execute_lucky_wheel_spin(session, remnawave, cache, None, 31002, use_ticket=False)
        assert res_daily["ok"] is True
        assert await cache.get("wheel:has_free_retry:31002") == 1


# ---------------------------------------------------------------------- #
# 2. Invite-Only Bypass via Other User's DIRECT Gift Card Blocked
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_invite_only_rejects_foreign_direct_gift_without_persisting_user(session_factory):
    store_inv = SimpleNamespace(access_mode="invite_only", maintenance_mode=False, support_contact="")
    async with session_factory() as session:
        await _seed_wallet_user(session, 41001, username="sender")
        session.add(
            GiftCard(
                code="GIFT-DIRECT99",
                sender_telegram_id=41001,
                sender_name="Sender",
                receiver_telegram_id=41002,
                receiver_username="real_target",
                delivery_type="DIRECT",
                gift_type="BALANCE",
                amount=25_000,
                is_claimed=False,
            )
        )
        session.add(
            GiftCard(
                code="GIFT-PUBLIC88",
                sender_telegram_id=41001,
                sender_name="Sender",
                delivery_type="LINK",
                gift_type="BALANCE",
                amount=15_000,
                is_claimed=False,
            )
        )
        await session.commit()

        # Stranger using DIRECT gift addressed to someone else MUST be blocked before User creation
        msg_attacker = AsyncMock()
        msg_attacker.from_user = SimpleNamespace(id=41999, username="attacker", full_name="Attacker")
        msg_attacker.text = "/start gift_GIFT-DIRECT99"
        msg_attacker.answer = AsyncMock()

        with (
            patch("bot.handlers.start.is_maintenance", AsyncMock(return_value=False)),
            patch("bot.handlers.start.get_store_settings", AsyncMock(return_value=store_inv)),
        ):
            await cmd_start(msg_attacker, AsyncMock(), UserRepository(session), session, AsyncMock())

        assert await UserRepository(session).get_by_telegram_id(41999) is None
        msg_attacker.answer.assert_awaited_once()

        # Legitimate LINK gift recipient CAN onboard under invite_only
        msg_link = AsyncMock()
        msg_link.from_user = SimpleNamespace(id=41003, username="link_friend", full_name="Link Friend")
        msg_link.text = "/start gift_GIFT-PUBLIC88"
        msg_link.answer = AsyncMock()
        remnawave = AsyncMock()
        remnawave.get_users_by_telegram_id = AsyncMock(return_value=[])
        bot_mock = MagicMock()
        bot_mock.session_factory = session_factory
        bot_mock.cache = FastCache(redis_client=None)

        with (
            patch("bot.handlers.start.is_maintenance", AsyncMock(return_value=False)),
            patch("bot.handlers.start.get_store_settings", AsyncMock(return_value=store_inv)),
            patch("bot.handlers.start.reset_menu", AsyncMock()),
            patch("bot.handlers.start.render_menu", AsyncMock()),
        ):
            await cmd_start(msg_link, bot_mock, UserRepository(session), session, AsyncMock(), remnawave=remnawave)

        assert await UserRepository(session).get_by_telegram_id(41003) is not None


# ---------------------------------------------------------------------- #
# 3. Voucher Redeem IntegrityError Savepoint + Capacity Rollback
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_redeem_credit_voucher_savepoint_and_purchase_capacity_cleanup(session_factory):
    now = datetime.now(timezone.utc)
    past_iso = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future_iso = (now + timedelta(days=15)).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with session_factory() as session:
        await _seed_wallet_user(session, 51001, balance=100_000)
        c_repo = CouponRepository(session)
        v = await c_repo.create("RACEVCH", discount_amount=10_000, max_uses=5, kind="voucher")
        v_id = v.id
        ok1, _, _ = await c_repo.redeem_credit_voucher("RACEVCH", 51001)
        assert ok1 is True
        await session.commit()

        # Force duplicate insert race (mock has_user_used -> False so INSERT hits unique constraint)
        with patch.object(c_repo, "has_user_used", AsyncMock(return_value=False)):
            ok2, amt2, _ = await c_repo.redeem_credit_voucher("RACEVCH", 51001)
        assert ok2 is False and amt2 == 0

        # Session must remain healthy for further queries & used_count must NOT be inflated
        refreshed_v = await session.get(Coupon, v_id, populate_existing=True)
        assert refreshed_v.used_count == 1
        assert refreshed_v.is_active is True

        # Purchase capacity leak check on needs_active_sub and panel failure
        svc = Service(
            name="Limited Addon",
            price=10_000,
            duration_days=0,
            traffic_gb=5,
            badge="traffic",
            max_purchases=1,
            purchases_count=0,
            is_active=True,
        )
        disc = await c_repo.create("CAP20", discount_percent=20, max_uses=2, kind="discount")
        session.add(svc)
        await session.flush()
        svc_id = svc.id
        disc_id = disc.id
        await session.commit()

        rem_exp = AsyncMock()
        expired_acc = {"id": 601, "username": "u_exp", "status": "EXPIRED", "expireAt": past_iso, "trafficLimitBytes": 10 * (1024**3)}
        res1 = await execute_purchase(
            rem_exp,
            session,
            svc,
            51001,
            chosen_account=expired_acc,
            coupon_code="CAP20",
            discount_amount=2_000,
        )
        assert res1.ok is False and res1.kind == "needs_active_sub"

        svc_after_1 = await session.get(Service, svc_id, populate_existing=True)
        disc_after_1 = await session.get(Coupon, disc_id, populate_existing=True)
        assert svc_after_1.purchases_count == 0
        assert svc_after_1.is_active is True
        assert disc_after_1.used_count == 0

        # Panel failure after reserving slot + switching squads must also release service capacity
        rem_fail = AsyncMock()
        rem_fail.set_user_squads = AsyncMock(return_value={"ok": True})
        rem_fail.update_user_subscription = AsyncMock(return_value=None)
        active_acc = {"id": 602, "username": "u_ok", "status": "ACTIVE", "expireAt": future_iso, "trafficLimitBytes": 10 * (1024**3)}
        res2 = await execute_purchase(
            rem_fail,
            session,
            svc_after_1,
            51001,
            chosen_account=active_acc,
            coupon_code="CAP20",
            discount_amount=2_000,
        )
        assert res2.ok is False and res2.kind == "failed"

        svc_after_2 = await session.get(Service, svc_id, populate_existing=True)
        disc_after_2 = await session.get(Coupon, disc_id, populate_existing=True)
        assert svc_after_2.purchases_count == 0
        assert svc_after_2.is_active is True
        assert disc_after_2.used_count == 0


# ---------------------------------------------------------------------- #
# 4. Encrypted Backup Uses AES-256 Only (No CLI `zip -P`)
# ---------------------------------------------------------------------- #
def test_backup_always_uses_pyzipper_aes256_never_cli_zip(tmp_path):
    dump_file = tmp_path / "sample_backup.json"
    dump_file.write_text('{"ok": true}', encoding="utf-8")

    with (
        patch("shutil.which", return_value="/usr/bin/zip"),
        patch.object(subprocess, "run", side_effect=AssertionError("CLI zip -P must never be invoked")),
    ):
        zip_path = create_encrypted_backup_archive(dump_file, password="TopSecretBackupPassword!")

    assert zip_path is not None and zip_path.is_file()
    assert not dump_file.exists()

    with pyzipper.AESZipFile(zip_path, "r") as zf:
        zf.setpassword(b"TopSecretBackupPassword!")
        assert zf.read("sample_backup.json") == b'{"ok": true}'

    with pytest.raises(RuntimeError):
        with pyzipper.AESZipFile(zip_path, "r") as zf:
            zf.setpassword(b"WrongPassword")
            zf.read("sample_backup.json")


# ---------------------------------------------------------------------- #
# 5. Reconcile Multi-Order Limit(1) & Node Monitor HTML Escaping
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_reconcile_and_node_monitor_safety(session_factory):
    now = datetime.now(timezone.utc)
    claimed_at = now - timedelta(minutes=30)

    async with session_factory() as session:
        await _seed_wallet_user(session, 61001, username="sender_r")
        await _seed_wallet_user(session, 61002, username="recv_r")
        svc = Service(name="Rec Svc", price=10_000, duration_days=30, traffic_gb=10)
        session.add(svc)
        await session.flush()

        session.add(
            GiftCard(
                code="GIFT-REC1",
                sender_telegram_id=61001,
                receiver_telegram_id=61002,
                delivery_type="DIRECT",
                gift_type="SERVICE",
                service_id=svc.id,
                is_claimed=True,
                claimed_at=claimed_at,
            )
        )
        # Two paid orders in the window must not raise MultipleResultsFound
        for _ in range(2):
            session.add(
                Order(
                    telegram_id=61002,
                    service_id=svc.id,
                    service_name=svc.name,
                    amount=10_000,
                    duration_days=30,
                    traffic_gb=10,
                    status="paid",
                    created_at=claimed_at,
                )
            )
        await session.commit()

    closed = await run_reconcile(AsyncMock(), session_factory)
    assert closed == 0

    _NODE_STATES.clear()
    mock_remna = AsyncMock()
    mock_remna.get_nodes = AsyncMock(
        return_value=[{"id": "n-xss", "name": "Bad<Node>", "address": "1.2.3.4<script>", "isConnected": False}]
    )
    sent_texts: list[str] = []

    async def _capture_notify(bot, text, session_factory=None):
        sent_texts.append(text)
        return True

    with patch("bot.services.node_monitor._notify_admins", side_effect=_capture_notify):
        await check_nodes_health_once(AsyncMock(), mock_remna, session_factory=session_factory)

    assert len(sent_texts) == 1
    assert "Bad&lt;Node&gt;" in sent_texts[0]
    assert "1.2.3.4&lt;script&gt;" in sent_texts[0]


# ---------------------------------------------------------------------- #
# 6. Frontend XSS / CSP / TMA Modal Stack Guards
# ---------------------------------------------------------------------- #
def test_frontend_security_csp_and_xss_guards():
    server_py = Path("bot/web/server.py").read_text(encoding="utf-8")
    assert "https://ipwho.is" in server_py
    assert "https://speed.cloudflare.com" in server_py

    js_dir = Path("bot/web/static/js")
    for js_file in sorted(js_dir.glob("*.js")):
        if js_file.name.endswith(".min.js"):
            continue
        lines = js_file.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, 1):
            if "window.open(" in line:
                assert "noopener" in line, f"{js_file.name}:{lineno} missing noopener on window.open"
            onclick_vals = re.findall(r'onclick="([^"]*)"', line)
            for onclick_val in onclick_vals:
                assert not re.search(
                    r"escapeHtml\(|'\$\{[^}]*(?:uuid|username|address|provider|remark|tag|token|photo|url)",
                    onclick_val,
                    re.IGNORECASE,
                ), f"{js_file.name}:{lineno} uses unguarded JS template inside onclick attribute"

    wheel_js = (js_dir / "wheel.js").read_text(encoding="utf-8")
    assert "allowHtml = false" in wheel_js
    assert "noopener noreferrer" in wheel_js
    assert "bodyEl.textContent" in wheel_js

    shop_js = (js_dir / "shop.js").read_text(encoding="utf-8")
    assert "allowHtml = false" in shop_js
    assert "escapeHtml(formatPlanTitle(planObj.name" in shop_js

    admin_js = (js_dir / "admin.js").read_text(encoding="utf-8")
    assert "esc(item.label" in admin_js and "esc(item.value" in admin_js
    assert "getTopOpenModal" in admin_js

    app_js = (js_dir / "app.js").read_text(encoding="utf-8")
    assert "'walletCurrencyModal'" in app_js
    assert "getTopOpenModal(APP_MODAL_IDS)" in app_js

    utils_js = (js_dir / "utils.js").read_text(encoding="utf-8")
    assert "openExternalUrl" in utils_js
    assert "delegateClick" in utils_js
    assert "topModal.id === 'revokeModal'" in utils_js
