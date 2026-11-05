"""TRX (Tron) on-chain payment processor and verification service."""
from datetime import datetime, timezone
import hashlib
import logging
from typing import Any

import aiohttp

from bot.db.repositories.crypto_repo import CryptoRepository
from bot.db.repositories.wallet_repo import WalletRepository

logger = logging.getLogger(__name__)

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def hex_to_tron_address(hex_addr: str) -> str:
    """Convert 41-prefixed Tron hex address to base58check T-address."""
    clean = hex_addr.strip().lower()
    if clean.startswith("0x"):
        clean = "41" + clean[2:]
    if clean.startswith("41") and len(clean) == 42:
        try:
            raw_bytes = bytes.fromhex(clean)
            h1 = hashlib.sha256(raw_bytes).digest()
            h2 = hashlib.sha256(h1).digest()
            full_bytes = raw_bytes + h2[:4]
            num = int.from_bytes(full_bytes, "big")
            encoded = []
            while num > 0:
                num, rem = divmod(num, 58)
                encoded.append(ALPHABET[rem])
            pad = len(full_bytes) - len(full_bytes.lstrip(b"\x00"))
            return "1" * pad + "".join(reversed(encoded))
        except Exception as e:
            logger.debug("Failed converting hex to tron address %s: %s", hex_addr, e)
    return hex_addr


async def fetch_trx_rate(store_rate: int = 0) -> int:
    """Resolve TRX/Toman rate. Uses store setting if configured, else polls Nobitex live."""
    if store_rate > 0:
        return store_rate

    # Fetch live TRX price from Nobitex directly
    try:
        timeout = aiohttp.ClientTimeout(total=4)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://apiv2.nobitex.ir/market/stats", headers={"User-Agent": "Remnabot/1.0"}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    trx_stat = data.get("stats", {}).get("trx-rls")
                    if trx_stat and trx_stat.get("latest"):
                        toman_price = int(float(trx_stat["latest"]) // 10)
                        if toman_price > 100:
                            return toman_price
    except Exception as exc:
        logger.warning("Could not poll Nobitex TRX rate directly: %s", exc)

    # Secondary: query live multi-exchange fetcher (Bitpin, Wallex, Binance benchmark)
    try:
        from bot.services.crypto.nobitex import get_crypto_rates_summary
        summary = await get_crypto_rates_summary()
        trx_prices = summary.get("trx_prices") or {}
        for exch in ("نوبیتکس", "بیت‌پین", "والکس"):
            if exch in trx_prices and trx_prices[exch] > 0:
                return trx_prices[exch]

        # Calculate from Binance TRX/USD * live domestic USDT
        bin_trx = summary.get("binance_trx_usd")
        usdt_prices = summary.get("usdt_prices") or {}
        best_usdt = next((v for v in usdt_prices.values() if v > 0), 0)
        if bin_trx and best_usdt > 0:
            return int(round(bin_trx * best_usdt))
    except Exception as exc:
        logger.warning("Could not resolve live TRX rate via secondary sources: %s", exc)

    logger.warning("Live TRX rate unavailable from all domestic and global exchanges; returning 0")
    return 0


async def verify_tron_transaction(
    tx_hash: str, expected_address: str, min_sun: int, min_timestamp_ms: int = 0
) -> tuple[bool, str, int]:
    """Verify on-chain Tron transaction via TronGrid RPC.

    Returns:
        (is_valid, error_reason_or_ok, confirmed_sun_amount)
    """
    clean_tx = tx_hash.strip().lower()
    if clean_tx.startswith("0x"):
        clean_tx = clean_tx[2:]
    if len(clean_tx) != 64:
        return False, "شناسه تراکنش نامعتبر است (باید ۶۴ کاراکتر هگزادسیمال باشد).", 0

    expected_clean = expected_address.strip()
    timeout = aiohttp.ClientTimeout(total=8)

    # 1. Query TronGrid JSON-RPC
    try:
        url = "https://api.trongrid.io/wallet/gettransactionbyid"
        headers = {"Content-Type": "application/json", "User-Agent": "Remnabot/1.0"}
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json={"value": clean_tx}, headers=headers) as resp:
                if resp.status == 200:
                    tx_data = await resp.json()
                    if tx_data and "ret" in tx_data:
                        # Verify execution result
                        ret_list = tx_data.get("ret") or []
                        if not ret_list or ret_list[0].get("contractRet") != "SUCCESS":
                            return False, "تراکنش روی شبکه ناموفق یا برگشت‌خورده است.", 0

                        # Verify contract parameter
                        contracts = tx_data.get("raw_data", {}).get("contract", [])
                        for c in contracts:
                            if c.get("type") == "TransferContract":
                                val_dict = c.get("parameter", {}).get("value", {})
                                raw_amount = int(val_dict.get("amount") or 0)
                                raw_to = str(val_dict.get("to_address") or "")
                                to_b58 = hex_to_tron_address(raw_to)

                                if to_b58.lower() == expected_clean.lower() or raw_to.lower() == expected_clean.lower():
                                    tx_ts = int(tx_data.get("raw_data", {}).get("timestamp") or 0)
                                    if min_timestamp_ms and tx_ts and tx_ts < min_timestamp_ms:
                                        return False, "این تراکنش قبل از زمان ایجاد فاکتور ثبت شده و نامعتبر است.", 0
                                    if raw_amount >= (min_sun - 100_000):  # strict amount check with minimal 0.1 TRX dust tolerance
                                        return True, "SUCCESS", raw_amount
                                    else:
                                        trx_paid = raw_amount / 1_000_000
                                        trx_expected = min_sun / 1_000_000
                                        return False, f"مبلغ واریزی ({trx_paid:.2f} TRX) کمتر از مقدار فاکتور ({trx_expected:.2f} TRX) است.", 0
    except Exception as exc:
        logger.warning("TronGrid verification failed for tx %s: %s", clean_tx, exc)

    # 2. Fallback to TronScan API
    try:
        scan_url = f"https://apilist.tronscanapi.com/api/transaction-info?hash={clean_tx}"
        headers = {"User-Agent": "Remnabot/1.0"}
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(scan_url, headers=headers) as resp:
                if resp.status == 200:
                    scan_data = await resp.json()
                    if scan_data and scan_data.get("contractRet") == "SUCCESS":
                        contract_type = scan_data.get("contractType")
                        if contract_type is not None and contract_type != 1:
                            return False, "نوع تراکنش نامعتبر است (فقط انتقال مستقیم TRX پذیرفته می‌شود).", 0
                        tx_ts = int(scan_data.get("timestamp") or 0)
                        if min_timestamp_ms and tx_ts and tx_ts < min_timestamp_ms:
                            return False, "این تراکنش قبل از زمان ایجاد فاکتور ثبت شده و نامعتبر است.", 0
                        to_addr = scan_data.get("toAddress", "")
                        raw_amount = int(scan_data.get("amount") or 0)
                        if to_addr.lower() == expected_clean.lower():
                            if raw_amount >= (min_sun - 100_000):
                                return True, "SUCCESS", raw_amount
                            else:
                                return False, "مبلغ واریز شده کمتر از فاکتور است.", 0
    except Exception as exc:
        logger.warning("TronScan verification fallback failed for tx %s: %s", clean_tx, exc)

    return False, "تراکنش هنوز در شبکه ترون تأیید نشده است یا یافت نشد. لطفاً چند لحظه بعد مجدداً امتحان کنید.", 0


async def verify_and_credit_trx_invoice(
    session: Any,
    invoice: Any,
    tx_hash: str,
    bot: Any = None,
) -> tuple[bool, int, str]:
    """Atomically verify and credit a TRX invoice."""
    clean_tx = tx_hash.strip().lower()
    if clean_tx.startswith("0x"):
        clean_tx = clean_tx[2:]

    if getattr(invoice, "currency", "TRX") != "TRX":
        logger.warning(
            "verify_and_credit_trx_invoice called with non-TRX invoice #%s (currency=%s)",
            invoice.id,
            getattr(invoice, "currency", None),
        )
        return False, 0, "این فاکتور مربوط به ارز ترون (TRX) نمی‌باشد."

    if invoice.status == "paid":
        w = await WalletRepository(session).get_wallet(invoice.telegram_id)
        return True, (w.balance if w else 0), "این فاکتور قبلاً پرداخت و تسویه شده است."

    crypto_repo = CryptoRepository(session)
    wallet_repo = WalletRepository(session)

    # Check anti-replay across system
    existing = await crypto_repo.get_by_tx_hash(clean_tx)
    if existing and existing.id != invoice.id:
        logger.warning(
            "TRX verify replay attempted: tx_hash=%s invoice_id=%s existing_invoice_id=%s tg_id=%s",
            clean_tx, invoice.id, existing.id, invoice.telegram_id,
        )
        return False, 0, "این شناسه تراکنش (TxID) قبلاً برای فاکتور دیگری ثبت و استفاده شده است."

    # Minimum SUN needed (1 TRX = 1,000,000 SUN)
    min_sun = invoice.nanotons  # We store SUN amount in nanotons field for TRX invoices

    now = datetime.now(timezone.utc)
    inv_created = invoice.created_at if (invoice.created_at and invoice.created_at.tzinfo) else (invoice.created_at.replace(tzinfo=timezone.utc) if invoice.created_at else now)
    min_timestamp_ms = int(inv_created.timestamp() * 1000) - 60_000

    ok, reason, confirmed_sun = await verify_tron_transaction(clean_tx, invoice.pay_address, min_sun, min_timestamp_ms=min_timestamp_ms)
    if not ok:
        logger.warning(
            "TRX verification failed: invoice_id=%s tg_id=%s tx_hash=%s reason=%s expected_sun=%s confirmed_sun=%s",
            invoice.id, invoice.telegram_id, clean_tx, reason, min_sun, confirmed_sun,
        )
        return False, 0, reason

    # Mark paid and credit atomically
    paid_inv = await crypto_repo.mark_paid(invoice.id, clean_tx, allow_expired=True)
    if not paid_inv:
        logger.warning("TRX mark_paid failed: invoice_id=%s tg_id=%s tx_hash=%s", invoice.id, invoice.telegram_id, clean_tx)
        return False, 0, "امکان تغییر وضعیت فاکتور به پرداخت‌شده وجود ندارد."

    new_bal = await wallet_repo.add_balance_atomic(invoice.telegram_id, invoice.amount_toman)
    logger.info(
        "TRX invoice paid and credited: invoice_id=%s tg_id=%s tx_hash=%s amount_toman=%s new_balance=%s confirmed_sun=%s",
        invoice.id, invoice.telegram_id, clean_tx, invoice.amount_toman, new_bal, confirmed_sun,
    )
    return True, new_bal, "پرداخت ترون (TRX) با موفقیت تأیید شد و کیف پول شارژ گردید!"
