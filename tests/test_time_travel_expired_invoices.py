"""Tests verifying time travel edge-cases, invoice expiration, and slot liberation."""
from datetime import datetime, timedelta, timezone

import pytest

from bot.db.models import CryptoInvoice, User
from bot.db.repositories.crypto_repo import CryptoRepository


@pytest.mark.anyio
async def test_expired_crypto_invoice_liberates_unique_slot(session_factory):
    """Verify that an overdue pending invoice is cleaned up by expire_overdue_invoices and liberates its unique slot."""
    user_id = 998811
    currency = "TRX"
    base_units = 10_000_000
    step_units = 10_000

    async with session_factory() as session:
        session.add(User(telegram_id=user_id, full_name="Crypto User"))
        await session.commit()

        repo = CryptoRepository(session)
        # 1. Allocate a unique unit
        allocated_unit = await repo.allocate_unique_crypto_units(
            base_units=base_units,
            step_units=step_units,
            currency=currency,
        )

        # 2. Create the pending invoice reserving this unit
        inv1 = await repo.create_invoice(
            telegram_id=user_id,
            amount_toman=100_000,
            amount_ton="10.05",
            nanotons=allocated_unit,
            pay_address="TTestAddressTRX123",
            expires_minutes=60,
            currency=currency,
        )
        assert inv1.status == "pending"
        await session.commit()

        # While pending and active, this unit is registered as occupied
        occupied = await repo.get_pending_nanotons(currency)
        assert allocated_unit in occupied

        # 3. Simulate Time Travel: Fast forward 61 minutes into the future
        past_expiration = datetime.now(timezone.utc) - timedelta(minutes=5)
        inv1.expires_at = past_expiration
        await session.commit()

        # 4. Run expiration cleanup
        expired_count = await repo.expire_overdue_invoices(currency)
        assert expired_count >= 1
        await session.commit()

        # 5. Verify the overdue invoice is now marked "expired" and the slot is freed
        refreshed = await session.get(CryptoInvoice, inv1.id)
        assert refreshed.status == "expired"

        occupied_after = await repo.get_pending_nanotons(currency)
        assert allocated_unit not in occupied_after
