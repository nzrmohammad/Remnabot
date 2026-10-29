"""Admin Top-up Approvals and Rejections."""
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, is_admin
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.menu import render_menu
from bot.services.topups import decide_topup

logger = logging.getLogger(__name__)
router = Router(name="admin_topups")

_is_admin = is_admin


async def _render_topups(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    lang = user.language or "fa"
    pending = await WalletRepository(session).list_pending_topups()

    lines = [t(lang, "topups_title"), SEPARATOR]
    if not pending:
        lines.append(t(lang, "topups_empty"))
    else:
        for tp in pending:
            lines.append(
                f"#{tp.id} — <code>{tp.telegram_id}</code> — "
                f"<b>{fmt(tp.amount)}</b> {t(lang, 'svc_currency')}"
            )

    kb = InlineKeyboardBuilder()
    for tp in pending:
        kb.button(text=t(lang, "btn_approve"), callback_data=f"adm:topup:ok:{tp.id}")
        kb.button(text=t(lang, "btn_reject"), callback_data=f"adm:topup:no:{tp.id}")
        kb.adjust(2)
    kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "adm:topups")
async def topups_list(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_topups(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data.startswith("adm:topup:"))
async def topup_decide_from_panel(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    try:
        _, _, action, topup_id_s = call.data.split(":")
        topup_id = int(topup_id_s)
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    changed, note = await decide_topup(
        bot, session, int(topup_id), approved=(action == "ok"),
        admin_id=call.from_user.id,
    )
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    if changed:
        await _render_topups(bot, user, user_repo, session)
    await call.answer(note, show_alert=not changed)


@router.message(F.text)
async def handle_manual_bank_sms(
    message: Message, bot: Bot, session: AsyncSession,
) -> None:
    """Process bank deposit SMS pasted directly by an admin in a dedicated topic or chat."""
    if not message.text or not message.from_user:
        return

    if not _is_admin(message.from_user.id):
        return

    from bot.config import get_settings
    from bot.services.app_settings import get_store_settings
    from bot.services.payment.card_auto_service import process_incoming_sms

    cfg = get_settings()
    store = await get_store_settings(session)
    admin_chat_id = getattr(cfg, "ADMIN_CHAT_ID", None)

    target_topic = store.topic_sms_manual or getattr(cfg, "ADMIN_TOPIC_SMS_MANUAL", None)
    msg_topic = getattr(message, "message_thread_id", None)

    is_target_topic = bool(
        target_topic
        and msg_topic
        and int(msg_topic) == int(target_topic)
        and (message.chat.id == admin_chat_id or message.chat.type in ("group", "supergroup"))
    )

    raw_text = message.text.strip()
    is_sms_command = raw_text.startswith("/sms")
    if is_sms_command:
        raw_text = raw_text[4:].strip()

    bank_keywords = ("واریز", "انتقال", "مانده", "بانک", "بانك", "حساب", "شبا", "پایا", "ساتنا", "پل")
    is_bank_like = any(kw in raw_text for kw in bank_keywords) and any(c.isdigit() for c in raw_text)

    if not (is_target_topic or is_sms_command or (message.chat.type == "private" and is_bank_like)):
        return

    if not raw_text:
        await message.reply("⚠️ لطفاً متن پیامک واریز بانکی را ارسال فرمایید.")
        return

    sender_label = f"ADMIN_{message.from_user.id}"
    res = await process_incoming_sms(
        session=session,
        bot=bot,
        settings=cfg,
        store=store,
        sender=sender_label,
        raw_message=raw_text,
    )
    await session.commit()

    action = res.get("action")
    if action == "ignored_non_deposit":
        await message.reply(
            "ℹ️ <b>پیامک به عنوان واریز بانکی شناسایی نشد.</b>\n"
            "الگوی واریز یا مبلغ مشخصی در متن یافت نشد. لطفاً متن کامل پیامک دریافتی از بانک را بدون تغییر پیست نمایید.",
            parse_mode="HTML",
        )
    elif action == "unmatched_deposit":
        amt = res.get("amount_toman", 0)
        bank = res.get("bank") or "نامشخص"
        await message.reply(
            "⚠️ <b>پیامک واریز خوانده شد، اما فاکتور معلق منطبقی یافت نشد!</b>\n"
            "──────────────────\n"
            f"💰 مبلغ تشخیص‌داده‌شده: <b>{amt:,} تومان</b>\n"
            f"🏦 بانک: <b>{bank}</b>\n\n"
            "💡 <i>علت: کاربر هنوز فاکتوری با این رقم ثبت نکرده یا مهلت ۱ ساعته پرداخت سپری شده است.</i>",
            parse_mode="HTML",
        )
    else:
        await message.reply(
            "✅ <b>شارژ خودکار با موفقیت انجام شد!</b>\n"
            "──────────────────\n"
            f"👤 شناسه کاربر: <code>{res.get('user_id')}</code>\n"
            f"💰 مبلغ شارژ: <b>{res.get('amount_toman', 0):,} تومان</b>\n"
            f"🏦 بانک: <b>{res.get('bank') or 'کارت بانکی'}</b>\n"
            f"🆔 شناسه فاکتور: <code>#{res.get('invoice_uuid')}</code>\n\n"
            "🎉 حساب کاربر شارژ شد و پیام تأیید نیز برای وی ارسال گردید.",
            parse_mode="HTML",
        )

