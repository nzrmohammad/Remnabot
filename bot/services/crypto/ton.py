"""TON blockchain watcher and automated payment processor."""
import asyncio
import base64
import logging
from datetime import datetime, timezone

import aiohttp
from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

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
            except Exception:
                pass

    return ""


async def fetch_ton_transactions(address: str, limit: int = 25) -> list[dict]:
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
        logger.debug("Failed to query TonCenter API: %s", e)

    return []


async def verify_and_process_payments(bot: Bot, session_factory) -> int:
    """Check pending invoices against TON blockchain and process payments."""
    async with session_factory() as session:
        crypto_repo = CryptoRepository(session)
        pending_invoices = await crypto_repo.get_all_pending()
        if not pending_invoices:
            return 0

        now = datetime.now(timezone.utc)
        # Check and expire overdue invoices
        active_invoices = []
        for inv in pending_invoices:
            exp = inv.expires_at
            if exp and exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp and exp < now:
                await crypto_repo.mark_expired(inv.id)
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

    # Fetch on-chain incoming transactions
    transactions = await fetch_ton_transactions(wallet_address)
    if not transactions:
        return 0

    processed_count = 0
    settings = get_settings()

    async with session_factory() as session:
        crypto_repo = CryptoRepository(session)
        wallet_repo = WalletRepository(session)
        user_repo = UserRepository(session)
        store = await get_store_settings(session)

        for inv in active_invoices:
            # Look for matching transaction
            matching_tx = None
            inv_created_ts = int(inv.created_at.timestamp()) if inv.created_at else 0
            for tx in transactions:
                if tx["comment"] != inv.comment or tx["nanotons"] < inv.nanotons:
                    continue
                # Timing check: transaction utime must not be before invoice creation (allow 60s clock skew)
                if inv_created_ts and tx.get("utime", 0) and tx["utime"] < (inv_created_ts - 60):
                    continue
                matching_tx = tx
                break

            if matching_tx:
                tx_hash = matching_tx.get("tx_hash") or ""
                # Prevent transaction replay: verify tx_hash has not been used by another invoice
                if tx_hash:
                    existing_tx_inv = await crypto_repo.get_by_tx_hash(tx_hash)
                    if existing_tx_inv and existing_tx_inv.id != inv.id:
                        logger.warning(
                            "TON tx_hash %s already claimed by invoice %s, rejecting replay for invoice %s",
                            tx_hash, existing_tx_inv.id, inv.id,
                        )
                        continue

                paid_inv = await crypto_repo.mark_paid(inv.id, tx_hash)
                if not paid_inv:
                    continue

                # Credit user wallet
                new_balance = await wallet_repo.add_balance_atomic(inv.telegram_id, inv.amount_toman)
                processed_count += 1

                # Send user notification
                try:
                    user = await user_repo.get_by_telegram_id(inv.telegram_id)
                    lang = user.language if user else "fa"
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
                except Exception:
                    logger.exception("Failed to notify user %d of TON topup", inv.telegram_id)

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
                except Exception:
                    logger.exception("Failed to notify admin chat of TON topup")

        await session.commit()

    return processed_count


async def ton_watcher_loop(bot: Bot, session_factory) -> None:
    """Background polling loop watching for incoming TON payments."""
    logger.info("Starting TON blockchain watcher loop")
    await asyncio.sleep(15)  # startup grace period

    while True:
        try:
            await verify_and_process_payments(bot, session_factory)
        except Exception:
            logger.exception("Error in TON payment watcher")

        await asyncio.sleep(25)
