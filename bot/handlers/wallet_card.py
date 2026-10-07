"""Wallet Card-to-Card top-up receipt upload and admin verification."""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import admin_thread_kwargs, fmt
from bot.config import get_settings
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.menu import delete_message_silently, render_menu
from bot.services.topups import decide_topup
from bot.states.wallet import TopupStates

logger = logging.getLogger(__name__)
router = Router(name="wallet_card")

MAX_TOPUP = 500_000_000  # sanity cap, Toman
MAX_PENDING_TOPUPS = 3
MAX_RECEIPT_BYTES = 10 * 1024 * 1024  # 10 MB
_fmt = fmt


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

    import hashlib as _hl

    receipt_hash: str | None = None
    receipt_photo_id = None
    if message.photo:
        biggest = message.photo[-1]
        receipt_hash = f"photo:{biggest.file_unique_id}"
        receipt_photo_id = biggest.file_id
    elif message.document:
        receipt_hash = f"doc:{message.document.file_unique_id}"
        if (message.document.mime_type or "").startswith("image/"):
            receipt_photo_id = message.document.file_id
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

    topup = await wallet_repo.create_topup(
        user.telegram_id, amount, receipt_hash, receipt_photo_id=receipt_photo_id
    )

    # receipt + info with approve/reject buttons → admin chat
    tg_username = f"@{message.from_user.username}" if message.from_user.username else "—"
    kb = InlineKeyboardBuilder()
    kb.button(text=t("fa", "btn_approve"), callback_data=f"topup:ok:{topup.id}")
    kb.button(text=t("fa", "btn_reject"), callback_data=f"topup:no:{topup.id}")
    kb.adjust(2)

    store = await get_store_settings(session)
    thread_kwargs = admin_thread_kwargs(store, settings, "topups")
    delivered = False
    admin_req_text = t(
        "fa", "admin_topup_request",
        id=topup.id,
        name=escape(message.from_user.full_name),
        tid=user.telegram_id,
        username=escape(tg_username),
        amount=_fmt(amount),
    )

    async def _send_admin_receipt(target_chat_id: int | str, **extra_kwargs):
        if message.photo:
            return await bot.send_photo(
                chat_id=target_chat_id,
                photo=message.photo[-1].file_id,
                caption=admin_req_text,
                reply_markup=kb.as_markup(),
                **extra_kwargs,
            )
        elif message.document:
            return await bot.send_document(
                chat_id=target_chat_id,
                document=message.document.file_id,
                caption=admin_req_text,
                reply_markup=kb.as_markup(),
                **extra_kwargs,
            )
        else:
            return await bot.send_message(
                chat_id=target_chat_id,
                text=admin_req_text,
                reply_markup=kb.as_markup(),
                **extra_kwargs,
            )

    # 1. Primary delivery to configured ADMIN_CHAT_ID (with topic if set)
    try:
        msg_obj = await _send_admin_receipt(settings.ADMIN_CHAT_ID, **thread_kwargs)
        delivered = True
        topup.admin_message_id = msg_obj.message_id
        await session.commit()
    except TelegramAPIError as exc:
        logger.warning(
            "Failed to deliver top-up %s to admin chat %s (%s). Attempting fallback to admins...",
            topup.id, settings.ADMIN_CHAT_ID, exc,
        )

    # 2. Fallback: if group delivery failed, deliver to individual admin private chats
    if not delivered and settings.ADMIN_IDS:
        for admin_id in settings.ADMIN_IDS:
            try:
                msg_obj = await _send_admin_receipt(admin_id)
                delivered = True
                if not topup.admin_message_id:
                    topup.admin_message_id = msg_obj.message_id
                    await session.commit()
            except Exception as admin_exc:
                logger.warning(
                    "Fallback delivery of top-up %s to admin %s failed: %s",
                    topup.id, admin_id, admin_exc,
                )

    await delete_message_silently(bot, message.chat.id, message.message_id)
    await state.clear()

    if not delivered:
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
        try:
            if call.message.photo or call.message.document:
                base_text = call.message.caption or ""
                new_caption = f"{base_text}\n\n{note}"
                await call.message.edit_caption(caption=new_caption, reply_markup=None)
            else:
                new_text = f"{call.message.html_text}\n\n{note}"
                await call.message.edit_text(new_text, reply_markup=None)
        except TelegramAPIError:
            pass
    await call.answer(note)
