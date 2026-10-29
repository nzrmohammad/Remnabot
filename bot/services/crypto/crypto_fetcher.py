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
    timeout = aiohttp.ClientTimeout(total=5, connect=2.0)

    ton_prices: dict[str, int] = {}
    usdt_prices: dict[str, int] = {}
    eur_prices: dict[str, int] = {}
    trx_prices: dict[str, int] = {}
    binance_trx_usd: float | None = None
    closed_status: dict[str, str] = {}
    binance_ton_usd: float | None = None
    binance_eur_usd: float | None = None
    global_ton_usd: float | None = None
    global_ton_source: str = ""

    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 1. Nobitex
        async def _fetch_nobitex():
            # First fetch stats to verify market active/closed status
            try:
                async with session.get("https://apiv2.nobitex.ir/market/stats", headers=headers, proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        st = data.get("stats", {})

                        # TON stats
                        ton_info = st.get("gram-rls") or st.get("ton-rls")
                        if ton_info:
                            if ton_info.get("isClosed") or ton_info.get("status") == "closed":
                                closed_status["نوبیتکس_ton"] = "موقتاً غیرفعال (محدودیت نظارتی)"
                            elif ton_info.get("latest"):
                                ton_prices["نوبیتکس"] = int(float(ton_info["latest"]) // 10)

                        # USDT stats
                        usdt_info = st.get("usdt-rls")
                        if usdt_info:
                            if usdt_info.get("isClosed") or usdt_info.get("status") == "closed":
                                closed_status["نوبیتکس_usdt"] = "موقتاً غیرفعال (محدودیت نظارتی)"
                            elif usdt_info.get("latest"):
                                usdt_prices["نوبیتکس"] = int(float(usdt_info["latest"]) // 10)

                        # EUR stats
                        eur_info = st.get("eur-rls") or st.get("eur-irt")
                        if eur_info:
                            if eur_info.get("isClosed") or eur_info.get("status") == "closed":
                                closed_status["نوبیتکس_eur"] = "موقتاً غیرفعال (محدودیت نظارتی)"
                            elif eur_info.get("latest"):
                                eur_prices["نوبیتکس"] = int(float(eur_info["latest"]) // 10)

                        # TRX stats
                        trx_info = st.get("trx-rls") or st.get("trx-irt")
                        if trx_info:
                            if trx_info.get("isClosed") or trx_info.get("status") == "closed":
                                closed_status["نوبیتکس_trx"] = "موقتاً غیرفعال"
                            elif trx_info.get("latest"):
                                trx_prices["نوبیتکس"] = int(float(trx_info["latest"]) // 10)
            except Exception as e:
                logger.debug("Nobitex stats failed: %s", e)

            # Orderbook as secondary for TON only if market is active and not already obtained
            if not closed_status.get("نوبیتکس_ton") and "نوبیتکس" not in ton_prices:
                for symbol in ("GRAMIRT", "TONIRT"):
                    try:
                        async with session.get(f"https://apiv2.nobitex.ir/v2/orderbook/{symbol}", headers=headers, proxy=proxy) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if not data.get("isClosed") and data.get("status") != "closed":
                                    p = data.get("lastTradePrice")
                                    if p:
                                        ton_prices["نوبیتکس"] = int(float(p) // 10)
                                        break
                    except Exception as exc:
                        logger.warning("Nobitex orderbook fetch failed for %s: %s", symbol, exc)

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
                                elif code in ("TRX_IRT", "TRX_TMN", "TRXIRT"):
                                    p = m.get("price") or (m.get("order_book_info") or {}).get("last_trade_price")
                                    if p:
                                        trx_prices["بیت‌پین"] = int(float(p))
                                elif code == "TRX_RLS":
                                    p = m.get("price") or (m.get("order_book_info") or {}).get("last_trade_price")
                                    if p:
                                        trx_prices["بیت‌پین"] = int(float(p) // 10)
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
                        for sym in ("TRXTMN", "TRXIRT"):
                            if sym in symbols:
                                lp = (symbols[sym].get("stats") or {}).get("lastPrice")
                                if lp and str(lp).strip() not in ("", "-"):
                                    trx_prices["والکس"] = int(float(lp))
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

        # 6. Binance (global) & TonAPI
        async def _fetch_binance():
            nonlocal binance_ton_usd, binance_eur_usd, global_ton_usd, global_ton_source
            # 1. Binance spot: Toncoin spot trades under active symbol GRAMUSDT
            try:
                async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=GRAMUSDT", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        p = float(data.get("price", "0"))
                        if p > 0:
                            binance_ton_usd = p
                            global_ton_usd = p
                            global_ton_source = "بایننس"
            except Exception as e:
                logger.debug("Binance GRAMUSDT failed: %s", e)

            # 2. TonAPI official fallback if Binance did not return a valid price
            if not global_ton_usd:
                try:
                    async with session.get("https://tonapi.io/v2/rates?tokens=ton&currencies=usd", headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            p = float((data.get("rates", {}).get("TON", {}).get("prices", {})).get("USD", 0))
                            if p > 0:
                                binance_ton_usd = round(p, 4)
                                global_ton_usd = round(p, 4)
                                global_ton_source = "TonAPI"
                except Exception as e:
                    logger.debug("TonAPI rates failed: %s", e)

            # 3. CoinGecko fallback
            if not global_ton_usd:
                try:
                    async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd", headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            p = float(data.get("the-open-network", {}).get("usd", 0))
                            if p > 0:
                                binance_ton_usd = round(p, 4)
                                global_ton_usd = round(p, 4)
                                global_ton_source = "CoinGecko"
                except Exception as e:
                    logger.debug("CoinGecko rates failed: %s", e)

            try:
                async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=EURUSDT", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        p = float(data.get("price", "0"))
                        if p > 0:
                            binance_eur_usd = p
            except Exception as e:
                logger.debug("Binance EUR failed: %s", e)

            try:
                nonlocal binance_trx_usd
                async with session.get("https://api.binance.com/api/v3/ticker/price?symbol=TRXUSDT", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        p = float(data.get("price", "0"))
                        if p > 0:
                            binance_trx_usd = p
            except Exception as e:
                logger.debug("Binance TRX failed: %s", e)

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
    )
    effective_usdt = int(effective_usdt or 0)

    if best_ton_price is None and global_ton_usd and effective_usdt > 0:
        best_ton_price = int(round(global_ton_usd * effective_usdt))
        src_label = global_ton_source or "جهانی"
        best_ton_source = f"{src_label} (${global_ton_usd:.2f})"

    # Priority for single best USDT: Nobitex > Tetherland > Ramzinex > Bitpin > Wallex
    best_usdt_price: int | None = None
    best_usdt_source = ""
    for src in ("نوبیتکس", "تترلند", "رمزینکس", "بیت‌پین", "والکس"):
        if src in usdt_prices:
            best_usdt_price = usdt_prices[src]
            best_usdt_source = src
            break

    # Calculate EUR in Toman for all domestic exchanges based on Binance EUR/USDT benchmark (no hardcoded fallback)
    eur_rate_mult = binance_eur_usd if (binance_eur_usd and binance_eur_usd > 0) else None
    if eur_rate_mult:
        for exch_name in ("نوبیتکس", "تترلند", "رمزینکس", "بیت‌پین", "والکس"):
            if exch_name not in eur_prices and exch_name in usdt_prices:
                u_price = usdt_prices[exch_name]
                if u_price > 0:
                    eur_prices[exch_name] = int(round(u_price * eur_rate_mult))

        if "بایننس" not in eur_prices and effective_usdt > 0:
            eur_prices["بایننس"] = int(round(eur_rate_mult * effective_usdt))

    best_eur_price: int | None = None
    best_eur_source = ""
    for src in ("نوبیتکس", "تترلند", "رمزینکس", "بیت‌پین", "والکس", "بایننس"):
        if src in eur_prices:
            best_eur_price = eur_prices[src]
            best_eur_source = src if src != "بایننس" else f"بایننس (${binance_eur_usd:.3f})"
            break

    best_trx_price: int | None = None
    best_trx_source = ""
    for src in ("نوبیتکس", "بیت‌پین", "والکس"):
        if src in trx_prices:
            best_trx_price = trx_prices[src]
            best_trx_source = src
            break

    if best_trx_price is None and binance_trx_usd and effective_usdt > 0:
        best_trx_price = int(round(binance_trx_usd * effective_usdt))
        best_trx_source = f"بایننس (${binance_trx_usd:.4f})"

    return {
        "ton": ton_prices,
        "usdt": usdt_prices,
        "eur": eur_prices,
        "trx": trx_prices,
        "closed_status": closed_status,
        "binance_usd": global_ton_usd,
        "global_ton_usd": global_ton_usd,
        "global_ton_source": global_ton_source,
        "binance_eur_usd": binance_eur_usd,
        "binance_trx_usd": binance_trx_usd,
        "best_ton": (best_ton_price, best_ton_source),
        "best_usdt": (best_usdt_price, best_usdt_source),
        "best_eur": (best_eur_price, best_eur_source),
        "best_trx": (best_trx_price, best_trx_source),
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
