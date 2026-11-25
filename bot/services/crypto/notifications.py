"""Shared Telegram notification helper for on-chain crypto wallet credits."""
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def notify_crypto_credit(
    bot: Any,
    session: Any,
    invoice: Any,
    new_bal: int,
    *,
    currency_code: str,
    currency_fa: str,
    emoji: str,
    explorer_label: str,
    tx_url: str,
    send_user: bool = True,
) -> None:
    """Send Telegram notifications to user and admin topic AFTER DB commit."""
    if not bot:
        return
    amount_crypto = getattr(invoice, "amount_ton", "") or ""
    amount_toman = int(getattr(invoice, "amount_toman", 0) or 0)
    try:
        from bot.common import admin_thread_kwargs
        from bot.config import get_settings
        from bot.services.app_settings import get_store_settings

        settings = get_settings()
        store = await get_store_settings(session)

        if send_user:
            user_msg = (
                f"✅ <b>شارژ موفق حساب با {currency_fa} ({currency_code})</b>\n\n"
                f"{emoji} مقدار واریزی: <code>{amount_crypto} {currency_code}</code>\n"
                f"💰 مبلغ شارژ: <b>{amount_toman:,} تومان</b>\n"
                f"👛 موجودی جدید: <b>{new_bal:,} تومان</b>"
            )
            await bot.send_message(invoice.telegram_id, user_msg)

        if settings.ADMIN_CHAT_ID:
            topic_id = (
                getattr(store, "topic_crypto", None)
                or settings.ADMIN_TOPIC_CRYPTO
                or getattr(store, "topic_topups", None)
                or settings.ADMIN_TOPIC_TOPUPS
            )
            thread_kwargs = admin_thread_kwargs(topic_id=topic_id)
            admin_msg = (
                f"{emoji} <b>واریز جدید با ارز {currency_fa} ({currency_code})</b>\n"
                f"──────────────────\n"
                f"👤 کاربر: <code>{invoice.telegram_id}</code>\n"
                f"💰 مبلغ تومانی: <b>{amount_toman:,} تومان</b>\n"
                f"{emoji} مقدار دریافتی: <code>{amount_crypto} {currency_code}</code>\n"
                f"🔗 <a href=\"{tx_url}\">مشاهده در {explorer_label}</a>\n\n"
                f"👛 موجودی جدید: <b>{new_bal:,} تومان</b>"
            )
            await bot.send_message(settings.ADMIN_CHAT_ID, admin_msg, **thread_kwargs)
    except Exception as n_err:
        logger.warning("Failed notifying user/admin of %s topup: %s", currency_code, n_err)
