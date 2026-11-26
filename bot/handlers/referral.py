"""Referral system handler: invite friends and earn free traffic."""
import logging
from urllib.parse import quote_plus

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, CopyTextButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR
from bot.common.links import ref_link
from bot.db.repositories.referral_repo import ReferralRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.menu import render_menu

logger = logging.getLogger(__name__)
router = Router(name="referral")


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
    reward_gb = int(store_settings.referral_reward_gb or 0)
    commission_pct = int(getattr(store_settings, "referral_commission_percent", 0) or 0)
    renew_comm = bool(getattr(store_settings, "referral_renew_commission_enabled", False))

    referral_repo = ReferralRepository(session)
    invites_count = await referral_repo.get_invites_count(user.telegram_id)
    total_gb = await referral_repo.get_total_gb_earned(user.telegram_id)

    bot_info = await bot.get_me()
    bot_username = bot_info.username or "bot"
    invite_link = ref_link(bot_username, user.telegram_id)
    share_text = "🚀 اینترنت آزاد، امن و پرسرعت با اکانت تست رایگان!\nجهت دریافت وارد ربات شوید:"
    share_url = f"https://t.me/share/url?url={invite_link}&text={quote_plus(share_text)}"

    if commission_pct > 0:
        scope_fa = "بابت اولین خرید و تمدیدهای بعدی" if renew_comm else "بابت اولین خرید"
        scope_en = "on their first purchase and renewals" if renew_comm else "on their first purchase"
        if lang == "fa":
            reward_parts = []
            if reward_gb > 0:
                reward_parts.append(f"<b>{reward_gb} گیگابایت ترافیک هدیه</b>")
            reward_parts.append(f"<b>{commission_pct}% پورسانت نقدی</b> (واریز مستقیم به کیف پول)")
            body_text = (
                f"با ارسال لینک اختصاصی خود به دوستانتان، به ازای هر دعوت موفق ({scope_fa} دوستتان)، "
                f"{' و '.join(reward_parts)} دریافت کنید!\n\n"
                f"🔗 <b>لینک دعوت اختصاصی شما (برای کپی لمس کنید):</b>\n"
                f"<code>{invite_link}</code>"
            )
        else:
            reward_parts = []
            if reward_gb > 0:
                reward_parts.append(f"<b>{reward_gb} GB free traffic</b>")
            reward_parts.append(f"<b>{commission_pct}% cash commission</b> (credited directly to your wallet)")
            body_text = (
                f"Share your referral link with friends. Once a referred friend completes {scope_en}, "
                f"earn {' and '.join(reward_parts)}!\n\n"
                f"🔗 <b>Your Invite Link (tap to copy):</b>\n"
                f"<code>{invite_link}</code>"
            )
    else:
        body_text = t(lang, "referral_body", reward_gb=reward_gb, link=invite_link)

    lines = [
        t(lang, "referral_title"),
        SEPARATOR,
        body_text,
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
