"""Automated Card-to-Card payment service.

Manages unique amount suffix allocation, expiration, collision prevention,
and processing incoming bank SMS messages to credit user wallets instantly.
"""
from __future__ import annotations

import logging
import random
from html import escape
from typing import Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import admin_thread_kwargs
from bot.db.models import CardAutoInvoice
from bot.db.repositories.card_auto_repo import CardAutoRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.app_settings import StoreSettings
from bot.services.payment.bank_sms_parser import parse_bank_sms

logger = logging.getLogger(__name__)


async def generate_card_auto_invoice(
    session: AsyncSession,
    telegram_id: int,
    base_amount: int,
    store: StoreSettings,
    ttl_minutes: int = 60,
) -> CardAutoInvoice:
    """Generate a card-to-card invoice with an exact amount suffix avoiding collisions."""
    repo = CardAutoRepository(session)

    # 1. If user already has an active pending invoice for the same or recent request, reuse it
    active_inv = await repo.get_active_invoice_by_user(telegram_id)
    if active_inv and active_inv.base_amount == base_amount:
        return active_inv

    # 2. Build candidate suffixes between 10 and 990 Tomans (step of 10 or 25)
    # Using random offsets ending in 0 or 5 for bank and user clarity
    candidates = [delta for delta in range(10, 990, 10)]
    random.shuffle(candidates)

    min_val = base_amount + 10
    max_val = base_amount + 990
    used_amounts = await repo.get_pending_amounts_in_range(min_val, max_val)

    selected_delta = None
    for delta in candidates:
        candidate_amount = base_amount + delta
        if candidate_amount not in used_amounts:
            selected_delta = delta
            break

    if selected_delta is None:
        # Fallback to random offset up to 1990 if high volume
        selected_delta = random.randint(1000, 1990)

    exact_amount = base_amount + selected_delta
    card_number = getattr(store, "card_number", "") or ""
    card_holder = getattr(store, "card_holder", "") or ""

    invoice = await repo.create_invoice(
        telegram_id=telegram_id,
        base_amount=base_amount,
        exact_amount=exact_amount,
        card_number=card_number,
        card_holder=card_holder,
        ttl_minutes=ttl_minutes,
    )
    return invoice


async def process_incoming_sms(
    session: AsyncSession,
    bot: Bot | None,
    settings: Any,
    store: StoreSettings,
    sender: str,
    raw_message: str,
    cache: Any = None,
) -> dict[str, Any]:
    """Process forwarded bank SMS, match to pending invoice, and credit user wallet."""
    repo = CardAutoRepository(session)
    wallet_repo = WalletRepository(session)

    parsed = parse_bank_sms(raw_message, sender)

    # Log incoming SMS
    log_entry = await repo.log_bank_sms(
        sender=sender,
        raw_message=raw_message,
        amount_toman=parsed.amount_toman,
        bank_detected=parsed.bank_name,
        processed=False,
    )

    if not parsed.is_deposit or not parsed.amount_toman:
        logger.info("Ignored non-deposit or unparsed SMS from %s: %s", sender, raw_message[:60])
        return {
            "ok": True,
            "action": "ignored_non_deposit",
            "reason": "Not recognized as deposit",
        }

    amount_toman = parsed.amount_toman
    invoice = await repo.claim_and_mark_paid(amount_toman, sms_log_id=log_entry.id)

    if not invoice:
        logger.warning(
            "Unmatched bank deposit SMS: %s Toman (%s) from %s",
            amount_toman, parsed.bank_name, sender
        )
        # Notify admin of unmatched deposit
        if bot and settings and getattr(settings, "ADMIN_CHAT_ID", None):
            try:
                thread_kwargs = admin_thread_kwargs(store, settings, kind="topups")
                admin_text = (
                    "⚠️ <b>پیامک واریزی بدون فاکتور منطبق!</b>\n"
                    "──────────────────\n"
                    f"💰 مبلغ واریز: <b>{amount_toman:,} تومان</b> ({parsed.amount_rial:,} ریال)\n"
                    f"🏦 بانک: <b>{escape(parsed.bank_name or 'نامشخص')}</b>\n"
                    f"📱 فرستنده: <code>{escape(sender)}</code>\n\n"
                    f"📝 متن پیامک:\n<code>{escape(raw_message[:300])}</code>\n\n"
                    "ℹ️ <i>علت: کاربر فاکتوری با این مبلغ ثبت نکرده یا مهلت فاکتور به پایان رسیده بود.</i>"
                )
                await bot.send_message(
                    chat_id=settings.ADMIN_CHAT_ID,
                    text=admin_text,
                    parse_mode="HTML",
                    **thread_kwargs,
                )
            except Exception as exc:
                logger.error("Failed to notify admin of unmatched SMS: %s", exc)

        return {
            "ok": True,
            "action": "unmatched_deposit",
            "amount_toman": amount_toman,
            "bank": parsed.bank_name,
        }

    # Invoice matched! Update log
    log_entry.matched_invoice_id = invoice.id
    log_entry.processed = True

    # Credit user wallet atomically
    credited_amount = invoice.exact_amount
    new_bal = await wallet_repo.add_balance_atomic(invoice.telegram_id, credited_amount)

    # Invalidate user TMA cache
    if cache and hasattr(cache, "delete"):
        try:
            await cache.delete(f"tma:user:{invoice.telegram_id}:profile")
            await cache.delete(f"tma:user:{invoice.telegram_id}:dashboard")
        except Exception:
            pass

    # 1. Notify user in Telegram
    if bot:
        try:
            user_msg = (
                "⚡️ <b>شارژ خودکار کارت‌به‌کارت با موفقیت تأیید شد!</b>\n"
                "──────────────────\n"
                f"💰 مبلغ شارژ: <b>{credited_amount:,} تومان</b> ({invoice.exact_rial:,} ریال)\n"
                f"💳 موجودی جدید کیف پول: <b>{new_bal:,} تومان</b>\n"
                f"🏦 بانک: <b>{escape(parsed.bank_name or 'کارت بانکی')}</b>\n"
                f"🆔 شناسه فاکتور: <code>{invoice.invoice_uuid}</code>\n\n"
                "🎉 حساب شما به‌صورت آنی شارژ شد و می‌توانید از خدمات استفاده نمایید."
            )
            await bot.send_message(
                chat_id=invoice.telegram_id,
                text=user_msg,
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("Failed to send user confirmation msg for invoice %s: %s", invoice.invoice_uuid, exc)

    # 2. Notify admin chat
    if bot and settings and getattr(settings, "ADMIN_CHAT_ID", None):
        try:
            thread_kwargs = admin_thread_kwargs(store, settings, kind="topups")
            admin_msg = (
                "✅ <b>واریز خودکار کارت‌به‌کارت تأیید شد</b>\n"
                "──────────────────\n"
                f"🆔 شناسه فاکتور: <code>#{invoice.invoice_uuid}</code>\n"
                f"👤 شناسه کاربر: <code>{invoice.telegram_id}</code>\n"
                f"💰 مبلغ واریزی: <b>{credited_amount:,} تومان</b>\n"
                f"🏦 بانک: <b>{escape(parsed.bank_name or 'بانک')}</b>\n"
                f"📱 فرستنده: <code>{escape(sender)}</code>\n"
                f"💳 موجودی جدید کاربر: <b>{new_bal:,} تومان</b>"
            )
            await bot.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=admin_msg,
                parse_mode="HTML",
                **thread_kwargs,
            )
        except Exception as exc:
            logger.warning("Failed to send admin notification for invoice %s: %s", invoice.invoice_uuid, exc)

    return {
        "ok": True,
        "action": "credited",
        "invoice_uuid": invoice.invoice_uuid,
        "amount_toman": credited_amount,
        "user_id": invoice.telegram_id,
        "bank": parsed.bank_name,
    }
