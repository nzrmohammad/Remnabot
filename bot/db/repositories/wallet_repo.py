"""Repository for wallet balances and card-to-card top-up requests."""
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Topup, Wallet


class WalletRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------ #
    # Wallet
    # ------------------------------------------------------------------ #
    async def get_wallet(self, telegram_id: int) -> Wallet:
        result = await self.session.execute(
            select(Wallet).where(Wallet.telegram_id == telegram_id)
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            wallet = Wallet(telegram_id=telegram_id, balance=0)
            self.session.add(wallet)
            await self.session.flush()
        return wallet

    async def add_balance(self, telegram_id: int, amount: int) -> Wallet:
        wallet = await self.get_wallet(telegram_id)
        wallet.balance += amount
        return wallet

    async def add_balance_atomic(self, telegram_id: int, amount: int) -> int:
        """Atomic credit that never loses concurrent updates.

        Returns the new balance.
        """
        row = await self.session.execute(
            text(
                "INSERT INTO wallets (telegram_id, balance) VALUES (:t, :a) "
                "ON CONFLICT (telegram_id) DO UPDATE SET balance = wallets.balance + :a "
                "RETURNING balance"
            ),
            {"t": telegram_id, "a": amount},
        )
        await self.session.flush()
        return int(row.scalar_one())

    async def adjust_balance_atomic(self, telegram_id: int, amount: int) -> int:
        """Atomic +/- (floor at 0). Returns the new balance."""
        row = await self.session.execute(
            text(
                "INSERT INTO wallets (telegram_id, balance) VALUES (:t, :b) "
                "ON CONFLICT (telegram_id) DO UPDATE SET "
                "balance = GREATEST(0, wallets.balance + :a) "
                "RETURNING balance"
            ),
            {"t": telegram_id, "a": amount, "b": max(0, amount)},
        )
        await self.session.flush()
        return int(row.scalar_one())

    async def claim_topup(self, topup_id: int, approved: bool) -> Topup | None:
        """Atomically move a top-up from pending -> decided.

        Returns the Topup on success, None if it was already decided
        (prevents double-credit when two admins click at once).
        """
        status = "approved" if approved else "rejected"
        now = datetime.now(timezone.utc)
        row = await self.session.execute(
            text(
                "UPDATE topups SET status = :s, decided_at = :now "
                "WHERE id = :i AND status = 'pending' RETURNING id"
            ),
            {"s": status, "now": now, "i": topup_id},
        )
        claimed = row.scalar_one_or_none()
        await self.session.flush()
        if claimed is None:
            return None
        return await self.get_topup(topup_id)

    async def subtract_balance(self, telegram_id: int, amount: int) -> Wallet | None:
        """Deduct `amount` if the balance covers it; otherwise return None."""
        wallet = await self.get_wallet(telegram_id)
        if wallet.balance < amount:
            return None
        wallet.balance -= amount
        return wallet

    async def set_balance(self, telegram_id: int, amount: int) -> Wallet:
        wallet = await self.get_wallet(telegram_id)
        wallet.balance = max(0, amount)
        return wallet

    async def list_wallets(self) -> list[Wallet]:
        result = await self.session.execute(
            select(Wallet).order_by(Wallet.telegram_id)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------ #
    # Top-ups
    # ------------------------------------------------------------------ #
    async def create_topup(
        self,
        telegram_id: int,
        amount: int,
        receipt_hash: str | None = None,
        receipt_photo_id: str | None = None,
    ) -> Topup:
        topup = Topup(
            telegram_id=telegram_id,
            amount=amount,
            receipt_hash=receipt_hash,
            receipt_photo_id=receipt_photo_id,
        )
        self.session.add(topup)
        await self.session.flush()  # populates topup.id
        return topup

    async def receipt_exists(self, receipt_hash: str) -> bool:
        """True if this receipt fingerprint was already submitted (any status)."""
        result = await self.session.execute(
            select(Topup).where(Topup.receipt_hash == receipt_hash).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_topup(self, topup_id: int) -> Topup | None:
        result = await self.session.execute(
            select(Topup).where(Topup.id == topup_id)
        )
        return result.scalar_one_or_none()

    async def decide_topup(self, topup: Topup, approved: bool) -> None:
        topup.status = "approved" if approved else "rejected"
        topup.decided_at = datetime.now(timezone.utc)

    async def pending_count(self, telegram_id: int) -> int:
        result = await self.session.execute(
            select(Topup).where(
                Topup.telegram_id == telegram_id, Topup.status == "pending"
            )
        )
        return len(result.scalars().all())

    async def list_pending_topups(self) -> list[Topup]:
        result = await self.session.execute(
            select(Topup)
            .where(Topup.status == "pending")
            .order_by(Topup.id.desc())
        )
        return list(result.scalars().all())

    async def cancel_pending(self, topup_id: int) -> None:
        """Remove an orphan pending top-up (e.g. admin delivery failed)."""
        topup = await self.get_topup(topup_id)
        if topup is not None and topup.status == "pending":
            await self.session.delete(topup)
            await self.session.flush()

    async def list_for_user(self, telegram_id: int, limit: int = 10) -> list[Topup]:
        result = await self.session.execute(
            select(Topup)
            .where(Topup.telegram_id == telegram_id)
            .order_by(Topup.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def topup_stats(self, since: datetime | None = None) -> tuple[int, int]:
        """Returns (count_approved, total_approved_amount) since given timestamp."""
        stmt = select(
            func.count(Topup.id),
            func.coalesce(func.sum(Topup.amount), 0),
        ).where(Topup.status == "approved")
        if since is not None:
            stmt = stmt.where(Topup.decided_at >= since)
        result = await self.session.execute(stmt)
        count, total = result.one()
        return int(count), int(total)
