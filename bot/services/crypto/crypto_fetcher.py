"""Crypto exchange price fetchers (Nobitex, Bitpin, Wallex, Tetherland, Ramzinex, Binance)."""
import asyncio
import logging

import aiohttp

from bot.config import get_settings

logger = logging.getLogger(__name__)


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
                except Exception as exc:
                    logger.warning("Nobitex orderbook fetch failed for %s: %s", symbol, exc)

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
        or getattr(settings, "USDT_RATE_TOMAN", 0)
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

    # Calculate EUR in Toman for all domestic exchanges based on Binance EUR/USDT benchmark
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
