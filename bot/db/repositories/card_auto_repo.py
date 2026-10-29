"""Repository for automated card-to-card invoices and bank SMS logs."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import BankSmsLog, CardAutoInvoice

logger = logging.getLogger(__name__)


class CardAutoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_invoice_by_user(self, telegram_id: int) -> CardAutoInvoice | None:
        """Return the active pending invoice for this user if not expired."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(CardAutoInvoice)
            .where(
                and_(
                    CardAutoInvoice.telegram_id == telegram_id,
                    CardAutoInvoice.status == "pending",
                    CardAutoInvoice.expires_at > now,
                )
            )
            .order_by(CardAutoInvoice.id.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_invoice_by_uuid(self, invoice_uuid: str) -> CardAutoInvoice | None:
        """Fetch invoice by its UUID string."""
        stmt = select(CardAutoInvoice).where(CardAutoInvoice.invoice_uuid == invoice_uuid)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_pending_amounts_in_range(self, min_amount: int, max_amount: int) -> set[int]:
        """Fetch all exact amounts currently in 'pending' status within range."""
        now = datetime.now(timezone.utc)
        stmt = select(CardAutoInvoice.exact_amount).where(
            and_(
                CardAutoInvoice.status == "pending",
                CardAutoInvoice.expires_at > now,
                CardAutoInvoice.exact_amount >= min_amount,
                CardAutoInvoice.exact_amount <= max_amount,
            )
        )
        res = await self.session.execute(stmt)
        return set(res.scalars().all())

    async def create_invoice(
        self,
        telegram_id: int,
        base_amount: int,
        exact_amount: int,
        card_number: str,
        card_holder: str,
        ttl_minutes: int = 15,
    ) -> CardAutoInvoice:
        """Create a new pending card-to-card invoice with unique exact amount."""
        now = datetime.now(timezone.utc)
        inv_uuid = f"c2c_{uuid.uuid4().hex[:12]}"
        exact_rial = exact_amount * 10
        expires_at = now + timedelta(minutes=ttl_minutes)

        invoice = CardAutoInvoice(
            invoice_uuid=inv_uuid,
            telegram_id=telegram_id,
            base_amount=base_amount,
            exact_amount=exact_amount,
            exact_rial=exact_rial,
            card_number=card_number,
            card_holder=card_holder,
            status="pending",
            expires_at=expires_at,
        )
        self.session.add(invoice)
        await self.session.flush()
        return invoice

    async def claim_and_mark_paid(
        self,
        amount_toman: int,
        sms_log_id: int | None = None,
    ) -> CardAutoInvoice | None:
        """Atomically find the pending invoice matching exact_amount and mark paid."""
        now = datetime.now(timezone.utc)
        # Find matching pending invoice with row lock if possible
        stmt = (
            select(CardAutoInvoice)
            .where(
                and_(
                    CardAutoInvoice.exact_amount == amount_toman,
                    CardAutoInvoice.status == "pending",
                    CardAutoInvoice.expires_at > now,
                )
            )
            .order_by(CardAutoInvoice.id.desc())
            .limit(1)
        )
        # For Postgres we can add with_for_update, fallback gracefully on sqlite
        try:
            stmt = stmt.with_for_update()
        except Exception:
            pass

        res = await self.session.execute(stmt)
        invoice = res.scalar_one_or_none()
        if not invoice:
            return None

        invoice.status = "paid"
        invoice.paid_at = now
        invoice.sms_log_id = sms_log_id
        await self.session.flush()
        return invoice

    async def cancel_invoice(self, invoice_uuid: str, telegram_id: int) -> bool:
        """Cancel a pending invoice belonging to user."""
        stmt = (
            update(CardAutoInvoice)
            .where(
                and_(
                    CardAutoInvoice.invoice_uuid == invoice_uuid,
                    CardAutoInvoice.telegram_id == telegram_id,
                    CardAutoInvoice.status == "pending",
                )
            )
            .values(status="cancelled")
        )
        res = await self.session.execute(stmt)
        return (res.rowcount or 0) > 0

    async def log_bank_sms(
        self,
        sender: str,
        raw_message: str,
        amount_toman: int | None,
        bank_detected: str | None,
        matched_invoice_id: int | None = None,
        processed: bool = False,
    ) -> BankSmsLog:
        """Log an incoming forwarded SMS for accounting & debugging."""
        log_entry = BankSmsLog(
            sender=sender[:64],
            raw_message=raw_message,
            amount_toman=amount_toman,
            bank_detected=bank_detected[:32] if bank_detected else None,
            matched_invoice_id=matched_invoice_id,
            processed=processed,
        )
        self.session.add(log_entry)
        await self.session.flush()
        return log_entry
