"""Admin Wallet and Bank Card Payment Settings."""
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, is_admin
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.menu import render_menu

logger = logging.getLogger(__name__)
router = Router(name="admin_settings_wallet")

WALLET_SETTING_FIELDS = {
    "card_number": ("settings_card", False),
    "card_holder": ("settings_holder", False),
    "topup_min_amount": ("settings_min", True),
}

WALLET_SETTING_DESCRIPTIONS = {
    "fa": {
        "card_number": "شماره کارت بانکی جهت دریافت مبالغ شارژ کیف پول توسط کاربران.",
        "card_holder": "نام و نام خانوادگی صاحب کارت بانکی جهت نمایش به کاربران در زمان شارژ.",
        "topup_min_amount": "حداقل مبلغ مجاز برای هر بار شارژ کیف پول به تومان.",
    },
    "en": {
        "card_number": "Bank card number for wallet top-ups.",
        "card_holder": "Bank card holder name shown to users.",
        "topup_min_amount": "Minimum top-up amount in Toman.",
    },
}


async def _render_wallet_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    """Render dedicated wallet/card settings view."""
    lang = user.language or "fa"
    store = await get_store_settings(session)
    kb = InlineKeyboardBuilder()

    c_badge = "✅" if store.card_enabled else "❌"
    card_toggle_txt = f"💳 وضعیت درگاه کارت {c_badge}" if lang == "fa" else f"💳 Card Gateway {c_badge}"
    kb.button(text=card_toggle_txt, callback_data="adm:settings:toggle:card_enabled")
    kb.button(text=f"💳 {t(lang, 'settings_card')}", callback_data="adm:set:card_number")
    kb.button(text=f"👤 {t(lang, 'settings_holder')}", callback_data="adm:set:card_holder")
    kb.button(text=f"💰 {t(lang, 'settings_min')}", callback_data="adm:set:topup_min_amount")
    kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    kb.adjust(1, 2, 1, 1)

    card_str = store.card_number or "—"
    holder_str = store.card_holder or "—"
    min_str = f"{fmt(store.topup_min_amount)} تومان" if store.topup_min_amount else "—"

    lines = [
        f"💳 <b>{t(lang, 'settings_wallet_title') if lang != 'fa' else 'تنظیمات کارت و کیف پول'}</b>\n{SEPARATOR}",
        f"⚡️ وضعیت درگاه کارت : <b>{c_badge}</b>",
        f"💳 شماره کارت : <code>{escape(card_str)}</code>",
        f"👤 صاحب حساب : <b>{escape(holder_str)}</b>",
        f"💰 حداقل واریز : <b>{min_str}</b>",
    ] if lang == "fa" else [
        f"💳 <b>Wallet & Card Settings</b>\n{SEPARATOR}",
        f"⚡️ Card Gateway Status : <b>{c_badge}</b>",
        f"💳 Card Number : <code>{escape(card_str)}</code>",
        f"👤 Card Holder : <b>{escape(holder_str)}</b>",
        f"💰 Minimum Top-up : <b>{min_str}</b>",
    ]

    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "adm:settings:wallet")
async def wallet_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_wallet_settings(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:settings:toggle:card_enabled")
async def toggle_card_enabled(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
    state: FSMContext | None = None,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    if state:
        await state.clear()

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    store = await get_store_settings(session)

    new_val = not store.card_enabled
    new_str = "1" if new_val else "0"

    await AppSettingRepository(session).set("card_enabled", new_str)
    await AdminLogRepository(session).log(
        call.from_user.id, "setting", detail=f"card_enabled={new_str}"
    )

    from bot.handlers.admin_settings_store import _render_settings
    await _render_settings(bot, user, user_repo, session)

    label = "درگاه کارت به کارت" if lang == "fa" else "Card Payment Gateway"
    status_text = ("فعال شد" if new_val else "غیرفعال شد") if lang == "fa" else ("Enabled" if new_val else "Disabled")
    await call.answer(f"✅ {label} {status_text}")
