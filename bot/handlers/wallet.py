"""Wallet section: balance, methods picker, and transactions history."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, parse_int
from bot.db.repositories.order_repo import OrderRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.handlers.wallet_card import (
    MAX_PENDING_TOPUPS,
    MAX_RECEIPT_BYTES,
    MAX_TOPUP,
    router as card_router,
    topup_decide,
    topup_receipt,
)
from bot.handlers.wallet_crypto import (
    _render_ton_invoice,
    router as crypto_router,
    ton_invoice_cancel,
    ton_invoice_check,
)
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings, is_maintenance
from bot.services.formatting import format_datetime
from bot.services.menu import delete_message_silently, render_menu
from bot.services.render import render_wallet
from bot.states.wallet import TopupStates

logger = logging.getLogger(__name__)

router = Router(name="wallet")
router.include_router(crypto_router)
router.include_router(card_router)

_parse_amount = parse_int
_fmt = fmt
_render_wallet = render_wallet


@router.callback_query(F.data == "wallet:history")
async def topup_history(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
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

    kb = InlineKeyboardBuilder()
    if has_card and has_crypto:
        if lang == "fa":
            kb.button(text=t(lang, "btn_topup_ton"), callback_data="wallet:method:ton")
            kb.button(text=t(lang, "btn_topup_card"), callback_data="wallet:method:card")
        else:
            kb.button(text=t(lang, "btn_topup_card"), callback_data="wallet:method:card")
            kb.button(text=t(lang, "btn_topup_ton"), callback_data="wallet:method:ton")
    elif has_card:
        kb.button(text=t(lang, "btn_topup_card"), callback_data="wallet:method:card")
    elif has_crypto:
        kb.button(text=t(lang, "btn_topup_ton"), callback_data="wallet:method:ton")

    kb.button(text="🎟 کارت شارژ / گیفت‌کارت", callback_data="wallet:voucher")
    kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")
    if has_card and has_crypto:
        kb.adjust(2, 1, 1)
    else:
        kb.adjust(1)

    await render_menu(bot, user, user_repo, t(lang, "topup_select_method"), kb.as_markup())
    await call.answer()
    return


@router.callback_query(F.data == "wallet:voucher")
async def voucher_prompt(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    state: FSMContext,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await state.set_state(TopupStates.waiting_voucher)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(user.language, "btn_cancel"), callback_data="menu:wallet")
    kb.adjust(1)
    msg = (
        "🎟 <b>فعال‌سازی کارت شارژ / گیفت‌کارت</b>\n\n"
        "لطفاً کد شارژ دریافتی را ارسال نمایید:"
    )
    await render_menu(bot, user, user_repo, msg, kb.as_markup())
    await call.answer()


@router.message(TopupStates.waiting_voucher)
async def voucher_redeem_message(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    await delete_message_silently(bot, message.chat.id, message.message_id)
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    code = (message.text or "").strip()
    if not code:
        return

    from bot.db.repositories.coupon_repo import CouponRepository
    coupon_repo = CouponRepository(session)
    ok, amount, msg = await coupon_repo.redeem_credit_voucher(code, user.telegram_id)
    if not ok:
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")
        kb.adjust(1)
        err_text = f"⚠️ <b>خطا در فعال‌سازی:</b>\n{msg}\n\nلطفاً مجدداً کد صحیح را ارسال فرمایید:"
        await render_menu(bot, user, user_repo, err_text, kb.as_markup())
        return

    await session.commit()
    await state.clear()
    wallet_repo = WalletRepository(session)
    await _render_wallet(bot, user, user_repo, wallet_repo, lang)


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

    if method == "card" and store.card_require_phone_verification and not getattr(user, "phone_number", None):
        kb = InlineKeyboardBuilder()
        kb.button(text="📱 احراز هویت و ارسال شماره تماس", callback_data="user:verify_phone_prompt")
        kb.button(text=t(lang, "btn_back"), callback_data="menu:wallet")
        kb.adjust(1)
        notice_text = (
            "🔒 <b>احراز هویت شماره همراه الزامی است</b>\n\n"
            "جهت استفاده از درگاه پرداخت کارت‌به‌کارت و جلوگیری از سوءاستفاده‌های بانکی (فیشینگ)، تأیید شماره تماس در ربات الزامی است.\n\n"
            "لطفاً بر روی دکمه زیر کلیک کرده و شماره همراه خود را ارسال فرمایید."
            if lang == "fa"
            else
            "🔒 <b>Phone Verification Required</b>\n\n"
            "To use Card-to-Card payment, you must verify your phone number first.\n"
            "Please tap the button below to share your contact."
        )
        await render_menu(bot, user, user_repo, notice_text, kb.as_markup())
        return

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


async def _create_and_render_ton_invoice(
    bot: Bot,
    user: Any,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    store: Any,
    amount: int,
) -> None:
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


async def _create_and_render_card_auto_invoice(
    bot: Bot,
    user: Any,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    store: Any,
    amount: int,
) -> None:
    from bot.services.payment.card_auto_service import generate_card_auto_invoice
    lang = user.language or "fa"
    invoice = await generate_card_auto_invoice(
        session=session,
        telegram_id=user.telegram_id,
        base_amount=amount,
        store=store,
        ttl_minutes=15,
    )
    await session.commit()
    await state.update_data(amount=amount, auto_invoice_uuid=invoice.invoice_uuid)
    await state.set_state(TopupStates.waiting_receipt)

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 استعلام وضعیت پرداخت", callback_data=f"wallet:c2c_check:{invoice.invoice_uuid}")
    kb.button(text="📤 ارسال دستی تصویر فیش", callback_data=f"wallet:manual_receipt:{invoice.invoice_uuid}")
    kb.button(text=t(lang, "btn_cancel"), callback_data=f"wallet:c2c_cancel:{invoice.invoice_uuid}")
    kb.adjust(1)

    c2c_text = (
        "⚡️ <b>فاکتور پرداخت هوشمند کارت‌به‌کارت (تأیید آنی)</b>\n"
        "──────────────────\n"
        f"💰 مبلغ به تومان: <code>{invoice.exact_amount:,}</code> تومان\n"
        f"💰 مبلغ به ریال: <code>{invoice.exact_rial:,}</code> ریال\n\n"
        f"💳 شماره کارت مقصد:\n<code>{escape(store.card_number)}</code>\n"
        f"👤 بنام: <b>{escape(store.card_holder or 'مدیریت')}</b>\n"
        f"⏳ مهلت پرداخت: <b>۱۵ دقیقه</b>\n\n"
        "⚠️ <b>توجه مهم:</b> لطفاً هنگام واریز از همراه‌بانک، <u>دقیقاً همین رقم</u> را وارد نمایید و مبلغ را رند نکنید. بلافاصله پس از واریز، کیف پول شما به صورت اتوماتیک شارژ خواهد شد."
    )
    await render_menu(bot, user, user_repo, c2c_text, kb.as_markup())


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

        await _create_and_render_ton_invoice(bot, user, user_repo, session, state, store, amount)
        await call.answer()
        return

    if getattr(store, "card_auto_enabled", False):
        await _create_and_render_card_auto_invoice(bot, user, user_repo, session, state, store, amount)
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

        await _create_and_render_ton_invoice(bot, user, user_repo, session, state, store, amount)
        return

    if getattr(store, "card_auto_enabled", False):
        await _create_and_render_card_auto_invoice(bot, user, user_repo, session, state, store, amount)
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


@router.callback_query(F.data == "user:verify_phone_prompt")
async def verify_phone_prompt_cb(call: CallbackQuery, bot: Bot):
    from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
    phone_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 اشتراک‌گذاری شماره تماس من", request_contact=True)]],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
    )
    await bot.send_message(
        chat_id=call.from_user.id,
        text=(
            "🔒 <b>احراز هویت شماره همراه</b>\n\n"
            "👇 <b>دکمه «📱 اشتراک‌گذاری شماره تماس من» در پایین صفحه (روی کیبورد تایپ پیام) نمایان شد:</b>\n"
            "لطفاً روی آن ضربه بزنید تا شماره شما تأیید و درگاه کارت‌به‌کارت فعال گردد.\n\n"
            "<i>(شماره شما صرفاً برای تأیید بانکی ذخیره شده و کاملاً محرمانه است)</i>"
        ),
        reply_markup=phone_kb,
        parse_mode="HTML",
    )
    await call.answer()


__all__ = [
    "router",
    "MAX_TOPUP",
    "MAX_PENDING_TOPUPS",
    "MAX_RECEIPT_BYTES",
    "_parse_amount",
    "_fmt",
    "_render_wallet",
    "render_menu",
    "delete_message_silently",
    "topup_history",
    "wallet_entry",
    "topup_start",
    "topup_method_pick",
    "_render_topup_amount_prompt",
    "_render_ton_invoice",
    "topup_preset_amount",
    "topup_amount",
    "ton_invoice_check",
    "ton_invoice_cancel",
    "topup_receipt",
    "topup_decide",
]


@router.callback_query(F.data.startswith("wallet:c2c_check:"))
async def c2c_check_callback(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    uuid_str = call.data.split(":", 2)[2]
    from bot.db.repositories.card_auto_repo import CardAutoRepository
    repo = CardAutoRepository(session)
    inv = await repo.get_invoice_by_uuid(uuid_str)
    if not inv or inv.telegram_id != call.from_user.id:
        await call.answer("فاکتور یافت نشد.", show_alert=True)
        return

    if inv.status == "paid":
        user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
        kb = InlineKeyboardBuilder()
        kb.button(text="🛍 مشاهده سرویس‌ها", callback_data="menu:services")
        kb.button(text="💳 کیف پول من", callback_data="menu:wallet")
        kb.adjust(2)
        await render_menu(
            bot, user, user_repo,
            f"✅ <b>پرداخت کارت‌به‌کارت شما با موفقیت تأیید شد!</b>\n\nمبلغ {inv.exact_amount:,} تومان به حساب شما منظور گردید.",
            kb.as_markup(),
        )
        await call.answer()
    elif inv.status == "expired":
        await call.answer("مهلت پرداخت این فاکتور به پایان رسیده است.", show_alert=True)
    else:
        await call.answer("هنوز پیامک واریز از بانک دریافت نشده است؛ لطفاً پس از واریز صبور باشید.", show_alert=True)


@router.callback_query(F.data.startswith("wallet:c2c_cancel:"))
async def c2c_cancel_callback(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
    state: FSMContext,
):
    uuid_str = call.data.split(":", 2)[2]
    from bot.db.repositories.card_auto_repo import CardAutoRepository
    repo = CardAutoRepository(session)
    await repo.cancel_invoice(uuid_str, call.from_user.id)
    await session.commit()
    await state.clear()
    await call.answer("فاکتور پرداخت لغو گردید.")
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_wallet(bot, user, user_repo, WalletRepository(session), user.language)


@router.callback_query(F.data.startswith("wallet:manual_receipt:"))
async def c2c_manual_receipt_callback(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
    state: FSMContext,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    data = await state.get_data()
    amount = data.get("amount", 0)
    store = await get_store_settings(session)
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
    await call.answer("اکنون تصویر فیش واریزی خود را ارسال فرمایید.")
