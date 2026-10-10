"""Telegram Stars (XTR) native payment handling."""
import logging
from aiogram import Bot, F, Router
from aiogram.types import Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import admin_thread_kwargs
from bot.db.repositories.wallet_repo import WalletRepository
from bot.db.repositories.user_repo import UserRepository
from bot.services.app_settings import get_store_settings

logger = logging.getLogger(__name__)
router = Router(name="payment_stars")


@router.pre_checkout_query()
async def stars_pre_checkout_handler(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """Confirm Telegram Stars pre-checkout inquiry."""
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
        logger.warning("Unrecognized successful_payment payload: %s", payload)
        return

    try:
        user_tid = int(parts[1])
        amount_toman = int(parts[2])
        stars_count = int(parts[3])
    except (ValueError, TypeError):
        logger.exception("Invalid payload numbers in %s", payload)
        return

    wallet_repo = WalletRepository(session)
    user_repo = UserRepository(session)

    # Atomically credit wallet
    new_balance = await wallet_repo.adjust_balance(user_tid, amount_toman)
    await session.commit()

    user = await user_repo.get_by_telegram_id(user_tid)
    first_name = user.full_name or f"@{user.username}" if user else f"کاربر {user_tid}"

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
            f"👤 کاربر: <b>{first_name}</b> (<code>{user_tid}</code>)\n"
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
