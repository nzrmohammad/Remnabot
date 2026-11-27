"""Tests for Section 5 engagement features:
1. Smart Renewal Advisor
2. Loyalty-Tiered Card & Story Themes
3. Weekly Interactive Quests (spin_tickets + badges ONLY)
4. Group Gift / Red Packet (atomic split, anti-double-claim, self-claim guard, refund)
5. Leaderboard Champion Badge
6. Direct P2P Wallet Transfer (atomic balance conservation & abuse guards)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import select

from bot.db.models import Order, OrderStatus, RedPacket, User, Wallet
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.engagement_service import (
    claim_red_packet,
    claim_weekly_quest_reward,
    compute_leaderboard_champion_badge,
    compute_renewal_advisor,
    create_red_packet,
    get_weekly_quests_state,
    record_weekly_quest_event,
    refund_red_packet,
    resolve_card_themes,
    set_user_card_theme,
    transfer_wallet_balance,
)
from bot.services.gift_service import redeem_code_to_wallet
from bot.services.wallet_history import fetch_user_transactions
from bot.web.cache import FastCache
from bot.web.server import create_web_app
from tests.test_tma_web import generate_valid_init_data


def _make_remnawave_mock():
    rm = MagicMock()
    rm.get_users_by_telegram_id = AsyncMock(return_value=[])
    rm.get_all_panel_users = AsyncMock(return_value=[])
    rm.get_nodes = AsyncMock(return_value=[])
    return rm


def test_smart_renewal_advisor_recommendations():
    cs = SimpleNamespace(enabled=True, min_gb=10, max_gb=300, min_days=10, max_days=180)
    fast = compute_renewal_advisor(
        {"avg_daily_gb": 1.87, "status": "fast", "days_left_plan": 20},
        {"days_left": 20, "traffic_remaining_gb": 10.0},
        custom_settings=cs,
        lang="fa",
    )
    assert fast["recommended_gb"] >= 80
    assert fast["recommended_gb"] % 5 == 0
    assert fast["recommended_days"] == 30
    assert "/روز" not in fast["summary"]
    assert " و 30 روز" in fast["summary"]
    assert fast["custom_plan_enabled"] is True

    idle_en = compute_renewal_advisor(
        {"avg_daily_gb": 0.0, "status": "idle", "days_left_plan": 15},
        {"days_left": 15, "traffic_remaining_gb": 20.0},
        custom_settings=cs,
        lang="en",
    )
    assert idle_en["recommended_gb"] == 30
    assert "Apply in Custom Plan" == idle_en["cta_label"]


def test_leaderboard_champion_badge():
    badge = compute_leaderboard_champion_badge(
        {"weekly": {"my_rank": 1, "my_used_gb": 48.2}, "daily": {"my_rank": 3, "my_used_gb": 5.0}},
        lang="fa",
    )
    assert badge is not None
    assert badge["rank"] == 1
    assert badge["icon"] == "🥇"

    none_badge = compute_leaderboard_champion_badge(
        {"weekly": {"my_rank": 4, "my_used_gb": 12.0}},
        lang="en",
    )
    assert none_badge is None


@pytest.mark.anyio
async def test_loyalty_card_themes_gating_and_persistence(session_factory):
    async with session_factory() as session:
        tid = 770011
        session.add(User(telegram_id=tid, username="theme_user", full_name="Theme User"))
        await session.commit()

        # Bronze user cannot select emerald (Silver+) or amber_vip (Gold+)
        denied = await set_user_card_theme(session, tid, "emerald", lang="en")
        assert denied["ok"] is False
        assert denied["status_code"] == 403

        # Bronze user can select ocean
        ok_res = await set_user_card_theme(session, tid, "ocean", lang="fa")
        assert ok_res["ok"] is True
        assert ok_res["card_theme"] == "ocean"

        # Upgrade user spend to 3,000,000 (Gold tier) -> amber_vip unlocks
        session.add(Order(telegram_id=tid, service_name="VIP Pack", amount=3_000_000, status=OrderStatus.PAID.value))
        await session.commit()

        gold_ok = await set_user_card_theme(session, tid, "amber_vip", lang="fa")
        assert gold_ok["ok"] is True
        assert gold_ok["card_theme"] == "amber_vip"

        resolved = resolve_card_themes("gold", "amber_vip", lang="en")
        assert resolved["selected"] == "amber_vip"
        assert next(t for t in resolved["themes"] if t["id"] == "amber_vip")["unlocked"] is True
        assert next(t for t in resolved["themes"] if t["id"] == "obsidian_diamond")["unlocked"] is False


@pytest.mark.anyio
async def test_weekly_quests_spin_tickets_only_and_single_claim(session_factory):
    async with session_factory() as session:
        tid = 770022
        session.add(User(telegram_id=tid, username="quest_user", spin_tickets=0))
        session.add(Wallet(telegram_id=tid, balance=50_000))
        await session.commit()

        # Claim before completion fails
        early = await claim_weekly_quest_reward(session, tid, "weekly_speedtest", lang="en")
        assert early["ok"] is False

        # Complete speedtest quest
        await record_weekly_quest_event(session, tid, "speedtest")
        state = await get_weekly_quests_state(session, tid, lang="fa")
        assert state["reward_policy"] == "spin_tickets_and_badges_only"
        sp_item = next(q for q in state["quests"] if q["id"] == "weekly_speedtest")
        assert sp_item["can_claim"] is True

        # Claim twice in same week -> second fails cleanly, tickets increment by exact +1, wallet untouched
        first_claim = await claim_weekly_quest_reward(session, tid, "weekly_speedtest", lang="fa")
        assert first_claim["ok"] is True
        assert first_claim["reward_type"] == "spin_ticket"
        assert first_claim["spin_tickets"] == 1

        second_claim = await claim_weekly_quest_reward(session, tid, "weekly_speedtest", lang="fa")
        assert second_claim["ok"] is False

        user_row = (await session.execute(select(User).where(User.telegram_id == tid))).scalar_one()
        wallet_row = (await session.execute(select(Wallet).where(Wallet.telegram_id == tid))).scalar_one()
        assert user_row.spin_tickets == 1
        assert wallet_row.balance == 50_000  # Policy: NEVER credit wallet or traffic


@pytest.mark.anyio
async def test_red_packet_create_claim_race_self_guard_and_expiry_refund(session_factory):
    async with session_factory() as session:
        sender_id, c1_id, c2_id, c3_id = 770100, 770101, 770102, 770103
        for uid in (sender_id, c1_id, c2_id, c3_id):
            session.add(User(telegram_id=uid, username=f"u_{uid}", full_name=f"User {uid}"))
        session.add(Wallet(telegram_id=sender_id, balance=25_000))
        await session.commit()

        # Total below min_claims * 5000 rejected
        too_low = await create_red_packet(
            session, sender_telegram_id=sender_id, sender_name="Sender", total_amount=8_000, max_claims=2
        )
        assert too_low["ok"] is False

        # Create 2-slot equal red packet of 20,000 Toman
        created = await create_red_packet(
            session,
            sender_telegram_id=sender_id,
            sender_name="Sender",
            total_amount=20_000,
            max_claims=2,
            split_mode="EQUAL",
            bot_username="remnabot",
        )
        assert created["ok"] is True
        assert created["new_balance"] == 5_000
        code = created["code"]

        # Sender self-claim blocked
        self_claim = await claim_red_packet(session, code=code, claimer_telegram_id=sender_id)
        assert self_claim["ok"] is False

        # First claimer succeeds (10,000)
        res1 = await claim_red_packet(session, code=code, claimer_telegram_id=c1_id)
        assert res1["ok"] is True
        assert res1["amount"] == 10_000

        # Duplicate claim by same user blocked
        dup = await claim_red_packet(session, code=code, claimer_telegram_id=c1_id)
        assert dup["ok"] is False

        # Second claimer succeeds via unified redeem_code_to_wallet (10,000)
        res2 = await redeem_code_to_wallet(session, code, c2_id)
        assert res2["ok"] is True
        assert res2["amount"] == 10_000

        # Third claimer hits exhausted limit
        res3 = await claim_red_packet(session, code=code, claimer_telegram_id=c3_id)
        assert res3["ok"] is False

        # Create an expired packet and verify refund
        created_exp = await create_red_packet(
            session, sender_telegram_id=c1_id, sender_name="C1", total_amount=10_000, max_claims=2
        )
        assert created_exp["ok"] is True
        rp_obj = (await session.execute(select(RedPacket).where(RedPacket.code == created_exp["code"]))).scalar_one()

        early_ref = await refund_red_packet(session, packet_id=rp_obj.id, sender_telegram_id=c1_id)
        assert early_ref["ok"] is False

        rp_obj.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await session.commit()

        ref_ok = await refund_red_packet(session, packet_id=rp_obj.id, sender_telegram_id=c1_id)
        assert ref_ok["ok"] is True
        assert ref_ok["refunded_amount"] == 10_000
        assert ref_ok["new_balance"] == 10_000


@pytest.mark.anyio
async def test_red_packet_concurrent_claims_never_overdraft(session_factory):
    async with session_factory() as session:
        sender_id = 770200
        session.add(User(telegram_id=sender_id, username="race_sender"))
        session.add(Wallet(telegram_id=sender_id, balance=100_000))
        claimers = [770201, 770202, 770203, 770204]
        for uid in claimers:
            session.add(User(telegram_id=uid, username=f"r_{uid}"))
        await session.commit()

        created = await create_red_packet(
            session, sender_telegram_id=sender_id, sender_name="Race", total_amount=20_000, max_claims=2, split_mode="RANDOM"
        )
        code = created["code"]

    cache = FastCache()

    async def _attempt(uid: int):
        async with session_factory() as s:
            return await claim_red_packet(s, code=code, claimer_telegram_id=uid, cache=cache)

    results = await asyncio.gather(*(_attempt(uid) for uid in claimers))
    succeeded = [r for r in results if r.get("ok")]
    assert len(succeeded) == 2
    assert sum(int(r["amount"]) for r in succeeded) == 20_000
    assert all(int(r["amount"]) >= 5_000 for r in succeeded)


@pytest.mark.anyio
async def test_p2p_wallet_transfer_atomicity_and_guards(session_factory):
    async with session_factory() as session:
        s_id, r_id, banned_id = 770300, 770301, 770302
        session.add_all([
            User(telegram_id=s_id, username="p2p_alice", full_name="Alice"),
            User(telegram_id=r_id, username="p2p_bob", full_name="Bob"),
            User(telegram_id=banned_id, username="p2p_banned", is_banned=True),
            Wallet(telegram_id=s_id, balance=60_000),
            Wallet(telegram_id=r_id, balance=10_000),
        ])
        await session.commit()

        # Reject self transfer
        assert (await transfer_wallet_balance(session, sender_telegram_id=s_id, recipient_target="@p2p_alice", amount=10_000))["ok"] is False
        # Reject banned recipient
        assert (await transfer_wallet_balance(session, sender_telegram_id=s_id, recipient_target="@p2p_banned", amount=10_000))["ok"] is False
        # Reject nonexistent user
        assert (await transfer_wallet_balance(session, sender_telegram_id=s_id, recipient_target="@nobody_999", amount=10_000))["ok"] is False
        # Reject float / boolean / insufficient amount
        assert (await transfer_wallet_balance(session, sender_telegram_id=s_id, recipient_target="@p2p_bob", amount=True))["ok"] is False
        assert (await transfer_wallet_balance(session, sender_telegram_id=s_id, recipient_target="@p2p_bob", amount=2_000))["ok"] is False

        bot = MagicMock()
        bot.send_message = AsyncMock()
        ok = await transfer_wallet_balance(
            session,
            sender_telegram_id=s_id,
            recipient_target="@p2p_bob",
            amount=25_000,
            note="Gift share",
            bot=bot,
        )
        assert ok["ok"] is True
        assert ok["new_balance"] == 35_000
        assert await WalletRepository(session).get_balance(r_id) == 35_000

        hist_sender = await fetch_user_transactions(session, s_id, lang="en")
        assert any(tx["type"] == "p2p_transfer" and tx["is_positive"] is False and tx["amount"] == 25_000 for tx in hist_sender)


@pytest.mark.anyio
async def test_web_engagement_endpoints_integration(session_factory):
    bot_token = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
    cache = FastCache()
    async with session_factory() as s:
        s.add_all([
            User(telegram_id=770400, username="api_alice", full_name="API Alice"),
            User(telegram_id=770401, username="api_bob", full_name="API Bob"),
            Wallet(telegram_id=770400, balance=100_000),
            Wallet(telegram_id=770401, balance=0),
        ])
        await s.commit()

    bot_mock = MagicMock()
    bot_mock._me = SimpleNamespace(username="remnabot")
    bot_mock.send_message = AsyncMock()
    app = create_web_app(
        bot=bot_mock,
        session_factory=session_factory,
        remnawave=_make_remnawave_mock(),
        settings=SimpleNamespace(TIMEZONE="Asia/Tehran", WEB_TRUSTED_ORIGINS=[], ADMIN_IDS=[], BOT_TOKEN=bot_token),
        cache=cache,
    )
    headers_alice = {"X-Telegram-Init-Data": generate_valid_init_data(bot_token, {"id": 770400, "first_name": "Alice", "username": "api_alice"})}
    headers_bob = {"X-Telegram-Init-Data": generate_valid_init_data(bot_token, {"id": 770401, "first_name": "Bob", "username": "api_bob"})}

    async with TestClient(TestServer(app)) as client:
        # Reject invalid/internal spin event spoofing
        bad_evt = await client.post("/api/user/quests/event", json={"event": "spin"}, headers=headers_alice)
        assert bad_evt.status == 400

        # Valid speedtest event -> claim +1 spin ticket
        ok_evt = await client.post("/api/user/quests/event", json={"event": "speedtest"}, headers=headers_alice)
        assert ok_evt.status == 200
        claim_res = await client.post("/api/user/quests/claim", json={"quest_id": "weekly_speedtest"}, headers=headers_alice)
        assert claim_res.status == 200
        claim_data = await claim_res.json()
        assert claim_data["ok"] is True
        assert claim_data["spin_tickets"] == 1

        # Theme endpoint: Bronze cannot pick obsidian_diamond -> 403
        bad_theme = await client.post("/api/user/theme", json={"theme_id": "obsidian_diamond"}, headers=headers_alice)
        assert bad_theme.status == 403

        # P2P transfer
        p2p_res = await client.post(
            "/api/user/wallet/transfer",
            json={"recipient": "@api_bob", "amount": 15_000, "note": "Lunch"},
            headers=headers_alice,
        )
        assert p2p_res.status == 200
        assert (await p2p_res.json())["new_balance"] == 85_000

        # Red packet create (Alice) & claim (Bob)
        rp_create = await client.post(
            "/api/user/red-packet/create",
            json={"total_amount": 20_000, "max_claims": 2, "split_mode": "EQUAL"},
            headers=headers_alice,
        )
        assert rp_create.status == 200
        rp_code = (await rp_create.json())["code"]

        rp_claim = await client.post("/api/user/red-packet/claim", json={"code": rp_code}, headers=headers_bob)
        assert rp_claim.status == 200
        assert (await rp_claim.json())["amount"] == 10_000

        # Check history endpoint & /api/user/me fields
        hist_res = await client.get("/api/user/red-packets", headers=headers_alice)
        assert hist_res.status == 200
        assert len((await hist_res.json())["red_packets"]["sent"]) == 1

        me_res = await client.get("/api/user/me?refresh=1", headers=headers_alice)
        assert me_res.status == 200
        me_data = (await me_res.json())["data"]
        assert "quests" in me_data
        assert "card_themes" in me_data
        assert me_data["user"]["card_theme"] == "ocean"
