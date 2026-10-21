from html import escape
from sqlalchemy.exc import IntegrityError
"""Telegram Stars (XTR) native payment handling."""
import logging
from aiogram import Bot, F, Router
from aiogram.types import Message, PreCheckoutQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from bot.common import admin_thread_kwargs
from bot.db.models import Topup, TopupStatus
from bot.db.repositories.wallet_repo import WalletRepository
from bot.db.repositories.user_repo import UserRepository
from bot.services.app_settings import get_store_settings

logger = logging.getLogger(__name__)
router = Router(name="payment_stars")


@router.pre_checkout_query()
async def stars_pre_checkout_handler(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """Validate and confirm Telegram Stars pre-checkout inquiry."""
    payload = str(pre_checkout_query.invoice_payload or "")
    if not payload.startswith("stars_topup:"):
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id, ok=False, error_message="شناسه فاکتور نامعتبر است."
        )
        return

    parts = payload.split(":")
    if len(parts) < 4:
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id, ok=False, error_message="اطلاعات فاکتور مخدوش است."
        )
        return

    try:
        user_tid = int(parts[1])
        stars_count = int(parts[3])
    except (ValueError, TypeError):
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id, ok=False, error_message="مقادیر فاکتور نامعتبر است."
        )
        return

    if pre_checkout_query.from_user.id != user_tid:
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id, ok=False, error_message="این فاکتور متعلق به حساب کاربری شما نیست."
        )
        return

    if pre_checkout_query.total_amount < stars_count:
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id, ok=False, error_message="مبلغ پرداختی کمتر از مبلغ فاکتور است."
        )
        return
    try:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    except Exception as exc:
        logger.exception("Failed to answer stars pre-checkout query: %s", exc)
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id, ok=False, error_message="خطا در اعتبارسنجی پرداخت با استارز."
        )


@router.message(F.successful_payment)
async def stars_successful_payment_handler(
    message: Message, bot: Bot, session: AsyncSession,
):
    """Credit wallet upon successful Stars payment."""
    sp = message.successful_payment
    if not sp:
        return

    payload = str(sp.invoice_payload or "")
    # Format: stars_topup:{telegram_id}:{amount_toman}:{stars_count}
    parts = payload.split(":")
    if len(parts) < 4 or parts[0] != "stars_topup":
        logger.error("Unrecognized successful_payment payload: %s", payload)
        try:
            from bot.services.error_reporter import report_error
            await report_error(
                bot,
                session=session,
                exc=f"Unrecognized Stars payment payload: {payload}",
                context=f"Stars payment amount={sp.total_amount} XTR",
                user_id=message.from_user.id if message.from_user else None,
            )
        except Exception:
            pass
        return

    try:
        user_tid = int(parts[1])
        amount_toman = int(parts[2])
        stars_count = int(parts[3])
    except (ValueError, TypeError) as exc:
        logger.exception("Invalid payload numbers in %s", payload)
        try:
            from bot.services.error_reporter import report_error
            await report_error(
                bot,
                session=session,
                exc=exc,
                context=f"Invalid payload numbers in Stars topup: {payload}",
                user_id=message.from_user.id if message.from_user else None,
            )
        except Exception:
            pass
        return

    # Idempotency guard: prevent duplicate crediting if Telegram retries webhook
    receipt_hash = f"stars:{sp.telegram_payment_charge_id}"
    dup_res = await session.execute(
        select(Topup).where(Topup.receipt_hash == receipt_hash)
    )
    if dup_res.scalar_one_or_none():
        logger.warning("Duplicate Stars payment received for charge_id %s, ignoring.", sp.telegram_payment_charge_id)
        return

    wallet_repo = WalletRepository(session)
    user_repo = UserRepository(session)

    store = await get_store_settings(session)
    stars_rate = getattr(store, "stars_rate_toman", 0) or 0
    credit_toman = (sp.total_amount * stars_rate) if (stars_rate > 0 and sp.total_amount) else amount_toman


    # Atomically credit wallet and record topup
    try:
        new_balance = await wallet_repo.add_balance_atomic(user_tid, credit_toman)
        topup = Topup(
            telegram_id=user_tid,
            amount=credit_toman,
            status=TopupStatus.APPROVED.value,
            receipt_hash=receipt_hash,
            decided_at=datetime.now(timezone.utc),
        )
        session.add(topup)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.warning("Duplicate Stars payment race condition caught for %s, rolled back credit.", receipt_hash)
        return
    except Exception as exc:
        logger.error("Failed to credit wallet for Stars topup: user=%s, amount=%s: %s", user_tid, amount_toman, exc)
        try:
            from bot.services.error_reporter import report_error
            await report_error(
                bot,
                session=session,
                exc=exc,
                context=f"Failed to credit wallet after Stars payment: {amount_toman} Toman",
                user_id=user_tid,
            )
        except Exception:
            pass
        raise

    user = await user_repo.get_by_telegram_id(user_tid)
    first_name = (
        user.full_name
        or (f"@{user.username}" if user.username else None)
        or f"کاربر {user_tid}"
    ) if user else f"کاربر {user_tid}"

    # Notify user
    receipt_text = (
        f"⭐️ <b>پرداخت با استارز تلگرام با موفقیت انجام شد!</b>\n\n"
        f"💰 مبلغ شارژ شده: <b>{amount_toman:,} تومان</b>\n"
        f"⭐️ ستاره‌های پرداختی: <b>{stars_count:,} XTR</b>\n"
        f"💳 موجودی جدید کیف پول: <b>{new_balance:,} تومان</b>\n\n"
        f"اکنون می‌توانید از موجودی کیف پول خود برای خرید یا تمدید اشتراک استفاده کنید."
    )
    try:
        await bot.send_message(chat_id=user_tid, text=receipt_text)
    except Exception as exc:
        logger.warning("Failed to send stars confirmation to user %s: %s", user_tid, exc)

    # Sync with Admin Supergroup/Topic
    store_settings = await get_store_settings(session)
    topic_id = store_settings.topic_topups
    if topic_id:
        admin_text = (
            f"⭐️ <b>شارژ موفق از طریق Telegram Stars</b>\n\n"
            f"👤 کاربر: <b>{escape(first_name)}</b> (<code>{user_tid}</code>)\n"
            f"💵 مبلغ: <b>{amount_toman:,} تومان</b>\n"
            f"⭐️ تعداد ستاره: <b>{stars_count:,} Stars</b>\n"
            f"🧾 شناسه تلگرام: <code>{sp.telegram_payment_charge_id}</code>"
        )
        try:
            from bot.config import get_settings
            admin_chat_id = get_settings().ADMIN_SUPERGROUP_ID
            if admin_chat_id:
                kwargs = admin_thread_kwargs(topic_id)
                await bot.send_message(chat_id=admin_chat_id, text=admin_text, **kwargs)
        except Exception as exc:
            logger.warning("Failed to notify admin of stars payment: %s", exc)
