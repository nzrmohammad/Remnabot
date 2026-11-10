"""Repository for on-chain cryptocurrency (TON) invoices."""
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import CryptoInvoice


class CryptoRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, invoice_id: int) -> CryptoInvoice | None:
        result = await self.session.execute(
            select(CryptoInvoice).where(CryptoInvoice.id == invoice_id)
        )
        return result.scalar_one_or_none()

    async def get_by_comment(self, comment: str) -> CryptoInvoice | None:
        result = await self.session.execute(
            select(CryptoInvoice).where(CryptoInvoice.comment == comment)
        )
        return result.scalar_one_or_none()

    async def get_pending_by_user(self, telegram_id: int, currency: str | None = None) -> CryptoInvoice | None:
        now = datetime.now(timezone.utc)
        conditions = [
            CryptoInvoice.telegram_id == telegram_id,
            CryptoInvoice.status == "pending",
            CryptoInvoice.expires_at > now,
        ]
        if currency:
            conditions.append(CryptoInvoice.currency == currency)
        result = await self.session.execute(
            select(CryptoInvoice)
            .where(and_(*conditions))
            .order_by(CryptoInvoice.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_all_pending(self, currency: str | None = None) -> list[CryptoInvoice]:
        stmt = select(CryptoInvoice).where(CryptoInvoice.status == "pending")
        if currency:
            stmt = stmt.where(CryptoInvoice.currency == currency)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_nanotons(self, currency: str) -> set[int]:
        """Return active non-expired exact smallest-unit amounts (SUN/Wei/nanoton) for a currency."""
        now = datetime.now(timezone.utc)
        stmt = select(CryptoInvoice.nanotons).where(
            and_(
                CryptoInvoice.currency == currency,
                CryptoInvoice.status == "pending",
                CryptoInvoice.expires_at > now,
            )
        )
        res = await self.session.execute(stmt)
        return {int(val) for val in res.scalars().all() if val is not None}

    async def allocate_unique_crypto_units(
        self,
        base_units: int,
        step_units: int,
        currency: str,
        max_steps: int = 99,
    ) -> int:
        """Allocate a unique fractional-suffixed amount in smallest units to prevent TX hijacking."""
        used = await self.get_pending_nanotons(currency)
        candidates = list(range(1, max_steps + 1))
        secrets.SystemRandom().shuffle(candidates)
        for k in candidates:
            cand = base_units + k * step_units
            if cand not in used:
                return cand
        for k in range(max_steps + 1, max_steps + 300):
            cand = base_units + k * step_units
            if cand not in used:
                return cand
        return base_units + (1 + secrets.randbelow(max_steps)) * step_units

    async def get_by_tx_hash(self, tx_hash: str) -> CryptoInvoice | None:
        if not tx_hash:
            return None
        result = await self.session.execute(
            select(CryptoInvoice).where(CryptoInvoice.tx_hash == tx_hash)
        )
        return result.scalar_one_or_none()

    async def generate_unique_comment(self) -> str:
        """Generate a cryptographically secure, globally unique numeric memo comment for TON transfer."""
        for _ in range(100):
            cand = str(10000 + secrets.randbelow(90000))
            existing = await self.get_by_comment(cand)
            if existing is None:
                return cand
        # fallback 6 digits
        for _ in range(100):
            cand = str(100000 + secrets.randbelow(900000))
            existing = await self.get_by_comment(cand)
            if existing is None:
                return cand
        # fallback 7 digits
        for _ in range(100):
            cand = str(1000000 + secrets.randbelow(9000000))
            existing = await self.get_by_comment(cand)
            if existing is None:
                return cand
        return str(10000000 + secrets.randbelow(90000000))

    async def create_invoice(
        self,
        telegram_id: int,
        amount_toman: int,
        amount_ton: str,
        nanotons: int,
        pay_address: str,
        expires_minutes: int = 60,
        currency: str = "TON",
    ) -> CryptoInvoice:
        for attempt in range(5):
            comment = await self.generate_unique_comment()
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)

            invoice = CryptoInvoice(
                telegram_id=telegram_id,
                amount_toman=amount_toman,
                amount_ton=amount_ton,
                nanotons=nanotons,
                currency=currency,
                comment=comment,
                pay_address=pay_address,
                status="pending",
                expires_at=expires_at,
            )
            self.session.add(invoice)
            try:
                async with self.session.begin_nested():
                    await self.session.flush()
                return invoice
            except IntegrityError:
                if attempt == 4:
                    raise
        return invoice

    async def mark_paid(
        self,
        invoice_id: int,
        tx_hash: str,
        allow_expired: bool = False,
        max_expired_grace_minutes: int = 120,
    ) -> CryptoInvoice | None:
        """Atomically transition invoice from pending (or recently expired within grace) -> paid.
        Prevents race-condition double-crediting if concurrent checks occur.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=max(0, int(max_expired_grace_minutes)))
        if allow_expired:
            row = await self.session.execute(
                text(
                    "UPDATE crypto_invoices SET status = 'paid', tx_hash = :tx, paid_at = :now "
                    "WHERE id = :i AND (status = 'pending' OR (status = 'expired' AND expires_at >= :cutoff)) "
                    "RETURNING id"
                ),
                {"tx": tx_hash, "now": now, "cutoff": cutoff, "i": invoice_id},
            )
        else:
            row = await self.session.execute(
                text(
                    "UPDATE crypto_invoices SET status = 'paid', tx_hash = :tx, paid_at = :now "
                    "WHERE id = :i AND status = 'pending' RETURNING id"
                ),
                {"tx": tx_hash, "now": now, "i": invoice_id},
            )
        claimed = row.scalar_one_or_none()
        await self.session.flush()
        if claimed is None:
            return None
        invoice = await self.get_by_id(invoice_id)
        if invoice:
            await self.session.refresh(invoice)
        return invoice

    async def mark_expired(self, invoice_id: int) -> bool:
        stmt = (
            update(CryptoInvoice)
            .where(CryptoInvoice.id == invoice_id, CryptoInvoice.status == "pending")
            .values(status="expired")
        )
        res = await self.session.execute(stmt)
        await self.session.flush()
        return (res.rowcount or 0) > 0

    async def mark_cancelled(self, invoice_id: int) -> bool:
        stmt = (
            update(CryptoInvoice)
            .where(CryptoInvoice.id == invoice_id, CryptoInvoice.status == "pending")
            .values(status="cancelled")
        )
        res = await self.session.execute(stmt)
        await self.session.flush()
        return (res.rowcount or 0) > 0
