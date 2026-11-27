"""Regression tests verifying Critical & High security and logic fixes."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pyzipper
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

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


# ---------------------------------------------------------------------- #
# 7. Medium Severity: Multi-Account Targeting, auto_renew, Expiring Fallback
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_multi_account_endpoints_auto_renew_and_expiring_fallback(session_factory):
    from bot.services.auto_renew import process_auto_renewals
    from bot.web.admin_users_actions import (
        post_admin_kill_sessions,
        post_admin_modify_user,
        post_admin_user_revoke_sub,
    )
    from bot.web.admin_users_detail import post_admin_user_delete_hwid
    from bot.web.admin_users_list import get_admin_users
    from bot.web.user_shop import post_user_kill_device

    now = datetime.now(timezone.utc)
    past_iso = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. User kill_device selects explicit account_id instead of always panel_users[0]
    remna_user = AsyncMock()
    remna_user.get_users_by_telegram_id = AsyncMock(
        return_value=[{"id": 101, "uuid": "u-101"}, {"id": 202, "uuid": "u-202"}]
    )
    remna_user.delete_hwid_device = AsyncMock(return_value=True)
    app_user = {
        "bot_token": "123:abc",
        "admin_ids": [],
        "is_dev": True,
        "session_factory": session_factory,
        "remnawave": remna_user,
        "cache": FastCache(redis_client=None),
    }

    req_kd = make_mocked_request("POST", "/api/user/kill_device?user_id=61001", app=app_user)
    req_kd.json = AsyncMock(return_value={"hwid": "hw-2", "account_id": "202"})
    resp_kd = await post_user_kill_device(req_kd)
    assert resp_kd.status == 200
    remna_user.delete_hwid_device.assert_awaited_once_with(202, "hw-2")

    req_kd_bad = make_mocked_request("POST", "/api/user/kill_device?user_id=61001", app=app_user)
    req_kd_bad.json = AsyncMock(return_value={"hwid": "hw-2", "account_id": "999"})
    assert (await post_user_kill_device(req_kd_bad)).status == 404

    # 2. Admin endpoints respect explicit panel_user_id & kill_sessions targets all non-DELETED when omitted
    remna_adm = AsyncMock()
    remna_adm.get_users_by_telegram_id = AsyncMock(
        return_value=[
            {"id": 101, "uuid": "u-101", "status": "ACTIVE", "trafficLimitBytes": 10 * 1024**3, "expireAt": past_iso},
            {"id": 202, "uuid": "u-202", "status": "ACTIVE", "trafficLimitBytes": 10 * 1024**3, "expireAt": past_iso},
        ]
    )
    remna_adm.update_user_subscription = AsyncMock(return_value={"ok": True})
    remna_adm.revoke_user_subscription = AsyncMock(return_value={"subscriptionUrl": "https://sub/new"})
    remna_adm.get_user_hwid_devices = AsyncMock(side_effect=[[{"hwid": "hw-a"}], [{"hwid": "hw-b"}]])
    remna_adm.delete_hwid_device = AsyncMock(return_value=True)
    app_adm = {
        "bot_token": "123:abc",
        "admin_ids": [99999],
        "is_dev": True,
        "session_factory": session_factory,
        "remnawave": remna_adm,
        "cache": FastCache(redis_client=None),
    }

    with patch("bot.web.admin_users_actions._check_admin", return_value={"id": 99999}):
        req_mod = make_mocked_request("POST", "/api/admin/user/modify", app=app_adm)
        req_mod.json = AsyncMock(return_value={"telegram_id": 61001, "panel_user_id": 202, "days": 5})
        assert (await post_admin_modify_user(req_mod)).status == 200
        assert remna_adm.update_user_subscription.await_args.args[0] == 202

        req_rev = make_mocked_request("POST", "/api/admin/user/revoke_sub", app=app_adm)
        req_rev.json = AsyncMock(return_value={"telegram_id": 61001, "panel_user_id": "202"})
        assert (await post_admin_user_revoke_sub(req_rev)).status == 200
        remna_adm.revoke_user_subscription.assert_awaited_once_with(202, user_uuid="u-202")

        req_kill = make_mocked_request("POST", "/api/admin/user/kill_sessions", app=app_adm)
        req_kill.json = AsyncMock(return_value={"telegram_id": 61001})
        resp_kill = await post_admin_kill_sessions(req_kill)
        assert json.loads(resp_kill.text)["killed_devices"] == 2
        remna_adm.delete_hwid_device.assert_any_await(101, "hw-a")
        remna_adm.delete_hwid_device.assert_any_await(202, "hw-b")

    with patch("bot.web.admin_users_detail._check_admin", return_value={"id": 99999}):
        remna_adm.delete_hwid_device.reset_mock()
        req_dhw = make_mocked_request("POST", "/api/admin/user/delete_hwid", app=app_adm)
        req_dhw.json = AsyncMock(return_value={"telegram_id": 61001, "panel_user_id": 202, "hwid": "hw-202"})
        assert (await post_admin_user_delete_hwid(req_dhw)).status == 200
        remna_adm.delete_hwid_device.assert_awaited_once_with(202, "hw-202")

    # 3. auto_renew skips DELETED / DISABLED panel accounts
    async with session_factory() as s:
        await _seed_wallet_user(s, 61003, balance=500_000, auto_renew=True)
        await _seed_wallet_user(s, 61001, balance=0)
        await _seed_wallet_user(s, 61002, balance=0)
        await s.commit()

    remna_ar = AsyncMock()
    remna_ar.get_users_by_telegram_id = AsyncMock(
        return_value=[
            {"id": 301, "status": "DELETED", "expireAt": past_iso, "trafficLimitBytes": 10**9},
            {"id": 302, "status": "DISABLED", "expireAt": past_iso, "trafficLimitBytes": 10**9},
        ]
    )
    with patch("bot.services.auto_renew.execute_purchase", AsyncMock()) as mock_pur:
        renewed = await process_auto_renewals(None, session_factory, remna_ar, cache=FastCache(redis_client=None))
    assert renewed == 0
    mock_pur.assert_not_awaited()

    # 4. admin users expiring filter works cleanly even when get_all_panel_users has unmapped rows
    remna_list = AsyncMock()
    remna_list.get_all_panel_users = AsyncMock(return_value=[{"username": "orphan_no_tid"}])
    remna_list.get_active_sessions = AsyncMock(return_value=[])
    remna_list.get_all_hwid_devices = AsyncMock(return_value=[])

    async def _by_tid(uid: int):
        if uid == 61002:
            return [{"id": 702, "status": "ACTIVE", "trafficLimitBytes": 10 * 1024**3, "userTraffic": {"usedTrafficBytes": 9 * 1024**3}}]
        return [{"id": 701, "status": "ACTIVE", "trafficLimitBytes": 50 * 1024**3, "userTraffic": {"usedTrafficBytes": 1 * 1024**3}}]

    remna_list.get_users_by_telegram_id = AsyncMock(side_effect=_by_tid)
    app_list = {"session_factory": session_factory, "remnawave": remna_list, "cache": FastCache(redis_client=None)}
    req_list = make_mocked_request("GET", "/api/admin/users?filter=expiring&page=1&limit=10", app=app_list)
    with patch("bot.web.admin_users_list._check_admin", return_value={"id": 99999}):
        resp_list = await get_admin_users(req_list)
    payload_list = json.loads(resp_list.text)
    assert payload_list["total"] == 1
    assert [u["telegram_id"] for u in payload_list["users"]] == [61002]


# ---------------------------------------------------------------------- #
# 8. Medium Severity: False-Zero Extra Device Rate & Custom Plan FSM Unstuck
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_zero_extra_device_percent_and_custom_plan_fsm(session_factory):
    from bot.handlers.custom_plan import custom_plan_custom_gb_input
    from bot.states.custom_plan import CustomPlanStates
    from bot.web.user_shop import compute_custom_plan_price, get_extra_device_rate

    st = SimpleNamespace(
        custom_plan_price_per_gb=1000,
        custom_plan_price_per_day=500,
        custom_plan_base_price=0,
        custom_plan_volume_tiers_json="",
        custom_plan_extra_device_percent=0,
    )
    assert get_extra_device_rate(st) == 0
    raw_base, _, disc_base = compute_custom_plan_price(10, 10, st, hwid_limit=3)
    assert raw_base == 15_000 and disc_base == 15_000

    shop_js = Path("bot/web/static/js/shop.js").read_text(encoding="utf-8")
    assert "settings.extra_device_percent ?? 15" in shop_js

    storage = MemoryStorage()
    fsm = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=61010, user_id=61010))
    await fsm.set_state(CustomPlanStates.waiting_for_custom_gb)
    await fsm.update_data(squad_uuid="sq-keep")

    async with session_factory() as s:
        u_repo = UserRepository(s)
        msg = MagicMock()
        msg.from_user = SimpleNamespace(id=61010, username="cplan_u")
        msg.text = "75"
        msg.reply = AsyncMock()
        await custom_plan_custom_gb_input(msg, MagicMock(), u_repo, s, fsm)

    assert await fsm.get_state() is None
    st_data = await fsm.get_data()
    assert st_data["traffic_gb"] == 75
    assert st_data["squad_uuid"] == "sq-keep"


# ---------------------------------------------------------------------- #
# 9. Medium Severity: Speedtest GeoIP / Quotas & Polygon RPC Fallback
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_speedtest_geoip_quotas_and_pol_rpc_fallback():
    from bot.services.crypto.pol import verify_polygon_transaction
    from bot.web.user_speedtest import (
        _lookup_isp,
        get_user_speedtest_payload,
        post_user_speedtest_upload,
    )

    st_src = Path("bot/web/user_speedtest.py").read_text(encoding="utf-8")
    assert "https://ip-api.com" not in st_src
    assert "https://ipwho.is" in st_src and "http://ip-api.com" in st_src

    assert await _lookup_isp("127.0.0.1") == "شبکه محلی (Local)"
    assert await _lookup_isp("::1") == "شبکه محلی (Local)"

    app_st = web.Application()
    app_st["bot_token"] = "123:abc"
    app_st["admin_ids"] = [61020]
    app_st["is_dev"] = True
    app_st["cache"] = FastCache(redis_client=None)
    app_st["settings"] = None
    # Bound download chunk to <= 16 MB and enforce byte quota per window
    for _ in range(16):
        req_dl = make_mocked_request("GET", "/api/user/speedtest/payload?user_id=61020&bytes=33554432", app=app_st)
        resp_dl = await get_user_speedtest_payload(req_dl)
        assert resp_dl.status == 200
        assert resp_dl.headers["Content-Length"] == str(16 * 1024 * 1024)

    req_over = make_mocked_request("GET", "/api/user/speedtest/payload?user_id=61020&bytes=16777216", app=app_st)
    resp_over = await get_user_speedtest_payload(req_over)
    assert resp_over.status == 429

    req_big_up = make_mocked_request(
        "POST",
        "/api/user/speedtest/upload?user_id=61020",
        headers={"Content-Length": str(9 * 1024 * 1024)},
        app=app_st,
    )
    assert (await post_user_speedtest_upload(req_big_up)).status == 413

    # Polygon RPC #1 returns tx_info without receipt -> must failover to RPC #2
    expected_addr = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
    val_wei = 10**18

    def _mk_cm(status: int, body: dict):
        resp = MagicMock()
        resp.status = status
        resp.json = AsyncMock(return_value=body)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=None)
        return cm

    class FallbackClientSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def post(self, url, json=None, headers=None):
            method = (json or {}).get("method")
            if "polygon-rpc.com" in url:
                if method == "eth_getTransactionByHash":
                    return _mk_cm(200, {"result": {"to": expected_addr.lower(), "value": hex(val_wei)}})
                return _mk_cm(200, {"result": None})
            if method == "eth_getTransactionByHash":
                return _mk_cm(200, {"result": {"to": expected_addr.lower(), "value": hex(val_wei)}})
            return _mk_cm(200, {"result": {"status": "0x1"}})

    with patch("aiohttp.ClientSession", FallbackClientSession):
        ok, reason, wei = await verify_polygon_transaction("0x" + "c" * 64, expected_addr, val_wei)
    assert ok is True and reason == "SUCCESS" and wei == val_wei


# ---------------------------------------------------------------------- #
# 10. Medium Severity: Gift HTML Escape & Cloudflare IPv6 Proxy Support
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_gift_receiver_html_escape_and_cloudflare_ipv6(session_factory):
    from bot.handlers.gift import gift_receiver_input
    from bot.states.gift import GiftStates
    from bot.web.auth import _is_trusted_proxy, get_client_ip

    storage = MemoryStorage()
    fsm = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=61030, user_id=61030))
    await fsm.set_state(GiftStates.waiting_for_receiver)

    async with session_factory() as s:
        u_repo = UserRepository(s)
        msg = MagicMock()
        msg.from_user = SimpleNamespace(id=61030, username="sender_u")
        msg.text = "@evil<b&tag"
        msg.reply = AsyncMock()
        await gift_receiver_input(msg, MagicMock(), u_repo, s, fsm)

    sent_html = msg.reply.await_args.args[0]
    assert "&lt;b&amp;tag" in sent_html
    assert "@evil<b" not in sent_html

    assert _is_trusted_proxy("2400:cb00:2048:1::6814:155") is True
    assert _is_trusted_proxy("::ffff:104.16.1.1") is True
    assert _is_trusted_proxy("2001:4860:4860::8888") is False

    req_cf_v6 = MagicMock()
    req_cf_v6.remote = "2400:cb00:2048:1::6814:155"
    req_cf_v6.headers = {"CF-Connecting-IP": "198.51.100.42"}
    assert get_client_ip(req_cf_v6) == "198.51.100.42"

    req_untrusted_v6 = MagicMock()
    req_untrusted_v6.remote = "2001:4860:4860::8888"
    req_untrusted_v6.headers = {"CF-Connecting-IP": "198.51.100.42"}
    assert get_client_ip(req_untrusted_v6) == "2001:4860:4860::8888"
