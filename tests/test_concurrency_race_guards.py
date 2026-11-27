"""Tests verifying atomic concurrency boundaries and race condition protections."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from bot.db.models import Base, GiftCard, Topup, TopupStatus, User, Wallet
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.gift_service import _claim_gift_core, create_gift
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.anyio
async def test_concurrent_admin_claim_topup_prevents_double_credit(session_factory):
    """Ensure two simultaneous admin approvals on a top-up result in exactly one winner."""
    async with session_factory() as session:
        user = User(telegram_id=987654, full_name="Topup User")
        session.add(user)
        await session.flush()
        topup = Topup(telegram_id=987654, amount=50_000, status=TopupStatus.PENDING)
        session.add(topup)
        await session.commit()
        topup_id = topup.id

    # Simulate two admin requests arriving concurrently across different sessions
    async def try_claim():
        async with session_factory() as s:
            repo = WalletRepository(s)
            res = await repo.claim_topup(topup_id, approved=True)
            await s.commit()
            return res

    results = await asyncio.gather(try_claim(), try_claim())

    # Exactly one admin approval succeeded
    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]
    assert len(winners) == 1
    assert len(losers) == 1

    # Verify final topup status in DB
    async with session_factory() as s:
        final_topup = await s.get(Topup, topup_id)
        assert final_topup.status == TopupStatus.APPROVED


@pytest.mark.anyio
async def test_concurrent_gift_claim_prevents_double_claim(tmp_path):
    """Ensure two users attempting to claim the same gift card concurrently cannot both succeed."""
    db_file = tmp_path / "test_concurrency_gift.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    sender_id = 111222
    claimer_a = 333444
    claimer_b = 555666

    async with sf() as session:
        session.add(User(telegram_id=sender_id, full_name="Gift Sender"))
        session.add(User(telegram_id=claimer_a, full_name="Claimer A"))
        session.add(User(telegram_id=claimer_b, full_name="Claimer B"))
        session.add(Wallet(telegram_id=sender_id, balance=100_000))
        await session.commit()

        gift_res = await create_gift(
            session=session,
            sender_telegram_id=sender_id,
            delivery_type="LINK",
            gift_type="BALANCE",
            amount=50_000,
        )
        assert gift_res["ok"] is True
        gift_code = gift_res["code"]
        await session.commit()

    # Fire concurrent claims from two claimers
    async def do_claim(claimer_id):
        async with sf() as s:
            return await _claim_gift_core(
                session=s,
                code=gift_code,
                claimer_telegram_id=claimer_id,
                session_factory=sf,
            )

    results = await asyncio.gather(do_claim(claimer_a), do_claim(claimer_b))

    successes = [r for r in results if r.get("ok") is True]
    failures = [r for r in results if r.get("ok") is False]

    assert len(successes) == 1, f"Expected exactly 1 success, got: {results}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got: {results}"
    assert "قبلاً" in failures[0].get("message", "")

    # Verify that only the winning user got the balance
    async with sf() as s:
        w_a = await WalletRepository(s).get_balance(claimer_a)
        w_b = await WalletRepository(s).get_balance(claimer_b)
        assert (w_a == 50_000 and w_b == 0) or (w_b == 50_000 and w_a == 0)

    await engine.dispose()
