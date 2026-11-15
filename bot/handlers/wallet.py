"""Wallet section: balance, methods picker, and transactions history."""
from __future__ import annotations

import logging
import math
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
    topup_decide,
    topup_receipt,
)
from bot.handlers.wallet_card import (
    router as card_router,
)
from bot.handlers.wallet_crypto import (
    _render_pol_invoice,
    _render_ton_invoice,
    _render_trx_invoice,
    ton_invoice_cancel,
    ton_invoice_check,
)
from bot.handlers.wallet_crypto import (
    router as crypto_router,
)
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings, is_maintenance
from bot.services.formatting import format_datetime
from bot.services.menu import delete_message_silently, render_menu
from bot.services.render import render_wallet
from bot.states.wallet import TopupStates
from bot.web.cache import FastCache

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
            "receipt_hash": getattr(tp, "receipt_hash", None),
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

    lines = [
        "📜 <b>تاریخچه تراکنش‌های کیف پول</b>" if lang == "fa" else t(lang, "topups_history_title"),
        SEPARATOR,
    ]
    if not transactions:
        lines.append(t(lang, "topups_history_empty"))
    else:
        for tx in transactions:
            when = format_datetime(tx["created_at"], lang) if tx["created_at"] else "—"
            amt_str = _fmt(tx["amount"])
            if tx["kind"] == "topup":
                status = tx["status"]
                receipt = str(tx.get("receipt_hash") or "")
                if receipt.startswith("stars:"):
                    method_name = "⭐️ تلگرام استارز"
                elif receipt.startswith("ton:"):
                    method_name = "💎 تون (TON)"
                elif receipt.startswith("trx:"):
                    method_name = "🔴 ترون (TRX)"
                elif receipt.startswith("pol:"):
                    method_name = "🟣 پلیگان (POL)"
                elif receipt.startswith("voucher:"):
                    method_name = "🎟 کارت شارژ"
                elif receipt.startswith("admin:"):
                    method_name = "👤 شارژ دستی"
                elif receipt.startswith("c2c:") or receipt.startswith("auto_c2c:"):
                    method_name = "⚡️ کارت‌به‌کارت آنی"
                else:
                    method_name = "💳 کارت به کارت"

                if status == "approved":
                    badge = "✅ تایید شده"
                    sign = "+"
                    icon = "🟢"
                elif status == "pending":
                    badge = "⏳ در انتظار بررسی"
                    sign = ""
                    icon = "🟡"
                else:
                    badge = "❌ رد شده"
                    sign = ""
                    icon = "🔴"

                lines.append(
                    f"{icon} <b>{badge}</b> | <b>{sign}{amt_str} {currency}</b>\n"
                    f"   روش: <b>{method_name}</b>\n"
                    f"   🕒 زمان: <code>{when}</code>\n"
                    f"   🔖 شناسه: <code>#{tx['id']}</code>"
                )
                lines.append("──────────────────")
            elif tx["kind"] == "order":
                svc_title = escape(tx.get("service_name") or t(lang, "services_title"))
                if tx["status"] == "refunded":
                    lines.append(
                        f"🔵 <b>↩️ بازگشت وجه</b> | <b>+{amt_str} {currency}</b>\n"
                        f"   سرویس: <b>{svc_title}</b>\n"
                        f"   🕒 زمان: <code>{when}</code>\n"
                        f"   🔖 سفارش: <code>#{tx['id']}</code>"
                    )
                else:
                    lines.append(
                        f"🟣 <b>🛒 خرید سرویس</b> | <b>-{amt_str} {currency}</b>\n"
                        f"   سرویس: <b>{svc_title}</b>\n"
                        f"   🕒 زمان: <code>{when}</code>\n"
                        f"   🔖 سفارش: <code>#{tx['id']}</code>"
                    )
                lines.append("──────────────────")

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
    lang = user.language or "fa"
    store = await get_store_settings(session)

    if await is_maintenance(session):
        await call.answer(t(lang, "maintenance_user"), show_alert=True)
        return

    has_card = bool(store.card_enabled and store.card_number and store.card_number.strip())
    has_stars = bool(getattr(store, "stars_enabled", False) and getattr(store, "stars_rate_toman", 0) > 0)
    has_ton = bool(store.crypto_enabled and store.ton_wallet_address and store.ton_wallet_address.strip() and store.ton_rate_toman > 0)
    has_trx = bool(getattr(store, "trx_enabled", False) and getattr(store, "trx_wallet_address", "") and store.trx_wallet_address.strip())
    has_pol = bool(getattr(store, "pol_enabled", False) and getattr(store, "pol_wallet_address", "") and store.pol_wallet_address.strip())

    if not has_card and not has_stars and not has_ton and not has_trx and not has_pol:
        await call.answer(t(lang, "topup_no_card"), show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    if has_card:
        kb.button(text="💳 کارت به کارت", callback_data="wallet:method:card")
    if has_stars:
        kb.button(text="⭐️ تلگرام استارز (Stars)", callback_data="wallet:method:stars")
    if has_ton:
        kb.button(text="💎 شبکه تون (TON)", callback_data="wallet:method:ton")
    if has_trx:
        kb.button(text="🔴 شبکه ترون (TRX)", callback_data="wallet:method:trx")
    if has_pol:
        kb.button(text="🟣 شبکه پلیگان (POL)", callback_data="wallet:method:pol")

    kb.button(text="🎟 کارت شارژ / گیفت‌کارت", callback_data="wallet:voucher")
    kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")
    kb.adjust(2, 2, 2, 1)

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
    remnawave: Any = None, cache: Any = None,
):
    await delete_message_silently(bot, message.chat.id, message.message_id)
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    code = (message.text or "").strip()
    if not code:
        return

    from bot.services.gift_service import redeem_code_to_wallet
    res = await redeem_code_to_wallet(
        session=session,
        code=code,
        telegram_id=user.telegram_id,
        username=user.username,
        remnawave=remnawave,
        bot=bot,
        session_factory=getattr(bot, "session_factory", None),
    )
    if not res.get("ok"):
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")
        kb.adjust(1)
        err_text = f"⚠️ <b>خطا در فعال‌سازی:</b>\n{escape(str(res.get('message', 'کد نامعتبر است.')))}\n\nلطفاً مجدداً کد صحیح را ارسال فرمایید:"
        await render_menu(bot, user, user_repo, err_text, kb.as_markup())
        return

    await state.clear()
    if cache and hasattr(cache, "invalidate_user"):
        await cache.invalidate_user(user.telegram_id)
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

    if method == "card" and not getattr(store, "card_auto_enabled", False):
        from bot.db.repositories.card_auto_repo import CardAutoRepository, format_manual_card_block_message
        block_info = await CardAutoRepository(session).get_manual_card_block_info(user.telegram_id)
        if block_info:
            kb_block = InlineKeyboardBuilder()
            kb_block.button(text=t(lang, "btn_back"), callback_data="menu:wallet")
            kb_block.adjust(1)
            await render_menu(
                bot, user, user_repo,
                format_manual_card_block_message(block_info["remaining_seconds"], lang),
                kb_block.as_markup(),
            )
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
    elif method == "stars":
        s_rate = getattr(store, "stars_rate_toman", 0) or 1500
        hint_crypto = f"\n\n⭐️ <b>نرخ محاسبه:</b> هر استارز = <b>{s_rate:,}</b> تومان"
    elif method == "trx":
        hint_crypto = "\n\n🔴 <b>شبکه ترون:</b> محاسبه نرخ لحظه‌ای معادل ریال / تتر"
    elif method == "pol":
        hint_crypto = "\n\n🟣 <b>شبکه پلیگان:</b> محاسبه نرخ لحظه‌ای معادل ریال / تتر"

    prompt_text = t(lang, "topup_amount_prompt", min=_fmt(store.topup_min_amount)) + hint_crypto
    await render_menu(bot, user, user_repo, prompt_text, kb.as_markup())


async def _create_and_render_stars_invoice(
    bot: Bot,
    user: Any,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    store: Any,
    amount: int,
) -> None:
    lang = user.language or "fa"
    stars_rate = getattr(store, "stars_rate_toman", 0) or 1500
    stars_count = max(1, math.ceil(amount / stars_rate))
    payload = f"stars_topup:{user.telegram_id}:{amount}:{stars_count}"

    link = None
    try:
        from aiogram.types import LabeledPrice
        link = await bot.create_invoice_link(
            title=f"شارژ کیف پول ({amount:,} تومان)",
            description=f"افزایش موجودی کیف پول به مبلغ {amount:,} تومان از طریق تلگرام استارز",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="شارژ کیف پول", amount=stars_count)],
        )
    except Exception as exc:
        logger.error("Failed creating Stars invoice link: %s", exc)

    await state.clear()
    kb = InlineKeyboardBuilder()
    if link:
        kb.button(text=f"⭐️ پرداخت {stars_count} استارز", url=link)
    kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")
    kb.adjust(1)

    text = (
        f"⭐️ <b>فاکتور پرداخت با تلگرام استارز (Stars)</b>\n"
        f"{SEPARATOR}\n"
        f"💰 مبلغ شارژ : <b>{amount:,} تومان</b>\n"
        f"⭐️ تعداد استارز : <b>{stars_count} XTR</b>\n"
        f"💎 نرخ محاسبه : <b>{stars_rate:,} تومان</b> به‌ازای هر استارز\n\n"
        f"⚡️ پس از کلیک روی دکمه پرداخت زیر و تکمیل فرآیند، کیف پول شما به‌طور آنی شارژ خواهد شد."
    )
    await render_menu(bot, user, user_repo, text, kb.as_markup())


async def _create_and_render_trx_invoice(
    bot: Bot,
    user: Any,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    store: Any,
    amount: int,
) -> None:
    from bot.db.repositories.crypto_repo import CryptoRepository
    from bot.services.crypto.trx import fetch_trx_rate
    crypto_repo = CryptoRepository(session)

    trx_rate = getattr(store, "trx_rate_toman", 0)
    if trx_rate <= 0:
        trx_rate = await fetch_trx_rate(0)
    if trx_rate <= 0:
        trx_rate = 15000

    base_sun = max(1_000_000, math.ceil((amount / trx_rate) * 100) * 10_000)
    sun = await crypto_repo.allocate_unique_crypto_units(base_sun, 10_000, "TRX", max_steps=99)
    trx_amount_str = f"{sun / 1e6:.2f}"

    invoice = await crypto_repo.create_invoice(
        telegram_id=user.telegram_id,
        amount_toman=amount,
        amount_ton=trx_amount_str,
        nanotons=sun,
        pay_address=store.trx_wallet_address.strip(),
        expires_minutes=60,
        currency="TRX",
    )
    await session.commit()
    await state.clear()
    await _render_trx_invoice(bot, user, user_repo, session, invoice)


async def _create_and_render_pol_invoice(
    bot: Bot,
    user: Any,
    user_repo: UserRepository,
    session: AsyncSession,
    state: FSMContext,
    store: Any,
    amount: int,
) -> None:
    from bot.db.repositories.crypto_repo import CryptoRepository
    from bot.services.crypto.pol import fetch_pol_rate
    crypto_repo = CryptoRepository(session)

    pol_rate = getattr(store, "pol_rate_toman", 0)
    if pol_rate <= 0:
        pol_rate = await fetch_pol_rate(0)
    if pol_rate <= 0:
        pol_rate = 25000

    base_wei = max(10_000_000_000_000_000, math.ceil((amount / pol_rate) * 1000) * 1_000_000_000_000_000)
    wei = await crypto_repo.allocate_unique_crypto_units(base_wei, 100_000_000_000_000, "POL", max_steps=99)
    pol_amount_str = f"{wei / 1e18:.4f}"

    invoice = await crypto_repo.create_invoice(
        telegram_id=user.telegram_id,
        amount_toman=amount,
        amount_ton=pol_amount_str,
        nanotons=wei,
        pay_address=store.pol_wallet_address.strip(),
        expires_minutes=60,
        currency="POL",
    )
    await session.commit()
    await state.clear()
    await _render_pol_invoice(bot, user, user_repo, session, invoice)


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
    ton_amount = max(0.01, math.ceil((amount / store.ton_rate_toman) * 10_000) / 10_000)
    nanotons = int(round(ton_amount * 1_000_000_000))
    invoice = await crypto_repo.create_invoice(
        telegram_id=user.telegram_id,
        amount_toman=amount,
        amount_ton=f"{ton_amount:.4f}",
        nanotons=nanotons,
        pay_address=store.ton_wallet_address,
        expires_minutes=60,
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
    cache: FastCache | None = None,
) -> None:
    from bot.services.payment.card_auto_service import generate_card_auto_invoice
    lang = user.language or "fa"
    invoice = await generate_card_auto_invoice(
        session=session,
        telegram_id=user.telegram_id,
        base_amount=amount,
        store=store,
        ttl_minutes=60,
    )
    await session.commit()
    if cache and hasattr(cache, "invalidate_user"):
        await cache.invalidate_user(user.telegram_id)
    await state.clear()

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 استعلام وضعیت پرداخت", callback_data=f"wallet:c2c_check:{invoice.invoice_uuid}")
    kb.button(text=t(lang, "btn_cancel"), callback_data=f"wallet:c2c_cancel:{invoice.invoice_uuid}")
    kb.adjust(1)

    c2c_text = (
        "⚡️ <b>فاکتور پرداخت هوشمند کارت‌به‌کارت (تأیید آنی)</b>\n"
        "──────────────────\n"
        f"💰 مبلغ به تومان: <code>{invoice.exact_amount:,}</code> تومان\n"
        f"💰 مبلغ به ریال: <code>{invoice.exact_rial:,}</code> ریال\n\n"
        f"💳 شماره کارت مقصد:\n<code>{escape(store.card_number)}</code>\n"
        f"👤 بنام: <b>{escape(store.card_holder or 'مدیریت')}</b>\n"
        f"⏳ مهلت پرداخت: <b>1 ساعت</b>\n\n"
        "⚠️ <b>توجه مهم:</b> لطفاً هنگام واریز از همراه‌بانک، <u>دقیقاً همین رقم</u> را وارد نمایید و مبلغ را رند نکنید. بلافاصله پس از واریز، کیف پول شما به صورت اتوماتیک شارژ خواهد شد."
    )
    await render_menu(bot, user, user_repo, c2c_text, kb.as_markup())


@router.callback_query(F.data.startswith("wallet:amt:"))
async def topup_preset_amount(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
    state: FSMContext, cache: FastCache | None = None,
):
    try:
        amount = int(call.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await call.answer()
        return

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language
    store = await get_store_settings(session)

    max_amt = getattr(store, "topup_max_amount", 0) or MAX_TOPUP
    if amount < store.topup_min_amount or amount > max_amt:
        await call.answer(
            t(lang, "topup_amount_invalid", min=_fmt(store.topup_min_amount)),
            show_alert=True,
        )
        return

    data = await state.get_data()
    method = data.get("topup_method", "card")

    if method == "card" and store.card_require_phone_verification and not getattr(user, "phone_number", None):
        kb_phone = InlineKeyboardBuilder()
        kb_phone.button(text="📱 احراز هویت و ارسال شماره تماس", callback_data="user:verify_phone_prompt")
        kb_phone.button(text=t(lang, "btn_back"), callback_data="menu:wallet")
        kb_phone.adjust(1)
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
        await render_menu(bot, user, user_repo, notice_text, kb_phone.as_markup())
        await call.answer()
        return

    if method == "stars":
        if not (getattr(store, "stars_enabled", False) and getattr(store, "stars_rate_toman", 0) > 0):
            await call.answer("❌ پرداخت استارز موقتاً غیرفعال است.", show_alert=True)
            return
        await _create_and_render_stars_invoice(bot, user, user_repo, session, state, store, amount)
        await call.answer()
        return

    if method == "ton":
        if not (store.crypto_enabled and store.ton_wallet_address and store.ton_rate_toman > 0):
            await call.answer("❌ پرداخت کریپتو موقتاً غیرفعال است.", show_alert=True)
            return

        await _create_and_render_ton_invoice(bot, user, user_repo, session, state, store, amount)
        await call.answer()
        return

    if method == "trx":
        if not (getattr(store, "trx_enabled", False) and getattr(store, "trx_wallet_address", "") and store.trx_wallet_address.strip()):
            await call.answer("❌ پرداخت با ترون موقتاً غیرفعال است.", show_alert=True)
            return

        await _create_and_render_trx_invoice(bot, user, user_repo, session, state, store, amount)
        await call.answer()
        return

    if method == "pol":
        if not (getattr(store, "pol_enabled", False) and getattr(store, "pol_wallet_address", "") and store.pol_wallet_address.strip()):
            await call.answer("❌ پرداخت با پلیگان موقتاً غیرفعال است.", show_alert=True)
            return

        await _create_and_render_pol_invoice(bot, user, user_repo, session, state, store, amount)
        await call.answer()
        return

    if getattr(store, "card_auto_enabled", False):
        await _create_and_render_card_auto_invoice(
            bot, user, user_repo, session, state, store, amount, cache=cache
        )
        await call.answer()
        return

    if not (store.card_enabled and store.card_number and store.card_number.strip()):
        err_msg = "❌ پرداخت کارت به کارت موقتاً غیرفعال است." if lang == "fa" else "❌ Card payment is temporarily disabled."
        await call.answer(err_msg, show_alert=True)
        return

    from bot.db.repositories.card_auto_repo import CardAutoRepository, format_manual_card_block_message
    block_info = await CardAutoRepository(session).get_manual_card_block_info(user.telegram_id)
    if block_info:
        await call.answer(
            format_manual_card_block_message(block_info["remaining_seconds"], lang),
            show_alert=True,
        )
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
    state: FSMContext, cache: FastCache | None = None,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    store = await get_store_settings(session)

    await delete_message_silently(bot, message.chat.id, message.message_id)

    amount = _parse_amount(message.text)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="menu:wallet")

    max_amt = getattr(store, "topup_max_amount", 0) or MAX_TOPUP
    if amount is None or amount < store.topup_min_amount or amount > max_amt:
        await render_menu(
            bot, user, user_repo,
            t(lang, "topup_amount_invalid", min=_fmt(store.topup_min_amount)),
            kb.as_markup(),
        )
        return

    data = await state.get_data()
    method = data.get("topup_method", "card")

    if method == "card" and store.card_require_phone_verification and not getattr(user, "phone_number", None):
        kb_phone = InlineKeyboardBuilder()
        kb_phone.button(text="📱 احراز هویت و ارسال شماره تماس", callback_data="user:verify_phone_prompt")
        kb_phone.button(text=t(lang, "btn_back"), callback_data="menu:wallet")
        kb_phone.adjust(1)
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
        await render_menu(bot, user, user_repo, notice_text, kb_phone.as_markup())
        return

    if method == "stars":
        if not (getattr(store, "stars_enabled", False) and getattr(store, "stars_rate_toman", 0) > 0):
            await render_menu(bot, user, user_repo, "❌ پرداخت استارز موقتاً غیرفعال است.", kb.as_markup())
            return
        await _create_and_render_stars_invoice(bot, user, user_repo, session, state, store, amount)
        return

    if method == "ton":
        if not (store.crypto_enabled and store.ton_wallet_address and store.ton_rate_toman > 0):
            await render_menu(bot, user, user_repo, "❌ پرداخت کریپتو موقتاً غیرفعال است.", kb.as_markup())
            return

        await _create_and_render_ton_invoice(bot, user, user_repo, session, state, store, amount)
        return

    if method == "trx":
        if not (getattr(store, "trx_enabled", False) and getattr(store, "trx_wallet_address", "") and store.trx_wallet_address.strip()):
            await render_menu(bot, user, user_repo, "❌ پرداخت با ترون موقتاً غیرفعال است.", kb.as_markup())
            return

        await _create_and_render_trx_invoice(bot, user, user_repo, session, state, store, amount)
        return

    if method == "pol":
        if not (getattr(store, "pol_enabled", False) and getattr(store, "pol_wallet_address", "") and store.pol_wallet_address.strip()):
            await render_menu(bot, user, user_repo, "❌ پرداخت با پلیگان موقتاً غیرفعال است.", kb.as_markup())
            return

        await _create_and_render_pol_invoice(bot, user, user_repo, session, state, store, amount)
        return

    if getattr(store, "card_auto_enabled", False):
        await _create_and_render_card_auto_invoice(
            bot, user, user_repo, session, state, store, amount, cache=cache
        )
        return

    if not (store.card_enabled and store.card_number and store.card_number.strip()):
        err_msg = "❌ پرداخت کارت به کارت موقتاً غیرفعال است." if lang == "fa" else "❌ Card payment is temporarily disabled."
        await render_menu(bot, user, user_repo, err_msg, kb.as_markup())
        return

    from bot.db.repositories.card_auto_repo import CardAutoRepository, format_manual_card_block_message
    block_info = await CardAutoRepository(session).get_manual_card_block_info(user.telegram_id)
    if block_info:
        await render_menu(
            bot, user, user_repo,
            format_manual_card_block_message(block_info["remaining_seconds"], lang),
            kb.as_markup(),
        )
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
            "(شماره شما صرفاً برای تأیید بانکی ذخیره شده و کاملاً محرمانه است)"
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
    state: FSMContext, cache: FastCache | None = None,
):
    uuid_str = call.data.split(":", 2)[2]
    from bot.db.repositories.card_auto_repo import CardAutoRepository
    repo = CardAutoRepository(session)
    await repo.cancel_invoice(uuid_str, call.from_user.id)
    await session.commit()
    if cache and hasattr(cache, "invalidate_user"):
        await cache.invalidate_user(call.from_user.id)
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
    uuid_str = call.data.split(":", 2)[2]
    from bot.db.repositories.card_auto_repo import CardAutoRepository, format_manual_card_block_message
    repo = CardAutoRepository(session)
    block_info = await repo.get_manual_card_block_info(user.telegram_id)
    if block_info:
        await call.answer(
            format_manual_card_block_message(block_info["remaining_seconds"], lang),
            show_alert=True,
        )
        return

    invoice = await repo.get_invoice_by_uuid(uuid_str)
    if invoice and invoice.status == "paid":
        await call.answer("این فاکتور پیش‌تر به‌صورت خودکار توسط سیستم پیامک بانکی تأیید شده است.", show_alert=True)
        return

    amount = invoice.exact_amount if invoice else 0
    if not amount:
        data = await state.get_data()
        amount = data.get("amount", 0)

    store = await get_store_settings(session)
    await state.update_data(amount=amount, auto_invoice_uuid=uuid_str)
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
