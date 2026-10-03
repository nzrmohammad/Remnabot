"""Wallet Crypto (TON) payment invoices and verification."""
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR
from bot.db.repositories.crypto_repo import CryptoRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.app_settings import get_store_settings
from bot.services.crypto.ton import fetch_ton_transactions
from bot.services.menu import render_menu
from bot.services.render import render_wallet

logger = logging.getLogger(__name__)
router = Router(name="wallet_crypto")

_render_wallet = render_wallet


async def _render_ton_invoice(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession, invoice,
) -> None:
    lang = user.language or "fa"
    deep_link = f"ton://transfer/{invoice.pay_address}?amount={invoice.nanotons}&text={invoice.comment}"

    kb = InlineKeyboardBuilder()
    tonkeeper_label = "🚀 پرداخت با Tonkeeper / ولت" if lang == "fa" else "🚀 Pay in Tonkeeper"
    check_label = "🔄 بررسی وضعیت پرداخت" if lang == "fa" else "🔄 Check Payment Status"
    cancel_label = "❌ لغو فاکتور" if lang == "fa" else "❌ Cancel Invoice"

    kb.button(text=tonkeeper_label, url=deep_link)
    kb.button(text=check_label, callback_data=f"wallet:ton:check:{invoice.id}")
    kb.button(text=cancel_label, callback_data=f"wallet:ton:cancel:{invoice.id}")
    kb.adjust(1)

    if lang == "fa":
        text = (
            f"💎 <b>فاکتور پرداخت با تون (TON)</b>\n"
            f"{SEPARATOR}\n"
            f"💰 مبلغ شارژ : <b>{invoice.amount_toman:,}</b> تومان\n"
            f"💎 مقدار قابل پرداخت : <code>{invoice.amount_ton} TON</code>\n\n"
            f"📬 <b>آدرس والت مقصد (لمس برای کپی):</b>\n"
            f"<code>{invoice.pay_address}</code>\n\n"
            f"⚠️ <b>بسیار مهم — شناسه پرداخت (Comment / Memo):</b>\n"
            f"<code>{invoice.comment}</code>\n"
            f"حتماً در بخش Comment یا پیام والت خود این شناسه را وارد کنید تا شارژ به‌طور خودکار انجام شود.\n\n"
            f"⏳ مهلت پرداخت : <b>۳۰ دقیقه</b>\n\n"
            f"💡 در صورت داشتن تونکیپر یا والت تلگرام، کافیست روی دکمه «پرداخت با Tonkeeper» کلیک کنید تا تمام فیلدها خودبه‌خود پر شوند."
        )
    else:
        text = (
            f"💎 <b>TON Payment Invoice</b>\n"
            f"{SEPARATOR}\n"
            f"💰 Top-up Amount : <b>{invoice.amount_toman:,}</b> Toman\n"
            f"💎 Payable Amount : <code>{invoice.amount_ton} TON</code>\n\n"
            f"📬 <b>Destination Wallet Address:</b>\n"
            f"<code>{invoice.pay_address}</code>\n\n"
            f"⚠️ <b>Important — Payment Memo / Comment:</b>\n"
            f"<code>{invoice.comment}</code>\n"
            f"<i>You must include this comment in your transfer so your wallet is credited automatically.</i>\n\n"
            f"⏳ Valid for : <b>30 minutes</b>"
        )

    await render_menu(bot, user, user_repo, text, kb.as_markup())


@router.callback_query(F.data.startswith("wallet:ton:check:"))
async def ton_invoice_check(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    try:
        inv_id = int(call.data.split(":", 3)[3])
    except (ValueError, IndexError):
        await call.answer()
        return

    crypto_repo = CryptoRepository(session)
    inv = await crypto_repo.get_by_id(inv_id)
    if not inv:
        await call.answer("❌ فاکتور یافت نشد.", show_alert=True)
        return

    if inv.status == "paid":
        wallet_repo = WalletRepository(session)
        w = await wallet_repo.get_wallet(inv.telegram_id)
        user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
        lang = user.language or "fa"
        kb = InlineKeyboardBuilder()
        kb.button(text="🛍 خرید سرویس" if lang == "fa" else "🛍 Buy Service", callback_data="menu:services")
        kb.button(text="🏠 منوی اصلی" if lang == "fa" else "🏠 Main Menu", callback_data="nav:main_menu")
        kb.adjust(1)
        msg = (
            f"🎉 <b>این فاکتور با موفقیت پرداخت و کیف پول شما شارژ شده است!</b>\n\n"
            f"💰 مبلغ : <b>{inv.amount_toman:,}</b> تومان\n"
            f"👛 موجودی فعلی : <b>{w.balance:,}</b> تومان"
        )
        await render_menu(bot, user, user_repo, msg, kb.as_markup())
        await call.answer()
        return

    if inv.status in ("expired", "cancelled"):
        await call.answer("⚠️ این فاکتور منقضی یا لغو شده است.", show_alert=True)
        return

    # Check on-chain immediately
    store = await get_store_settings(session)
    txs = await fetch_ton_transactions(store.ton_wallet_address)
    matched = False
    for tx in txs:
        if tx["comment"] == inv.comment and tx["nanotons"] >= inv.nanotons:
            paid_inv = await crypto_repo.mark_paid(inv.id, tx["tx_hash"])
            if paid_inv:
                wallet_repo = WalletRepository(session)
                new_bal = await wallet_repo.add_balance_atomic(inv.telegram_id, inv.amount_toman)
                await session.commit()
                matched = True
                user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
                lang = user.language or "fa"
                kb = InlineKeyboardBuilder()
                kb.button(text="🛍 خرید سرویس" if lang == "fa" else "🛍 Buy Service", callback_data="menu:services")
                kb.button(text="🏠 منوی اصلی" if lang == "fa" else "🏠 Main Menu", callback_data="nav:main_menu")
                kb.adjust(1)
                msg = (
                    f"🎉 <b>کیف پول شما با موفقیت شارژ شد!</b>\n"
                    f"{SEPARATOR}\n"
                    f"💎 دریافتی : <code>{inv.amount_ton} TON</code>\n"
                    f"💰 مبلغ شارژ : <b>{inv.amount_toman:,}</b> تومان\n"
                    f"👛 موجودی جدید : <b>{new_bal:,}</b> تومان"
                )
                await render_menu(bot, user, user_repo, msg, kb.as_markup())
                await call.answer("✅ پرداخت تایید و کیف پول شارژ شد!", show_alert=True)
                return

    if not matched:
        await call.answer(
            "⏳ هنوز تراکنشی با این شناسه در شبکه ثبت نشده است. لطفاً پس از ارسال کمی صبر کنید و دوباره امتحان نمایید.",
            show_alert=True,
        )


@router.callback_query(F.data.startswith("wallet:ton:cancel:"))
async def ton_invoice_cancel(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    try:
        inv_id = int(call.data.split(":", 3)[3])
    except (ValueError, IndexError):
        await call.answer()
        return

    crypto_repo = CryptoRepository(session)
    await crypto_repo.mark_cancelled(inv_id)
    await session.commit()

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    wallet_repo = WalletRepository(session)
    await _render_wallet(bot, user, user_repo, wallet_repo, lang)
    await call.answer("❌ فاکتور پرداخت لغو شد.")
