"""Automated Card-to-Card payment service.

Manages unique amount suffix allocation, expiration, collision prevention,
and processing incoming bank SMS messages to credit user wallets instantly.
"""
from __future__ import annotations

import logging
import random
import re
from html import escape
from typing import Any

from aiogram import Bot
from sqlalchemy.exc import IntegrityError
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

    card_number = getattr(store, "card_number", "") or ""
    card_holder = getattr(store, "card_holder", "") or ""

    # 1. If user already has an active pending invoice for the exact same base_amount AND current card, reuse it
    active_inv = await repo.get_active_invoice_by_user(telegram_id)
    if active_inv and active_inv.base_amount == base_amount:
        if active_inv.card_number == card_number:
            return active_inv
        await repo.cancel_invoice(active_inv.invoice_uuid, telegram_id)

    # 2. Build candidate suffixes between 10 and 990 Tomans (step of 10)
    # Using random offsets ending in 0 for bank and user clarity
    candidates = [delta for delta in range(10, 990, 10)]
    random.shuffle(candidates)

    min_val = base_amount + 10
    max_val = base_amount + 9990
    used_amounts = await repo.get_pending_amounts_in_range(min_val, max_val)

    for attempt in range(8):
        selected_delta = None
        for delta in candidates:
            candidate_amount = base_amount + delta
            if candidate_amount not in used_amounts:
                selected_delta = delta
                break

        if selected_delta is None:
            # Fallback: scan available offsets 1000..9990 (step 10)
            fallback_candidates = [d for d in range(1000, 9991, 10)]
            random.shuffle(fallback_candidates)
            for fallback_delta in fallback_candidates:
                if (base_amount + fallback_delta) not in used_amounts:
                    selected_delta = fallback_delta
                    break
            if selected_delta is None:
                raise RuntimeError("تمامی پسوندهای مجاز برای این مبلغ در حال حاضر پر هستند.")

        exact_amount = base_amount + selected_delta

        try:
            async with session.begin_nested():
                invoice = await repo.create_invoice(
                    telegram_id=telegram_id,
                    base_amount=base_amount,
                    exact_amount=exact_amount,
                    card_number=card_number,
                    card_holder=card_holder,
                    ttl_minutes=ttl_minutes,
                )
            logger.info(
                "Created card-auto invoice: uuid=%s telegram_id=%s base_amount=%s exact_amount=%s ttl_min=%s",
                invoice.invoice_uuid, telegram_id, base_amount, exact_amount, ttl_minutes,
            )
            return invoice
        except IntegrityError:
            logger.warning(
                "Collision on exact_amount=%s, retrying with new suffix (attempt %s/8)",
                exact_amount, attempt + 1,
            )
            used_amounts.add(exact_amount)
            fresh = await repo.get_pending_amounts_in_range(min_val, max_val)
            used_amounts.update(fresh)

    raise RuntimeError("امکان تخصیص مبلغ یکتا در شلوغی لحظه‌ای وجود نداشت. لطفاً چند لحظه بعد تلاش کنید.")


async def notify_admin_sms_webhook_log(
    bot: Bot | None,
    settings: Any,
    store: StoreSettings,
    sender: str,
    raw_message: str,
    action: str,
    parsed: Any,
    invoice: CardAutoInvoice | None = None,
    new_balance: int | None = None,
    reason: str = "",
) -> None:
    """Send real-time incoming SMS notification and bot decision to admin SMS topic."""
    if not bot or not settings or not getattr(settings, "ADMIN_CHAT_ID", None):
        return

    topic_id = (
        getattr(store, "topic_sms_logs", None)
        or getattr(settings, "ADMIN_TOPIC_SMS_LOGS", None)
        or getattr(store, "topic_sms_manual", None)
        or getattr(settings, "ADMIN_TOPIC_SMS_MANUAL", None)
    )
    if not topic_id:
        return

    thread_kwargs = admin_thread_kwargs(topic_id=topic_id)
    bank_label = escape(parsed.bank_name or "نامشخص")
    sender_label = escape(sender)
    clean_preview = escape(raw_message.strip()[:400])

    amount_str = f"<b>{parsed.amount_toman:,} تومان</b> ({parsed.amount_rial:,} ریال)" if getattr(parsed, "amount_toman", 0) else "<i>تشخیص داده نشد</i>"

    if action == "credited" and invoice:
        status_header = "🟢 <b>تأیید و شارژ خودکار کیف پول</b>"
        missing_card_warn = (
            "\n⚠️ <i>توجه: شماره کارت مقصد در متن پیامک درج نشده بود؛ مطابقت بر اساس مبلغ یکتا انجام شد.</i>"
            if not getattr(parsed, "card_last4", None)
            else ""
        )
        decision_details = (
            f"▫️ شناسه فاکتور: <code>#{invoice.invoice_uuid}</code>\n"
            f"▫️ شناسه کاربر: <code>{invoice.telegram_id}</code>\n"
            f"▫️ مبلغ شارژ: <b>{invoice.exact_amount:,} تومان</b>\n"
            f"▫️ موجودی جدید: <b>{new_balance:,} تومان</b>{missing_card_warn}"
        )
    elif action == "unmatched_deposit":
        status_header = "🟡 <b>واریزی بدون فاکتور منطبق</b>"
        decision_details = (
            "▫️ وضعیت: واریز به حساب تشخیص داده شد اما هیچ فاکتور بازی با این مبلغ یافت نشد.\n"
            "▫️ اقدام: در انتظار بررسی دستی یا ثبت فاکتور توسط کاربر."
        )
    elif action == "card_mismatch":
        status_header = "🔴 <b>عدم تطابق شماره کارت مقصد</b>"
        store_card = getattr(store, "card_number", None) or "—"
        decision_details = (
            f"▫️ کارت پیامک: <code>{escape(parsed.card_last4 or '—')}</code>\n"
            f"▫️ کارت فروشگاه: <code>{escape(str(store_card))}</code>\n"
            "▫️ اقدام: نادیده گرفته شد (واریزی به کارت شخصی ادمین یا حساب دیگر)."
        )
    elif action == "ignored_non_deposit":
        status_header = "⚪️ <b>نادیده گرفته شد (پیامک غیرواریزی)</b>"
        decision_details = (
            "▫️ وضعیت: پیامک تراکنش واریز به حساب تشخیص داده نشد.\n"
            f"▫️ علت: {escape(reason or 'تراکنش برداشت، انتقال ناموفق، پیامک خدمات یا اطلاع‌رسانی')}"
        )
    else:
        status_header = f"ℹ️ <b>نتیجه پردازش: {escape(action)}</b>"
        decision_details = f"▫️ توضیحات: {escape(reason or '—')}"

    text = (
        f"📥 <b>پیامک دریافتی از وب‌هوک</b>\n"
        "──────────────────\n"
        f"📱 فرستنده: <code>{sender_label}</code>\n"
        f"🏦 بانک: <b>{bank_label}</b>\n"
        f"💰 مبلغ استخراج‌شده: {amount_str}\n\n"
        "📝 <b>متن پیامک:</b>\n"
        f"<code>{clean_preview}</code>\n\n"
        f"🤖 <b>تصمیم ربات:</b>\n"
        f"{status_header}\n"
        f"{decision_details}"
    )

    try:
        await bot.send_message(
            chat_id=settings.ADMIN_CHAT_ID,
            text=text,
            parse_mode="HTML",
            **thread_kwargs,
        )
    except Exception as exc:
        logger.warning("Failed to deliver SMS webhook log to admin topic %s: %s", topic_id, exc)


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
    logger.debug(
        "Bank SMS parsed result: sender=%r is_deposit=%s amount_rial=%s amount_toman=%s bank=%s raw_preview=%r",
        sender, parsed.is_deposit, parsed.amount_rial, parsed.amount_toman, parsed.bank_name, raw_message[:80],
    )

    # Log incoming SMS atomically with replay deduplication
    sms_hash = repo.compute_sms_hash(sender, raw_message)
    log_entry = await repo.log_bank_sms(
        sender=sender,
        raw_message=raw_message,
        amount_toman=parsed.amount_toman,
        bank_detected=parsed.bank_name,
        processed=False,
        sms_hash=sms_hash,
    )
    if log_entry is None:
        logger.warning("Duplicate SMS replay ignored from sender=%s hash=%s", sender, sms_hash[:12])
        return {
            "ok": True,
            "action": "duplicate_ignored",
            "reason": "Duplicate SMS replay blocked",
        }

    if not parsed.is_deposit or not parsed.amount_toman:
        logger.info("Ignored non-deposit or unparsed SMS from %s: %s", sender, raw_message[:60])
        reason = "Not recognized as deposit"
        await notify_admin_sms_webhook_log(
            bot=bot, settings=settings, store=store, sender=sender,
            raw_message=raw_message, action="ignored_non_deposit", parsed=parsed, reason=reason
        )
        return {
            "ok": True,
            "action": "ignored_non_deposit",
            "reason": reason,
        }

    # Card destination check: If store has a designated card number and SMS specifies card_last4,
    # verify that the SMS actually belongs to the store's card rather than personal admin cards.
    if store and getattr(store, "card_number", None):
        clean_store_card = re.sub(r"\D", "", str(store.card_number))
        if len(clean_store_card) >= 4:
            store_card_last4 = clean_store_card[-4:]
            if parsed.card_last4 and parsed.card_last4 != store_card_last4:
                logger.warning(
                    "Bank deposit card mismatch: SMS card_last4=%s does not match store card_last4=%s (sender=%s)",
                    parsed.card_last4, store_card_last4, sender,
                )
                reason = f"Card {parsed.card_last4} does not match store card {store_card_last4}"
                await notify_admin_sms_webhook_log(
                    bot=bot, settings=settings, store=store, sender=sender,
                    raw_message=raw_message, action="card_mismatch", parsed=parsed, reason=reason
                )
                return {
                    "ok": True,
                    "action": "card_mismatch",
                    "reason": reason,
                }

    amount_toman = parsed.amount_toman
    invoice = await repo.claim_and_mark_paid(amount_toman, sms_log_id=log_entry.id)

    if not invoice:
        logger.warning(
            "Unmatched bank deposit SMS: %s Toman (%s) from %s",
            amount_toman, parsed.bank_name, sender
        )
        # 1. Notify SMS logs topic
        await notify_admin_sms_webhook_log(
            bot=bot, settings=settings, store=store, sender=sender,
            raw_message=raw_message, action="unmatched_deposit", parsed=parsed
        )

        # 2. Notify topups topic if distinct from SMS logs topic or if SMS logs topic not set
        sms_topic = (
            getattr(store, "topic_sms_logs", None)
            or getattr(settings, "ADMIN_TOPIC_SMS_LOGS", None)
            or getattr(store, "topic_sms_manual", None)
            or getattr(settings, "ADMIN_TOPIC_SMS_MANUAL", None)
        )
        topups_topic = getattr(store, "topic_topups", None) or getattr(settings, "ADMIN_TOPIC_TOPUPS", None)
        if bot and settings and getattr(settings, "ADMIN_CHAT_ID", None) and (not sms_topic or sms_topic != topups_topic):
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
    logger.info(
        "Card-auto deposit credited successfully: invoice_uuid=%s sms_log_id=%s telegram_id=%s amount=%s new_balance=%s bank=%s",
        invoice.invoice_uuid, log_entry.id, invoice.telegram_id, credited_amount, new_bal, parsed.bank_name,
    )

    # Invalidate user TMA cache
    if cache and hasattr(cache, "delete"):
        try:
            if hasattr(cache, "invalidate_user"):
                await cache.invalidate_user(invoice.telegram_id)
            else:
                await cache.delete(f"tma:user:{invoice.telegram_id}")
        except Exception as exc:
            logger.debug("Failed invalidating user cache for %s: %s", invoice.telegram_id, exc)

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

    # 2. Notify SMS logs topic
    await notify_admin_sms_webhook_log(
        bot=bot, settings=settings, store=store, sender=sender,
        raw_message=raw_message, action="credited", parsed=parsed,
        invoice=invoice, new_balance=new_bal
    )

    # 3. Notify admin topups topic if distinct from SMS logs topic or if SMS logs topic not set
    sms_topic = (
        getattr(store, "topic_sms_logs", None)
        or getattr(settings, "ADMIN_TOPIC_SMS_LOGS", None)
        or getattr(store, "topic_sms_manual", None)
        or getattr(settings, "ADMIN_TOPIC_SMS_MANUAL", None)
    )
    topups_topic = getattr(store, "topic_topups", None) or getattr(settings, "ADMIN_TOPIC_TOPUPS", None)
    if bot and settings and getattr(settings, "ADMIN_CHAT_ID", None) and (not sms_topic or sms_topic != topups_topic):
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
