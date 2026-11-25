"""Regression tests covering all P0 production release-blocker fixes."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from sqlalchemy import select

from bot.db.models import (
    BankSmsLog,
    Campaign,
    CardAutoInvoice,
    NodeCost,
    Service,
    Topup,
    User,
    Wallet,
)
from bot.db.repositories.crypto_repo import CryptoRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.handlers.payment_stars import stars_successful_payment_handler
from bot.handlers.shop_trial import service_trial_username
from bot.services.backup import create_database_backup, restore_database_backup
from bot.services.crypto.ton import verify_and_process_payments
from bot.services.purchases import execute_purchase
from bot.services.remnawave import RemnawaveClient
from bot.web.admin_campaigns import post_admin_campaign_create, post_admin_campaign_delete
from bot.web.auth import build_signed_qr_url
from bot.web.server import api_rate_limit_middleware
from bot.web.user_nodes import get_qr_code
from tests.test_tma_web import generate_valid_init_data


@pytest.mark.anyio
async def test_ton_watcher_notifies_and_invalidates_matching_user_only(session_factory):
    """P0-1: When multiple TON invoices are pending, only the paying user receives notice & cache clear."""
    from bot.db.repositories.app_setting_repo import AppSettingRepository

    async with session_factory() as session:
        app_repo = AppSettingRepository(session)
        await app_repo.set("ton_wallet_address", "EQB_TON_MULTI_TEST")
        await app_repo.set("crypto_enabled", "1")

        session.add_all([
            User(telegram_id=101, username="payer101", language="fa"),
            User(telegram_id=202, username="other202", language="fa"),
            Wallet(telegram_id=101, balance=0),
            Wallet(telegram_id=202, balance=0),
        ])
        await session.flush()

        crypto_repo = CryptoRepository(session)
        inv_first = await crypto_repo.create_invoice(
            telegram_id=101,
            amount_toman=100_000,
            amount_ton="0.2",
            nanotons=200_000_000,
            pay_address="EQB_TON_MULTI_TEST",
        )
        # Second invoice sits later in get_all_pending() (would clobber outer loop variable `inv`)
        _inv_last = await crypto_repo.create_invoice(
            telegram_id=202,
            amount_toman=200_000,
            amount_ton="0.4",
            nanotons=400_000_000,
            pay_address="EQB_TON_MULTI_TEST",
        )
        await session.commit()

    txs = [
        {
            "nanotons": 200_000_000,
            "comment": inv_first.comment,
            "tx_hash": "tx_multi_101",
            "utime": int(datetime.now(timezone.utc).timestamp()) + 10,
        }
    ]

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()
    mock_bot.cache = MagicMock()
    mock_bot.cache.invalidate_user = AsyncMock()
    mock_bot.cache.delete = AsyncMock()

    with patch("bot.services.crypto.ton.fetch_ton_transactions", AsyncMock(return_value=txs)):
        processed = await verify_and_process_payments(mock_bot, session_factory)

    assert processed == 1
    mock_bot.cache.invalidate_user.assert_awaited_once_with(101)

    sent_chat_ids = [call.args[0] for call in mock_bot.send_message.await_args_list]
    assert 101 in sent_chat_ids
    assert 202 not in sent_chat_ids

    # Admin notification must mention 101 and NOT 202
    admin_msgs = [str(call.args[1]) for call in mock_bot.send_message.await_args_list if call.args[0] != 101]
    assert admin_msgs and "101" in admin_msgs[0] and "202" not in admin_msgs[0]


@pytest.mark.anyio
async def test_campaign_create_and_delete_persist_across_sessions(session_factory):
    """P0-2: Creating and deleting campaigns via Admin API commits cleanly to the database."""
    app = {
        "session_factory": session_factory,
        "settings": SimpleNamespace(BOT_USERNAME="testbot"),
        "bot": None,
    }

    req_create = make_mocked_request("POST", "/api/admin/campaign/create", app=app)
    req_create.json = AsyncMock(return_value={"name": "Telegram Ad", "code": "tg_spring", "cost": 500_000})
    with patch("bot.web.admin_campaigns._check_admin", return_value={"id": 1}):
        resp_create = await post_admin_campaign_create(req_create)

    assert resp_create.status == 200
    payload = json.loads(resp_create.text)
    assert payload["ok"] is True
    camp_id = payload["campaign"]["id"]

    # Verify persistence from a fresh session
    async with session_factory() as verify_sess:
        saved = await verify_sess.get(Campaign, camp_id)
        assert saved is not None
        assert saved.code == "tg_spring"
        assert saved.cost == 500_000

    # Negative cost returns 400
    req_bad = make_mocked_request("POST", "/api/admin/campaign/create", app=app)
    req_bad.json = AsyncMock(return_value={"name": "Bad", "code": "bad_camp", "cost": -100})
    with patch("bot.web.admin_campaigns._check_admin", return_value={"id": 1}):
        resp_bad = await post_admin_campaign_create(req_bad)
    assert resp_bad.status == 400

    # Delete and verify persistence from a fresh session
    req_del = make_mocked_request("POST", "/api/admin/campaign/delete", app=app)
    req_del.json = AsyncMock(return_value={"id": camp_id})
    with patch("bot.web.admin_campaigns._check_admin", return_value={"id": 1}):
        resp_del = await post_admin_campaign_delete(req_del)

    assert resp_del.status == 200
    assert json.loads(resp_del.text)["ok"] is True

    async with session_factory() as verify_sess2:
        assert await verify_sess2.get(Campaign, camp_id) is None


@pytest.mark.anyio
async def test_squad_switch_none_aborts_purchase_and_skips_wallet_deduction(session_factory):
    """P0-3a: If set_user_squads returns None, purchase aborts without charging wallet."""
    async with session_factory() as session:
        session.add(Wallet(telegram_id=7001, balance=300_000))
        service = Service(
            name="Tunnel Plan",
            price=120_000,
            duration_days=30,
            traffic_gb=50,
            squad_uuid="sq-new",
            is_active=True,
        )
        session.add(service)
        await session.commit()

        remnawave = AsyncMock()
        remnawave.set_user_squads = AsyncMock(return_value=None)
        remnawave.update_user_subscription = AsyncMock()

        account = {
            "id": 99,
            "username": "u7001",
            "expireAt": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "trafficLimitBytes": 10 * 1024 ** 3,
            "activeInternalSquads": [{"uuid": "sq-old"}],
            "status": "ACTIVE",
        }
        result = await execute_purchase(remnawave, session, service, 7001, chosen_account=account)

        assert result.ok is False
        assert result.kind == "failed"
        remnawave.update_user_subscription.assert_not_awaited()
        assert await WalletRepository(session).get_balance(7001) == 300_000


@pytest.mark.anyio
async def test_remnawave_client_does_not_retry_non_idempotent_post():
    """P0-3b: POST requests do not auto-retry on network failure, while GET requests do."""
    client = RemnawaveClient(base_url="https://fake-panel.local", token="tok")
    assert hasattr(client._client.request, "retry")

    post_calls = 0
    get_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls, get_calls
        if request.method == "POST":
            post_calls += 1
            raise httpx.ReadTimeout("timeout on POST", request=request)
        get_calls += 1
        if get_calls == 1:
            raise httpx.ConnectError("transient GET failure", request=request)
        return httpx.Response(200, json={"response": {"ok": True}})

    test_client = RemnawaveClient(base_url="https://fake-panel.local", token="tok")
    assert hasattr(test_client._client.request, "retry")
    test_client._client._transport = httpx.MockTransport(handler)
    try:
        with pytest.raises(httpx.ReadTimeout):
            await test_client._client.post("/api/users", json={"username": "dup"})
        assert post_calls == 1

        resp = await test_client._client.get("/api/nodes")
        assert resp.status_code == 200
        assert get_calls == 2
    finally:
        await test_client.close()


@pytest.mark.anyio
async def test_trial_claim_rolls_back_cleanly_when_username_taken_in_same_session(session_factory):
    """P0-4: Failed trial lookup/create does not leave has_claimed_trial=True stuck due to stale ORM cache."""
    from bot.db.repositories.app_setting_repo import AppSettingRepository

    tid = 88001
    storage = MemoryStorage()
    fsm = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=tid, user_id=tid))

    async with session_factory() as session:
        await AppSettingRepository(session).set("trial_enabled", "1")
        user_repo = UserRepository(session)
        await user_repo.get_or_create(tid, "trial_tester")
        await session.commit()

    # Step 1: User enters an already-taken username in the exact real handler lifecycle
    async with session_factory() as session:
        user_repo = UserRepository(session)
        msg = MagicMock()
        msg.from_user = SimpleNamespace(id=tid, username="trial_tester")
        msg.chat = SimpleNamespace(id=tid)
        msg.message_id = 10
        msg.text = "taken_name"

        mock_bot = AsyncMock()
        mock_remna = AsyncMock()
        mock_remna.get_user_by_username = AsyncMock(return_value={"id": 55, "username": "taken_name"})

        with patch("bot.handlers.shop_trial.render_menu", AsyncMock()), patch(
            "bot.handlers.shop_trial.delete_message_silently", AsyncMock()
        ):
            await service_trial_username(msg, mock_bot, user_repo, session, mock_remna, fsm)
        await session.commit()

    # Step 2: Verify from a brand-new session that has_claimed_trial is rolled back to False
    async with session_factory() as verify_sess:
        db_user = await UserRepository(verify_sess).get_by_telegram_id(tid)
        assert db_user is not None
        assert db_user.has_claimed_trial is False


@pytest.mark.anyio
async def test_backup_preserves_all_fields_circular_fks_and_resets_pg_sequences(session_factory, tmp_path):
    """P0-5: Export/Restore preserves omitted User/Service/NodeCost fields, circular SMS<->Invoice FKs, and PG sequences."""
    due = datetime(2027, 1, 15, 12, 0, tzinfo=timezone.utc)
    async with session_factory() as session:
        session.add(
            User(
                telegram_id=9101,
                username="bak_user",
                full_name="Backup Full Name",
                campaign_code="camp_bak",
                spin_tickets=4,
                menu_message_id=777,
            )
        )
        svc = Service(
            id=15,
            name="Backup VIP",
            description="High-speed desc",
            badge="vip",
            price=150_000,
            duration_days=30,
            traffic_gb=100,
            max_purchases=50,
            purchases_count=7,
            sort_order=3,
            is_active=True,
        )
        session.add(svc)
        session.add(NodeCost(id=8, node_uuid="uuid-node-8", due_date=due, monthly_cost_toman=250_000))
        sms = BankSmsLog(id=41, sender="+983000", raw_message="Deposit 100000", sms_hash="hash_41", processed=True)
        session.add(sms)
        await session.flush()

        inv = CardAutoInvoice(
            id=61,
            invoice_uuid="inv-uuid-61",
            telegram_id=9101,
            base_amount=100_000,
            exact_amount=100_001,
            exact_rial=1_000_010,
            card_number="6037",
            card_holder="Holder",
            status="paid",
            sms_log_id=41,
            expires_at=due,
        )
        session.add(inv)
        await session.flush()
        sms.matched_invoice_id = 61
        await session.commit()

        bak_file = await create_database_backup(session, out_dir=tmp_path)

    # Clear tables cleanly before restore
    async with session_factory() as wipe_sess:
        for model in (CardAutoInvoice, BankSmsLog, NodeCost, Service, User):
            rows = (await wipe_sess.execute(select(model))).scalars().all()
            for row in rows:
                await wipe_sess.delete(row)
        await wipe_sess.commit()

    async with session_factory() as restore_sess:
        stats = await restore_database_backup(restore_sess, bak_file)
        assert stats["users"] == 1
        assert stats["services"] == 1
        assert stats["node_costs"] == 1
        assert stats["bank_sms_logs"] == 1
        assert stats["card_auto_invoices"] == 1

    async with session_factory() as check_sess:
        u = await UserRepository(check_sess).get_by_telegram_id(9101)
        assert u.full_name == "Backup Full Name"
        assert u.campaign_code == "camp_bak"
        assert u.spin_tickets == 4
        assert u.menu_message_id == 777

        s = await check_sess.get(Service, 15)
        assert s.description == "High-speed desc"
        assert s.badge == "vip"
        assert s.max_purchases == 50
        assert s.purchases_count == 7
        assert s.sort_order == 3

        nc = await check_sess.get(NodeCost, 8)
        assert nc.due_date is not None and nc.due_date.year == 2027

        restored_inv = (await check_sess.execute(select(CardAutoInvoice))).scalar_one()
        restored_sms = (await check_sess.execute(select(BankSmsLog))).scalar_one()
        assert restored_inv.sms_log_id == restored_sms.id
        assert restored_sms.matched_invoice_id == restored_inv.id

    # Verify Postgres sequence reset path executes setval when dialect is postgresql
    pg_calls: list[tuple[str, dict]] = []
    pg_session = AsyncMock()
    pg_session.add = MagicMock()
    pg_session.get_bind = MagicMock(return_value=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))

    async def _pg_execute(stmt, params=None):
        sql_txt = str(stmt)
        res = MagicMock()
        if "pg_get_serial_sequence" in sql_txt:
            pg_calls.append((sql_txt, dict(params or {})))
            res.scalar_one_or_none.return_value = None
        elif "max(" in sql_txt.lower():
            res.scalar_one_or_none.return_value = 42
        else:
            res.scalar_one_or_none.return_value = None
        return res

    pg_session.execute = AsyncMock(side_effect=_pg_execute)
    pg_session.get = AsyncMock(return_value=None)
    await restore_database_backup(pg_session, bak_file)
    assert any(p.get("tbl") == "services" and p.get("val") == 42 for _, p in pg_calls)

    # Verify fail-closed encrypted backup raises and removes plaintext when encryption fails
    async with session_factory() as fail_sess:
        with patch("bot.services.backup.create_encrypted_backup_archive", return_value=None):
            with pytest.raises(RuntimeError):
                await create_database_backup(fail_sess, out_dir=tmp_path, password="strong_password")
        assert not any(p.suffix == ".json" and p != bak_file for p in tmp_path.iterdir())


@pytest.mark.anyio
async def test_expired_stars_payment_refunds_user_and_blocks_replay(session_factory):
    """P0-6: Expired Stars successful_payment triggers refund_star_payment, notifies user, and avoids duplicate refund."""
    tid = 9202
    expired_ts = int(time.time()) - 300
    msg = MagicMock()
    msg.from_user = SimpleNamespace(id=tid)
    msg.successful_payment = SimpleNamespace(
        invoice_payload=f"stars_topup:{tid}:50000:50:{expired_ts}",
        telegram_payment_charge_id="chg_exp_9202",
        currency="XTR",
        total_amount=50,
    )
    bot = AsyncMock()

    async with session_factory() as session:
        await stars_successful_payment_handler(msg, bot=bot, session=session)
        # Replay delivery should be ignored cleanly without double refund
        await stars_successful_payment_handler(msg, bot=bot, session=session)

        res = await session.execute(select(Topup).where(Topup.telegram_id == tid))
        row = res.scalar_one()
        assert row.status == "rejected"
        assert row.receipt_hash == "refunded_expired:chg_exp_9202"
        assert row.decided_at is not None

    bot.refund_star_payment.assert_awaited_once_with(
        user_id=tid,
        telegram_payment_charge_id="chg_exp_9202",
    )
    bot.send_message.assert_awaited_once()


@pytest.mark.anyio
async def test_qr_endpoint_requires_auth_or_signed_token_and_rate_limits():
    """P0-7: Unauthenticated QR calls are rejected (401), valid auth/signature succeed (200), and /api/qr is rate-limited."""
    bot_token = "999888:SecretTokenForQrTests"
    app = {"is_dev": False, "bot_token": bot_token, "admin_ids": []}

    # 1. Unauthenticated request without signature -> 401
    req_unauth = make_mocked_request("GET", "/api/user/qr?text=vless://secret", app=app)
    resp_unauth = await get_qr_code(req_unauth)
    assert resp_unauth.status == 401

    # 2. Tampered signature -> 401
    req_bad_sig = make_mocked_request("GET", "/api/qr?text=hello&exp=9999999999&sig=deadbeef", app=app)
    resp_bad_sig = await get_qr_code(req_bad_sig)
    assert resp_bad_sig.status == 401

    # 3. Valid signed URL (used by Telegram shareToStory) -> 200 image/png
    signed_url = build_signed_qr_url("https://t.me/mybot?start=ref_1", bot_token)
    req_signed = make_mocked_request("GET", signed_url, app=app)
    resp_signed = await get_qr_code(req_signed)
    assert resp_signed.status == 200
    assert resp_signed.content_type == "image/png"

    # 4. Authenticated initData header -> 200 image/png
    init_data = generate_valid_init_data(bot_token, {"id": 555, "first_name": "QrUser"})
    req_auth = make_mocked_request(
        "GET",
        "/api/user/qr?text=vless://auth-user",
        headers={"X-Telegram-Init-Data": init_data},
        app=app,
    )
    resp_auth = await get_qr_code(req_auth)
    assert resp_auth.status == 200
    assert resp_auth.content_type == "image/png"

    # 5. /api/qr passes through rate limit middleware (blocks after quota exceeded)
    rl_app = {"is_dev": False, "cache": None}
    ok_handler = AsyncMock(return_value=web.Response(status=200))
    blocked_statuses = []
    with patch("bot.web.server._API_MAX_GENERAL", 2):
        for _ in range(3):
            rl_req = make_mocked_request("GET", "/api/qr?text=spam", app=rl_app)
            rl_resp = await api_rate_limit_middleware(rl_req, ok_handler)
            blocked_statuses.append(rl_resp.status)
    assert blocked_statuses == [200, 200, 429]
