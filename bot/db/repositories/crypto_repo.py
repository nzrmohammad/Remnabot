"""Repository for on-chain cryptocurrency (TON) invoices."""
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, text
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

    async def get_all_pending(self) -> list[CryptoInvoice]:
        result = await self.session.execute(
            select(CryptoInvoice).where(CryptoInvoice.status == "pending")
        )
        return list(result.scalars().all())

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
        await self.session.flush()
        return invoice

    async def mark_paid(
        self, invoice_id: int, tx_hash: str, allow_expired: bool = False
    ) -> CryptoInvoice | None:
        """Atomically transition invoice from pending (or recently expired) -> paid.
        Prevents race-condition double-crediting if concurrent checks occur.
        """
        now = datetime.now(timezone.utc)
        status_clause = "status IN ('pending', 'expired')" if allow_expired else "status = 'pending'"
        row = await self.session.execute(
            text(
                f"UPDATE crypto_invoices SET status = 'paid', tx_hash = :tx, paid_at = :now "
                f"WHERE id = :i AND {status_clause} RETURNING id"
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

    async def mark_expired(self, invoice_id: int) -> None:
        invoice = await self.get_by_id(invoice_id)
        if invoice and invoice.status == "pending":
            invoice.status = "expired"
            await self.session.flush()

    async def mark_cancelled(self, invoice_id: int) -> None:
        invoice = await self.get_by_id(invoice_id)
        if invoice and invoice.status == "pending":
            invoice.status = "cancelled"
            await self.session.flush()
