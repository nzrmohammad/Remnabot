"""Nobitex rate checker and daily scheduled notifier for TON & USDT prices.

Decomposed into submodules:
- crypto_fetcher.py: multi-exchange API price polling (Nobitex, Bitpin, Wallex, Tetherland, Ramzinex, Binance).
- crypto_rates.py: admin message and inline keyboard formatting.
- crypto_notifier.py: cron-like scheduled notifications in Tehran timezone.
"""
from bot.services.crypto.crypto_fetcher import (
    fetch_all_exchange_prices,
    fetch_nobitex_ton_price,
    fetch_ton_market_price,
)
from bot.services.crypto.crypto_notifier import (
    RATE_CHECK_HOURS,
    _seconds_until_next_target,
    nobitex_rate_loop,
    send_rate_notification,
)
from bot.services.crypto.crypto_rates import (
    format_full_crypto_market_alert,
    format_multi_rate_alert,
    format_rate_alert,
    format_ton_rate_alert,
    format_usdt_rate_alert,
)


async def get_crypto_rates_summary() -> dict:
    """Fetch live crypto rates summary formatted for web & admin dashboards."""
    data = await fetch_all_exchange_prices()
    best_ton_price, best_ton_source = data.get("best_ton", (None, ""))
    best_usdt_price, best_usdt_source = data.get("best_usdt", (None, ""))
    best_eur_price, best_eur_source = data.get("best_eur", (None, ""))
    return {
        "ok": True,
        "ton_prices": data.get("ton", {}),
        "usdt_prices": data.get("usdt", {}),
        "eur_prices": data.get("eur", {}),
        "closed_status": data.get("closed_status", {}),
        "binance_usd": data.get("binance_usd"),
        "binance_eur_usd": data.get("binance_eur_usd"),
        "best_ton": {"price": best_ton_price, "source": best_ton_source},
        "best_usdt": {"price": best_usdt_price, "source": best_usdt_source},
        "best_eur": {"price": best_eur_price, "source": best_eur_source},
    }


__all__ = [
    "RATE_CHECK_HOURS",
    "fetch_all_exchange_prices",
    "fetch_ton_market_price",
    "fetch_nobitex_ton_price",
    "format_rate_alert",
    "format_multi_rate_alert",
    "format_ton_rate_alert",
    "format_usdt_rate_alert",
    "format_full_crypto_market_alert",
    "_seconds_until_next_target",
    "send_rate_notification",
    "nobitex_rate_loop",
    "get_crypto_rates_summary",
]
