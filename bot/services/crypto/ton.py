"""TON blockchain watcher and automated payment processor."""
import asyncio
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from bot.common import admin_thread_kwargs
from bot.config import get_settings
from bot.db.repositories.crypto_repo import CryptoRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings

logger = logging.getLogger(__name__)


def _extract_comment(in_msg: dict) -> str:
    """Extract memo/comment from a TON transaction in_msg."""
    # 1. Direct message field
    msg = in_msg.get("message")
    if msg and isinstance(msg, str) and msg.strip():
        return msg.strip()

    # 2. Check msg_data
    msg_data = in_msg.get("msg_data") or {}
    if isinstance(msg_data, dict):
        text = msg_data.get("text")
        if text and isinstance(text, str):
            try:
                decoded = base64.b64decode(text).decode("utf-8", errors="ignore").strip()
                if decoded:
                    return decoded
            except Exception as exc:
                logger.warning("Failed to decode base64 ton comment text: %s", exc)

    return ""


async def fetch_ton_transactions(address: str, limit: int = 100) -> list[dict]:
    """Fetch recent incoming transactions for a TON address from TonCenter public API."""
    if not address or not address.strip():
        return []

    url = f"https://toncenter.com/api/v2/getTransactions?address={address.strip()}&limit={limit}"
    headers = {"User-Agent": "Remnabot/1.0"}
    timeout = aiohttp.ClientTimeout(total=10)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        raw_txs = data.get("result", [])
                        parsed = []
                        for tx in raw_txs:
                            in_msg = tx.get("in_msg") or {}
                            val_str = in_msg.get("value", "0")
                            try:
                                nanotons = int(val_str)
                            except (ValueError, TypeError):
                                nanotons = 0

                            comment = _extract_comment(in_msg)
                            tx_id = tx.get("transaction_id") or {}
                            tx_hash = tx_id.get("hash", "")
                            utime = tx.get("utime", 0)

                            if nanotons > 0 and comment:
                                parsed.append({
                                    "nanotons": nanotons,
                                    "comment": comment,
                                    "tx_hash": tx_hash,
                                    "utime": utime,
                                })
                        return parsed
    except Exception as e:
        logger.warning("Failed to query TonCenter API: %s", e)

    return []


async def verify_and_credit_ton_invoice(
    session: Any,
    inv: Any,
    txs: list[dict],
    allow_expired: bool = True,
    bot: Any = None,
) -> tuple[bool, int, str]:
    """Verify on-chain transactions for an invoice, check timing & prevent replay (SSOT).

    Returns:
        (is_paid, new_balance, tx_hash)
    """
    if getattr(inv, "currency", "TON") != "TON":
        logger.warning(
            "verify_and_credit_ton_invoice called with non-TON invoice #%s (currency=%s)",
            inv.id,
            getattr(inv, "currency", None),
        )
        return False, 0, ""

    if inv.status == "paid":
        w = await WalletRepository(session).get_wallet(inv.telegram_id)
        return True, (w.balance if w else 0), getattr(inv, "tx_hash", "") or ""

    if inv.status == "cancelled":
        return False, 0, ""

    now = datetime.now(timezone.utc)
    inv_created = inv.created_at if (inv.created_at and inv.created_at.tzinfo) else (inv.created_at.replace(tzinfo=timezone.utc) if inv.created_at else now)
    inv_created_ts = int(inv_created.timestamp()) if inv_created else 0

    inv_exp = getattr(inv, "expires_at", None)
    inv_exp_ts = 0
    if inv_exp is not None:
        exp_utc = inv_exp if inv_exp.tzinfo else inv_exp.replace(tzinfo=timezone.utc)
        inv_exp_ts = int(exp_utc.timestamp())
        if (inv.status == "expired" or exp_utc < now) and (now - exp_utc) > timedelta(hours=2):
            return False, 0, ""

    crypto_repo = CryptoRepository(session)
    wallet_repo = WalletRepository(session)

    for tx in txs:
        if tx.get("comment") == inv.comment and tx.get("nanotons", 0) < inv.nanotons:
            logger.warning(
                "TON deposit underpaid for invoice #%s (tg_id=%s): expected_nano=%s, received_nano=%s, tx=%s",
                inv.id, inv.telegram_id, inv.nanotons, tx.get("nanotons", 0), tx.get("tx_hash"),
            )
        if tx.get("comment") != inv.comment or tx.get("nanotons", 0) < inv.nanotons:
            continue
        # Timing checks: tx must be after invoice creation AND before invoice expiry (+60s clock skew)
        tx_utime = tx.get("utime", 0)
        if inv_created_ts and tx_utime and tx_utime < (inv_created_ts - 60):
            continue
        if inv_exp_ts and tx_utime and tx_utime > (inv_exp_ts + 60):
            continue
        tx_hash = tx.get("tx_hash", "")
        # Prevent replay: verify tx_hash not claimed by another invoice
        if tx_hash:
            existing = await crypto_repo.get_by_tx_hash(tx_hash)
            if existing and existing.id != inv.id:
                logger.warning(
                    "TON tx_hash %s already claimed by invoice %s, rejecting replay for invoice %s",
                    tx_hash, existing.id, inv.id,
                )
                continue

        paid_inv = await crypto_repo.mark_paid(inv.id, tx_hash, allow_expired=allow_expired, max_expired_grace_minutes=120)
        if not paid_inv:
            continue

        try:
            new_bal = await wallet_repo.add_balance_atomic(inv.telegram_id, inv.amount_toman)
            logger.info(
                "TON invoice paid and credited: invoice_id=%s tg_id=%s tx_hash=%s amount_toman=%s new_balance=%s",
                inv.id, inv.telegram_id, tx_hash, inv.amount_toman, new_bal,
            )
        except Exception as exc:
            logger.error("Failed to credit wallet for TON invoice %s: %s", inv.id, exc, exc_info=True)
            if bot:
                try:
                    from bot.services.error_reporter import report_error
                    await report_error(
                        bot,
                        session=session,
                        exc=exc,
                        context=f"Failed to credit wallet for TON invoice #{inv.id} amount={inv.amount_toman}",
                        user_id=inv.telegram_id,
                    )
                except Exception as rep_err:
                    logger.warning("Failed reporting TON credit error to admin topic: %s", rep_err)
            raise
        return True, new_bal, tx_hash

    return False, 0, ""


async def verify_and_process_payments(bot: Any, session_factory: Any) -> int:
    """Check pending invoices against TON blockchain and process payments."""
    async with session_factory() as session:
        crypto_repo = CryptoRepository(session)
        pending_invoices = await crypto_repo.get_all_pending(currency="TON")
        if not pending_invoices:
            return 0

        now = datetime.now(timezone.utc)
        # Check and expire overdue invoices
        active_invoices = []
        for inv in pending_invoices:
            if getattr(inv, "currency", "TON") != "TON":
                continue
            exp = inv.expires_at
            if exp and exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp and exp < now:
                await crypto_repo.mark_expired(inv.id)
                if (now - exp) <= timedelta(hours=2):
                    active_invoices.append(inv)
            else:
                active_invoices.append(inv)

        if not active_invoices:
            await session.commit()
            return 0

        store = await get_store_settings(session)
        wallet_address = store.ton_wallet_address
        if not wallet_address:
            await session.commit()
            return 0
        await session.commit()

    # Fetch on-chain incoming transactions
    transactions = await fetch_ton_transactions(wallet_address)
    if not transactions:
        return 0

    processed_count = 0
    settings = get_settings()

    async with session_factory() as session:
        crypto_repo = CryptoRepository(session)
        user_repo = UserRepository(session)
        store = await get_store_settings(session)

        for inv in active_invoices:
            live_inv = await crypto_repo.get_by_id(inv.id)
            inv_to_process = live_inv or inv
            matched, new_balance, tx_hash = await verify_and_credit_ton_invoice(
                session=session,
                inv=inv_to_process,
                txs=transactions,
                allow_expired=True,
                bot=bot,
            )
            if matched:
                # Commit DB state BEFORE dispatching Telegram notifications so notifications never outrun persistence
                await session.commit()
                processed_count += 1

                if hasattr(bot, "cache") and bot.cache:
                    try:
                        if hasattr(bot.cache, "invalidate_user"):
                            await bot.cache.invalidate_user(inv.telegram_id)
                        else:
                            await bot.cache.delete(f"tma:user:{inv.telegram_id}")
                        await bot.cache.delete("tma:admin:overview")
                    except Exception as exc:
                        logger.debug("Failed invalidating cache after TON payment: %s", exc)

                # Send user notification
                try:
                    user = await user_repo.get_by_telegram_id(inv.telegram_id)
                    lang = user.language if user else "fa"
                    from aiogram.utils.keyboard import InlineKeyboardBuilder
                    kb = InlineKeyboardBuilder()
                    buy_text = "🛍 خرید سرویس" if lang == "fa" else "🛍 Buy Service"
                    kb.button(text=buy_text, callback_data="menu:services")
                    kb.button(
                        text=t(lang, "btn_back_to_menu") if lang == "fa" else "🏠 Main Menu",
                        callback_data="nav:main_menu",
                    )
                    kb.adjust(1)

                    if lang == "fa":
                        user_msg = (
                            f"🎉 <b>کیف پول شما با موفقیت شارژ شد!</b>\n"
                            f"──────────────────\n"
                            f"💎 مقدار دریافتی : <code>{inv.amount_ton} TON</code>\n"
                            f"💰 مبلغ شارژ : <b>{inv.amount_toman:,}</b> تومان\n"
                            f"👛 موجودی جدید کیف پول : <b>{new_balance:,}</b> تومان\n\n"
                            f"💡 اکنون می‌توانید با انتخاب دکمه زیر، پلن مورد نظر خود را خریداری کنید."
                        )
                    else:
                        user_msg = (
                            f"🎉 <b>Wallet Top-up Successful!</b>\n"
                            f"──────────────────\n"
                            f"💎 Received : <code>{inv.amount_ton} TON</code>\n"
                            f"💰 Credited : <b>{inv.amount_toman:,}</b> Toman\n"
                            f"👛 New Balance : <b>{new_balance:,}</b> Toman"
                        )
                    await bot.send_message(inv.telegram_id, user_msg, reply_markup=kb.as_markup())
                except Exception as exc:
                    logger.warning("Failed to notify user %d of TON topup: %s", inv.telegram_id, exc)

                # Send admin notification
                try:
                    topic_id = (
                        store.topic_crypto
                        or settings.ADMIN_TOPIC_CRYPTO
                        or store.topic_topups
                    )
                    thread_kwargs = admin_thread_kwargs(topic_id=topic_id)

                    tx_url = f"https://tonviewer.com/transaction/{tx_hash}"
                    admin_msg = (
                        f"💎 <b>شارژ خودکار کیف پول با تون (TON)</b>\n"
                        f"──────────────────\n"
                        f"👤 کاربر : <code>{inv.telegram_id}</code>\n"
                        f"💰 مبلغ شارژ : <b>{inv.amount_toman:,}</b> تومان\n"
                        f"💎 مقدار دریافتی : <code>{inv.amount_ton} TON</code>\n"
                        f"🏷 شناسه پیگیری (Comment) : <code>{inv.comment}</code>\n"
                        f"🌐 <a href=\"{tx_url}\">مشاهده تراکنش در Tonviewer</a>\n\n"
                        f"👛 موجودی جدید : <b>{new_balance:,}</b> تومان"
                    )
                    await bot.send_message(settings.ADMIN_CHAT_ID, admin_msg, **thread_kwargs)
                except Exception as exc:
                    logger.warning("Failed to notify admin chat of TON topup: %s", exc)

    return processed_count


async def ton_watcher_loop(bot: Any, session_factory: Any) -> None:
    """Background polling loop watching for incoming TON payments."""
    logger.info("Starting TON blockchain watcher loop")
    await asyncio.sleep(15)  # startup grace period

    while True:
        try:
            await verify_and_process_payments(bot, session_factory)
        except Exception as exc:
            logger.error("Error in TON payment watcher: %s", exc)

        await asyncio.sleep(25)
