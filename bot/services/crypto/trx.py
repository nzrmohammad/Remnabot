"""TRX (Tron) on-chain payment processor and verification service."""
import asyncio
import hashlib
import logging
from datetime import datetime, timezone
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

    # Fetch live TRX price from Nobitex
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
        logger.debug("Could not poll Nobitex TRX rate: %s", exc)

    return 90_000  # Fallback reasonable estimate


async def verify_tron_transaction(
    tx_hash: str, expected_address: str, min_sun: int
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
                            if c.get("type") in ("TransferContract", "TriggerSmartContract"):
                                val_dict = c.get("parameter", {}).get("value", {})
                                raw_amount = int(val_dict.get("amount") or 0)
                                raw_to = str(val_dict.get("to_address") or "")
                                to_b58 = hex_to_tron_address(raw_to)

                                if to_b58.lower() == expected_clean.lower() or raw_to.lower() == expected_clean.lower():
                                    if raw_amount >= (min_sun * 0.98):  # allow 2% tolerance for dust/fee differences
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
                        to_addr = scan_data.get("toAddress", "")
                        raw_amount = int(scan_data.get("amount") or 0)
                        if to_addr.lower() == expected_clean.lower():
                            if raw_amount >= (min_sun * 0.98):
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

    if invoice.status == "paid":
        w = await WalletRepository(session).get_wallet(invoice.telegram_id)
        return True, (w.balance if w else 0), "این فاکتور قبلاً پرداخت و تسویه شده است."

    crypto_repo = CryptoRepository(session)
    wallet_repo = WalletRepository(session)

    # Check anti-replay across system
    existing = await crypto_repo.get_by_tx_hash(clean_tx)
    if existing and existing.id != invoice.id:
        return False, 0, "این شناسه تراکنش (TxID) قبلاً برای فاکتور دیگری ثبت و استفاده شده است."

    # Minimum SUN needed (1 TRX = 1,000,000 SUN)
    min_sun = invoice.nanotons  # We store SUN amount in nanotons field for TRX invoices

    ok, reason, _ = await verify_tron_transaction(clean_tx, invoice.pay_address, min_sun)
    if not ok:
        return False, 0, reason

    # Mark paid and credit atomically
    paid_inv = await crypto_repo.mark_paid(invoice.id, clean_tx, allow_expired=True)
    if not paid_inv:
        return False, 0, "امکان تغییر وضعیت فاکتور به پرداخت‌شده وجود ندارد."

    new_bal = await wallet_repo.add_balance_atomic(invoice.telegram_id, invoice.amount_toman)
    return True, new_bal, "پرداخت ترون (TRX) با موفقیت تأیید شد و کیف پول شارژ گردید!"
