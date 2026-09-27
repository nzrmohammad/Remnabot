"""Nobitex rate checker and daily scheduled notifier for TON price."""
import asyncio
import logging
from datetime import datetime, timedelta
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


async def fetch_ton_market_price(usdt_rate: int | None = None) -> tuple[int | None, str]:
    """Fetch latest TON price in Toman from Nobitex, with Bitpin, Wallex, Tabdeal,
    and global Binance/TonAPI fallbacks (TON/USD * USDT rate).

    Returns (price_in_toman, source_name).
    """
    settings = get_settings()
    proxy = settings.IRAN_PROXY.strip() if getattr(settings, "IRAN_PROXY", "") else None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fa,en-US;q=0.9,en;q=0.8",
        "Referer": "https://nobitex.ir/",
    }
    timeout = aiohttp.ClientTimeout(total=8)

    # 1. Nobitex v2 orderbook (with optional IRAN_PROXY)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.nobitex.ir/v2/orderbook/TONIRT", headers=headers, proxy=proxy) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    last_price = data.get("lastTradePrice")
                    if last_price:
                        return int(float(last_price)), "نوبیتکس"
                else:
                    logger.warning("Nobitex v2 orderbook returned HTTP %s", resp.status)
    except Exception as e:
        logger.debug("Nobitex v2 orderbook request failed: %s", e)

    # 2. Nobitex market/stats fallback
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.nobitex.ir/market/stats?srcCurrency=ton&dstCurrency=rls", headers=headers, proxy=proxy) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    stats = data.get("stats", {})
                    ton_rls = stats.get("ton-rls", {})
                    latest_rls = ton_rls.get("latest")
                    if latest_rls:
                        return int(float(latest_rls) // 10), "نوبیتکس"
                else:
                    logger.warning("Nobitex stats returned HTTP %s", resp.status)
    except Exception as e:
        logger.debug("Nobitex stats request failed: %s", e)

    # 3. Bitpin API fallback
    for bitpin_domain in ("api.bitpin.org", "api.bitpin.ir"):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"https://{bitpin_domain}/v1/mkt/markets/", headers=headers, proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results") or (data if isinstance(data, list) else [])
                        for m in results:
                            code = m.get("code") or ""
                            if code in ("TON_IRT", "TON_RLS"):
                                price_raw = m.get("price") or (m.get("order_book_info") or {}).get("last_trade_price")
                                if price_raw:
                                    return int(float(price_raw) // 10), "بیت‌پین"
                    else:
                        logger.warning("Bitpin %s returned HTTP %s", bitpin_domain, resp.status)
        except Exception as e:
            logger.debug("Bitpin %s request failed: %s", bitpin_domain, e)

    # 4. Wallex API fallback
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.wallex.ir/v1/markets", headers=headers, proxy=proxy) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    symbols = (data.get("result") or {}).get("symbols") or {}
                    for sym_name in ("TONTMN", "TONIRT"):
                        if sym_name in symbols:
                            last_price = (symbols[sym_name].get("stats") or {}).get("lastPrice")
                            if last_price:
                                return int(float(last_price)), "والکس"
                else:
                    logger.warning("Wallex returned HTTP %s", resp.status)
    except Exception as e:
        logger.debug("Wallex markets request failed: %s", e)

    # 5. Global Fallback: Binance TON/USDT * USDT Rate (100% accessible worldwide)
    benchmark_usdt = usdt_rate or getattr(settings, "USDT_RATE_TOMAN", 95000) or 95000
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    usd_p = float(data.get("price", "0"))
                    if usd_p > 0:
                        toman_p = int(round(usd_p * benchmark_usdt))
                        return toman_p, f"بایننس (${usd_p:.2f})"
                else:
                    logger.warning("Binance TONUSDT returned HTTP %s", resp.status)
    except Exception as e:
        logger.debug("Binance TONUSDT request failed: %s", e)

    # 6. Global Fallback: TonAPI (TON Foundation official)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://tonapi.io/v2/rates?tokens=ton&currencies=usd", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rates = data.get("rates", {}).get("TON", {}).get("prices", {})
                    usd_p = float(rates.get("USD", 0))
                    if usd_p > 0:
                        toman_p = int(round(usd_p * benchmark_usdt))
                        return toman_p, f"TonAPI (${usd_p:.2f})"
                else:
                    logger.warning("TonAPI returned HTTP %s", resp.status)
    except Exception as e:
        logger.debug("TonAPI request failed: %s", e)

    # 7. Global Fallback: CoinGecko
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    usd_p = float(data.get("the-open-network", {}).get("usd", 0))
                    if usd_p > 0:
                        toman_p = int(round(usd_p * benchmark_usdt))
                        return toman_p, f"CoinGecko (${usd_p:.2f})"
                else:
                    logger.warning("CoinGecko returned HTTP %s", resp.status)
    except Exception as e:
        logger.debug("CoinGecko request failed: %s", e)

    return None, ""


async def fetch_nobitex_ton_price() -> int | None:
    """Fetch latest TON/IRT price in Toman (backward compatible)."""
    price, _ = await fetch_ton_market_price()
    return price


def format_rate_alert(
    nobitex_price: int, current_rate: int, hour_str: str = "", source_name: str = "نوبیتکس"
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
    src_title = source_name or "نوبیتکس"
    text = (
        f"💎 <b>استعلام نرخ تون ({src_title}){time_header}</b>\n"
        f"──────────────────\n"
        f"📊 قیمت لحظه‌ای {src_title} : <b>{nobitex_price:,}</b> تومان\n"
        f"⚙️ نرخ فعلی در فروشگاه : <b>{curr_rate_str}</b>\n"
        f"📈 اختلاف : <b>{diff_str}</b> <b>{percent_str}</b>\n\n"
        f"💡 برای به‌روزرسانی نرخ در فروشگاه، دکمه زیر را لمس کنید:"
    )

    kb = InlineKeyboardBuilder()
    kb.button(
        text=f"🔄 اعمال قیمت {src_title} ({nobitex_price:,} تومان)",
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
    """Fetch market price and send alert to crypto topic."""
    settings = get_settings()
    async with session_factory() as session:
        store = await get_store_settings(session)
        price, source = await fetch_ton_market_price(usdt_rate=store.usdt_rate_toman)
        if price is None:
            logger.warning("Could not fetch TON price from any exchange for scheduled alert")
            return False

        text, kb = format_rate_alert(price, store.ton_rate_toman, hour_str, source_name=source or "نوبیتکس")

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
