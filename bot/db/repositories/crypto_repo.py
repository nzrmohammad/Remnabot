"""Repository for on-chain cryptocurrency (TON) invoices."""
import random
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_, update
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

    async def get_pending_by_user(self, telegram_id: int) -> CryptoInvoice | None:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(CryptoInvoice).where(
                and_(
                    CryptoInvoice.telegram_id == telegram_id,
                    CryptoInvoice.status == "pending",
                    CryptoInvoice.expires_at > now,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_all_pending(self) -> list[CryptoInvoice]:
        result = await self.session.execute(
            select(CryptoInvoice).where(CryptoInvoice.status == "pending")
        )
        return list(result.scalars().all())

    async def generate_unique_comment(self) -> str:
        """Generate a unique 5-6 digit numeric memo comment for TON transfer."""
        for _ in range(100):
            cand = str(random.randint(10000, 99999))
            existing = await self.get_by_comment(cand)
            if existing is None or existing.status in ("paid", "expired", "cancelled"):
                return cand
        # fallback 6 digits
        return str(random.randint(100000, 999999))

    async def create_invoice(
        self,
        telegram_id: int,
        amount_toman: int,
        amount_ton: str,
        nanotons: int,
        pay_address: str,
        expires_minutes: int = 30,
    ) -> CryptoInvoice:
        comment = await self.generate_unique_comment()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)

        invoice = CryptoInvoice(
            telegram_id=telegram_id,
            amount_toman=amount_toman,
            amount_ton=amount_ton,
            nanotons=nanotons,
            comment=comment,
            pay_address=pay_address,
            status="pending",
            expires_at=expires_at,
        )
        self.session.add(invoice)
        await self.session.flush()
        return invoice

    async def mark_paid(self, invoice_id: int, tx_hash: str) -> CryptoInvoice | None:
        invoice = await self.get_by_id(invoice_id)
        if invoice and invoice.status == "pending":
            invoice.status = "paid"
            invoice.tx_hash = tx_hash
            invoice.paid_at = datetime.now(timezone.utc)
            await self.session.flush()
            return invoice
        return None

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
