"""POL (Polygon Ecosystem Token) on-chain payment processor and verification service."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from bot.db.repositories.crypto_repo import CryptoRepository
from bot.db.repositories.wallet_repo import WalletRepository

logger = logging.getLogger(__name__)

POLYGON_RPCS = [
    "https://polygon-rpc.com",
    "https://rpc.ankr.com/polygon",
    "https://polygon-bor-rpc.publicnode.com",
    "https://1rpc.io/matic",
]


async def fetch_pol_rate(store_rate: int = 0) -> int:
    """Resolve POL/Toman rate. Uses store setting if configured, else polls Nobitex live."""
    if store_rate > 0:
        return store_rate

    # 1. Fetch live POL price from Nobitex directly
    try:
        timeout = aiohttp.ClientTimeout(total=4)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://apiv2.nobitex.ir/market/stats", headers={"User-Agent": "Remnabot/1.0"}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    stats = data.get("stats", {})
                    # Nobitex supports pol-rls (or fallback matic-rls)
                    pol_stat = stats.get("pol-rls") or stats.get("matic-rls")
                    if pol_stat and pol_stat.get("latest"):
                        toman_price = int(float(pol_stat["latest"]) // 10)
                        if toman_price > 100:
                            return toman_price
    except Exception as exc:
        logger.warning("Could not poll Nobitex POL rate directly: %s", exc)

    # 2. Secondary: Calculate from Binance POL/USDT * live domestic USDT
    try:
        from bot.services.crypto.nobitex import get_crypto_rates_summary
        summary = await get_crypto_rates_summary()
        usdt_prices = summary.get("usdt_prices") or {}
        best_usdt = next((v for v in usdt_prices.values() if v > 0), 0)

        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for symbol in ("POLUSDT", "MATICUSDT"):
                try:
                    async with session.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}") as b_resp:
                        if b_resp.status == 200:
                            b_data = await b_resp.json()
                            pol_usd = float(b_data.get("price") or 0)
                            if pol_usd > 0 and best_usdt > 0:
                                return int(round(pol_usd * best_usdt))
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("Could not resolve live POL rate via secondary sources: %s", exc)

    logger.warning("Live POL rate unavailable; returning 0")
    return 0


async def verify_polygon_transaction(
    tx_hash: str,
    expected_address: str,
    min_wei: int,
    min_timestamp_ms: int = 0,
    max_wei: int | None = None,
    max_timestamp_ms: int = 0,
) -> tuple[bool, str, int]:
    """Verify on-chain Polygon transaction via EVM JSON-RPC.

    Returns:
        (is_valid, error_reason_or_ok, confirmed_wei_amount)
    """
    clean_tx = tx_hash.strip().lower()
    if not clean_tx.startswith("0x"):
        clean_tx = "0x" + clean_tx
    if len(clean_tx) != 66:
        return False, "شناسه تراکنش نامعتبر است (باید 66 کاراکتر هگزادسیمال با پیشوند 0x باشد).", 0

    expected_clean = expected_address.strip().lower()
    timeout = aiohttp.ClientTimeout(total=6)

    payload_tx = {
        "jsonrpc": "2.0",
        "method": "eth_getTransactionByHash",
        "params": [clean_tx],
        "id": 1,
    }
    payload_receipt = {
        "jsonrpc": "2.0",
        "method": "eth_getTransactionReceipt",
        "params": [clean_tx],
        "id": 2,
    }

    headers = {"Content-Type": "application/json", "User-Agent": "Remnabot/1.0"}

    for rpc_url in POLYGON_RPCS:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(rpc_url, json=payload_tx, headers=headers) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    tx_info = data.get("result")
                    if not tx_info:
                        continue

                # Query Receipt to confirm execution status
                async with session.post(rpc_url, json=payload_receipt, headers=headers) as r_resp:
                    if r_resp.status != 200:
                        continue
                    r_data = await r_resp.json()
                    receipt = r_data.get("result")
                    if not receipt:
                        return False, "تراکنش هنوز در بلاک‌های شبکه پالیگان تأیید (Mined) نشده است. لطفاً چند لحظه بعد تلاش کنید.", 0

                    status = str(receipt.get("status") or "")
                    if status != "0x1" and status != "1":
                        return False, "تراکنش روی شبکه پالیگان ناموفق یا برگشت‌خورده (Reverted) است.", 0

                # Validate destination address
                to_addr = str(tx_info.get("to") or "").lower()
                if to_addr != expected_clean:
                    return False, f"مقصد واریزی ({to_addr}) با آدرس ولت تعیین‌شده سامانه مطابقت ندارد.", 0

                # Validate value in Wei: never allow 0 POL or dust >= 0.1% / >= half of 0.0001 suffix step
                val_hex = tx_info.get("value") or "0x0"
                raw_wei = int(val_hex, 16) if isinstance(val_hex, str) else int(val_hex)

                dust_tolerance_wei = min(40_000_000_000_000, max(0, min_wei // 1000))
                if raw_wei <= 0 or raw_wei < (min_wei - dust_tolerance_wei):
                    paid_pol = raw_wei / 1e18
                    expected_pol = min_wei / 1e18
                    return False, f"مبلغ واریزی ({paid_pol:.4f} POL) کمتر از فاکتور ({expected_pol:.4f} POL) است.", 0
                if max_wei is not None and raw_wei > max_wei:
                    paid_pol = raw_wei / 1e18
                    expected_pol = min_wei / 1e18
                    return False, f"مبلغ تراکنش ({paid_pol:.4f} POL) با مبلغ دقیق این فاکتور ({expected_pol:.4f} POL) مطابقت ندارد.", 0

                # Prevent reusing old pre-invoice or post-expiry transactions by checking mined block timestamp
                if min_timestamp_ms > 0 or max_timestamp_ms > 0:
                    block_num = receipt.get("blockNumber")
                    if not block_num:
                        continue
                    payload_block = {
                        "jsonrpc": "2.0",
                        "method": "eth_getBlockByNumber",
                        "params": [block_num, False],
                        "id": 3,
                    }
                    async with session.post(rpc_url, json=payload_block, headers=headers) as b_resp:
                        if b_resp.status != 200:
                            continue
                        b_data = await b_resp.json()
                        block_info = b_data.get("result")
                        if not block_info or block_info.get("timestamp") is None:
                            continue
                        ts_raw = block_info["timestamp"]
                        block_ts_sec = (
                            int(ts_raw, 16)
                            if isinstance(ts_raw, str) and ts_raw.startswith("0x")
                            else int(ts_raw)
                        )
                        if min_timestamp_ms > 0 and block_ts_sec * 1000 < min_timestamp_ms:
                            return False, "این تراکنش قبل از زمان ایجاد فاکتور ثبت شده و نامعتبر است.", 0
                        if max_timestamp_ms > 0 and block_ts_sec * 1000 > max_timestamp_ms:
                            return False, "این تراکنش پس از پایان مهلت فاکتور ثبت شده و نامعتبر است.", 0

                return True, "SUCCESS", raw_wei

        except Exception as exc:
            logger.debug("Polygon RPC error on %s for tx %s: %s", rpc_url, clean_tx, exc)
            continue

    return False, "تراکنش هنوز در شبکه پالیگان یافت یا تأیید نشده است. لطفاً 1 دقیقه صبر کرده و مجدداً امتحان نمایید.", 0


async def verify_and_credit_pol_invoice(
    session: Any,
    invoice: Any,
    tx_hash: str,
    bot: Any = None,
) -> tuple[bool, int, str]:
    """Atomically verify and credit a POL invoice."""
    clean_tx = tx_hash.strip().lower()
    if not clean_tx.startswith("0x"):
        clean_tx = "0x" + clean_tx

    if getattr(invoice, "currency", "POL") != "POL":
        logger.warning(
            "verify_and_credit_pol_invoice called with non-POL invoice #%s (currency=%s)",
            invoice.id,
            getattr(invoice, "currency", None),
        )
        return False, 0, "این فاکتور مربوط به ارز پالیگان (POL) نمی‌باشد."

    if invoice.status == "paid":
        w = await WalletRepository(session).get_wallet(invoice.telegram_id)
        return True, (w.balance if w else 0), "این فاکتور قبلاً پرداخت و تسویه شده است."

    if invoice.status == "cancelled":
        return False, 0, "این فاکتور لغو شده و دیگر قابل پرداخت نیست."

    crypto_repo = CryptoRepository(session)
    wallet_repo = WalletRepository(session)

    # Check anti-replay across system
    existing = await crypto_repo.get_by_tx_hash(clean_tx)
    if existing and existing.id != invoice.id:
        logger.warning(
            "POL verify replay attempted: tx_hash=%s invoice_id=%s existing_invoice_id=%s tg_id=%s",
            clean_tx, invoice.id, existing.id, invoice.telegram_id,
        )
        return False, 0, "این شناسه تراکنش (TxHash) قبلاً برای فاکتور دیگری ثبت و استفاده شده است."

    min_wei = invoice.nanotons

    now = datetime.now(timezone.utc)
    inv_created = invoice.created_at if (invoice.created_at and invoice.created_at.tzinfo) else (invoice.created_at.replace(tzinfo=timezone.utc) if invoice.created_at else now)
    min_timestamp_ms = int(inv_created.timestamp() * 1000) - 60_000

    inv_exp = getattr(invoice, "expires_at", None)
    max_timestamp_ms = 0
    if inv_exp is not None:
        exp_utc = inv_exp if inv_exp.tzinfo else inv_exp.replace(tzinfo=timezone.utc)
        if invoice.status == "expired" or exp_utc < now:
            if (now - exp_utc) > timedelta(hours=2):
                return False, 0, "مهلت این فاکتور به پایان رسیده است. لطفاً فاکتور جدید ایجاد نمایید."
        max_timestamp_ms = int(exp_utc.timestamp() * 1000) + 60_000

    max_wei = min_wei + 40_000_000_000_000
    ok, reason, confirmed_wei = await verify_polygon_transaction(
        clean_tx,
        invoice.pay_address,
        min_wei,
        min_timestamp_ms=min_timestamp_ms,
        max_wei=max_wei,
        max_timestamp_ms=max_timestamp_ms,
    )
    if not ok:
        logger.warning(
            "POL verification failed: invoice_id=%s tg_id=%s tx_hash=%s reason=%s expected_wei=%s confirmed_wei=%s",
            invoice.id, invoice.telegram_id, clean_tx, reason, min_wei, confirmed_wei,
        )
        return False, 0, reason

    # Mark paid and credit atomically (expired invoices allowed only within 2h confirmation grace when tx was pre-expiry)
    paid_inv = await crypto_repo.mark_paid(invoice.id, clean_tx, allow_expired=True, max_expired_grace_minutes=120)
    if not paid_inv:
        logger.warning("POL mark_paid failed: invoice_id=%s tg_id=%s tx_hash=%s", invoice.id, invoice.telegram_id, clean_tx)
        return False, 0, "امکان تغییر وضعیت فاکتور به پرداخت‌شده وجود ندارد."

    new_bal = await wallet_repo.add_balance_atomic(invoice.telegram_id, invoice.amount_toman)
    logger.info(
        "POL invoice paid and credited: invoice_id=%s tg_id=%s tx_hash=%s amount_toman=%s new_balance=%s confirmed_wei=%s",
        invoice.id, invoice.telegram_id, clean_tx, invoice.amount_toman, new_bal, confirmed_wei,
    )

    if bot:
        try:
            from bot.common import admin_thread_kwargs
            from bot.config import get_settings
            from bot.services.app_settings import get_store_settings
            settings = get_settings()
            store = await get_store_settings(session)

            # User confirmation message
            user_msg = (
                f"✅ <b>شارژ موفق حساب با پالیگان (POL)</b>\n\n"
                f"🟣 مقدار واریزی: <code>{invoice.amount_ton} POL</code>\n"
                f"💰 مبلغ شارژ: <b>{invoice.amount_toman:,} تومان</b>\n"
                f"👛 موجودی جدید: <b>{new_bal:,} تومان</b>"
            )
            await bot.send_message(invoice.telegram_id, user_msg)

            # Admin notification
            if settings.ADMIN_CHAT_ID:
                topic_id = store.topic_crypto or settings.ADMIN_TOPIC_CRYPTO or store.topic_topups or settings.ADMIN_TOPIC_TOPUPS
                thread_kwargs = admin_thread_kwargs(topic_id=topic_id)
                admin_msg = (
                    f"🟣 <b>واریز جدید با ارز پالیگان (POL)</b>\n"
                    f"──────────────────\n"
                    f"👤 کاربر: <code>{invoice.telegram_id}</code>\n"
                    f"💰 مبلغ تومانی: <b>{invoice.amount_toman:,} تومان</b>\n"
                    f"🟣 مقدار دریافتی: <code>{invoice.amount_ton} POL</code>\n"
                    f"🔗 <a href=\"https://polygonscan.com/tx/{clean_tx}\">مشاهده در PolygonScan</a>\n\n"
                    f"👛 موجودی جدید: <b>{new_bal:,} تومان</b>"
                )
                await bot.send_message(settings.ADMIN_CHAT_ID, admin_msg, **thread_kwargs)
        except Exception as n_err:
            logger.warning("Failed notifying user/admin of POL topup: %s", n_err)

    return True, new_bal, "پرداخت پالیگان (POL) با موفقیت تأیید شد و کیف پول شارژ گردید!"
