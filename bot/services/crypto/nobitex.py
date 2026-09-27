"""Nobitex rate checker and daily scheduled notifier for TON price."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import get_settings
from bot.services.app_settings import get_store_settings

logger = logging.getLogger(__name__)

# Daily scheduled hours (Asia/Tehran) — 4 times per day: 10:00, 14:00, 18:00, 22:00
RATE_CHECK_HOURS = (10, 14, 18, 22)


async def fetch_nobitex_ton_price() -> int | None:
    """Fetch latest TON/IRT price in Toman from Nobitex."""
    headers = {"User-Agent": "Remnabot/1.0"}
    timeout = aiohttp.ClientTimeout(total=8)

    # 1. Try v2 orderbook
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.nobitex.ir/v2/orderbook/TONIRT", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    last_price = data.get("lastTradePrice")
                    if last_price:
                        return int(float(last_price))
    except Exception as e:
        logger.debug("nobitex v2 orderbook request failed: %s", e)

    # 2. Try market/stats fallback
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.nobitex.ir/market/stats?srcCurrency=ton&dstCurrency=rls", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    stats = data.get("stats", {})
                    ton_rls = stats.get("ton-rls", {})
                    latest_rls = ton_rls.get("latest")
                    if latest_rls:
                        return int(float(latest_rls) // 10)
    except Exception as e:
        logger.debug("nobitex stats request failed: %s", e)

    return None


def format_rate_alert(
    nobitex_price: int, current_rate: int, hour_str: str = ""
) -> tuple[str, InlineKeyboardMarkup]:
    """Format the rate notification text and keyboard with proper LTR signs."""
    diff = nobitex_price - current_rate

    if current_rate > 0:
        percent = (diff / current_rate) * 100.0
    else:
        percent = 0.0

    if diff > 0:
        diff_str = f"\u200e+{diff:,} تومان"
        percent_str = f"(\u200e+{percent:.1f}%)"
    elif diff < 0:
        diff_str = f"\u200e-{abs(diff):,} تومان"
        percent_str = f"(\u200e-{abs(percent):.1f}%)"
    else:
        diff_str = "0 تومان"
        percent_str = "(0%)"

    curr_rate_str = f"{current_rate:,} تومان" if current_rate > 0 else "— (تنظیم‌نشده)"

    time_header = f" — ساعت {hour_str}" if hour_str else ""
    text = (
        f"💎 <b>استعلام نرخ تون (نوبیتکس){time_header}</b>\n"
        f"──────────────────\n"
        f"📊 قیمت لحظه‌ای نوبیتکس : <b>{nobitex_price:,}</b> تومان\n"
        f"⚙️ نرخ فعلی در فروشگاه : <b>{curr_rate_str}</b>\n"
        f"📈 اختلاف : <b>{diff_str}</b> <b>{percent_str}</b>\n\n"
        f"💡 برای به‌روزرسانی نرخ در فروشگاه، دکمه زیر را لمس کنید:"
    )

    kb = InlineKeyboardBuilder()
    kb.button(
        text=f"🔄 اعمال قیمت نوبیتکس ({nobitex_price:,} تومان)",
        callback_data=f"adm:rate:apply:{nobitex_price}",
    )
    kb.button(
        text="✏️ تنظیم نرخ دلخواه",
        callback_data="adm:set:ton_rate_toman",
    )
    kb.adjust(1)

    return text, kb.as_markup()


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
        # First target hour tomorrow
        tomorrow = now + timedelta(days=1)
        target_h = sorted(target_hours)[0]
        target_dt = tomorrow.replace(hour=target_h, minute=0, second=0, microsecond=0)

    wait = (target_dt - now).total_seconds()
    return max(1.0, wait), target_h


async def send_rate_notification(bot: Bot, session_factory, hour_str: str = "") -> bool:
    """Fetch Nobitex price and send alert to crypto topic."""
    price = await fetch_nobitex_ton_price()
    if price is None:
        logger.warning("Could not fetch TON price from Nobitex for scheduled alert")
        return False

    settings = get_settings()
    async with session_factory() as session:
        store = await get_store_settings(session)
        text, kb = format_rate_alert(price, store.ton_rate_toman, hour_str)

        topic_id = (
            store.topic_crypto
            or settings.ADMIN_TOPIC_CRYPTO
            or store.topic_alerts
            or settings.ADMIN_TOPIC_ALERTS
            or store.topic_topups
            or settings.ADMIN_TOPIC_TOPUPS
        )
        thread_kwargs = {"message_thread_id": topic_id} if topic_id else {}

        try:
            await bot.send_message(settings.ADMIN_CHAT_ID, text, reply_markup=kb, **thread_kwargs)
            logger.info("Sent Nobitex TON rate alert to topic %s (price: %d)", topic_id, price)
            return True
        except Exception:
            logger.exception("Failed to send Nobitex rate alert to admin chat")
            return False


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
        except Exception:
            logger.exception("Error in Nobitex rate scheduled task")

        # Sleep briefly to avoid double-triggering in the same minute
        await asyncio.sleep(120)
