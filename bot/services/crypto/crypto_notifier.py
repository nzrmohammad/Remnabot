"""Crypto price notification scheduler and admin topic broadcaster."""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from bot.common import admin_thread_kwargs
from bot.config import get_settings
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.services.app_settings import get_store_settings
from bot.services.crypto.crypto_fetcher import fetch_all_exchange_prices
from bot.services.crypto.crypto_rates import (
    format_full_crypto_market_alert,
)

logger = logging.getLogger(__name__)

# Daily scheduled hours (Asia/Tehran) — 4 times per day: 10:00, 14:00, 18:00, 22:00
RATE_CHECK_HOURS = (10, 14, 18, 22)


def _seconds_until_next_target(
    target_hours: tuple[int, ...] = RATE_CHECK_HOURS,
    tz_name: str = "Asia/Tehran",
) -> tuple[float, int]:
    """Calculate seconds until the next target hour in Tehran timezone."""
    now = datetime.now(ZoneInfo(tz_name))
    candidates = []
    for h in sorted(target_hours):
        dt = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if dt > now:
            candidates.append((dt, h))

    if candidates:
        target_dt, target_h = candidates[0]
    else:
        tomorrow = now + timedelta(days=1)
        target_h = sorted(target_hours)[0]
        target_dt = tomorrow.replace(hour=target_h, minute=0, second=0, microsecond=0)

    wait = (target_dt - now).total_seconds()
    return max(1.0, wait), target_h


async def send_rate_notification(bot: Bot, session_factory, hour_str: str = "") -> bool:
    """Fetch market prices, delete previous rate message, and send comprehensive rate alert to crypto topic."""
    settings = get_settings()
    async with session_factory() as session:
        store = await get_store_settings(session)
        market_data = await fetch_all_exchange_prices(usdt_rate=store.usdt_rate_toman)
        best_ton, _ = market_data.get("best_ton", (None, ""))
        if best_ton is None and not market_data.get("usdt"):
            logger.warning("Could not fetch TON or USDT price from any exchange for scheduled alert")
            return False

        topic_id = (
            store.topic_crypto
            or settings.ADMIN_TOPIC_CRYPTO
            or store.topic_alerts
            or settings.ADMIN_TOPIC_ALERTS
            or store.topic_topups
            or settings.ADMIN_TOPIC_TOPUPS
        )
        thread_kwargs = admin_thread_kwargs(topic_id=topic_id)

        app_repo = AppSettingRepository(session)

        # 1. Delete previous price alert message(s) to avoid clutter in the topic
        prev_raw = await app_repo.get("last_admin_crypto_rate_msg_ids")
        if prev_raw:
            try:
                prev_ids = json.loads(prev_raw)
                for mid in prev_ids:
                    try:
                        await bot.delete_message(chat_id=settings.ADMIN_CHAT_ID, message_id=mid)
                    except Exception:
                        pass
            except Exception as clean_err:
                logger.debug("Failed cleaning previous crypto rate alert: %s", clean_err)

        # 2. Format comprehensive rate alert covering TON, USDT, Stars, and EUR
        alert_text, alert_kb = format_full_crypto_market_alert(
            market_data=market_data,
            store=store,
            hour_str=hour_str,
        )

        delivered = False
        if settings.ADMIN_CHAT_ID:
            try:
                sent_msg = await bot.send_message(
                    settings.ADMIN_CHAT_ID,
                    alert_text,
                    reply_markup=alert_kb,
                    **thread_kwargs,
                )
                delivered = True
                await app_repo.set(
                    "last_admin_crypto_rate_msg_ids",
                    json.dumps([sent_msg.message_id]),
                )
                await session.commit()
            except Exception as exc:
                logger.warning("Failed to send comprehensive crypto rate alert to admin chat: %s", exc)
                # Fallback without thread_kwargs if topic delivery fails
                if thread_kwargs:
                    try:
                        sent_msg = await bot.send_message(
                            settings.ADMIN_CHAT_ID,
                            alert_text,
                            reply_markup=alert_kb,
                        )
                        delivered = True
                        await app_repo.set(
                            "last_admin_crypto_rate_msg_ids",
                            json.dumps([sent_msg.message_id]),
                        )
                        await session.commit()
                    except Exception as fallback_exc:
                        logger.warning("Failed fallback send to admin chat: %s", fallback_exc)

        return delivered


async def nobitex_rate_loop(bot: Bot, session_factory) -> None:
    """Runs 4 times a day (10:00, 14:00, 18:00, 22:00 Tehran time) sending rate alerts."""
    settings = get_settings()
    tz_name = settings.TIMEZONE or "Asia/Tehran"
    logger.info("Starting Nobitex TON rate scheduler (target hours: %s %s)", RATE_CHECK_HOURS, tz_name)

    # Initial brief warm-up
    await asyncio.sleep(20)

    while True:
        wait_seconds, next_hour = _seconds_until_next_target(RATE_CHECK_HOURS, tz_name)
        logger.info(
            "Next Nobitex TON rate alert scheduled in %.0f s (at %02d:00 %s)",
            wait_seconds, next_hour, tz_name,
        )
        await asyncio.sleep(wait_seconds)

        hour_str = f"{next_hour:02d}:00"
        try:
            async with session_factory() as session:
                store = await get_store_settings(session)
                # Only send if crypto is enabled or configured
                if store.crypto_enabled or store.ton_wallet_address or store.ton_rate_toman > 0:
                    await send_rate_notification(bot, session_factory, hour_str)
        except Exception as exc:
            logger.error("Error in Nobitex rate scheduled task: %s", exc)

        # Sleep briefly to avoid double-triggering in the same minute
        await asyncio.sleep(120)
