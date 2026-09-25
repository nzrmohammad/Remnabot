"""Support section.

User flow:
1. «پشتیبانی» in the main menu → bot asks for the question.
2. Whatever the user sends (text / photo / file) is copied to the admin
   chat, with an info header attached as a reply to it.
3. The admin replies to that message → the bot routes the reply back to
   the user's chat as a «پاسخ پشتیبانی» message.

The mapping admin-chat-message-id → telegram-id is stored in the
`support_messages` table, so replies keep working after restarts.
"""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import get_settings
from bot.db.repositories.support_repo import SupportMessageRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.menu import delete_message_silently, render_menu
from bot.states.support import SupportStates

logger = logging.getLogger(__name__)
router = Router(name="support")


@router.callback_query(F.data == "menu:support")
async def support_entry(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    await state.clear()
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    await state.set_state(SupportStates.waiting_message)
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_cancel"), callback_data="nav:main_menu")
    kb.adjust(1)

    await render_menu(bot, user, user_repo, t(lang, "support_prompt"), kb.as_markup())
    await call.answer()


@router.message(SupportStates.waiting_message)
async def support_forward(
    message: Message, bot: Bot, user_repo: UserRepository, state: FSMContext,
):
    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    settings = get_settings()

    sent_to_admin = False
    from bot.services.app_settings import get_store_settings
    store = await get_store_settings(user_repo.session)
    topic_id = store.topic_support if store.topic_support is not None else settings.ADMIN_TOPIC_SUPPORT
    thread_kwargs = {"message_thread_id": topic_id} if topic_id else {}
    try:
        # 1) copy the raw content so nothing is lost (media, captions, ...)
        content = await bot.copy_message(
            chat_id=settings.ADMIN_CHAT_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            **thread_kwargs,
        )
        # 2) header attached as a reply → replying to either one works
        tg_username = f"@{message.from_user.username}" if message.from_user.username else "—"
        target = await UserRepository(user_repo.session).get_by_telegram_id(user.telegram_id)
        header_lang = (target.language if target else None) or lang or "fa"
        header = await bot.send_message(
            settings.ADMIN_CHAT_ID,
            t(
                header_lang, "support_admin_header",
                name=escape(message.from_user.full_name),
                tid=user.telegram_id,
                username=escape(tg_username),
            ),
            reply_parameters={"message_id": content.message_id},
            **thread_kwargs,
        )
        repo = SupportMessageRepository(user_repo.session)
        await repo.map_message(content.message_id, user.telegram_id)
        await repo.map_message(header.message_id, user.telegram_id)
        sent_to_admin = True
    except Exception:
        logger.exception("failed to deliver support message to admin chat")

    await delete_message_silently(bot, message.chat.id, message.message_id)
    await state.clear()

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    kb.adjust(1)

    key = "support_sent" if sent_to_admin else "support_failed"
    await render_menu(bot, user, user_repo, t(lang, key), kb.as_markup())


# --------------------------------------------------------------------- #
# Admin side: reply to a support message → routed back to the user
# --------------------------------------------------------------------- #
@router.message(F.reply_to_message)
async def admin_support_reply(
    message: Message, bot: Bot, session, state: FSMContext,
):
    """Route admin replies (text AND media) back to the user.

    Only messages inside ADMIN_CHAT_ID from an admin are routed.
    Anything else is ignored (never delete user messages here —
    the menu-cleanup handler owns that job and only for known states).
    """
    from aiogram.exceptions import TelegramAPIError as _TGError

    settings = get_settings()
    if message.chat.id != settings.ADMIN_CHAT_ID:
        return
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    replied_id = message.reply_to_message.message_id
    repo = SupportMessageRepository(session)
    telegram_id = await repo.get_user(replied_id)
    if telegram_id is None:
        return  # not a support message (purchase log, receipt, ...)

    target = await UserRepository(session).get_by_telegram_id(telegram_id)
    user_lang = (target.language if target else None) or "fa"
    header = t(user_lang, "support_reply_header")

    try:
        if message.text:
            await bot.send_message(telegram_id, f"{header}\n\n{escape(message.text)}")
        elif message.photo or message.video or message.document or message.voice:
            await bot.copy_message(
                chat_id=telegram_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            # Header as a follow-up so the user knows it's from support.
            try:
                await bot.send_message(telegram_id, header)
            except _TGError:
                pass
        else:
            await bot.copy_message(
                chat_id=telegram_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
    except Exception:
        logger.exception("could not deliver support reply to %s", telegram_id)
        return

    # GC: one support thread can create many rows — keep the table bounded.
    try:
        await repo.prune_old(limit=5000)
    except Exception:
        pass
