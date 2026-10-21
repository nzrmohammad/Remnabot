"""Admin store settings dashboard and toggle view handlers."""
import logging
from html import escape

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, is_admin
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.user_repo import UserRepository
from bot.handlers.admin_settings_common import render_menu
from bot.handlers.admin_settings_topics import get_admin_group_title
from bot.handlers.admin_settings_trial_referral import (
    _render_referral_settings,
    _render_trial_settings,
)
from bot.locales.texts import t
from bot.services.app_settings import (
    get_store_settings,
    is_maintenance,
    set_maintenance,
)
from bot.services.formatting import ltr_frag

logger = logging.getLogger(__name__)


async def _render_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    lang = user.language or "fa"
    store = await get_store_settings(session)
    maint_on = await is_maintenance(session)
    kb = InlineKeyboardBuilder()

    has_contact = bool(
        store.support_contact
        and store.support_contact.strip()
        and store.support_contact.strip() not in ("—", "-")
    )

    if lang == "fa":
        # Persian RTL: first added is LEFT, second added is RIGHT
        # Row 1: Right = Maintenance, Left = Direct Support
        if has_contact:
            sup_toggle_text = f"📞 پشتیبانی مستقیم {'✅' if store.support_direct_enabled else '❌'}"
        else:
            sup_toggle_text = "📞 پشتیبانی مستقیم ❌"
        kb.button(text=sup_toggle_text, callback_data="adm:settings:toggle:support_direct_enabled")
        kb.button(text=f"🚧 حالت تعمیر {'✅' if maint_on else '❌'}", callback_data="adm:maint")

        # Row 2: Right = Name, Left = Card Number
        kb.button(text=f"💳 {t(lang, 'settings_card')}", callback_data="adm:set:card_number")
        kb.button(text=f"👤 {t(lang, 'settings_holder')}", callback_data="adm:set:card_holder")

        # Row 3: Right = Min Topup, Left = Support Contact
        kb.button(text=f"📞 {t(lang, 'settings_support_contact')}", callback_data="adm:set:support_contact")
        kb.button(text=f"💰 {t(lang, 'settings_min')}", callback_data="adm:set:topup_min_amount")

        # Row 4: Right = Crypto, Left = Invite
        kb.button(text="🤝 دعوت", callback_data="adm:settings:referral")
        kb.button(text="💎 کریپتو", callback_data="adm:settings:crypto")

        # Row 5: Right = Remind Days, Left = Grace Days
        kb.button(text=f"⏳ {t(lang, 'settings_grace_days')}", callback_data="adm:set:expiry_grace_days")
        kb.button(text=f"🔔 {t(lang, 'settings_remind_days')}", callback_data="adm:set:expiry_remind_days")

        # Row 6: Right = Test, Left = Topics
        kb.button(text=t(lang, "settings_topics_btn"), callback_data="adm:settings:topics")
        kb.button(text="🎁 تست", callback_data="adm:settings:trial")

        # Row 7: Right = Squad, Left = Back
        kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")
        kb.button(text=f"🧩 {t(lang, 'settings_squad')}", callback_data="adm:set:default_squad_uuid")
    else:
        # English LTR
        if has_contact:
            sup_toggle_text = f"📞 Direct Support {'✅' if store.support_direct_enabled else '❌'}"
        else:
            sup_toggle_text = "📞 Direct Support ❌"
        kb.button(text=f"🚧 Maintenance {'✅' if maint_on else '❌'}", callback_data="adm:maint")
        kb.button(text=sup_toggle_text, callback_data="adm:settings:toggle:support_direct_enabled")

        kb.button(text=f"💳 {t(lang, 'settings_card')}", callback_data="adm:set:card_number")
        kb.button(text=f"👤 {t(lang, 'settings_holder')}", callback_data="adm:set:card_holder")

        kb.button(text=f"💰 {t(lang, 'settings_min')}", callback_data="adm:set:topup_min_amount")
        kb.button(text=f"📞 {t(lang, 'settings_support_contact')}", callback_data="adm:set:support_contact")

        kb.button(text="💎 Crypto", callback_data="adm:settings:crypto")
        kb.button(text="🤝 Invite", callback_data="adm:settings:referral")

        kb.button(text=f"⏳ {t(lang, 'settings_grace_days')}", callback_data="adm:set:expiry_grace_days")
        kb.button(text=f"🔔 {t(lang, 'settings_remind_days')}", callback_data="adm:set:expiry_remind_days")

        kb.button(text="🎁 Trial", callback_data="adm:settings:trial")
        kb.button(text=t(lang, "settings_topics_btn"), callback_data="adm:settings:topics")

        kb.button(text=f"🧩 {t(lang, 'settings_squad')}", callback_data="adm:set:default_squad_uuid")
        kb.button(text=t(lang, "btn_back"), callback_data="menu:admin")

    kb.adjust(2, 2, 2, 2, 2, 2, 2)

    squad_show = store.default_squad_uuid or "—"

    if has_contact:
        sup_status = "✅" if store.support_direct_enabled else "❌"
        support_block = (
            f"📞 پشتیبانی مستقیم : {sup_status}\n"
            f"📞 {t(lang, 'settings_support_contact')} : \u200e{escape(store.support_contact)}"
        )
    else:
        support_block = f"📞 {t(lang, 'settings_support_contact')} : —"

    trial_desc = (
        f"✅\n   حجم : {ltr_frag(f'{store.trial_traffic_gb} GB')}\n   زمان : {store.trial_duration_days} روز"
        if store.trial_enabled
        else "❌"
    )

    ref_desc = (
        f"✅\n   حجم : {ltr_frag(f'{store.referral_reward_gb} GB')}"
        if store.referral_enabled
        else "❌"
    )

    grp_title = await get_admin_group_title(bot)
    topics_header = f"🎧 تاپیک‌ها ({escape(grp_title)}) :" if grp_title else "🎧 تاپیک‌ها :"
    topics_header_en = f"🎧 Topics ({escape(grp_title)}) :" if grp_title else "🎧 Topics :"

    t_topups = f"شارژ ({store.topic_topups}) : Topups" if store.topic_topups is not None else "شارژ : — (Topups)"
    t_orders = f"سفارش ({store.topic_orders}) : Orders" if store.topic_orders is not None else "سفارش : — (Orders)"
    t_support = f"پشتیبانی ({store.topic_support}) : Support" if store.topic_support is not None else "پشتیبانی : — (Support)"
    t_alerts = f"هشدار ({store.topic_alerts}) : Alerts" if store.topic_alerts is not None else "هشدار : — (Alerts)"
    t_crypto = f"کریپتو ({store.topic_crypto}) : Crypto" if store.topic_crypto is not None else "کریپتو : — (Crypto)"
    t_errors = f"ارور ({store.topic_errors}) : Errors" if store.topic_errors is not None else "ارور : — (Errors)"

    crypto_status_fa = "✅" if store.crypto_enabled else "❌"
    rate_fa = f"{store.ton_rate_toman:,} تومان" if store.ton_rate_toman > 0 else "—"

    maint_badge = "✅" if maint_on else "❌"

    if lang == "fa":
        lines = [
            f"{t(lang, 'store_settings_title')}\n{SEPARATOR}",
            f"💳 {t(lang, 'settings_card')} : <code>{escape(store.card_number or '—')}</code>{' (غیرفعال)' if not store.card_enabled else ''}",
            f"👤 {t(lang, 'settings_holder')} : {escape(store.card_holder or '—')}",
            f"💰 {t(lang, 'settings_min')} : {fmt(store.topup_min_amount)} {t(lang, 'svc_currency')}",
            "",
            support_block,
            "",
            f"🎁 سرویس تست : {trial_desc}",
            f"🤝 سیستم دعوت : {ref_desc}",
            f"💎 پرداخت کریپتو : {crypto_status_fa}",
            f"   قیمت تبدیل : {rate_fa}",
            "",
            f"⏳ {t(lang, 'settings_grace_days')} : {store.expiry_grace_days} روز",
            f"🔔 {t(lang, 'settings_remind_days')} : {escape(store.expiry_remind_days)}",
            f"🧩 {t(lang, 'settings_squad')} : {escape(squad_show[:24])}",
            "",
            topics_header,
            f"   {t_topups}",
            f"   {t_orders}",
            f"   {t_support}",
            f"   {t_alerts}",
            f"   {t_crypto}",
            f"   {t_errors}",
            "",
            f"🚧 {t(lang, 'settings_maintenance')} : {maint_badge}",
        ]
    else:
        trial_en = (
            f"✅\n   Traffic : {store.trial_traffic_gb} GB\n   Duration : {store.trial_duration_days}d"
            if store.trial_enabled
            else "❌"
        )
        ref_en = (
            f"✅\n   Traffic : {store.referral_reward_gb} GB"
            if store.referral_enabled
            else "❌"
        )
        sup_status_en = "✅" if store.support_direct_enabled else "❌"
        if has_contact:
            sup_block_en = (
                f"📞 Direct Support : {sup_status_en}\n"
                f"📞 {t(lang, 'settings_support_contact')} : \u200e{escape(store.support_contact)}"
            )
        else:
            sup_block_en = f"📞 {t(lang, 'settings_support_contact')} : —"

        topup_en = f"   Top-ups ({store.topic_topups}) : Topups" if store.topic_topups is not None else "   Top-ups : — (Topups)"
        orders_en = f"   Orders ({store.topic_orders}) : Orders" if store.topic_orders is not None else "   Orders : — (Orders)"
        support_en = f"   Support ({store.topic_support}) : Support" if store.topic_support is not None else "   Support : — (Support)"
        alerts_en = f"   Alerts ({store.topic_alerts}) : Alerts" if store.topic_alerts is not None else "   Alerts : — (Alerts)"
        crypto_en = f"   Crypto ({store.topic_crypto}) : Crypto" if store.topic_crypto is not None else "   Crypto : — (Crypto)"
        errors_en = f"   Errors ({store.topic_errors}) : Errors" if store.topic_errors is not None else "   Errors : — (Errors)"

        crypto_status_en = "✅" if store.crypto_enabled else "❌"
        rate_en = f"{store.ton_rate_toman:,} Toman" if store.ton_rate_toman > 0 else "—"

        lines = [
            f"{t(lang, 'store_settings_title')}\n{SEPARATOR}",
            f"💳 {t(lang, 'settings_card')} : <code>{escape(store.card_number or '—')}</code>{' (Disabled)' if not store.card_enabled else ''}",
            f"👤 {t(lang, 'settings_holder')} : {escape(store.card_holder or '—')}",
            f"💰 {t(lang, 'settings_min')} : <b>{fmt(store.topup_min_amount)}</b> {t(lang, 'svc_currency')}",
            "",
            sup_block_en,
            "",
            f"🎁 Free Trial : {trial_en}",
            f"🤝 Referral : {ref_en}",
            f"💎 Crypto Payment : {crypto_status_en}",
            f"   Exchange Rate : {rate_en}",
            "",
            f"⏳ {t(lang, 'settings_grace_days')} : {store.expiry_grace_days}d",
            f"🔔 {t(lang, 'settings_remind_days')} : {escape(store.expiry_remind_days)}",
            f"🧩 {t(lang, 'settings_squad')} : {escape(squad_show[:24])}",
            "",
            topics_header_en,
            topup_en,
            orders_en,
            support_en,
            alerts_en,
            crypto_en,
            errors_en,
            "",
            f"🚧 {t(lang, 'settings_maintenance')} : {maint_badge}",
        ]
    await render_menu(bot, user, user_repo, "\n".join(lines), kb.as_markup())


async def store_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_settings(bot, user, user_repo, session)
    await call.answer()


async def setting_toggle_boolean(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
    state: FSMContext | None = None,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    field = call.data.rsplit(":", 1)[1]
    if field not in ("trial_enabled", "referral_enabled", "support_direct_enabled", "card_enabled"):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    if state:
        await state.clear()

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    store = await get_store_settings(session)

    if field == "support_direct_enabled":
        has_contact = bool(
            store.support_contact
            and store.support_contact.strip()
            and store.support_contact.strip() not in ("—", "-")
        )
        if not has_contact:
            alert_text = (
                "⚠️ ابتدا باید آیدی پشتیبانی را در تنظیمات وارد کنید."
                if lang == "fa"
                else "⚠️ Please set the support contact ID first."
            )
            await call.answer(alert_text, show_alert=True)
            return

    curr_val = getattr(store, field, False)
    new_val = not curr_val
    new_str = "1" if new_val else "0"

    await AppSettingRepository(session).set(field, new_str)
    await AdminLogRepository(session).log(
        call.from_user.id, "setting", detail=f"{field}={new_str}"
    )

    if field == "trial_enabled":
        await _render_trial_settings(bot, user, user_repo, session)
        label = "سرویس تست" if lang == "fa" else "Free Trial"
    elif field == "referral_enabled":
        await _render_referral_settings(bot, user, user_repo, session)
        label = "سیستم دعوت" if lang == "fa" else "Referral"
    elif field == "card_enabled":
        await _render_settings(bot, user, user_repo, session)
        label = "درگاه کارت به کارت" if lang == "fa" else "Card Payment Gateway"
    else:
        await _render_settings(bot, user, user_repo, session)
        label = "پشتیبانی مستقیم" if lang == "fa" else "Direct Support"
    status_text = (
        ("فعال شد" if new_val else "غیرفعال شد")
        if lang == "fa"
        else ("Enabled" if new_val else "Disabled")
    )
    await call.answer(f"✅ {label} {status_text}")


async def maintenance_toggle(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return

    enabled = not await is_maintenance(session)
    await set_maintenance(session, enabled)
    await AdminLogRepository(session).log(
        call.from_user.id, "maintenance",
        detail="on" if enabled else "off",
    )
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_settings(bot, user, user_repo, session)
    await call.answer(
        t(user.language or "fa", "maint_toggled", state=t(
            user.language or "fa", "toggle_on" if enabled else "toggle_off")),
    )
