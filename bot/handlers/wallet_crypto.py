"""Wallet Crypto (TON, TRX, POL) payment invoices and verification."""
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR
from bot.db.repositories.crypto_repo import CryptoRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.app_settings import get_store_settings
from bot.services.crypto.pol import verify_and_credit_pol_invoice
from bot.services.crypto.ton import fetch_ton_transactions
from bot.services.crypto.trx import verify_and_credit_trx_invoice
from bot.services.menu import render_menu
from bot.services.render import render_wallet
from bot.states.wallet import TopupStates

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
            f"⏳ مهلت پرداخت : <b>30 دقیقه</b>\n\n"
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
            f"You must include this comment in your transfer so your wallet is credited automatically.\n\n"
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

    if inv.telegram_id != call.from_user.id:
        await call.answer("❌ این فاکتور متعلق به حساب شما نیست.", show_alert=True)
        return

    if getattr(inv, "currency", "TON") != "TON":
        await call.answer("❌ این فاکتور مربوط به شبکه تون (TON) نمی‌باشد.", show_alert=True)
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

    # Check on-chain immediately using unified verification (SSOT)
    store = await get_store_settings(session)
    txs = await fetch_ton_transactions(store.ton_wallet_address)
    from bot.services.crypto.ton import verify_and_credit_ton_invoice
    matched, new_bal, _ = await verify_and_credit_ton_invoice(session, inv, txs, allow_expired=False, bot=bot)
    if matched:
        await session.commit()
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
    inv = await crypto_repo.get_by_id(inv_id)
    if not inv or inv.telegram_id != call.from_user.id:
        await call.answer("❌ فاکتور یافت نشد یا متعلق به شما نیست.", show_alert=True)
        return

    await crypto_repo.mark_cancelled(inv_id)
    await session.commit()

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    wallet_repo = WalletRepository(session)
    await _render_wallet(bot, user, user_repo, wallet_repo, lang)
    await call.answer("❌ فاکتور پرداخت لغو شد.")


async def _render_trx_invoice(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession, invoice,
) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔍 ثبت هش تراکنش (TxID)", callback_data=f"wallet:trx:submit_tx:{invoice.id}")
    kb.button(text="❌ لغو فاکتور", callback_data=f"wallet:trx:cancel:{invoice.id}")
    kb.adjust(1)

    text = (
        f"🔴 <b>فاکتور پرداخت با ترون (TRX)</b>\n"
        f"{SEPARATOR}\n"
        f"💰 مبلغ شارژ : <b>{invoice.amount_toman:,}</b> تومان\n"
        f"🔴 مقدار دقیق قابل پرداخت : <code>{invoice.amount_ton} TRX</code>\n\n"
        f"📬 <b>آدرس والت مقصد (لمس برای کپی):</b>\n"
        f"<code>{invoice.pay_address}</code>\n\n"
        f"⚠️ <b>توجه بسیار مهم:</b> لطفاً <u>دقیقاً</u> رقم <code>{invoice.amount_ton} TRX</code> را واریز نمایید تا سیستم به‌صورت خودکار و بدون تداخل تراکنش شما را شناسایی کند.\n\n"
        f"⏳ مهلت پرداخت : <b>60 دقیقه</b>\n\n"
        f"💡 پس از واریز از والت، روی دکمه «ثبت هش تراکنش (TxID)» کلیک فرمایید."
    )
    await render_menu(bot, user, user_repo, text, kb.as_markup())


async def _render_pol_invoice(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession, invoice,
) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔍 ثبت هش تراکنش (TxHash)", callback_data=f"wallet:pol:submit_tx:{invoice.id}")
    kb.button(text="❌ لغو فاکتور", callback_data=f"wallet:pol:cancel:{invoice.id}")
    kb.adjust(1)

    text = (
        f"🟣 <b>فاکتور پرداخت با پلیگان (POL)</b>\n"
        f"{SEPARATOR}\n"
        f"💰 مبلغ شارژ : <b>{invoice.amount_toman:,}</b> تومان\n"
        f"🟣 مقدار دقیق قابل پرداخت : <code>{invoice.amount_ton} POL</code>\n\n"
        f"📬 <b>آدرس والت مقصد (لمس برای کپی):</b>\n"
        f"<code>{invoice.pay_address}</code>\n\n"
        f"⚠️ <b>توجه بسیار مهم:</b> لطفاً <u>دقیقاً</u> رقم <code>{invoice.amount_ton} POL</code> را انتقال دهید تا سیستم به‌صورت خودکار تراکنش را تأیید نماید.\n\n"
        f"⏳ مهلت پرداخت : <b>60 دقیقه</b>\n\n"
        f"💡 پس از واریز از والت، روی دکمه «ثبت هش تراکنش (TxHash)» کلیک فرمایید."
    )
    await render_menu(bot, user, user_repo, text, kb.as_markup())


@router.callback_query(F.data.startswith("wallet:trx:submit_tx:"))
async def trx_invoice_submit_tx(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    try:
        inv_id = int(call.data.split(":", 3)[3])
    except (ValueError, IndexError):
        await call.answer()
        return

    await state.set_state(TopupStates.waiting_tx_hash)
    await state.update_data(crypto_inv_id=inv_id, crypto_curr="TRX")
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)

    kb = InlineKeyboardBuilder()
    kb.button(text="❌ لغو", callback_data=f"wallet:trx:cancel:{inv_id}")
    kb.adjust(1)
    msg = (
        "🔴 <b>ثبت شناسه تراکنش ترون (TxID)</b>\n\n"
        "لطفاً هش تراکنش ۶۴ رقمی انتقال خود را به صورت متن ارسال نمایید:"
    )
    await render_menu(bot, user, user_repo, msg, kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("wallet:pol:submit_tx:"))
async def pol_invoice_submit_tx(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    try:
        inv_id = int(call.data.split(":", 3)[3])
    except (ValueError, IndexError):
        await call.answer()
        return

    await state.set_state(TopupStates.waiting_tx_hash)
    await state.update_data(crypto_inv_id=inv_id, crypto_curr="POL")
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)

    kb = InlineKeyboardBuilder()
    kb.button(text="❌ لغو", callback_data=f"wallet:pol:cancel:{inv_id}")
    kb.adjust(1)
    msg = (
        "🟣 <b>ثبت شناسه تراکنش پلیگان (TxHash)</b>\n\n"
        "لطفاً هش تراکنش انتقال خود را به صورت متن ارسال نمایید:"
    )
    await render_menu(bot, user, user_repo, msg, kb.as_markup())
    await call.answer()


@router.message(TopupStates.waiting_tx_hash)
async def crypto_tx_hash_message(
    message: Message,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    cache=None,
):
    data = await state.get_data()
    inv_id = data.get("crypto_inv_id")
    curr = data.get("crypto_curr", "TRX")
    tx_hash = (message.text or "").strip()

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)

    if not tx_hash or not inv_id:
        return

    crypto_repo = CryptoRepository(session)
    inv = await crypto_repo.get_by_id(inv_id)
    if not inv or inv.telegram_id != message.from_user.id:
        await state.clear()
        await message.reply("❌ فاکتور مورد نظر یافت نشد.")
        return

    # If invoice was already cancelled or expired (e.g. from Mini App website)
    if inv.status in ("cancelled", "expired"):
        await state.clear()
        kb_canc = InlineKeyboardBuilder()
        kb_canc.button(text="💳 کیف پول من", callback_data="menu:wallet")
        kb_canc.adjust(1)
        await render_menu(
            bot, user, user_repo,
            "⚠️ <b>این فاکتور پرداخت قبلاً لغو یا منقضی شده است.</b>\n\nامکان ارسال شناسه برای این فاکتور وجود ندارد.",
            kb_canc.as_markup(),
        )
        return

    # If invoice was already paid
    if inv.status == "paid":
        await state.clear()
        kb_paid = InlineKeyboardBuilder()
        kb_paid.button(text="🛍 خرید سرویس", callback_data="menu:services")
        kb_paid.button(text="💳 کیف پول من", callback_data="menu:wallet")
        kb_paid.adjust(2)
        await render_menu(
            bot, user, user_repo,
            "🎉 <b>این فاکتور قبلاً با موفقیت پرداخت و کیف پول شما شارژ شده است.</b>",
            kb_paid.as_markup(),
        )
        return

    if curr == "TRX":
        ok, new_bal, msg = await verify_and_credit_trx_invoice(session, inv, tx_hash, bot=bot)
    else:
        ok, new_bal, msg = await verify_and_credit_pol_invoice(session, inv, tx_hash, bot=bot)

    if ok:
        await session.commit()
        await state.clear()
        if cache and hasattr(cache, "invalidate_user"):
            await cache.invalidate_user(user.telegram_id)
        kb = InlineKeyboardBuilder()
        kb.button(text="🛍 خرید سرویس", callback_data="menu:services")
        kb.button(text="💳 کیف پول من", callback_data="menu:wallet")
        kb.adjust(2)
        success_text = (
            f"🎉 <b>پرداخت با موفقیت تأیید شد و کیف پول شما شارژ گردید!</b>\n"
            f"{SEPARATOR}\n"
            f"💰 مبلغ شارژ : <b>{inv.amount_toman:,}</b> تومان\n"
            f"👛 موجودی جدید : <b>{new_bal:,}</b> تومان"
        )
        await render_menu(bot, user, user_repo, success_text, kb.as_markup())
    else:
        kb_retry = InlineKeyboardBuilder()
        cancel_cb = f"wallet:trx:cancel:{inv.id}" if curr == "TRX" else f"wallet:pol:cancel:{inv.id}"
        kb_retry.button(text="❌ لغو پرداخت", callback_data=cancel_cb)
        kb_retry.adjust(1)
        err_text = f"⚠️ <b>خطا در بررسی تراکنش:</b>\n{msg}\n\nلطفاً مجدداً هش صحیح تراکنش را ارسال کنید یا لغو نمایید:"
        await render_menu(bot, user, user_repo, err_text, kb_retry.as_markup())


@router.callback_query(F.data.startswith("wallet:trx:cancel:"))
async def trx_invoice_cancel(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext | None = None,
):
    try:
        inv_id = int(call.data.split(":", 3)[3])
    except (ValueError, IndexError):
        await call.answer()
        return

    if state:
        await state.clear()

    crypto_repo = CryptoRepository(session)
    inv = await crypto_repo.get_by_id(inv_id)
    if not inv or inv.telegram_id != call.from_user.id:
        await call.answer("❌ فاکتور یافت نشد یا متعلق به شما نیست.", show_alert=True)
        return

    await crypto_repo.mark_cancelled(inv_id)
    await session.commit()

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    wallet_repo = WalletRepository(session)
    await _render_wallet(bot, user, user_repo, wallet_repo, lang)
    await call.answer("❌ فاکتور پرداخت لغو شد.")


@router.callback_query(F.data.startswith("wallet:pol:cancel:"))
async def pol_invoice_cancel(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext | None = None,
):
    try:
        inv_id = int(call.data.split(":", 3)[3])
    except (ValueError, IndexError):
        await call.answer()
        return

    if state:
        await state.clear()

    crypto_repo = CryptoRepository(session)
    inv = await crypto_repo.get_by_id(inv_id)
    if not inv or inv.telegram_id != call.from_user.id:
        await call.answer("❌ فاکتور یافت نشد یا متعلق به شما نیست.", show_alert=True)
        return

    await crypto_repo.mark_cancelled(inv_id)
    await session.commit()

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    wallet_repo = WalletRepository(session)
    await _render_wallet(bot, user, user_repo, wallet_repo, lang)
    await call.answer("❌ فاکتور پرداخت لغو شد.")
