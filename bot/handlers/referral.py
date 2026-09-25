"""Referral system handler: invite friends and earn free traffic."""
import logging
from urllib.parse import quote_plus

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, CopyTextButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.repositories.referral_repo import ReferralRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.menu import render_menu

logger = logging.getLogger(__name__)
router = Router(name="referral")

SEPARATOR = "─" * 18


@router.callback_query(F.data == "menu:referral")
async def referral_entry(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    session: AsyncSession,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"

    store_settings = await get_store_settings(session)
    reward_gb = store_settings.referral_reward_gb

    referral_repo = ReferralRepository(session)
    invites_count = await referral_repo.get_invites_count(user.telegram_id)
    total_gb = await referral_repo.get_total_gb_earned(user.telegram_id)

    bot_info = await bot.get_me()
    bot_username = bot_info.username or "bot"
    invite_link = f"https://t.me/{bot_username}?start=ref_{user.telegram_id}"
    share_text = "🚀 اینترنت آزاد، امن و پرسرعت با اکانت تست رایگان!\nجهت دریافت وارد ربات شوید:"
    share_url = f"https://t.me/share/url?url={invite_link}&text={quote_plus(share_text)}"

    lines = [
        t(lang, "referral_title"),
        SEPARATOR,
        t(lang, "referral_body", reward_gb=reward_gb, link=invite_link),
        SEPARATOR,
        t(lang, "referral_stats", count=invites_count, total_gb=total_gb),
    ]

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_share_link"), url=share_url)
    kb.button(text=t(lang, "btn_copy_sub_link"), copy_text=CopyTextButton(text=invite_link))
    kb.button(text=t(lang, "btn_back"), callback_data="menu:profile")
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    kb.adjust(1, 1, 2)

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())
    await call.answer()
