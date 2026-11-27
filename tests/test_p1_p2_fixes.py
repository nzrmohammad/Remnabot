"""Regression tests for P1/P2 financial, logic, caching, and security fixes."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiohttp.test_utils import make_mocked_request

from bot.db.models import Order, User, Wallet
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.crypto_repo import CryptoRepository
from bot.services.auto_renew import process_auto_renewals
from bot.services.configs import _is_internal_host
from bot.services.crypto.pol import verify_and_credit_pol_invoice
from bot.services.crypto.trx import verify_and_credit_trx_invoice
from bot.services.menu import _truncate_telegram_html, render_menu
from bot.services.remnawave import RemnawaveClient
from bot.web.admin_infra_api import get_admin_tools_check_host
from bot.web.admin_plans import post_admin_plan_delete, post_admin_plan_save, post_admin_plan_toggle
from bot.web.admin_tickets import post_admin_reply_ticket
from bot.web.admin_users_actions import post_admin_user_wallet
from bot.web.admin_users_list import get_admin_users
from bot.web.cache import FastCache, invalidate_user_cache
from bot.web.user_topup import (
    get_user_topup_trx_redirect,
    post_user_topup_pol_verify,
    post_user_topup_trx_verify,
)


@pytest.mark.anyio
async def test_pol_and_trx_verify_notify_only_after_commit_and_trx_notifies(session_factory):
    """P1-1: If commit fails, neither POL nor TRX dispatches Telegram notifications; TRX notifies on commit."""
    tx_trx = "a" * 64
    tx_pol = "0x" + "b" * 64
    async with session_factory() as session:
        await AppSettingRepository(session).set("admin_chat_id", "-100999")
        repo = CryptoRepository(session)
        inv_pol = await repo.create_invoice(1001, 100_000, "10.0000", 10**19, "0xAddr", currency="POL")
        inv_trx = await repo.create_invoice(1002, 100_000, "50.0000", 50_000_000, "TAddr", currency="TRX")
        await session.commit()

    # Case A: POL commit raises -> bot.send_message MUST NOT run
    mock_bot = AsyncMock()
    req_pol = make_mocked_request("POST", "/api/user/topup/pol/verify", app={"bot": mock_bot, "cache": None})
    req_pol.json = AsyncMock(return_value={"invoice_id": inv_pol.id, "tx_hash": tx_pol})

    async with session_factory() as failing_sess:
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=failing_sess)
        cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(failing_sess, "commit", AsyncMock(side_effect=RuntimeError("DB commit failed"))),
            patch("bot.web.user_topup.require_user", return_value=({"id": 1001}, None)),
            patch("bot.web.user_topup.db_session", return_value=cm),
            patch("bot.services.crypto.pol.verify_polygon_transaction", AsyncMock(return_value=(True, "SUCCESS", 10**19))),
        ):
            with pytest.raises(RuntimeError, match="DB commit failed"):
                await post_user_topup_pol_verify(req_pol)
    mock_bot.send_message.assert_not_awaited()

    # Case B: TRX succeeds and commits -> notifies user (and admin if configured)
    app_trx = {"session_factory": session_factory, "bot": mock_bot, "cache": FastCache()}
    req_trx = make_mocked_request("POST", "/api/user/topup/trx/verify", app=app_trx)
    req_trx.json = AsyncMock(return_value={"invoice_id": inv_trx.id, "tx_hash": tx_trx})
    with (
        patch("bot.web.user_topup.require_user", return_value=({"id": 1002}, None)),
        patch("bot.services.crypto.trx.verify_tron_transaction", AsyncMock(return_value=(True, "SUCCESS", 50_000_000))),
    ):
        resp_trx = await post_user_topup_trx_verify(req_trx)
    assert resp_trx.status == 200
    assert json.loads(resp_trx.text)["paid"] is True
    assert any(c.args[0] == 1002 for c in mock_bot.send_message.await_args_list)

    # Standalone helpers still work cleanly with defaults
    async with session_factory() as s2:
        standalone_bot = AsyncMock()
        inv2 = await CryptoRepository(s2).create_invoice(1003, 50_000, "25.0000", 25_000_000, "TAddr", currency="TRX")
        await s2.commit()
        with patch("bot.services.crypto.trx.verify_tron_transaction", AsyncMock(return_value=(True, "SUCCESS", 25_000_000))):
            ok, _, _ = await verify_and_credit_trx_invoice(s2, inv2, "c" * 64, bot=standalone_bot)
            assert ok is True
            assert standalone_bot.send_message.await_count >= 1

        inv3 = await CryptoRepository(s2).create_invoice(1004, 50_000, "5.0000", 5 * 10**18, "0xAddr", currency="POL")
        await s2.commit()
        with patch("bot.services.crypto.pol.verify_polygon_transaction", AsyncMock(return_value=(True, "SUCCESS", 5 * 10**18))):
            ok_p, _, _ = await verify_and_credit_pol_invoice(s2, inv3, "0x" + "d" * 64, bot=standalone_bot)
            assert ok_p is True


@pytest.mark.anyio
async def test_crypto_repo_retries_colliding_units_and_raises_when_exhausted(session_factory):
    """P1-2: create_invoice reallocates colliding fractional units instead of failing; exhausted slots raise."""
    async with session_factory() as session:
        repo = CryptoRepository(session)
        await repo.create_invoice(1101, 50_000, "10.0001", 10_000_100, "TAddr", currency="TRX")
        await session.commit()

        # Pass exact colliding nanotons=10_000_100 -> IntegrityError triggers unit reallocation
        inv2 = await repo.create_invoice(1102, 50_000, "10.0001", 10_000_100, "TAddr", currency="TRX")
        assert inv2.nanotons != 10_000_100
        assert inv2.nanotons > 10_000_100
        await session.commit()

        # Exhaustion raises RuntimeError instead of returning a colliding amount
        exhausted_used = {10_000_000 + k * 100 for k in range(1, 510)}
        with patch.object(repo, "get_pending_nanotons", AsyncMock(return_value=exhausted_used)):
            with pytest.raises(RuntimeError, match="Exhausted unique payment unit slots"):
                await repo.allocate_unique_crypto_units(10_000_000, 100, "TRX", max_steps=5)


@pytest.mark.anyio
async def test_invalidate_user_cache_clears_secondary_accounts_and_loyalty():
    """P1-3: Multi-account dashboard, configs, and loyalty tier caches are all wiped for user."""
    cache = FastCache()
    tid = 2001
    await cache.set(f"tma:user:{tid}:dashboard:default", {"v": 1}, ttl_seconds=60)
    await cache.set(f"tma:user:{tid}:dashboard:999", {"v": 2}, ttl_seconds=60)
    await cache.set(f"tma:user:{tid}:configs:999", {"cfg": True}, ttl_seconds=60)
    await cache.set(f"loyalty:user:v2:{tid}", {"tier_id": "gold"}, ttl_seconds=60)

    await invalidate_user_cache(cache, tid)
    assert await cache.get(f"tma:user:{tid}:dashboard:default") is None
    assert await cache.get(f"tma:user:{tid}:dashboard:999") is None
    assert await cache.get(f"tma:user:{tid}:configs:999") is None
    assert await cache.get(f"loyalty:user:v2:{tid}") is None

    # Mock cache exposing only .delete() works cleanly without error
    mock_cache = MagicMock(delete=AsyncMock())
    await invalidate_user_cache(mock_cache, tid)
    assert mock_cache.delete.await_count >= 3


@pytest.mark.anyio
async def test_remnawave_fallback_loops_continue_on_network_exceptions():
    """P1-4: Multi-path fallback endpoints try remaining URLs if earlier ones raise."""
    client = RemnawaveClient(base_url="https://fake-panel.local", token="tok")
    try:
        call_paths: list[str] = []

        async def _fake_get(path, **kwargs):
            call_paths.append(path)
            if len(call_paths) == 1:
                raise RuntimeError("first endpoint down")
            resp = MagicMock(status_code=200)
            if "sessions" in path:
                resp.json.return_value = {"response": [{"id": 1}]}
            elif "devices" in path and "stats" not in path:
                resp.json.return_value = {"response": {"devices": [{"hwid": "abc"}]}}
            else:
                resp.json.return_value = {"response": {"total": 5}}
            return resp

        client._client.get = _fake_get

        assert await client.get_active_sessions() == [{"id": 1}]
        call_paths.clear()
        assert await client.get_system_recap() == {"total": 5}
        call_paths.clear()
        assert await client.get_hwid_stats() == {"total": 5}
        call_paths.clear()
        assert await client.get_all_hwid_devices() == [{"hwid": "abc"}]
        call_paths.clear()
        assert await client.get_srh_stats() == {"total": 5}
    finally:
        await client.close()


@pytest.mark.anyio
async def test_html_escaping_in_admin_replies_wallet_and_menu_truncation(session_factory):
    """P1-5: Admin ticket/wallet HTML escapes special chars; menu HTML truncates safely & handles blocked users."""
    mock_bot = AsyncMock()
    app = {"session_factory": session_factory, "bot": mock_bot, "cache": FastCache()}

    # Ticket reply escapes < and &
    req_tkt = make_mocked_request("POST", "/api/admin/ticket/reply", app=app)
    req_tkt.json = AsyncMock(return_value={"telegram_id": 3001, "reply_text": "Plan <10GB> & faster"})
    with patch("bot.web.admin_tickets._check_admin", return_value={"id": 1}):
        resp_tkt = await post_admin_reply_ticket(req_tkt)
    assert resp_tkt.status == 200
    sent_tkt_text = mock_bot.send_message.await_args.kwargs["text"]
    assert "&lt;10GB&gt; &amp; faster" in sent_tkt_text

    # Wallet adjustment escapes reason
    async with session_factory() as s:
        s.add(User(telegram_id=3001, username="u3001"))
        await s.flush()
        s.add(Wallet(telegram_id=3001, balance=0))
        await s.commit()
    mock_bot.send_message.reset_mock()
    req_wal = make_mocked_request("POST", "/api/admin/user/wallet", app=app)
    req_wal.json = AsyncMock(return_value={"telegram_id": 3001, "amount": 5000, "reason": "Gift <script> & bonus"})
    with patch("bot.web.admin_users_actions._check_admin", return_value={"id": 1}):
        resp_wal = await post_admin_user_wallet(req_wal)
    assert resp_wal.status == 200
    sent_wal_text = mock_bot.send_message.await_args.kwargs["text"]
    assert "&lt;script&gt; &amp; bonus" in sent_wal_text

    # Menu HTML truncation preserves valid tag closing
    long_html = "<b>Title</b> " + ("<code>abc</code> " * 400)
    truncated = _truncate_telegram_html(long_html, limit=100)
    assert len(truncated) <= 120
    assert not truncated.endswith("<")
    assert truncated.count("<code>") == truncated.count("</code>")

    # Menu render_menu suppresses TelegramForbiddenError cleanly
    blocked_bot = AsyncMock()
    blocked_bot.edit_message_text = AsyncMock(
        side_effect=TelegramForbiddenError(method=MagicMock(), message="bot was blocked by the user")
    )
    fake_user = SimpleNamespace(telegram_id=3002, menu_message_id=99)
    await render_menu(blocked_bot, fake_user, MagicMock(), "Hello")


@pytest.mark.anyio
async def test_admin_plans_and_users_validation_and_expiring_pagination(session_factory):
    """P1-6: Negative/bad admin inputs return 400; expiring/expired filter paginates accurately without N+1."""
    app = {"session_factory": session_factory, "cache": FastCache()}

    with patch("bot.web.admin_plans._check_admin", return_value={"id": 1}):
        # Negative price rejected
        req_neg = make_mocked_request("POST", "/api/admin/plans/save", app=app)
        req_neg.json = AsyncMock(return_value={"name": "Bad", "price": -500, "traffic_gb": 10, "duration_days": 30, "squad_uuid": "sq1"})
        assert (await post_admin_plan_save(req_neg)).status == 400

        # Non-numeric ID rejected cleanly with 400
        for endpoint in (post_admin_plan_toggle, post_admin_plan_delete):
            req_id = make_mocked_request("POST", "/api/admin/plans/x", app=app)
            req_id.json = AsyncMock(return_value={"id": "not-an-int"})
            assert (await endpoint(req_id)).status == 400

    # Invalid pagination query returns 400
    req_bad_page = make_mocked_request("GET", "/api/admin/users?page=abc", app={"session_factory": session_factory, "remnawave": AsyncMock()})
    with patch("bot.web.admin_users_list._check_admin", return_value={"id": 1}):
        assert (await get_admin_users(req_bad_page)).status == 400

    # Accurate pagination on filter=expiring when 5 healthy users precede 2 expiring users
    async with session_factory() as s:
        for i in range(1, 8):
            s.add(User(telegram_id=4000 + i, username=f"u{i}"))
        await s.commit()

    panel_list = [
        {"telegramId": 4000 + i, "username": f"tg_{4000+i}", "status": "ACTIVE", "trafficLimitBytes": 10 * 1024**3, "userTraffic": {"usedTrafficBytes": 1 * 1024**3}}
        for i in range(1, 6)
    ] + [
        {"telegramId": 4000 + i, "username": f"tg_{4000+i}", "status": "ACTIVE", "trafficLimitBytes": 10 * 1024**3, "userTraffic": {"usedTrafficBytes": 9 * 1024**3}}
        for i in range(6, 8)
    ]
    mock_remna = AsyncMock()
    mock_remna.get_all_panel_users = AsyncMock(return_value=panel_list)
    mock_remna.get_active_sessions = AsyncMock(return_value=[])
    mock_remna.get_all_hwid_devices = AsyncMock(return_value=[])

    req_exp = make_mocked_request(
        "GET",
        "/api/admin/users?filter=expiring&page=1&limit=5",
        app={"session_factory": session_factory, "remnawave": mock_remna},
    )
    with patch("bot.web.admin_users_list._check_admin", return_value={"id": 1}):
        resp_exp = await get_admin_users(req_exp)
    data = json.loads(resp_exp.text)
    assert data["total"] == 2
    assert [u["telegram_id"] for u in data["users"]] == [4006, 4007]
    mock_remna.get_users_by_telegram_id.assert_not_awaited()


@pytest.mark.anyio
async def test_ssrf_blocked_in_check_host_and_trx_redirect_escapes_script():
    """P1-7: Internal/metadata IPs & internal DNS targets blocked with 400; TRX redirect escapes script tag."""
    assert _is_internal_host("169.254.169.254") is True
    assert _is_internal_host("metadata.google.internal") is True

    app = {"admin_id": 1, "settings": None}
    for bad_host in ("127.0.0.1", "169.254.169.254", "localhost", "10.0.0.1"):
        req = make_mocked_request("POST", "/api/admin/tools/check_host", app=app)
        req.json = AsyncMock(return_value={"host": bad_host, "check_type": "tcp", "port": 80})
        with patch("bot.web.admin_infra_api._check_admin", return_value={"id": 1}):
            resp = await get_admin_tools_check_host(req)
        assert resp.status == 400

    # External domain resolving to loopback is rejected too
    fake_loop = MagicMock(getaddrinfo=AsyncMock(return_value=[(2, 1, 6, "", ("127.0.0.1", 0))]))
    req_dns = make_mocked_request("POST", "/api/admin/tools/check_host", app=app)
    req_dns.json = AsyncMock(return_value={"host": "rebind.example.com", "check_type": "ping"})
    with (
        patch("bot.web.admin_infra_api._check_admin", return_value={"id": 1}),
        patch("asyncio.get_running_loop", return_value=fake_loop),
    ):
        resp_dns = await get_admin_tools_check_host(req_dns)
    assert resp_dns.status == 400

    # TRX redirect escapes '<' / '>' inside inline JSON script string
    valid_addr = "T" + "A" * 33
    req_redir = make_mocked_request(
        "GET",
        f"/api/user/topup/trx/redirect?address={valid_addr}&amount=10&evil=%3C/script%3E",
    )
    resp_redir = await get_user_topup_trx_redirect(req_redir)
    assert resp_redir.status == 200
    assert "</script><" not in resp_redir.text
    assert "\\u003c/script\\u003e" in resp_redir.text or "tronlinkoutside://" in resp_redir.text


@pytest.mark.anyio
async def test_auto_renew_supports_custom_plans_and_uses_24h_low_balance_cooldown(session_factory):
    """P1-8: Auto-renew processes custom plans (service_id=None) and sets 24h TTL on low-balance alert."""
    tid = 5001
    async with session_factory() as s:
        await AppSettingRepository(s).set("custom_plan_enabled", "1")
        await AppSettingRepository(s).set("custom_plan_price_per_gb", "2000")
        await AppSettingRepository(s).set("custom_plan_price_per_day", "500")
        await AppSettingRepository(s).set("custom_plan_base_price", "0")
        s.add(User(telegram_id=tid, username="custom_renewer", auto_renew=True, is_banned=False))
        await s.flush()
        # Low balance initially -> tests 24h cooldown
        s.add(Wallet(telegram_id=tid, balance=100))
        s.add(
            Order(
                telegram_id=tid,
                service_id=None,
                service_name="بسته دلخواه",
                amount=35_000,
                duration_days=30,
                traffic_gb=10,
                panel_user_id=77,
                panel_username="tg_5001",
                status="paid",
            )
        )
        await s.commit()

    exp_soon = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    panel_acc = {
        "id": 77,
        "username": "tg_5001",
        "expireAt": exp_soon,
        "trafficLimitBytes": 10 * 1024**3,
        "usedTrafficBytes": 0,
        "hwidDeviceLimit": 1,
        "activeInternalSquads": [{"uuid": "sq-custom"}],
        "status": "ACTIVE",
    }
    remna = AsyncMock()
    remna.get_users_by_telegram_id = AsyncMock(return_value=[panel_acc])
    bot = AsyncMock()
    cache = FastCache()

    # 1. Low balance triggers alert once per 24h even if 1h retry cooldown expires
    with patch.object(cache, "set", wraps=cache.set) as spy_set:
        renewed_1 = await process_auto_renewals(bot, session_factory, remna, cache=cache)
        assert renewed_1 == 0
        assert any(call.kwargs.get("ttl_seconds") == 86400 for call in spy_set.await_args_list)
        assert any(call.kwargs.get("ttl_seconds") == 3600 for call in spy_set.await_args_list)
        assert bot.send_message.await_count == 1

    # Simulate 6h later (retry key expired, 24h notice key still active) -> no repeat low-balance DM
    await cache.delete(f"auto_renew_attempt:{tid}:77")
    renewed_retry = await process_auto_renewals(bot, session_factory, remna, cache=cache)
    assert renewed_retry == 0
    assert bot.send_message.await_count == 1

    # 2. Top up wallet and clear cooldown -> custom plan renews cleanly via execute_purchase
    await cache.delete(f"auto_renew_attempt:{tid}:77")
    async with session_factory() as s2:
        w = await s2.get(Wallet, tid)
        w.balance = 100_000
        await s2.commit()

    remna.update_user_subscription = AsyncMock(
        return_value={"id": 77, "username": "tg_5001", "subscriptionUrl": "https://sub.local/5001"}
    )
    renewed_2 = await process_auto_renewals(bot, session_factory, remna, cache=cache)
    assert renewed_2 == 1
