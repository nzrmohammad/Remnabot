"""Repository for automated card-to-card invoices and bank SMS logs."""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import BankSmsLog, CardAutoInvoice
from bot.services.payment.bank_sms_parser import normalize_sms_digits

logger = logging.getLogger(__name__)

MANUAL_CARD_COOLDOWN_HOURS = 6


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None or not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def format_manual_card_block_message(remaining_seconds: int, lang: str = "fa") -> str:
    """Format localized message explaining the 6-hour manual card receipt lockout."""
    rem = max(1, int(remaining_seconds))
    hours = rem // 3600
    mins = (rem % 3600) // 60
    if lang != "fa":
        return (
            f"Manual receipt submission is locked for {MANUAL_CARD_COOLDOWN_HOURS} hours "
            f"while/after using an automated card-to-card invoice. "
            f"Time remaining: {hours}h {mins}m."
        )
    if hours > 0 and mins > 0:
        rem_str = f"{hours} ساعت و {mins} دقیقه"
    elif hours > 0:
        rem_str = f"{hours} ساعت"
    else:
        rem_str = f"{max(1, mins)} دقیقه"
    return (
        f"🔒 به دلیل وجود فاکتور کارت‌به‌کارت خودکار، امکان ورود و ارسال دستی فیش واریزی تا {MANUAL_CARD_COOLDOWN_HOURS} ساعت مسدود است.\n"
        f"⏳ زمان باقیمانده تا آزادسازی: {rem_str}"
    )


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

    async def get_recent_paid_invoice_by_user(
        self, telegram_id: int, since_hours: int = 6
    ) -> CardAutoInvoice | None:
        """Return the most recent paid card-auto invoice within `since_hours`."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        stmt = (
            select(CardAutoInvoice)
            .where(
                and_(
                    CardAutoInvoice.telegram_id == telegram_id,
                    CardAutoInvoice.status == "paid",
                    CardAutoInvoice.paid_at >= cutoff,
                )
            )
            .order_by(CardAutoInvoice.id.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_manual_card_block_info(
        self, telegram_id: int, since_hours: int = MANUAL_CARD_COOLDOWN_HOURS
    ) -> dict | None:
        """Return active 6-hour manual receipt block details if user has a pending, paid, or expired card-auto invoice."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(CardAutoInvoice)
            .where(
                and_(
                    CardAutoInvoice.telegram_id == telegram_id,
                    CardAutoInvoice.status != "cancelled",
                )
            )
            .order_by(CardAutoInvoice.id.desc())
            .limit(5)
        )
        res = await self.session.execute(stmt)
        scalars_fn = getattr(res, "scalars", None)
        rows = list(scalars_fn().all()) if callable(scalars_fn) else []
        latest_unlock: datetime | None = None
        blocking_inv: CardAutoInvoice | None = None

        for inv in rows:
            if not hasattr(inv, "status") or not isinstance(getattr(inv, "id", None), int):
                continue
            ref_dt = _as_utc(getattr(inv, "paid_at", None)) or _as_utc(getattr(inv, "created_at", None))
            exp_dt = _as_utc(getattr(inv, "expires_at", None))
            unlock_at: datetime | None = None
            if ref_dt is not None:
                unlock_at = ref_dt + timedelta(hours=since_hours)
            if inv.status == "pending" and exp_dt is not None and exp_dt > now:
                candidate = exp_dt + timedelta(hours=max(0, since_hours - 1))
                unlock_at = max(unlock_at, candidate, exp_dt) if unlock_at is not None else max(candidate, exp_dt)
            if unlock_at is None or unlock_at <= now:
                continue
            if latest_unlock is None or unlock_at > latest_unlock:
                latest_unlock = unlock_at
                blocking_inv = inv

        if blocking_inv is None or latest_unlock is None:
            return None
        rem_secs = max(1, int((latest_unlock - now).total_seconds()))
        return {
            "invoice": blocking_inv,
            "status": str(blocking_inv.status),
            "unlock_at": latest_unlock,
            "remaining_seconds": rem_secs,
        }

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
        ttl_minutes: int = 60,
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
        bind = self.session.get_bind()
        if not (bind and bind.dialect.name == "sqlite"):
            stmt = stmt.with_for_update()

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

    @staticmethod
    def compute_sms_hash(sender: str, raw_message: str) -> str:
        norm_msg = " ".join(normalize_sms_digits(raw_message or "").split())
        norm_sender = (sender or "").strip().lower()
        return hashlib.sha256(f"{norm_sender}::{norm_msg}".encode()).hexdigest()

    async def sms_hash_exists(self, sms_hash: str) -> bool:
        if not sms_hash:
            return False
        res = await self.session.execute(
            select(BankSmsLog.id).where(BankSmsLog.sms_hash == sms_hash).limit(1)
        )
        return res.scalar_one_or_none() is not None

    async def log_bank_sms(
        self,
        sender: str,
        raw_message: str,
        amount_toman: int | None,
        bank_detected: str | None,
        matched_invoice_id: int | None = None,
        processed: bool = False,
        sms_hash: str | None = None,
    ) -> BankSmsLog | None:
        """Log an incoming forwarded SMS atomically; return None if sms_hash already exists."""
        computed_hash = sms_hash or self.compute_sms_hash(sender, raw_message)
        if await self.sms_hash_exists(computed_hash):
            return None
        log_entry = BankSmsLog(
            sender=sender[:64],
            raw_message=raw_message,
            sms_hash=computed_hash,
            amount_toman=amount_toman,
            bank_detected=bank_detected[:32] if bank_detected else None,
            matched_invoice_id=matched_invoice_id,
            processed=processed,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(log_entry)
                await self.session.flush()
            return log_entry
        except IntegrityError:
            return None
