"""Wallet section: balance + card-to-card top-up with admin approval.

Flow:
1. «شارژ کیف پول» → user sends the amount (Toman).
2. Bot shows the card number → user sends the receipt (photo or text).
3. Receipt is copied to the admin chat with Approve / Reject buttons.
4. On approve the wallet balance is increased and the user is notified.
"""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings, is_maintenance
from bot.services.menu import delete_message_silently, render_menu
from bot.services.topups import decide_topup
from bot.states.wallet import TopupStates

logger = logging.getLogger(__name__)
router = Router(name="wallet")

SEPARATOR = "─" * 18

# Persian/Arabic digits → Latin, so «۱۰۰۰۰۰» works too
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

MAX_TOPUP = 500_000_000  # sanity cap, Toman
MAX_PENDING_TOPUPS = 3
MAX_RECEIPT_BYTES = 10 * 1024 * 1024  # 10 MB


def _parse_amount(text: str) -> int | None:
    cleaned = text.translate(_DIGIT_MAP).replace(",", "").replace("،", "").strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def _fmt(amount: int) -> str:
    return f"{amount:,}"


async def _render_wallet(
    bot: Bot, user, user_repo: UserRepository, wallet_repo: WalletRepository, lang: str
) -> None:
    wallet = await wallet_repo.get_wallet(user.telegram_id)
    pending = await wallet_repo.pending_count(user.telegram_id)

    lines = [
        t(lang, "wallet_title"),
        SEPARATOR,
        t(lang, "wallet_balance", balance=_fmt(wallet.balance)),
    ]
    if pending:
        lines.append(t(lang, "wallet_pending", count=pending))

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        kb.button(text=t(lang, "btn_topup_history"), callback_data="wallet:history")
        kb.button(text=t(lang, "btn_topup"), callback_data="wallet:topup")
    else:
        kb.button(text=t(lang, "btn_topup"), callback_data="wallet:topup")
        kb.button(text=t(lang, "btn_topup_history"), callback_data="wallet:history")

    menu_label = "🏠 منوی اصلی" if lang == "fa" else "🏠 Main Menu"
    kb.button(text=menu_label, callback_data="nav:main_menu")
    kb.adjust(2, 1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "wallet:history")
async def topup_history(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    from datetime import datetime, timezone

    from bot.db.repositories.order_repo import OrderRepository
    from bot.services.formatting import format_datetime

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    currency = t(lang, "svc_currency")

    topups = await WalletRepository(session).list_for_user(user.telegram_id, limit=20)
    orders = await OrderRepository(session).list_for_user(user.telegram_id, limit=20)

    transactions = []
    for tp in topups:
        transactions.append({
            "kind": "topup",
            "id": tp.id,
            "amount": tp.amount,
            "status": tp.status,
            "created_at": tp.created_at,
        })

    for od in orders:
        if od.status == "failed":
            continue
        transactions.append({
            "kind": "order",
            "id": od.id,
            "amount": od.amount,
            "service_name": od.service_name,
            "status": od.status,
            "created_at": od.created_at,
        })

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    transactions.sort(key=lambda x: x["created_at"] or epoch, reverse=True)
    transactions = transactions[:15]

    lines = [t(lang, "topups_history_title"), SEPARATOR]
    if not transactions:
        lines.append(t(lang, "topups_history_empty"))
    else:
        for tx in transactions:
            when = format_datetime(tx["created_at"], lang) if tx["created_at"] else "—"
            amt_str = _fmt(tx["amount"])
            if tx["kind"] == "topup":
                status = tx["status"]
                if status == "approved":
                    lines.append(
                        f"➕ <b>+{amt_str}</b> {currency} · {t(lang, 'tx_topup')}\n"
                        f"   ✅ {t(lang, 'topup_status_approved')} · 🕒 {when}"
                    )
                elif status == "pending":
                    lines.append(
                        f"⏳ <b>{amt_str}</b> {currency} · {t(lang, 'tx_topup_pending')}\n"
                        f"   🕒 {when}"
                    )
                else:
                    lines.append(
                        f"❌ <b>{amt_str}</b> {currency} · {t(lang, 'tx_topup_rejected')}\n"
                        f"   🕒 {when}"
                    )
            elif tx["kind"] == "order":
                svc_title = escape(tx.get("service_name") or t(lang, "services_title"))
                if tx["status"] == "refunded":
                    lines.append(
                        f"🔄 <b>+{amt_str}</b> {currency} · {svc_title}\n"
                        f"   ↩️ {t(lang, 'tx_order_refunded')} · 🕒 {when}"
                    )
                else:
                    lines.append(
                        f"➖ <b>-{amt_str}</b> {currency} · {svc_title}\n"
                        f"   🛒 {t(lang, 'tx_order_paid')} · 🕒 {when}"
                    )

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back"), callback_data="menu:wallet")
    kb.adjust(1)
    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()


@router.callback_query(F.data == "menu:wallet")
async def wallet_entry(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_wallet(bot, user, user_repo, WalletRepository(session), user.language)
    await call.answer()


@router.callback_query(F.data == "wallet:topup")
async def topup_start(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
    state: FSMContext,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language
    store = await get_store_settings(session)

    if await is_maintenance(session):
        await call.answer(t(lang, "maintenance_user"), show_alert=True)
        return

    has_card = bool(store.card_enabled and store.card_number and store.card_number.strip())
    has_crypto = bool(store.crypto_enabled and store.ton_wallet_address and store.ton_rate_toman > 0)

    if not has_card and not has_crypto:
        await call.answer(t(lang, "topup_no_card"), show_alert=True)
        return

    if has_card and has_crypto:
        kb = InlineKeyboardBuilder()
        if lang == "fa":
            kb.button(text=t(lang, "btn_topup_ton"), callback_data="wallet:method:ton")
            kb.button(text=t(lang, "btn_topup_card"), callback_data="wallet:method:card")
        else:
            kb.button(text=t(lang, "btn_topup_card"), callback_data="wallet:method:card")
            kb.button(text=t(lang, "btn_topup_ton"), callback_data="wallet:method:ton")
        kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")
        kb.adjust(2, 1)
        await render_menu(bot, user, user_repo, t(lang, "topup_select_method"), kb.as_markup())
        await call.answer()
        return

    method = "ton" if has_crypto else "card"
    await _render_topup_amount_prompt(bot, user, user_repo, session, state, method)
    await call.answer()


@router.callback_query(F.data.startswith("wallet:method:"))
async def topup_method_pick(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
    state: FSMContext,
):
    method = call.data.split(":", 2)[2]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_topup_amount_prompt(bot, user, user_repo, session, state, method)
    await call.answer()


async def _render_topup_amount_prompt(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
    state: FSMContext, method: str,
) -> None:
    lang = user.language or "fa"
    store = await get_store_settings(session)
    await state.set_state(TopupStates.waiting_amount)
    await state.update_data(topup_method=method)

    min_amt = store.topup_min_amount
    presets = [min_amt, min_amt * 2, min_amt * 3, min_amt * 5]

    kb = InlineKeyboardBuilder()
    if lang == "fa":
        row1 = (presets[1], presets[0])
        row2 = (presets[3], presets[2])
    else:
        row1 = (presets[0], presets[1])
        row2 = (presets[2], presets[3])

    for amt in row1:
        kb.button(
            text=f"💰 {_fmt(amt)} {t(lang, 'svc_currency')}",
            callback_data=f"wallet:amt:{amt}",
        )
    for amt in row2:
        kb.button(
            text=f"💰 {_fmt(amt)} {t(lang, 'svc_currency')}",
            callback_data=f"wallet:amt:{amt}",
        )
    kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")
    kb.adjust(2, 2, 1)

    hint_crypto = ""
    if method == "ton" and store.ton_rate_toman > 0:
        hint_crypto = (
            f"\n\n💎 <b>نرخ محاسبه:</b> هر تون = <b>{store.ton_rate_toman:,}</b> تومان"
            if lang == "fa"
            else f"\n\n💎 <b>Conversion rate:</b> 1 TON = <b>{store.ton_rate_toman:,}</b> Toman"
        )

    prompt_text = t(lang, "topup_amount_prompt", min=_fmt(store.topup_min_amount)) + hint_crypto
    await render_menu(bot, user, user_repo, prompt_text, kb.as_markup())


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


@router.callback_query(F.data.startswith("wallet:amt:"))
async def topup_preset_amount(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
    state: FSMContext,
):
    try:
        amount = int(call.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await call.answer()
        return

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language
    store = await get_store_settings(session)

    if amount < store.topup_min_amount or amount > MAX_TOPUP:
        await call.answer(
            t(lang, "topup_amount_invalid", min=_fmt(store.topup_min_amount)),
            show_alert=True,
        )
        return

    data = await state.get_data()
    method = data.get("topup_method", "card")

    if method == "ton":
        if not (store.crypto_enabled and store.ton_wallet_address and store.ton_rate_toman > 0):
            await call.answer("❌ پرداخت کریپتو موقتاً غیرفعال است.", show_alert=True)
            return

        from bot.db.repositories.crypto_repo import CryptoRepository
        crypto_repo = CryptoRepository(session)
        ton_amount = round(amount / store.ton_rate_toman, 4)
        nanotons = int(round(ton_amount * 1_000_000_000))
        invoice = await crypto_repo.create_invoice(
            telegram_id=user.telegram_id,
            amount_toman=amount,
            amount_ton=f"{ton_amount:.4f}",
            nanotons=nanotons,
            pay_address=store.ton_wallet_address,
            expires_minutes=30,
        )
        await session.commit()
        await state.clear()
        await _render_ton_invoice(bot, user, user_repo, session, invoice)
        await call.answer()
        return

    await state.update_data(amount=amount)
    await state.set_state(TopupStates.waiting_receipt)

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")
    kb.adjust(1)

    await render_menu(
        bot, user, user_repo,
        t(
            lang, "topup_card_info",
            amount=_fmt(amount),
            card=escape(store.card_number),
            holder=escape(store.card_holder or "—"),
        ),
        kb.as_markup(),
    )
    await call.answer()


@router.message(TopupStates.waiting_amount, F.text)
async def topup_amount(
    message: Message, bot: Bot, user_repo: UserRepository, session: AsyncSession,
    state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    store = await get_store_settings(session)

    await delete_message_silently(bot, message.chat.id, message.message_id)

    amount = _parse_amount(message.text)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")

    if amount is None or amount < store.topup_min_amount or amount > MAX_TOPUP:
        await render_menu(
            bot, user, user_repo,
            t(lang, "topup_amount_invalid", min=_fmt(store.topup_min_amount)),
            kb.as_markup(),
        )
        return

    data = await state.get_data()
    method = data.get("topup_method", "card")

    if method == "ton":
        if not (store.crypto_enabled and store.ton_wallet_address and store.ton_rate_toman > 0):
            await render_menu(bot, user, user_repo, "❌ پرداخت کریپتو موقتاً غیرفعال است.", kb.as_markup())
            return

        from bot.db.repositories.crypto_repo import CryptoRepository
        crypto_repo = CryptoRepository(session)
        ton_amount = round(amount / store.ton_rate_toman, 4)
        nanotons = int(round(ton_amount * 1_000_000_000))
        invoice = await crypto_repo.create_invoice(
            telegram_id=user.telegram_id,
            amount_toman=amount,
            amount_ton=f"{ton_amount:.4f}",
            nanotons=nanotons,
            pay_address=store.ton_wallet_address,
            expires_minutes=30,
        )
        await session.commit()
        await state.clear()
        await _render_ton_invoice(bot, user, user_repo, session, invoice)
        return

    if not (store.card_enabled and store.card_number and store.card_number.strip()):
        err_msg = "❌ پرداخت کارت به کارت موقتاً غیرفعال است." if lang == "fa" else "❌ Card payment is temporarily disabled."
        await render_menu(bot, user, user_repo, err_msg, kb.as_markup())
        return

    await state.update_data(amount=amount)
    await state.set_state(TopupStates.waiting_receipt)

    await render_menu(
        bot, user, user_repo,
        t(
            lang, "topup_card_info",
            amount=_fmt(amount),
            card=escape(store.card_number),
            holder=escape(store.card_holder or "—"),
        ),
        kb.as_markup(),
    )


@router.callback_query(F.data.startswith("wallet:ton:check:"))
async def ton_invoice_check(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    try:
        inv_id = int(call.data.split(":", 3)[3])
    except (ValueError, IndexError):
        await call.answer()
        return

    from bot.db.repositories.crypto_repo import CryptoRepository
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
    from bot.services.crypto.ton import fetch_ton_transactions
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

    from bot.db.repositories.crypto_repo import CryptoRepository
    crypto_repo = CryptoRepository(session)
    await crypto_repo.mark_cancelled(inv_id)
    await session.commit()

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    wallet_repo = WalletRepository(session)
    await _render_wallet(bot, user, user_repo, wallet_repo, lang)
    await call.answer("❌ فاکتور پرداخت لغو شد.")


@router.message(TopupStates.waiting_receipt, F.photo | F.text | F.document)
async def topup_receipt(
    message: Message,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    settings = get_settings()

    data = await state.get_data()
    amount = int(data.get("amount", 0))
    if amount <= 0:
        await state.clear()
        await delete_message_silently(bot, message.chat.id, message.message_id)
        return

    wallet_repo = WalletRepository(session)
    # Anti-spam: cap concurrent pending requests.
    if await wallet_repo.pending_count(user.telegram_id) >= MAX_PENDING_TOPUPS:
        await delete_message_silently(bot, message.chat.id, message.message_id)
        await state.clear()
        back = InlineKeyboardBuilder()
        back.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
        await render_menu(
            bot, user, user_repo, t(lang, "topup_pending_limit"), back.as_markup()
        )
        return

    # Stable receipt fingerprint: file_unique_id survives forwards/copies,
    # so the same photo/file can't be submitted twice. Text receipts are
    # normalized (whitespace collapsed) and hashed.
    import hashlib as _hl

    receipt_hash: str | None = None
    if message.photo:
        biggest = message.photo[-1]
        receipt_hash = f"photo:{biggest.file_unique_id}"
    elif message.document:
        receipt_hash = f"doc:{message.document.file_unique_id}"
    elif message.text:
        normalized = " ".join(message.text.split())
        receipt_hash = "text:" + _hl.sha256(normalized.encode("utf-8")).hexdigest()[:48]

    if receipt_hash and await wallet_repo.receipt_exists(receipt_hash):
        await delete_message_silently(bot, message.chat.id, message.message_id)
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")
        await render_menu(
            bot, user, user_repo, t(lang, "topup_duplicate_receipt"), kb.as_markup()
        )
        return

    # Validate receipt size/type (photo/document); text receipts pass through.
    if message.document:
        size = message.document.file_size or 0
        mime = (message.document.mime_type or "")
        allowed = mime.startswith("image/") or mime == "application/pdf"
        if size > MAX_RECEIPT_BYTES or not allowed:
            await delete_message_silently(bot, message.chat.id, message.message_id)
            kb = InlineKeyboardBuilder()
            kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")
            await render_menu(
                bot, user, user_repo, t(lang, "topup_receipt_invalid"), kb.as_markup()
            )
            return
    if message.photo:
        biggest = message.photo[-1] if message.photo else None
        if biggest is not None and (biggest.file_size or 0) > MAX_RECEIPT_BYTES:
            await delete_message_silently(bot, message.chat.id, message.message_id)
            kb = InlineKeyboardBuilder()
            kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")
            await render_menu(
                bot, user, user_repo, t(lang, "topup_receipt_invalid"), kb.as_markup()
            )
            return

    topup = await wallet_repo.create_topup(user.telegram_id, amount, receipt_hash)

    # receipt + info with approve/reject buttons → admin chat
    tg_username = f"@{message.from_user.username}" if message.from_user.username else "—"
    kb = InlineKeyboardBuilder()
    kb.button(text=t("fa", "btn_approve"), callback_data=f"topup:ok:{topup.id}")
    kb.button(text=t("fa", "btn_reject"), callback_data=f"topup:no:{topup.id}")
    kb.adjust(2)

    store = await get_store_settings(session)
    topic_id = store.topic_topups if store.topic_topups is not None else settings.ADMIN_TOPIC_TOPUPS
    thread_kwargs = {"message_thread_id": topic_id} if topic_id else {}
    delivered = False
    admin_req_text = t(
        "fa", "admin_topup_request",
        id=topup.id,
        name=escape(message.from_user.full_name),
        tid=user.telegram_id,
        username=escape(tg_username),
        amount=_fmt(amount),
    )

    # 1. Primary delivery to configured ADMIN_CHAT_ID (with topic if set)
    try:
        await bot.copy_message(
            chat_id=settings.ADMIN_CHAT_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            **thread_kwargs,
        )
        await bot.send_message(
            settings.ADMIN_CHAT_ID,
            admin_req_text,
            reply_markup=kb.as_markup(),
            **thread_kwargs,
        )
        delivered = True
    except TelegramAPIError as exc:
        logger.warning(
            "Failed to deliver top-up %s to admin chat %s (%s). Attempting fallback to admins...",
            topup.id, settings.ADMIN_CHAT_ID, exc,
        )

    # 2. Fallback: if group delivery failed, deliver to individual admin private chats
    if not delivered and settings.ADMIN_IDS:
        for admin_id in settings.ADMIN_IDS:
            try:
                await bot.copy_message(
                    chat_id=admin_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
                await bot.send_message(
                    admin_id,
                    admin_req_text,
                    reply_markup=kb.as_markup(),
                )
                delivered = True
            except Exception as admin_exc:
                logger.warning(
                    "Fallback delivery of top-up %s to admin %s failed: %s",
                    topup.id, admin_id, admin_exc,
                )

    await delete_message_silently(bot, message.chat.id, message.message_id)
    await state.clear()

    if not delivered:
        # Don't leave an orphan pending top-up the admin never saw.
        try:
            await wallet_repo.cancel_pending(topup.id)
        except Exception:
            pass
        back = InlineKeyboardBuilder()
        back.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
        await render_menu(
            bot, user, user_repo, t(lang, "support_failed"), back.as_markup()
        )
        return

    back = InlineKeyboardBuilder()
    back.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    await render_menu(
        bot, user, user_repo, t(lang, "topup_receipt_registered"), back.as_markup()
    )


# --------------------------------------------------------------------- #
# Admin approval
# --------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("topup:"))
async def topup_decide(call: CallbackQuery, bot: Bot, session: AsyncSession):
    if call.from_user.id not in get_settings().ADMIN_IDS:
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return

    try:
        _, action, topup_id_s = call.data.split(":", 2)
        topup_id = int(topup_id_s)
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    changed, note = await decide_topup(
        bot, session, int(topup_id), approved=(action == "ok"),
        admin_id=call.from_user.id,
    )
    if not changed:
        await call.answer(note, show_alert=True)
        return

    # stamp the admin message so it can't be pressed twice
    if call.message is not None:
        new_text = f"{call.message.html_text}\n\n{note}"
        try:
            await call.message.edit_text(new_text)
        except TelegramAPIError:
            pass
    await call.answer(note)
