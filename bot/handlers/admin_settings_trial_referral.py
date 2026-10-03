"""Admin Free Trial and Referral System Settings."""
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, is_admin, resolve_op
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.menu import render_menu

logger = logging.getLogger(__name__)
router = Router(name="admin_settings_trial_referral")


async def _render_trial_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    store_fn = resolve_op("get_store_settings", get_store_settings)
    render_menu_fn = resolve_op("render_menu", render_menu)

    lang = user.language or "fa"
    store = await store_fn(session)
    kb = InlineKeyboardBuilder()

    trial_badge = "✅" if store.trial_enabled else "❌"
    trial_btn_text = f"وضعیت {'✅' if store.trial_enabled else '❌'}"

    if lang == "fa":
        kb.button(text=f"⏳ زمان: {store.trial_duration_days} روز", callback_data="adm:set:trial_duration_days")
        kb.button(text=f"📊 حجم: {store.trial_traffic_gb} GB", callback_data="adm:set:trial_traffic_gb")
        kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
        kb.button(text=trial_btn_text, callback_data="adm:settings:toggle:trial_enabled")
    else:
        kb.button(text=f"📊 Traffic: {store.trial_traffic_gb} GB", callback_data="adm:set:trial_traffic_gb")
        kb.button(text=f"⏳ Days: {store.trial_duration_days}", callback_data="adm:set:trial_duration_days")
        kb.button(text=f"Status {'✅' if store.trial_enabled else '❌'}", callback_data="adm:settings:toggle:trial_enabled")
        kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")

    kb.adjust(2, 2)

    text = (
        f"🎁 <b>تنظیمات اکانت تست</b>\n{SEPARATOR}\n"
        f"🎁 <b>وضعیت تست :</b> {trial_badge}\n"
        f"📊 <b>حجم :</b> {store.trial_traffic_gb} GB\n"
        f"⏳ <b>زمان :</b> {store.trial_duration_days} روز\n\n"
        f"💡 جهت فعال یا غیرفعال‌سازی، روی دکمه وضعیت کلیک کنید. برای تغییر حجم یا زمان، دکمه مربوطه را انتخاب کنید."
    ) if lang == "fa" else (
        f"🎁 <b>Free Trial Settings</b>\n{SEPARATOR}\n"
        f"🎁 <b>Trial Status :</b> {trial_badge}\n"
        f"📊 <b>Traffic :</b> {store.trial_traffic_gb} GB\n"
        f"⏳ <b>Days :</b> {store.trial_duration_days} Days\n\n"
        f"Tap the status button to enable/disable, or tap traffic/days to edit."
    )
    await render_menu_fn(bot, user, user_repo, text, kb.as_markup())


async def _render_referral_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    store_fn = resolve_op("get_store_settings", get_store_settings)
    render_menu_fn = resolve_op("render_menu", render_menu)

    lang = user.language or "fa"
    store = await store_fn(session)
    kb = InlineKeyboardBuilder()

    ref_badge = "✅" if store.referral_enabled else "❌"
    ref_btn_text = f"وضعیت {'✅' if store.referral_enabled else '❌'}"

    if lang == "fa":
        kb.button(text=f"📊 حجم: {store.referral_reward_gb} GB", callback_data="adm:set:referral_reward_gb")
        kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
        kb.button(text=ref_btn_text, callback_data="adm:settings:toggle:referral_enabled")
    else:
        kb.button(text=f"📊 Traffic: {store.referral_reward_gb} GB", callback_data="adm:set:referral_reward_gb")
        kb.button(text=f"Status {'✅' if store.referral_enabled else '❌'}", callback_data="adm:settings:toggle:referral_enabled")
        kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")

    kb.adjust(1, 2)

    text = (
        f"🤝 <b>تنظیمات سیستم دعوت</b>\n{SEPARATOR}\n"
        f"🤝 <b>وضعیت سیستم دعوت :</b> {ref_badge}\n"
        f"🎁 <b>حجم :</b> {store.referral_reward_gb} GB\n\n"
        f"💡 جهت فعال یا غیرفعال‌سازی، روی دکمه وضعیت کلیک کنید. برای تغییر مقدار هدیه، دکمه حجم را انتخاب کنید."
    ) if lang == "fa" else (
        f"🤝 <b>Invite System Settings</b>\n{SEPARATOR}\n"
        f"🤝 <b>Invite Status :</b> {ref_badge}\n"
        f"🎁 <b>Traffic :</b> {store.referral_reward_gb} GB\n\n"
        f"Tap the status button to enable/disable, or tap traffic to edit."
    )
    await render_menu_fn(bot, user, user_repo, text, kb.as_markup())


@router.callback_query(F.data == "adm:settings:trial")
async def trial_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_trial_fn = resolve_op("_render_trial_settings", _render_trial_settings)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_trial_fn(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:settings:referral")
async def referral_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_ref_fn = resolve_op("_render_referral_settings", _render_referral_settings)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_ref_fn(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:settings:trial_ref")
async def trial_ref_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_trial_fn = resolve_op("_render_trial_settings", _render_trial_settings)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_trial_fn(bot, user, user_repo, session)
    await call.answer()
