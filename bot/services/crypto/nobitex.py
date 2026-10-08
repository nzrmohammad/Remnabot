"""Nobitex rate checker and daily scheduled notifier for TON price."""
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.common import admin_thread_kwargs
from bot.config import get_settings
from bot.services.app_settings import get_store_settings

logger = logging.getLogger(__name__)

# Daily scheduled hours (Asia/Tehran) — 4 times per day: 10:00, 14:00, 18:00, 22:00
RATE_CHECK_HOURS = (10, 14, 18, 22)


async def fetch_all_exchange_prices(usdt_rate: int | None = None) -> dict:
    """Fetch live TON and USDT prices across domestic exchanges (Nobitex, Bitpin, Wallex)
    and international benchmark (Binance TON/USDT).
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

    ton_prices: dict[str, int] = {}
    usdt_prices: dict[str, int] = {}
    eur_prices: dict[str, int] = {}
    binance_ton_usd: float | None = None
    binance_eur_usd: float | None = None

    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 1. Nobitex
        async def _fetch_nobitex():
            for symbol in ("GRAMIRT", "TONIRT"):
                try:
                    async with session.get(f"https://apiv2.nobitex.ir/v2/orderbook/{symbol}", headers=headers, proxy=proxy) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            p = data.get("lastTradePrice")
                            if p:
                                ton_prices["نوبیتکس"] = int(float(p) // 10)
                                break
                except Exception:
                    pass

            try:
                async with session.get("https://apiv2.nobitex.ir/market/stats", headers=headers, proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        st = data.get("stats", {})
                        if "نوبیتکس" not in ton_prices:
                            ton_info = st.get("gram-rls") or st.get("ton-rls")
                            if ton_info and ton_info.get("latest"):
                                ton_prices["نوبیتکس"] = int(float(ton_info["latest"]) // 10)
                        usdt_info = st.get("usdt-rls")
                        if usdt_info and usdt_info.get("latest"):
                            usdt_prices["نوبیتکس"] = int(float(usdt_info["latest"]) // 10)
                        eur_info = st.get("eur-rls") or st.get("eur-irt")
                        if eur_info and eur_info.get("latest"):
                            eur_prices["نوبیتکس"] = int(float(eur_info["latest"]) // 10)
            except Exception as e:
                logger.debug("Nobitex stats failed: %s", e)

        # 2. Bitpin
        async def _fetch_bitpin():
            for bitpin_domain in ("api.bitpin.org", "api.bitpin.ir"):
                try:
                    async with session.get(f"https://{bitpin_domain}/v1/mkt/markets/", headers=headers, proxy=proxy) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            results = data.get("results") or (data if isinstance(data, list) else [])
                            for m in results:
                                code = (m.get("code") or "").upper()
                                if code in ("GRAM_IRT", "TON_IRT"):
                                    p = m.get("price") or (m.get("order_book_info") or {}).get("last_trade_price")
                                    if p:
                                        ton_prices["بیت‌پین"] = int(float(p))
                                elif code in ("GRAM_RLS", "TON_RLS"):
                                    p = m.get("price") or (m.get("order_book_info") or {}).get("last_trade_price")
                                    if p:
                                        ton_prices["بیت‌پین"] = int(float(p) // 10)
                                elif code == "USDT_IRT":
                                    p = m.get("price") or (m.get("order_book_info") or {}).get("last_trade_price")
                                    if p:
                                        usdt_prices["بیت‌پین"] = int(float(p))
                                elif code == "USDT_RLS":
                                    p = m.get("price") or (m.get("order_book_info") or {}).get("last_trade_price")
                                    if p:
                                        usdt_prices["بیت‌پین"] = int(float(p) // 10)
                            if "بیت‌پین" in ton_prices or "بیت‌پین" in usdt_prices:
                                break
                except Exception as e:
                    logger.debug("Bitpin %s failed: %s", bitpin_domain, e)

        # 3. Wallex
        async def _fetch_wallex():
            try:
                async with session.get("https://api.wallex.ir/v1/markets", headers=headers, proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        symbols = (data.get("result") or {}).get("symbols") or {}
                        for sym in ("GRAMTMN", "GRAMIRT", "TONTMN", "TONIRT"):
                            if sym in symbols:
                                lp = (symbols[sym].get("stats") or {}).get("lastPrice")
                                if lp and str(lp).strip() not in ("", "-"):
                                    ton_prices["والکس"] = int(float(lp))
                                    break
                        for sym in ("USDTTMN", "USDTIRT"):
                            if sym in symbols:
                                lp = (symbols[sym].get("stats") or {}).get("lastPrice")
                                if lp and str(lp).strip() not in ("", "-"):
                                    usdt_prices["والکس"] = int(float(lp))
                                    break
            except Exception as e:
                logger.debug("Wallex failed: %s", e)

        # 4. TetherLand (تترلند)
        async def _fetch_tetherland():
            try:
                async with session.get("https://api.tetherland.com/currencies", headers=headers, proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        p = (data.get("data", {}).get("currencies", {}).get("USDT", {})).get("price")
                        if p:
                            usdt_prices["تترلند"] = int(float(p))
            except Exception as e:
                logger.debug("Tetherland failed: %s", e)

        # 5. Ramzinex (رمزینکس)
        async def _fetch_ramzinex():
            try:
                async with session.get("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs/11", headers=headers, proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        sell = (data.get("data") or {}).get("sell")
                        if sell:
                            usdt_prices["رمزینکس"] = int(float(sell) // 10)
            except Exception as e:
                logger.debug("Ramzinex USDT failed: %s", e)

            try:
                async with session.get("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/pairs/272", headers=headers, proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        sell = (data.get("data") or {}).get("sell")
                        if sell:
                            ton_prices["رمزینکس"] = int(float(sell) // 10)
            except Exception as e:
                logger.debug("Ramzinex TON failed: %s", e)

        # 6. Binance (global)
        async def _fetch_binance():
            nonlocal binance_ton_usd, binance_eur_usd
            try:
                async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        p = float(data.get("price", "0"))
                        if p > 0:
                            binance_ton_usd = p
            except Exception as e:
                logger.debug("Binance TON failed: %s", e)

            try:
                async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=EURUSDT", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        p = float(data.get("price", "0"))
                        if p > 0:
                            binance_eur_usd = p
            except Exception as e:
                logger.debug("Binance EUR failed: %s", e)

        await asyncio.gather(
            _fetch_nobitex(),
            _fetch_bitpin(),
            _fetch_wallex(),
            _fetch_tetherland(),
            _fetch_ramzinex(),
            _fetch_binance(),
            return_exceptions=True,
        )

    # Priority for single best TON: Nobitex > Ramzinex > Bitpin > Wallex > Binance
    best_ton_price: int | None = None
    best_ton_source = ""
    for src in ("نوبیتکس", "رمزینکس", "بیت‌پین", "والکس"):
        if src in ton_prices:
            best_ton_price = ton_prices[src]
            best_ton_source = src
            break

    effective_usdt = (
        usdt_prices.get("نوبیتکس")
        or usdt_prices.get("تترلند")
        or usdt_prices.get("رمزینکس")
        or usdt_prices.get("بیت‌پین")
        or usdt_prices.get("والکس")
        or usdt_rate
        or getattr(settings, "USDT_RATE_TOMAN", 95000)
        or 95000
    )

    if best_ton_price is None and binance_ton_usd:
        best_ton_price = int(round(binance_ton_usd * effective_usdt))
        best_ton_source = f"بایننس (${binance_ton_usd:.2f})"

    # Priority for single best USDT: Nobitex > Tetherland > Ramzinex > Bitpin > Wallex
    best_usdt_price: int | None = None
    best_usdt_source = ""
    for src in ("نوبیتکس", "تترلند", "رمزینکس", "بیت‌پین", "والکس"):
        if src in usdt_prices:
            best_usdt_price = usdt_prices[src]
            best_usdt_source = src
            break

    # Calculate EUR in Toman for all domestic exchanges (Nobitex, Tetherland, Ramzinex, Bitpin, Wallex)
    # based on their live USDT exchange rate and international Binance EUR/USDT benchmark
    eur_rate_mult = binance_eur_usd if (binance_eur_usd and binance_eur_usd > 0) else 1.085
    for exch_name in ("نوبیتکس", "تترلند", "رمزینکس", "بیت‌پین", "والکس"):
        if exch_name not in eur_prices and exch_name in usdt_prices:
            u_price = usdt_prices[exch_name]
            if u_price > 0:
                eur_prices[exch_name] = int(round(u_price * eur_rate_mult))

    if binance_eur_usd and "بایننس" not in eur_prices:
        eur_prices["بایننس"] = int(round(binance_eur_usd * effective_usdt))

    best_eur_price: int | None = None
    best_eur_source = ""
    for src in ("نوبیتکس", "تترلند", "رمزینکس", "بیت‌پین", "والکس", "بایننس"):
        if src in eur_prices:
            best_eur_price = eur_prices[src]
            best_eur_source = src if src != "بایننس" else f"بایننس (${binance_eur_usd:.3f})"
            break

    return {
        "ton": ton_prices,
        "usdt": usdt_prices,
        "eur": eur_prices,
        "binance_usd": binance_ton_usd,
        "binance_eur_usd": binance_eur_usd,
        "best_ton": (best_ton_price, best_ton_source),
        "best_usdt": (best_usdt_price, best_usdt_source),
        "best_eur": (best_eur_price, best_eur_source),
    }


async def fetch_ton_market_price(usdt_rate: int | None = None) -> tuple[int | None, str]:
    """Fetch latest TON price in Toman from Nobitex, Bitpin, Wallex, or global Binance.

    Returns (price_in_toman, source_name).
    """
    market_data = await fetch_all_exchange_prices(usdt_rate=usdt_rate)
    p, src = market_data.get("best_ton", (None, ""))
    if p is not None:
        return p, src
    return None, ""


async def fetch_nobitex_ton_price() -> int | None:
    """Fetch latest TON/IRT price in Toman (backward compatible)."""
    price, _ = await fetch_ton_market_price()
    return price


def format_rate_alert(
    nobitex_price: int, current_rate: int, hour_str: str = "", source_name: str = "نوبیتکس"
) -> tuple[str, InlineKeyboardMarkup]:
    """Format single-source rate notification text and keyboard with proper LTR signs."""
    diff = nobitex_price - current_rate

    if current_rate > 0:
        percent = (diff / current_rate) * 100.0
    else:
        percent = 0.0

    if diff > 0:
        diff_str = f"{diff:,}+ تومان"
        percent_str = f"(%{percent:.1f}+)"
    elif diff < 0:
        diff_str = f"{abs(diff):,}- تومان"
        percent_str = f"(%{abs(percent):.1f}-)"
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
    kb.button(
        text="🔙 بازگشت",
        callback_data="adm:settings:crypto",
    )
    kb.adjust(1)

    return text, kb.as_markup()


def format_multi_rate_alert(
    market_data: dict,
    current_ton_rate: int,
    current_usdt_rate: int,
    hour_str: str = "",
) -> tuple[str, InlineKeyboardMarkup]:
    """Format comprehensive rate notification showing Nobitex, Bitpin, Wallex, and USDT rates."""
    ton_prices = market_data.get("ton", {})
    usdt_prices = market_data.get("usdt", {})
    binance_usd = market_data.get("binance_usd")

    best_ton_p, best_ton_src = market_data.get("best_ton", (None, ""))
    ref_ton_price = best_ton_p or current_ton_rate

    diff_ton = ref_ton_price - current_ton_rate
    if current_ton_rate > 0:
        percent = (diff_ton / current_ton_rate) * 100.0
    else:
        percent = 0.0

    if diff_ton > 0:
        diff_str = f"{diff_ton:,}+ تومان"
        percent_str = f"(%{percent:.1f}+)"
    elif diff_ton < 0:
        diff_str = f"{abs(diff_ton):,}- تومان"
        percent_str = f"(%{abs(percent):.1f}-)"
    else:
        diff_str = "0 تومان"
        percent_str = "(0%)"

    curr_ton_str = f"{current_ton_rate:,} تومان" if current_ton_rate > 0 else "— (تنظیم‌نشده)"
    curr_usdt_str = f"{current_usdt_rate:,} تومان" if current_usdt_rate > 0 else "—"

    time_header = f" — ساعت {hour_str}" if hour_str else ""

    lines = [
        f"💎 <b>استعلام نرخ لحظه‌ای صرافی‌ها{time_header}</b>",
        "──────────────────",
        "📊 <b>قیمت لحظه‌ای تون (TON):</b>",
    ]

    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = ton_prices.get(name)
        val_str = f"<b>{p:,}</b> تومان" if p else "<i>عدم دسترسی</i>"
        lines.append(f"   🔹 {name} : {val_str}")

    if binance_usd:
        lines.append(f"   🌐 بایننس جهانی : <b>${binance_usd:.2f}</b>")

    lines.append("")
    lines.append("💵 <b>قیمت لحظه‌ای تتر (USDT / دلار):</b>")
    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = usdt_prices.get(name)
        val_str = f"<b>{p:,}</b> تومان" if p else "<i>عدم دسترسی</i>"
        lines.append(f"   🔹 {name} : {val_str}")

    lines.append("")
    lines.append("⚙️ <b>وضعیت فعلی در فروشگاه:</b>")
    lines.append(f"   💎 نرخ فعلی تون : <b>{curr_ton_str}</b>")
    if current_ton_rate > 0 and ref_ton_price:
        lines.append(f"   📈 اختلاف تون : <b>{diff_str}</b> <b>{percent_str}</b>")
    lines.append(f"   💵 نرخ مبنای تتر : <b>{curr_usdt_str}</b>")
    lines.append("")
    lines.append("💡 برای به‌روزرسانی نرخ در فروشگاه، دکمه مورد نظر را لمس فرمایید:")

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()

    # TON apply buttons
    ton_btns_count = 0
    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = ton_prices.get(name)
        if p:
            kb.button(
                text=f"🔄 اعمال تون {name} ({p:,} تومان)",
                callback_data=f"adm:rate:apply:ton:{p}",
            )
            ton_btns_count += 1

    # USDT apply buttons
    usdt_btns_count = 0
    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = usdt_prices.get(name)
        if p:
            kb.button(
                text=f"💵 اعمال تتر {name} ({p:,} تومان)",
                callback_data=f"adm:rate:apply:usdt:{p}",
            )
            usdt_btns_count += 1

    # Manual adjustments
    kb.button(text="✏️ نرخ دلخواه تون", callback_data="adm:set:ton_rate_toman")
    kb.button(text="✏️ نرخ دلخواه تتر", callback_data="adm:set:usdt_rate_toman")

    # Back button
    kb.button(text="🔙 بازگشت", callback_data="adm:settings:crypto")

    adjust_spec = [1] * ton_btns_count + [1] * usdt_btns_count + [2, 1]
    kb.adjust(*adjust_spec)

    return text, kb.as_markup()


def format_ton_rate_alert(
    market_data: dict,
    current_ton_rate: int,
    hour_str: str = "",
) -> tuple[str, InlineKeyboardMarkup]:
    """Format TON price notification showing Nobitex, Bitpin, Wallex, and Binance."""
    ton_prices = market_data.get("ton", {})
    binance_usd = market_data.get("binance_usd")

    best_ton_p, best_ton_src = market_data.get("best_ton", (None, ""))
    ref_ton_price = best_ton_p or current_ton_rate

    diff_ton = ref_ton_price - current_ton_rate
    if current_ton_rate > 0:
        percent = (diff_ton / current_ton_rate) * 100.0
    else:
        percent = 0.0

    if diff_ton > 0:
        diff_str = f"{diff_ton:,}+ تومان"
        percent_str = f"(%{percent:.1f}+)"
    elif diff_ton < 0:
        diff_str = f"{abs(diff_ton):,}- تومان"
        percent_str = f"(%{abs(percent):.1f}-)"
    else:
        diff_str = "0 تومان"
        percent_str = "(0%)"

    curr_ton_str = f"{current_ton_rate:,} تومان" if current_ton_rate > 0 else "— (تنظیم‌نشده)"
    time_header = f" — ساعت {hour_str}" if hour_str else ""

    lines = [
        f"💎 <b>استعلام نرخ لحظه‌ای تون (TON){time_header}</b>",
        "──────────────────",
        "📊 <b>قیمت لحظه‌ای تون در صرافی‌ها:</b>",
    ]

    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = ton_prices.get(name)
        val_str = f"<b>{p:,}</b> تومان" if p else "<i>عدم دسترسی</i>"
        lines.append(f"   🔹 {name} : {val_str}")

    if binance_usd:
        lines.append(f"   🌐 بایننس جهانی : <b>${binance_usd:.2f}</b>")

    lines.append("")
    lines.append("⚙️ <b>وضعیت فعلی در فروشگاه:</b>")
    lines.append(f"   💎 نرخ فعلی تون : <b>{curr_ton_str}</b>")
    if current_ton_rate > 0 and ref_ton_price:
        lines.append(f"   📈 اختلاف تون : <b>{diff_str}</b> <b>{percent_str}</b>")
    lines.append("")
    lines.append("💡 برای به‌روزرسانی نرخ در فروشگاه، دکمه مورد نظر را لمس فرمایید:")

    text = "\n".join(lines)
    kb = InlineKeyboardBuilder()

    ton_btns_count = 0
    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = ton_prices.get(name)
        if p:
            kb.button(
                text=f"🔄 اعمال تون {name} ({p:,} تومان)",
                callback_data=f"adm:rate:apply:ton:{p}",
            )
            ton_btns_count += 1

    kb.adjust(1)

    return text, kb.as_markup()


def format_usdt_rate_alert(
    market_data: dict,
    current_usdt_rate: int,
    hour_str: str = "",
) -> tuple[str, InlineKeyboardMarkup]:
    """Format USDT price notification showing Nobitex, Bitpin, Wallex."""
    usdt_prices = market_data.get("usdt", {})

    best_usdt_p, best_usdt_src = market_data.get("best_usdt", (None, ""))
    ref_usdt_price = best_usdt_p or current_usdt_rate

    diff_usdt = ref_usdt_price - current_usdt_rate
    if current_usdt_rate > 0:
        percent = (diff_usdt / current_usdt_rate) * 100.0
    else:
        percent = 0.0

    if diff_usdt > 0:
        diff_str = f"{diff_usdt:,}+ تومان"
        percent_str = f"(%{percent:.1f}+)"
    elif diff_usdt < 0:
        diff_str = f"{abs(diff_usdt):,}- تومان"
        percent_str = f"(%{abs(percent):.1f}-)"
    else:
        diff_str = "0 تومان"
        percent_str = "(0%)"

    curr_usdt_str = f"{current_usdt_rate:,} تومان" if current_usdt_rate > 0 else "—"
    time_header = f" — ساعت {hour_str}" if hour_str else ""

    lines = [
        f"💵 <b>استعلام نرخ لحظه‌ای تتر (USDT / دلار){time_header}</b>",
        "──────────────────",
        "📊 <b>قیمت لحظه‌ای تتر در صرافی‌ها:</b>",
    ]

    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = usdt_prices.get(name)
        val_str = f"<b>{p:,}</b> تومان" if p else "<i>عدم دسترسی</i>"
        lines.append(f"   🔹 {name} : {val_str}")

    lines.append("")
    lines.append("⚙️ <b>وضعیت فعلی در فروشگاه:</b>")
    lines.append(f"   💵 نرخ مبنای تتر : <b>{curr_usdt_str}</b>")
    if current_usdt_rate > 0 and ref_usdt_price:
        lines.append(f"   📈 اختلاف تتر : <b>{diff_str}</b> <b>{percent_str}</b>")
    lines.append("")
    lines.append("💡 برای به‌روزرسانی نرخ در فروشگاه، دکمه مورد نظر را لمس فرمایید:")

    text = "\n".join(lines)
    kb = InlineKeyboardBuilder()

    usdt_btns_count = 0
    for name in ("نوبیتکس", "بیت‌پین", "والکس"):
        p = usdt_prices.get(name)
        if p:
            kb.button(
                text=f"💵 اعمال تتر {name} ({p:,} تومان)",
                callback_data=f"adm:rate:apply:usdt:{p}",
            )
            usdt_btns_count += 1

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
        tomorrow = now + timedelta(days=1)
        target_h = sorted(target_hours)[0]
        target_dt = tomorrow.replace(hour=target_h, minute=0, second=0, microsecond=0)

    wait = (target_dt - now).total_seconds()
    return max(1.0, wait), target_h


async def send_rate_notification(bot: Bot, session_factory, hour_str: str = "") -> bool:
    """Fetch market prices and send separate TON and USDT rate alerts to crypto topic."""
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

        delivered = False
        # 1. Send TON alert
        if market_data.get("ton") or best_ton is not None:
            ton_text, ton_kb = format_ton_rate_alert(
                market_data=market_data,
                current_ton_rate=store.ton_rate_toman,
                hour_str=hour_str,
            )
            try:
                await bot.send_message(settings.ADMIN_CHAT_ID, ton_text, reply_markup=ton_kb, **thread_kwargs)
                delivered = True
            except Exception:
                logger.exception("Failed to send TON rate alert to admin chat")

        # 2. Send USDT alert
        if market_data.get("usdt"):
            usdt_text, usdt_kb = format_usdt_rate_alert(
                market_data=market_data,
                current_usdt_rate=store.usdt_rate_toman,
                hour_str=hour_str,
            )
            try:
                await bot.send_message(settings.ADMIN_CHAT_ID, usdt_text, reply_markup=usdt_kb, **thread_kwargs)
                delivered = True
            except Exception:
                logger.exception("Failed to send USDT rate alert to admin chat")

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
        except Exception:
            logger.exception("Error in Nobitex rate scheduled task")

        # Sleep briefly to avoid double-triggering in the same minute
        await asyncio.sleep(120)
