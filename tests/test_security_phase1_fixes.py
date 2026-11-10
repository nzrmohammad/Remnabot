"""Comprehensive Phase 1 security, financial integrity & abuse-prevention tests."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import make_mocked_request
from sqlalchemy import select

from bot.db.models import (
    BankSmsLog,
    Campaign,
    CardAutoInvoice,
    Coupon,
    CryptoInvoice,
    GiftCard,
    Order,
    ReferralReward,
    Service,
    User,
    Wallet,
)
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.crypto_repo import CryptoRepository
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.handlers.admin_orders_detail import _revert_panel_subscription, order_view_or_refund
from bot.handlers.custom_plan import custom_plan_execute_purchase
from bot.handlers.payment_stars import stars_pre_checkout_handler, stars_successful_payment_handler
from bot.handlers.shop_purchase_views import prepare_bot_discounts
from bot.handlers.start import cmd_start
from bot.services.auto_renew import process_auto_renewals
from bot.services.backup import create_database_backup, restore_database_backup
from bot.services.crypto.pol import verify_polygon_transaction
from bot.services.crypto.ton import verify_and_credit_ton_invoice
from bot.services.crypto.trx import verify_tron_transaction
from bot.services.gift_service import claim_gift, create_gift, get_user_gifts, redeem_code_to_wallet
from bot.services.payment.bank_sms_parser import parse_bank_sms
from bot.services.payment.card_auto_service import process_incoming_sms
from bot.services.purchases import execute_purchase, maybe_reward_referrer
from bot.services.wheel_service import execute_lucky_wheel_spin
from bot.web.admin_common import _check_admin
from bot.web.admin_infra_api import get_admin_tools_check_host
from bot.web.admin_plans import post_admin_coupon_save
from bot.web.admin_users_actions import post_admin_toggle_ban
from bot.web.cache import FastCache
from bot.web.user_common import _check_user
from bot.web.user_profile import get_user_me, post_user_set_birthday
from bot.web.user_topup import post_user_topup_card


async def _seed_user_wallet(session, tid: int, balance: int = 0, username: str | None = None, **user_kw):
    user = User(telegram_id=tid, username=username or f"user_{tid}", full_name=f"User {tid}", **user_kw)
    session.add(user)
    session.add(Wallet(telegram_id=tid, balance=balance))
    await session.flush()
    return user


# ---------------------------------------------------------------------- #
# 1. Extra-Traffic 2099 Expired Account Exploit & Active LIMITED Allowance
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_expired_extra_traffic_2099_blocked_and_active_limited_allowed(session_factory):
    now = datetime.now(timezone.utc)
    past_iso = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future_iso = (now + timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with session_factory() as session:
        await _seed_user_wallet(session, 1001, balance=100_000)
        svc = Service(name="Extra 5GB", price=15_000, duration_days=0, traffic_gb=5, badge="traffic")
        session.add(svc)
        await session.flush()

        # Case A: Expired account -> MUST be rejected cleanly without calling update_user_subscription
        remnawave = AsyncMock()
        remnawave.update_user_subscription = AsyncMock()
        expired_acc = {
            "id": 9001,
            "username": "u_expired",
            "status": "EXPIRED",
            "expireAt": past_iso,
            "trafficLimitBytes": 10 * (1024**3),
        }
        res_exp = await execute_purchase(remnawave, session, svc, 1001, chosen_account=expired_acc)
        assert res_exp.ok is False
        assert res_exp.kind == "needs_active_sub"
        remnawave.update_user_subscription.assert_not_awaited()
        assert await WalletRepository(session).get_balance(1001) == 100_000

        # Case B: Active-time LIMITED account -> ALLOWED
        limited_acc = {
            "id": 9002,
            "username": "u_limited",
            "status": "LIMITED",
            "expireAt": future_iso,
            "trafficLimitBytes": 10 * (1024**3),
        }
        remnawave.update_user_subscription.return_value = {
            "id": 9002,
            "username": "u_limited",
            "subscriptionUrl": "https://sub.local/9002",
        }
        res_ok = await execute_purchase(remnawave, session, svc, 1001, chosen_account=limited_acc)
        assert res_ok.ok is True
        remnawave.update_user_subscription.assert_awaited_once()
        assert await WalletRepository(session).get_balance(1001) == 85_000


# ---------------------------------------------------------------------- #
# 2. Bot Custom Plan Negative / Zero GB & Days Validation
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_custom_plan_negative_gb_rejected_in_bot_callback(session_factory):
    async with session_factory() as session:
        user = await _seed_user_wallet(session, 1002, balance=200_000)
        await session.commit()

        store_mock = SimpleNamespace(
            custom_plan_enabled=True,
            custom_plan_min_gb=5,
            custom_plan_max_gb=500,
            custom_plan_min_days=7,
            custom_plan_max_days=365,
            custom_plan_price_per_gb=3000,
            custom_plan_price_per_day=1000,
            custom_plan_base_price=0,
        )
        call = AsyncMock()
        call.from_user = SimpleNamespace(id=1002, username="u1002", full_name="Test")
        call.data = "cplan:buy:-500:0"
        call.answer = AsyncMock()

        bot = AsyncMock()
        user_repo = UserRepository(session)
        remnawave = AsyncMock()

        with patch("bot.handlers.custom_plan.get_store_settings", AsyncMock(return_value=store_mock)):
            await custom_plan_execute_purchase(call, bot, user_repo, session, remnawave, state=None)

        call.answer.assert_awaited()
        _, kwargs = call.answer.call_args
        assert kwargs.get("show_alert") is True
        assert await WalletRepository(session).get_balance(1002) == 200_000
        orders = (await session.execute(select(Order).where(Order.telegram_id == user.telegram_id))).scalars().all()
        assert orders == []


# ---------------------------------------------------------------------- #
# 3. Coupon.kind Isolation, Bound User & Bot Voucher Redeem + Admin Bounds
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_coupon_voucher_kind_isolation_bound_user_and_admin_validation(session_factory):
    async with session_factory() as session:
        await _seed_user_wallet(session, 101, balance=0)
        await _seed_user_wallet(session, 202, balance=50_000)
        c_repo = CouponRepository(session)

        # Checkout fixed discount MUST NOT cash out to wallet
        disc = await c_repo.create("DISC50", discount_amount=50_000, max_uses=5, kind="discount")
        assert disc.kind == "discount"
        ok_r, amt_r, _ = await c_repo.redeem_credit_voucher("DISC50", 101)
        assert ok_r is False and amt_r == 0

        # Credit voucher MUST NOT work as checkout coupon
        vouch = await c_repo.create("VOUCH50", discount_amount=50_000, max_uses=1, kind="voucher")
        assert vouch.kind == "voucher"
        ok_v, err_v, _ = await c_repo.validate_coupon("VOUCH50", 101, price=100_000)
        assert ok_v is False and err_v == "coupon_is_voucher"

        # Bound coupon only valid for bound_telegram_id
        await c_repo.create("BOUND101", discount_percent=20, max_uses=1, kind="discount", bound_telegram_id=101)
        ok_other, err_other, _ = await c_repo.validate_coupon("BOUND101", 202, price=100_000)
        assert ok_other is False and err_other == "coupon_not_yours"
        ok_owner, err_owner, disc_val = await c_repo.validate_coupon("BOUND101", 101, price=100_000)
        assert ok_owner is True and err_owner is None and disc_val == 20_000

        # Unified redeem helper handles GIFT- cards for bot & TMA cleanly
        gift = await create_gift(session, 202, "Sender", delivery_type="LINK", gift_type="BALANCE", amount=10_000)
        assert gift["ok"] is True
        await session.commit()

    async with session_factory() as session2:
        res_redeem = await redeem_code_to_wallet(session2, gift["code"], 101, "claimer101")
        assert res_redeem["ok"] is True
        assert await WalletRepository(session2).get_balance(101) == 10_000


@pytest.mark.anyio
async def test_admin_coupon_save_bounds_rejected():
    for bad_payload in (
        {"code": "BADPCT", "percent": 150, "amount": 0},
        {"code": "BADNEG", "percent": 0, "amount": -500},
    ):
        req = make_mocked_request("POST", "/api/admin/coupons/save", app={})
        req.json = AsyncMock(return_value=bad_payload)
        with patch("bot.web.admin_plans._check_admin", return_value={"id": 1}):
            resp = await post_admin_coupon_save(req)
        assert resp.status == 400


# ---------------------------------------------------------------------- #
# 4. Crypto Gateways: 0-POL, TX-Hijack Upper Bounds, Expiry, TON Atomicity
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_crypto_pol_trx_bounds_unique_units_and_ton_expiry(session_factory):
    # 0 POL and oversized POL rejected
    mock_rpc_zero = {
        "result": {"to": "0x1111111111111111111111111111111111111111", "value": "0x0", "blockNumber": "0x1"}
    }
    mock_receipt_ok = {"result": {"status": "0x1"}}
    mock_block = {"result": {"timestamp": "0x67000000"}}

    async def _fake_rpc_call(session_http, url, payload, *a, **kw):
        m = MagicMock()
        m.status = 200
        method = payload.get("method")
        if method == "eth_getTransactionByHash":
            m.json = AsyncMock(return_value=mock_rpc_zero)
        elif method == "eth_getTransactionReceipt":
            m.json = AsyncMock(return_value=mock_receipt_ok)
        else:
            m.json = AsyncMock(return_value=mock_block)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=m)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    with patch("bot.services.crypto.pol.aiohttp.ClientSession.post", side_effect=_fake_rpc_call):
        ok_zero, msg_zero, _ = await verify_polygon_transaction(
            "0x" + "a" * 64,
            "0x1111111111111111111111111111111111111111",
            min_wei=10**18,
            min_timestamp_ms=0,
        )
        assert ok_zero is False
        assert msg_zero

    # Huge TX exceeding max_wei rejected (anti-hijack)
    mock_rpc_huge = {
        "result": {
            "to": "0x1111111111111111111111111111111111111111",
            "value": hex(50 * 10**18),
            "blockNumber": "0x1",
        }
    }

    async def _fake_rpc_huge(session_http, url, payload, *a, **kw):
        m = MagicMock()
        m.status = 200
        method = payload.get("method")
        if method == "eth_getTransactionByHash":
            m.json = AsyncMock(return_value=mock_rpc_huge)
        elif method == "eth_getTransactionReceipt":
            m.json = AsyncMock(return_value=mock_receipt_ok)
        else:
            m.json = AsyncMock(return_value=mock_block)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=m)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    with patch("bot.services.crypto.pol.aiohttp.ClientSession.post", side_effect=_fake_rpc_huge):
        ok_big, _, _ = await verify_polygon_transaction(
            "0x" + "b" * 64,
            "0x1111111111111111111111111111111111111111",
            min_wei=10 * 10**18,
            min_timestamp_ms=0,
            max_wei=11 * 10**18,
        )
        assert ok_big is False

    # TRX post-expiry & max_sun rejection
    tron_payload = {
        "ret": [{"contractRet": "SUCCESS"}],
        "raw_data": {
            "timestamp": 2_000_000_000_000,
            "contract": [
                {
                    "type": "TransferContract",
                    "parameter": {
                        "value": {
                            "to_address": "41" + "22" * 20,
                            "amount": 100_000_000,
                        }
                    },
                }
            ],
        },
    }
    mock_tron_resp = MagicMock()
    mock_tron_resp.status = 200
    mock_tron_resp.json = AsyncMock(return_value=tron_payload)
    cm_tron = MagicMock()
    cm_tron.__aenter__ = AsyncMock(return_value=mock_tron_resp)
    cm_tron.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("bot.services.crypto.trx.hex_to_tron_address", return_value="TValid"),
        patch("bot.services.crypto.trx.aiohttp.ClientSession.post", return_value=cm_tron),
    ):
        ok_trx_late, _, _ = await verify_tron_transaction(
            "tx_late",
            "TValid",
            min_sun=90_000_000,
            min_timestamp_ms=1_000_000_000_000,
            max_timestamp_ms=1_500_000_000_000,
        )
        assert ok_trx_late is False
        ok_trx_huge, _, _ = await verify_tron_transaction(
            "tx_huge", "TValid", min_sun=10_000_000, min_timestamp_ms=0, max_sun=20_000_000
        )
        assert ok_trx_huge is False

    # DB unique unit allocation, cancelled/expired guard, TON utime > expires_at + 60s
    async with session_factory() as session:
        await _seed_user_wallet(session, 1003, balance=0)
        repo = CryptoRepository(session)
        u1 = await repo.allocate_unique_crypto_units(10_000_000, 100, "TRX")
        inv1 = await repo.create_invoice(1003, 50_000, "10.0000", u1, "TAddr", currency="TRX")
        u2 = await repo.allocate_unique_crypto_units(10_000_000, 100, "TRX")
        assert u2 != u1

        # Cancelled invoice CANNOT be marked paid
        inv1.status = "cancelled"
        await session.flush()
        assert await repo.mark_paid(inv1.id, "tx_cancelled") is None

        # Invoice expired 5 hours ago (>2h grace) CANNOT be marked paid
        inv_old = CryptoInvoice(
            telegram_id=1003,
            amount_toman=50_000,
            amount_ton="1",
            nanotons=10**9,
            currency="TON",
            comment="REMNA_OLD",
            pay_address="UQTest",
            status="expired",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        session.add(inv_old)
        await session.flush()
        assert await repo.mark_paid(inv_old.id, "tx_old_exp", allow_expired=True) is None

        # TON transaction sent way after expiry window rejected
        inv_ton = await repo.create_invoice(1003, 50_000, "1", 10**9, "UQTest", expires_minutes=10, currency="TON")
        exp_ts = int(inv_ton.expires_at.timestamp())
        late_tx = {
            "hash": "ton_late_hash",
            "utime": exp_ts + 600,
            "in_msg": {"source": "UQSndr", "value": str(10**9), "message": inv_ton.comment},
        }
        credited = await verify_and_credit_ton_invoice(session, inv_ton, [late_tx])
        assert credited[0] is False


# ---------------------------------------------------------------------- #
# 5. Bank SMS Replay Hash Dedup, Parser Fixes & Card 6h Double-Topup Block
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_sms_replay_hash_dedup_and_bank_sms_parser_fixes(session_factory):
    # Parser: hyphenated withdrawal NOT parsed as deposit, balance lines skipped
    parsed_wd = parse_bank_sms("حساب 1234\nبرداشت: 140,500-\nمانده: 5,000,000 ریال")
    assert parsed_wd.is_deposit is False

    parsed_dep = parse_bank_sms("واریز به حساب 1234\nمبلغ 250,012 ریال\nموجودی 9,000,000 ریال")
    assert parsed_dep.is_deposit is True
    assert parsed_dep.amount_toman == 25_001

    async with session_factory() as session:
        await _seed_user_wallet(session, 1004, balance=0)
        inv = CardAutoInvoice(
            invoice_uuid="inv-sms-1",
            telegram_id=1004,
            base_amount=25_000,
            exact_amount=25_001,
            exact_rial=250_010,
            card_number="6037991122334455",
            card_holder="Test",
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        session.add(inv)
        await session.commit()

        store = SimpleNamespace(card_auto_enabled=True, admin_topic_payments=None, topic_topups=None)
        settings = SimpleNamespace(ADMIN_CHAT_ID=-1001, ADMIN_TOPIC_TOPUPS=None)
        raw_sms = "بانک ملی\nواریز مبلغ 250,010 ریال به حساب 4455"

        r1 = await process_incoming_sms(session, None, settings, store, "+981000", raw_sms)
        assert r1["action"] == "credited"
        await session.commit()
        assert await WalletRepository(session).get_balance(1004) == 25_001

        # Exact replay (or Persian-digit replay) MUST be blocked by sms_hash
        r2 = await process_incoming_sms(session, None, settings, store, "+981000", raw_sms)
        assert r2["action"] == "duplicate_ignored"
        assert await WalletRepository(session).get_balance(1004) == 25_001


@pytest.mark.anyio
async def test_manual_card_topup_blocked_when_exact_card_auto_paid_within_6h(session_factory):
    async with session_factory() as session:
        await _seed_user_wallet(session, 1005, balance=50_001)
        session.add(
            CardAutoInvoice(
                invoice_uuid="inv-recent-6h",
                telegram_id=1005,
                base_amount=50_000,
                exact_amount=50_001,
                exact_rial=500_010,
                card_number="6037991122334455",
                card_holder="Test",
                status="paid",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
                paid_at=datetime.now(timezone.utc) - timedelta(minutes=20),
            )
        )
        await session.commit()

    cache = FastCache(redis_client=None)

    class _SessionCM:
        async def __aenter__(self):
            return session_factory()

        async def __aexit__(self, *a):
            pass

    app = {
        "session_factory": session_factory,
        "cache": cache,
        "bot": AsyncMock(),
        "settings": SimpleNamespace(ADMIN_CHAT_ID=-1001, ADMIN_TOPIC_TOPUPS=None),
        "remnawave": AsyncMock(),
    }
    req = make_mocked_request("POST", "/api/user/topup/card", app=app)
    req.json = AsyncMock(return_value={"amount": 50_001, "receipt_photo_b64": ""})

    store = SimpleNamespace(
        invite_only=False,
        card_to_card_enabled=True,
        card_number="6037991122334455",
        card_holder="Test",
        min_topup_amount=10_000,
        max_topup_amount=50_000_000,
    )
    with (
        patch("bot.web.user_topup.require_user", return_value=({"id": 1005, "username": "u1005"}, None)),
        patch("bot.web.user_topup.get_store_settings", AsyncMock(return_value=store)),
    ):
        resp = await post_user_topup_card(req)

    assert resp.status == 400
    data = json.loads(resp.text)
    assert data["ok"] is False


# ---------------------------------------------------------------------- #
# 6. Gift Service Fixes: get_by_id, No VIP Discount Arbitrage, Claim Revert
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_gift_service_get_by_id_no_vip_discount_and_transient_claim_revert(session_factory):
    async with session_factory() as session:
        # VIP sender (has 500k spent paid orders -> would get VIP discount if buggy)
        await _seed_user_wallet(session, 1006, balance=100_000)
        await _seed_user_wallet(session, 1007, balance=0)
        svc = Service(name="Gift Gold", price=80_000, duration_days=30, traffic_gb=30, max_purchases=5)
        session.add(svc)
        await session.flush()
        session.add(Order(telegram_id=1006, service_id=svc.id, service_name="Prior", amount=1_000_000, status="paid"))
        await session.commit()

        # Verify ServiceRepository.get_by_id alias
        fetched = await ServiceRepository(session).get_by_id(svc.id)
        assert fetched is not None and fetched.id == svc.id

        # Creating SERVICE gift MUST charge full price (80k), NOT VIP-discounted price
        res = await create_gift(session, 1006, "VIP", delivery_type="LINK", gift_type="SERVICE", service_id=svc.id)
        assert res["ok"] is True
        assert await WalletRepository(session).get_balance(1006) == 20_000
        await session.commit()

    # Check get_user_gifts includes gift_desc
    async with session_factory() as session_list:
        listed = await get_user_gifts(session_list, 1006)
        assert len(listed["sent"]) == 1
        assert "gift_desc" in listed["sent"][0]

    # Claiming SERVICE gift when panel throws transient error MUST revert is_claimed=False & NOT credit wallet!
    async with session_factory() as session_claim:
        broken_panel = AsyncMock()
        broken_panel.get_users_by_telegram_id = AsyncMock(side_effect=RuntimeError("panel timeout"))
        with patch("bot.services.purchases.execute_purchase", side_effect=RuntimeError("panel timeout")):
            claim_res = await claim_gift(
                session_claim,
                res["code"],
                1007,
                "claimer1007",
                remnawave=broken_panel,
                session_factory=session_factory,
            )
        assert claim_res["ok"] is False

    async with session_factory() as session_chk:
        gc = (await session_chk.execute(select(GiftCard).where(GiftCard.code == res["code"]))).scalar_one()
        assert gc.is_claimed is False
        assert await WalletRepository(session_chk).get_balance(1007) == 0


# ---------------------------------------------------------------------- #
# 7. Wheel Unlimited Traffic Fallback & Bound Coupon + Trial No Referrer
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_wheel_unlimited_traffic_fallback_and_bound_coupon(session_factory):
    future_iso = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    async with session_factory() as session:
        await _seed_user_wallet(session, 1008, balance=0)
        await session.commit()

        remnawave = AsyncMock()
        remnawave.get_users_by_telegram_id = AsyncMock(
            return_value=[
                {
                    "id": 8801,
                    "username": "u_unlim",
                    "status": "ACTIVE",
                    "expireAt": future_iso,
                    "trafficLimitBytes": 0,  # Unlimited traffic!
                }
            ]
        )
        remnawave.update_user_subscription = AsyncMock(return_value={"id": 8801})
        cache = FastCache(redis_client=None)

        traffic_prize = {"id": "2gb", "name": "۲ گیگ هدیه", "icon": "👑", "type": "traffic", "value": 2}
        with patch("bot.services.wheel_service.random.choices", return_value=[traffic_prize]):
            res_t = await execute_lucky_wheel_spin(session, remnawave, cache, None, 1008)
        assert res_t["ok"] is True
        # Because account had unlimited traffic (0), update_user_subscription extends expireAt while keeping trafficLimitBytes=0!
        call_args = remnawave.update_user_subscription.call_args.args
        assert call_args[0] == 8801 and call_args[2] == 0

        # Coupon prize binds coupon to telegram_id
        user = await UserRepository(session).get_by_telegram_id(1008)
        user.spin_tickets = 1
        user.wheel_last_spin_at = None
        await session.commit()

        cpn_prize = {"id": "discount10", "name": "۱۰٪ کد تخفیف ویژه", "icon": "🎟", "type": "coupon", "code": "OFF10"}
        with patch("bot.services.wheel_service.random.choices", return_value=[cpn_prize]):
            res_c = await execute_lucky_wheel_spin(session, remnawave, cache, None, 1008, use_ticket=True)
        assert res_c["ok"] is True
        code = res_c["prize"].get("code")
        assert code and code.startswith("WHEEL10_")
        cpn = (await session.execute(select(Coupon).where(Coupon.code == code))).scalar_one()
        assert cpn.bound_telegram_id == 1008

        # Unlimited-traffic referrer marks reward.applied=False & does NOT set finite trafficLimitBytes
        inviter = await _seed_user_wallet(session, 1080, balance=0)
        referee = await _seed_user_wallet(session, 1081, balance=0, referred_by_id=inviter.telegram_id)
        await session.commit()
        rem_ref = AsyncMock()
        rem_ref.get_users_by_telegram_id = AsyncMock(
            return_value=[{"id": 8888, "status": "ACTIVE", "trafficLimitBytes": 0}]
        )
        rem_ref.update_user = AsyncMock()
        with patch("bot.services.purchases.get_store_settings", AsyncMock(return_value=SimpleNamespace(
            referral_enabled=True, referral_reward_gb=5
        ))):
            await maybe_reward_referrer(AsyncMock(), session, rem_ref, referee)
        rem_ref.update_user.assert_not_awaited()
        rr = (await session.execute(select(ReferralReward).where(ReferralReward.referee_id == 1081))).scalar_one()
        assert rr.applied is False


# ---------------------------------------------------------------------- #
# 8. Birthday Lock After Set & Invite-Only Enforcement
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_birthday_locked_after_first_set_and_invite_only_checked(session_factory):
    async with session_factory() as session:
        await _seed_user_wallet(session, 1009, balance=0)
        await session.commit()

    store_open = SimpleNamespace(access_mode="open")
    app = {"session_factory": session_factory, "cache": FastCache(redis_client=None), "remnawave": AsyncMock()}

    async def _post_bday(bdate: str):
        req = make_mocked_request("POST", "/api/user/birthday", app=app)
        req.json = AsyncMock(return_value={"birth_date": bdate})
        with (
            patch("bot.web.user_profile.require_user", return_value=({"id": 1009}, None)),
            patch("bot.services.app_settings.get_store_settings", AsyncMock(return_value=store_open)),
        ):
            return await post_user_set_birthday(req)

    r1 = await _post_bday("1375/05/12")
    assert r1.status == 200
    r2 = await _post_bday("1375/05/13")
    assert r2.status == 400


# ---------------------------------------------------------------------- #
# 9. Invite-Only Deep-Link Validation & Uninvited TMA No User Row Created
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_invite_only_db_validation_and_uninvited_tma_isolation(session_factory):
    async with session_factory() as session:
        # Uninvited TMA /api/user/me under invite_only MUST return 403 and NOT create a User row
        store_inv = SimpleNamespace(
            access_mode="invite_only",
            maintenance_mode=False,
            loyalty_enabled=False,
            birthday_enabled=False,
            custom_plan_enabled=False,
        )
        app = {
            "session_factory": session_factory,
            "cache": FastCache(redis_client=None),
            "remnawave": AsyncMock(),
            "settings": SimpleNamespace(ADMIN_IDS=[], TIMEZONE="Asia/Tehran"),
        }
        app["remnawave"].get_users_by_telegram_id = AsyncMock(return_value=[])
        req = make_mocked_request("GET", "/api/user/me", app=app)
        with (
            patch("bot.web.user_profile.require_user", return_value=({"id": 777001, "username": "stranger"}, None)),
            patch("bot.services.app_settings.get_store_settings", AsyncMock(return_value=store_inv)),
            patch("bot.web.user_profile.get_store_settings", AsyncMock(return_value=store_inv)),
        ):
            resp = await get_user_me(req)
        assert resp.status == 200
        assert json.loads(resp.text)["data"]["is_invite_only"] is True
        assert await UserRepository(session).get_by_telegram_id(777001) is None

        req_bday_denied = make_mocked_request("POST", "/api/user/birthday", app=app)
        req_bday_denied.json = AsyncMock(return_value={"birth_date": "1375/05/12"})
        with (
            patch("bot.web.user_profile.require_user", return_value=({"id": 777001, "username": "stranger"}, None)),
            patch("bot.services.app_settings.get_store_settings", AsyncMock(return_value=store_inv)),
        ):
            resp_denied = await post_user_set_birthday(req_bday_denied)
        assert resp_denied.status == 403

        # Bot /start with forged inv_123 or nonexistent ref_999999 / ad_FAKE rejected under invite_only
        for bad_arg in ("/start inv_123", "/start ref_999999", "/start ad_FAKE"):
            msg = AsyncMock()
            msg.from_user = SimpleNamespace(id=777002, username="attacker", full_name="Attacker")
            msg.text = bad_arg
            msg.answer = AsyncMock()
            state = AsyncMock()
            bot = AsyncMock()
            remnawave = AsyncMock()
            remnawave.get_users_by_telegram_id = AsyncMock(return_value=[])
            with patch("bot.handlers.start.get_store_settings", AsyncMock(return_value=store_inv)):
                await cmd_start(msg, bot, UserRepository(session), session, state, remnawave=remnawave)
            assert await UserRepository(session).get_by_telegram_id(777002) is None

        # Valid existing referrer DOES pass under invite_only
        await _seed_user_wallet(session, 888001, balance=0)
        await session.commit()
        msg_ok = AsyncMock()
        msg_ok.from_user = SimpleNamespace(id=777003, username="invited", full_name="Invited User")
        msg_ok.text = "/start ref_888001"
        msg_ok.answer = AsyncMock()
        bot_ok = AsyncMock()
        rem_ok = AsyncMock()
        rem_ok.get_users_by_telegram_id = AsyncMock(return_value=[])
        with (
            patch("bot.handlers.start.get_store_settings", AsyncMock(return_value=store_inv)),
            patch("bot.handlers.start.reset_menu", AsyncMock()),
            patch("bot.handlers.start.render_menu", AsyncMock()),
        ):
            await cmd_start(msg_ok, bot_ok, UserRepository(session), session, AsyncMock(), remnawave=rem_ok)
        created = await UserRepository(session).get_by_telegram_id(777003)
        assert created is not None and created.referred_by_id == 888001

        # Valid existing Campaign ad_ code DOES pass under invite_only
        session.add(Campaign(code="promo1", name="Promo", cost=0))
        await session.commit()
        msg_ad = AsyncMock()
        msg_ad.from_user = SimpleNamespace(id=777004, username="ad_user", full_name="Ad User")
        msg_ad.text = "/start ad_PROMO1"
        msg_ad.answer = AsyncMock()
        with (
            patch("bot.handlers.start.get_store_settings", AsyncMock(return_value=store_inv)),
            patch("bot.handlers.start.reset_menu", AsyncMock()),
            patch("bot.handlers.start.render_menu", AsyncMock()),
        ):
            await cmd_start(msg_ad, bot_ok, UserRepository(session), session, AsyncMock(), remnawave=rem_ok)
        ad_u = await UserRepository(session).get_by_telegram_id(777004)
        assert ad_u is not None and ad_u.campaign_code == "promo1"


# ---------------------------------------------------------------------- #
# 10. Refund Disable Instead of 0-Unlimited, Ban Cache Invalidation,
#     Auto-Renew Extra-Time Skip & Backup/Restore Round-Trip
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_refund_disables_and_ban_clears_both_caches_and_auto_renew_skips_extra_time(
    session_factory, tmp_path: Path
):
    # A. Refund subtraction reaching 0 MUST disable user instead of setting 0 (unlimited)
    rem_refund = AsyncMock()
    rem_refund.get_users_by_telegram_id = AsyncMock(
        return_value=[
            {
                "id": 5001,
                "trafficLimitBytes": 30 * (1024**3),
                "expireAt": (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        ]
    )
    rem_refund.update_user_subscription = AsyncMock()
    order_mock = SimpleNamespace(
        telegram_id=1010, panel_user_id=5001, traffic_gb=30, duration_days=30, is_renewal=True
    )
    await _revert_panel_subscription(rem_refund, order_mock)
    rem_refund.update_user_subscription.assert_awaited_once()
    call_args = rem_refund.update_user_subscription.call_args
    assert call_args.args[2] > 0  # NEVER 0 (unlimited)
    assert call_args.kwargs.get("status") == "DISABLED"

    # B. Ban endpoint clears BOTH tma:ban:{tid} and user:ban:{tid}
    cache = FastCache(redis_client=None)
    await cache.set("tma:ban:1011", "0", ttl_seconds=60)
    await cache.set("user:ban:1011", "0", ttl_seconds=60)
    async with session_factory() as session:
        await _seed_user_wallet(session, 1011, balance=0)
        await session.commit()
    app_ban = {"session_factory": session_factory, "cache": cache, "remnawave": AsyncMock(), "bot": AsyncMock()}
    app_ban["remnawave"].get_users_by_telegram_id = AsyncMock(return_value=[])
    req_ban = make_mocked_request("POST", "/api/admin/users/ban", app=app_ban)
    req_ban.json = AsyncMock(return_value={"telegram_id": 1011})
    with patch("bot.web.admin_users_actions._check_admin", return_value={"id": 1}):
        resp_ban = await post_admin_toggle_ban(req_ban)
    assert resp_ban.status == 200
    assert await cache.get("tma:ban:1011") is None
    assert await cache.get("user:ban:1011") is None

    # C. Auto-renew skips Extra Time add-on order & renews base plan instead
    async with session_factory() as session:
        await _seed_user_wallet(session, 1012, balance=100_000, auto_renew=True)
        base_svc = Service(name="Base 30d 30GB", price=50_000, duration_days=30, traffic_gb=30, badge=None)
        time_svc = Service(name="Extra Time 7d", price=10_000, duration_days=7, traffic_gb=0, badge="time")
        session.add_all([base_svc, time_svc])
        await session.flush()
        now = datetime.now(timezone.utc)
        session.add(
            Order(
                telegram_id=1012,
                service_id=base_svc.id,
                service_name=base_svc.name,
                amount=50_000,
                duration_days=30,
                traffic_gb=30,
                panel_user_id=6001,
                panel_username="u1012",
                status="paid",
                created_at=now - timedelta(days=20),
            )
        )
        session.add(
            Order(
                telegram_id=1012,
                service_id=time_svc.id,
                service_name=time_svc.name,
                amount=10_000,
                duration_days=7,
                traffic_gb=0,
                panel_user_id=6001,
                panel_username="u1012",
                status="paid",
                created_at=now - timedelta(days=2),
            )
        )
        await session.commit()

    rem_auto = AsyncMock()
    exp_soon = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rem_auto.get_users_by_telegram_id = AsyncMock(
        return_value=[{"id": 6001, "username": "u1012", "status": "ACTIVE", "expireAt": exp_soon}]
    )
    rem_auto.update_user_subscription = AsyncMock(
        return_value={"id": 6001, "username": "u1012", "subscriptionUrl": "https://sub/6001"}
    )
    renewed = await process_auto_renewals(None, session_factory, rem_auto, cache=FastCache(redis_client=None))
    assert renewed == 1
    async with session_factory() as session_after:
        latest = (
            await session_after.execute(
                select(Order).where(Order.telegram_id == 1012).order_by(Order.id.desc()).limit(1)
            )
        ).scalar_one()
        assert latest.service_id == base_svc.id

    # D. Backup & Restore round-trip for Coupon.kind/bound_telegram_id, GiftCard, CardAutoInvoice, BankSmsLog
    async with session_factory() as session:
        session.add(
            Coupon(
                code="BKPVOUCH",
                kind="voucher",
                bound_telegram_id=1011,
                discount_amount=30_000,
                max_uses=1,
            )
        )
        session.add(
            GiftCard(
                code="GIFT-BKP1",
                sender_telegram_id=1011,
                delivery_type="LINK",
                gift_type="BALANCE",
                amount=15_000,
            )
        )
        session.add(
            CardAutoInvoice(
                invoice_uuid="bkp-inv-1",
                telegram_id=1011,
                base_amount=40_000,
                exact_amount=40_003,
                exact_rial=400_030,
                card_number="6037991122334455",
                card_holder="Test",
                status="pending",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )
        )
        session.add(
            BankSmsLog(
                sender="+981000",
                raw_message="واریز 400030 ریال",
                sms_hash="hash_bkp_1",
                amount_toman=40_003,
                processed=True,
            )
        )
        await session.commit()
        backup_path = await create_database_backup(session, out_dir=tmp_path)
        assert backup_path.is_file()

        # Wipe target tables and restore from JSON backup
        for tbl in (BankSmsLog, CardAutoInvoice, GiftCard, Coupon):
            rows = (await session.execute(select(tbl))).scalars().all()
            for r in rows:
                await session.delete(r)
        await session.commit()

        counts = await restore_database_backup(session, backup_path)
        assert counts.get("gift_cards", 0) >= 1
        assert counts.get("card_auto_invoices", 0) >= 1
        assert counts.get("bank_sms_logs", 0) >= 1

        restored_cpn = (await session.execute(select(Coupon).where(Coupon.code == "BKPVOUCH"))).scalar_one()
        assert restored_cpn.kind == "voucher" and restored_cpn.bound_telegram_id == 1011


# ---------------------------------------------------------------------- #
# 11. Track A Remaining 1C Items: Bot VIP Loyalty, Refund Cache Clear,
#     Stars Expiry + Cache Clear, Infra HTTP Port Default, Auth Dedup
# ---------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_bot_vip_loyalty_refund_cache_stars_expiry_infra_port_and_auth_dedup(session_factory):
    cache = FastCache(redis_client=None)

    # A. Bot VIP loyalty discount calculation & refund cache invalidation
    async with session_factory() as session:
        await _seed_user_wallet(session, 1020, balance=0)
        # 2.5M spent -> Gold tier (5% discount)
        ord1 = Order(
            telegram_id=1020,
            service_id=None,
            service_name="Gold Qualifying",
            amount=2_500_000,
            status="paid",
        )
        session.add(ord1)
        await session.flush()

        loyalty_disc, total_disc = await prepare_bot_discounts(session, 1020, 100_000, coupon_discount=10_000)
        assert loyalty_disc == 5_000
        assert total_disc == 15_000

        # Populate user dashboard & loyalty caches, then trigger refund -> both cleared
        await cache.set("tma:user:1020:dashboard:default", {"cached": True}, ttl_seconds=60)
        await cache.set("loyalty:user:v2:1020", {"tier_id": "gold"}, ttl_seconds=60)

        call = AsyncMock()
        call.from_user = SimpleNamespace(id=1, username="admin")
        call.data = f"adm:ord:refyes:{ord1.id}:all:0"
        call.answer = AsyncMock()
        with (
            patch("bot.handlers.admin_orders_detail._is_admin", return_value=True),
            patch("bot.handlers.admin_orders_detail._render_order_detail", AsyncMock()),
        ):
            await order_view_or_refund(
                call, AsyncMock(), UserRepository(session), session, AsyncMock(), remnawave=None, cache=cache
            )
        assert await cache.get("tma:user:1020:dashboard:default") is None
        assert await cache.get("loyalty:user:v2:1020") is None

    # B. Stars pre-checkout rejects expired 5-part payload & successful payment clears user cache
    expired_payload = f"stars_topup:1021:50000:50:{int(time.time()) - 120}"
    pq = AsyncMock()
    pq.id = "pq_exp"
    pq.invoice_payload = expired_payload
    pq.from_user = SimpleNamespace(id=1021)
    pq.currency = "XTR"
    pq.total_amount = 50
    bot_stars = AsyncMock()
    await stars_pre_checkout_handler(pq, bot_stars)
    assert bot_stars.answer_pre_checkout_query.call_args.kwargs.get("ok") is False

    async with session_factory() as session:
        await _seed_user_wallet(session, 1021, balance=0)
        await session.commit()
        await cache.set("tma:user:1021:dashboard", {"stale": True}, ttl_seconds=60)
        msg_stars = AsyncMock()
        msg_stars.from_user = SimpleNamespace(id=1021)
        msg_stars.successful_payment = SimpleNamespace(
            invoice_payload=f"stars_topup:1021:50000:50:{int(time.time()) + 600}",
            telegram_payment_charge_id="chg_stars_1021",
            currency="XTR",
            total_amount=50,
        )
        await stars_successful_payment_handler(msg_stars, AsyncMock(), session, cache=cache)
        assert await cache.get("tma:user:1021:dashboard") is None
        assert await WalletRepository(session).get_balance(1021) == 50_000

    # C. Admin network check HTTP with port=None falls back to port 80 (not None -> TypeError)
    app_infra = {"admin_id": 1, "settings": None}
    req_infra = make_mocked_request("POST", "/api/admin/tools/check_host", app=app_infra)
    req_infra.json = AsyncMock(return_value={"host": "1.1.1.1", "check_type": "http", "max_nodes": 3})
    mock_writer = MagicMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    with (
        patch("bot.web.admin_infra_api._check_admin", return_value={"id": 1, "is_admin": True}),
        patch("aiohttp.ClientSession.get", side_effect=RuntimeError("check-host down")),
        patch("asyncio.open_connection", AsyncMock(return_value=(MagicMock(), mock_writer))) as mock_conn,
    ):
        resp_infra = await get_admin_tools_check_host(req_infra)
    assert resp_infra.status == 200
    assert mock_conn.call_args.args == ("1.1.1.1", 80)

    # D. Auth caching avoids duplicate HMAC calls on a single request
    req_auth = make_mocked_request("GET", "/api/admin/users", app={})
    admin_dict = {"id": 99, "is_admin": True, "is_preview": False}
    with (
        patch("bot.web.user_common.get_authenticated_user", return_value=admin_dict) as mock_u_auth,
        patch("bot.web.admin_common.get_authenticated_user", return_value=admin_dict) as mock_a_auth,
    ):
        assert _check_user(req_auth) == admin_dict
        assert _check_admin(req_auth) == admin_dict
        assert mock_u_auth.call_count == 1
        assert mock_a_auth.call_count == 0
