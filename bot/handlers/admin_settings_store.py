"""Admin Store Core Settings, Reminders, Grace Period, and FSM Wizard."""
import logging
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, is_admin, parse_int, resolve_op
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.user_repo import UserRepository
from bot.handlers.admin_settings_crypto import _render_crypto_settings
from bot.handlers.admin_settings_topics import (
    _render_topics_settings,
    get_admin_group_title,
)
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
from bot.services.menu import delete_message_silently, render_menu
from bot.services.remnawave import RemnawaveClient
from bot.states.admin import SettingsStates

logger = logging.getLogger(__name__)
router = Router(name="admin_settings_store")

_parse_int = parse_int


def _is_admin(user_id: int) -> bool:
    import bot.handlers.admin_ops as _ops
    fn = getattr(_ops, "_is_admin", is_admin)
    return fn(user_id)


# settings field key -> (text key, is_numeric)
SETTING_FIELDS = {
    "card_number": ("settings_card", False),
    "card_holder": ("settings_holder", False),
    "topup_min_amount": ("settings_min", True),
    "default_squad_uuid": ("settings_squad", False),
    "expiry_grace_days": ("settings_grace_days", True),
    "expiry_remind_days": ("settings_remind_days", False),
    "topic_topups": ("settings_topic_topups", True),
    "topic_orders": ("settings_topic_orders", True),
    "topic_support": ("settings_topic_support", True),
    "topic_alerts": ("settings_topic_alerts", True),
    "support_contact": ("settings_support_contact", False),
    "trial_enabled": ("settings_trial_enabled", True),
    "trial_traffic_gb": ("settings_trial_traffic", True),
    "trial_duration_days": ("settings_trial_duration", True),
    "referral_enabled": ("settings_referral_enabled", True),
    "referral_reward_gb": ("settings_referral_reward", True),
    "topic_crypto": ("settings_topic_crypto", True),
    "topic_errors": ("settings_topic_errors", True),
    "ton_wallet_address": ("settings_ton_wallet", False),
    "ton_rate_toman": ("settings_ton_rate", True),
    "usdt_rate_toman": ("settings_usdt_rate", True),
}

SETTING_DESCRIPTIONS = {
    "fa": {
        "card_number": "شماره کارت بانکی جهت دریافت مبالغ شارژ کیف پول توسط کاربران.",
        "card_holder": "نام و نام خانوادگی صاحب کارت بانکی جهت نمایش به کاربران در زمان شارژ.",
        "topup_min_amount": "حداقل مبلغ مجاز برای هر بار شارژ کیف پول به تومان.",
        "support_contact": "آیدی یا لینک پشتیبانی که در بخش ارتباط با پشتیبانی نمایش داده می‌شود.",
        "expiry_grace_days": "تعداد روزهایی که پس از پایان اشتراک، اکانت در پنل حفظ می‌شود تا کاربر فرصت تمدید داشته باشد.",
        "expiry_remind_days": "روزهای مانده به انقضا (مانند 3,1) که پیام هشدار تمدید برای کاربر ارسال می‌شود.",
        "topic_topups": "شناسه تاپیک تایید شارژها در سوپرگروه مدیریت تلگرام جهت ارسال فیش‌های کاربران.",
        "topic_orders": "شناسه تاپیک سفارشات در سوپرگروه مدیریت تلگرام جهت ارسال لاگ خرید بسته‌ها.",
        "topic_support": "شناسه تاپیک پشتیبانی در سوپرگروه مدیریت تلگرام جهت فوروارد پیام‌های کاربران.",
        "topic_alerts": "شناسه تاپیک هشدارهای سیستم و ارسال خودکار فایل پشتیبان دیتابیس در سوپرگروه مدیریت.",
        "topic_crypto": "شناسه تاپیک کریپتو در سوپرگروه مدیریت جهت ارسال استعلام نرخ نوبیتکس و لاگ پرداخت‌های تون.",
        "topic_errors": "شناسه تاپیک لاگ‌های خطا و ارورهای سیستم در سوپرگروه مدیریت تلگرام.",
        "ton_wallet_address": "آدرس عمومی کیف پول تون (مانند UQ... یا EQ...) جهت دریافت وجه از کاربران.",
        "ton_rate_toman": "نرخ تبدیل هر یک تون به تومان جهت صدور فاکتور شارژ کیف پول.",
        "usdt_rate_toman": "نرخ هر تتر (USDT) به تومان جهت تبدیل قیمت دلاری تون در صرافی‌های جهانی.",
        "trial_enabled": "فعال (1) یا غیرفعال (0) بودن امکان دریافت اکانت تست رایگان توسط کاربران جدید.",
        "trial_traffic_gb": "حجم ترافیک اختصاص داده شده به اکانت تست رایگان به گیگابایت.",
        "trial_duration_days": "مدت زمان اعتبار اکانت تست رایگان به روز.",
        "referral_enabled": "فعال (1) یا غیرفعال (0) بودن سیستم دعوت از دوستان و دریافت ترافیک رایگان.",
        "referral_reward_gb": "حجم ترافیک هدیه (GB) که با هر دعوت موفق به کاربر معرف اهدا می‌شود.",
    },
    "en": {
        "card_number": "Bank card number for wallet top-ups.",
        "card_holder": "Bank card holder name shown to users.",
        "topup_min_amount": "Minimum top-up amount in Toman.",
        "support_contact": "Support contact username or link.",
        "expiry_grace_days": "Days an account is preserved in panel after expiry before deletion.",
        "expiry_remind_days": "Days before expiry (e.g. 3,1) to send renewal reminders.",
        "topic_topups": "Telegram topic ID for top-up receipts in admin supergroup.",
        "topic_orders": "Telegram topic ID for order purchase notifications.",
        "topic_support": "Telegram topic ID for support message forwarding.",
        "topic_alerts": "Telegram topic ID for system alerts and auto database backups.",
        "topic_crypto": "Telegram topic ID for crypto rates and TON payment logs.",
        "topic_errors": "Telegram topic ID for system error logs and exceptions in admin supergroup.",
        "ton_wallet_address": "Public TON wallet address for receiving user payments.",
        "ton_rate_toman": "Conversion rate of 1 TON in Toman for invoices.",
        "usdt_rate_toman": "Benchmark USDT rate in Toman for global crypto price conversion.",
        "trial_enabled": "Enable (1) or disable (0) free trial accounts.",
        "trial_traffic_gb": "Free trial traffic volume in GB.",
        "trial_duration_days": "Free trial duration in days.",
        "referral_enabled": "Enable (1) or disable (0) referral system.",
        "referral_reward_gb": "Traffic reward in GB given to referrer per invite.",
    },
}


async def _render_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    store_fn = resolve_op("get_store_settings", get_store_settings)
    maint_fn = resolve_op("is_maintenance", is_maintenance)
    render_menu_fn = resolve_op("render_menu", render_menu)
    group_title_fn = resolve_op("_get_admin_group_title", get_admin_group_title)

    lang = user.language or "fa"
    store = await store_fn(session)
    maint_on = await maint_fn(session)
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
        f"✅\n   حجم : \u200e{store.trial_traffic_gb} GB\n   زمان : {store.trial_duration_days} روز"
        if store.trial_enabled
        else "❌"
    )

    ref_desc = (
        f"✅\n   حجم : \u200e{store.referral_reward_gb} GB"
        if store.referral_enabled
        else "❌"
    )

    grp_title = await group_title_fn(bot)
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
    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "adm:settings")
async def store_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_settings_fn = resolve_op("_render_settings", _render_settings)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_settings_fn(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data.startswith("adm:settings:toggle:"))
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

    store_fn = resolve_op("get_store_settings", get_store_settings)
    app_setting_repo_cls = resolve_op("AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = resolve_op("AdminLogRepository", AdminLogRepository)
    render_settings_fn = resolve_op("_render_settings", _render_settings)
    render_trial_fn = resolve_op("_render_trial_settings", _render_trial_settings)
    render_ref_fn = resolve_op("_render_referral_settings", _render_referral_settings)

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language or "fa"
    store = await store_fn(session)

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

    await app_setting_repo_cls(session).set(field, new_str)
    await admin_log_repo_cls(session).log(
        call.from_user.id, "setting", detail=f"{field}={new_str}"
    )

    if field == "trial_enabled":
        await render_trial_fn(bot, user, user_repo, session)
        label = "سرویس تست" if lang == "fa" else "Free Trial"
    elif field == "referral_enabled":
        await render_ref_fn(bot, user, user_repo, session)
        label = "سیستم دعوت" if lang == "fa" else "Referral"
    elif field == "card_enabled":
        await render_settings_fn(bot, user, user_repo, session)
        label = "درگاه کارت به کارت" if lang == "fa" else "Card Payment Gateway"
    else:
        await render_settings_fn(bot, user, user_repo, session)
        label = "پشتیبانی مستقیم" if lang == "fa" else "Direct Support"
    status_text = (
        ("فعال شد" if new_val else "غیرفعال شد")
        if lang == "fa"
        else ("Enabled" if new_val else "Disabled")
    )
    await call.answer(f"✅ {label} {status_text}")


@router.callback_query(F.data == "adm:maint")
async def maintenance_toggle(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    maint_fn = resolve_op("is_maintenance", is_maintenance)
    set_maint_fn = resolve_op("set_maintenance", set_maintenance)
    admin_log_repo_cls = resolve_op("AdminLogRepository", AdminLogRepository)
    render_settings_fn = resolve_op("_render_settings", _render_settings)

    enabled = not await maint_fn(session)
    await set_maint_fn(session, enabled)
    await admin_log_repo_cls(session).log(
        call.from_user.id, "maintenance",
        detail="on" if enabled else "off",
    )
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_settings_fn(bot, user, user_repo, session)
    await call.answer(
        t(user.language or "fa", "maint_toggled", state=t(
            user.language or "fa", "toggle_on" if enabled else "toggle_off")),
    )


REMIND_DAYS_CHOICES = [0, 1, 2, 3, 5, 7, 10, 14]


def _parse_remind_days_set(raw: str | None) -> set[int]:
    if not raw:
        return set()
    result = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.add(int(part))
    return result


async def _render_remind_days_picker(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    store_fn = resolve_op("get_store_settings", get_store_settings)
    render_menu_fn = resolve_op("render_menu", render_menu)

    lang = user.language or "fa"
    store = await store_fn(session)
    active_days = _parse_remind_days_set(store.expiry_remind_days)
    kb = InlineKeyboardBuilder()

    if lang == "fa":
        for d in [3, 2, 1, 0]:
            mark = " ✅" if d in active_days else ""
            kb.button(text=f"{d} روز{mark}", callback_data=f"adm:remind:toggle:{d}")
        for d in [14, 10, 7, 5]:
            mark = " ✅" if d in active_days else ""
            kb.button(text=f"{d} روز{mark}", callback_data=f"adm:remind:toggle:{d}")

        kb.button(text="❌ غیرفعال‌سازی همه هشدارهای انقضا", callback_data="adm:remind:toggle:clear")
        kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    else:
        for d in [0, 1, 2, 3]:
            mark = " ✅" if d in active_days else ""
            kb.button(text=f"{d}d{mark}", callback_data=f"adm:remind:toggle:{d}")
        for d in [5, 7, 10, 14]:
            mark = " ✅" if d in active_days else ""
            kb.button(text=f"{d}d{mark}", callback_data=f"adm:remind:toggle:{d}")

        kb.button(text="❌ Disable All Expiry Reminders", callback_data="adm:remind:toggle:clear")
        kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")

    kb.adjust(4, 4, 1, 1)

    active_sorted = sorted(active_days, reverse=True)
    if lang == "fa":
        if active_sorted:
            display_str = "، ".join(f"{d} روز" for d in active_sorted)
        else:
            display_str = "هیچ‌کدام (غیرفعال)"
        text = (
            f"🔔 <b>تنظیم روزهای هشدار انقضا</b>\n{SEPARATOR}\n"
            f"روزهای انتخابی فعلی: <b>{display_str}</b>\n\n"
            f"💡 با لمس هر گزینه، می‌توانید آن را فعال یا غیرفعال کنید (امکان انتخاب همزمان چند روز وجود دارد):\n"
            f"پیام یادآوری تمدید اشتراک در این روزها به صورت خودکار برای کاربران ارسال خواهد شد."
        )
    else:
        if active_sorted:
            display_str = ", ".join(f"{d}d" for d in active_sorted)
        else:
            display_str = "None (Disabled)"
        text = (
            f"🔔 <b>Expiry Reminder Days</b>\n{SEPARATOR}\n"
            f"Currently selected: <b>{display_str}</b>\n\n"
            f"💡 Tap any option to toggle it on or off (multiple choices supported):\n"
            f"Renewal reminder messages will be sent automatically to users on these days."
        )

    await render_menu_fn(bot, user, user_repo, text, kb.as_markup())


@router.callback_query(F.data == "adm:remind:picker")
async def remind_days_picker_entry(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_remind_fn = resolve_op("_render_remind_days_picker", _render_remind_days_picker)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_remind_fn(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data.startswith("adm:remind:toggle:"))
async def remind_days_toggle(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    store_fn = resolve_op("get_store_settings", get_store_settings)
    app_setting_repo_cls = resolve_op("AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = resolve_op("AdminLogRepository", AdminLogRepository)
    render_remind_fn = resolve_op("_render_remind_days_picker", _render_remind_days_picker)

    action = call.data.rsplit(":", 1)[1]
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    store = await store_fn(session)
    active_days = _parse_remind_days_set(store.expiry_remind_days)

    if action == "clear":
        active_days.clear()
        new_val = ""
        ans_msg = "❌ تمام هشدارهای انقضا غیرفعال شدند" if user.language == "fa" else "All reminders disabled"
    else:
        try:
            day_num = int(action)
        except ValueError:
            await call.answer(t("fa", "acc_error"), show_alert=True)
            return
        if day_num in active_days:
            active_days.remove(day_num)
            ans_msg = f"❌ هشدار {day_num} روز حذف شد" if user.language == "fa" else f"Removed {day_num}d reminder"
        else:
            active_days.add(day_num)
            ans_msg = f"✅ هشدار {day_num} روز افزوده شد" if user.language == "fa" else f"Added {day_num}d reminder"
        new_val = ",".join(str(d) for d in sorted(active_days, reverse=True))

    await app_setting_repo_cls(session).set("expiry_remind_days", new_val)
    await admin_log_repo_cls(session).log(
        call.from_user.id, "setting", detail=f"expiry_remind_days={new_val}"
    )
    await render_remind_fn(bot, user, user_repo, session)
    await call.answer(ans_msg)


GRACE_DAYS_CHOICES = [0, 1, 2, 3, 5, 7, 10, 14, 30]


async def _render_grace_days_picker(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    store_fn = resolve_op("get_store_settings", get_store_settings)
    render_menu_fn = resolve_op("render_menu", render_menu)

    lang = user.language or "fa"
    store = await store_fn(session)
    current_grace = store.expiry_grace_days
    kb = InlineKeyboardBuilder()

    if lang == "fa":
        for d in [2, 1, 0]:
            label = "بدون مهلت (0)" if d == 0 else f"{d} روز"
            mark = " ✅" if current_grace == d else ""
            kb.button(text=f"{label}{mark}", callback_data=f"adm:grace:set:{d}")
        for d in [7, 5, 3]:
            mark = " ✅" if current_grace == d else ""
            kb.button(text=f"{d} روز{mark}", callback_data=f"adm:grace:set:{d}")
        for d in [30, 14, 10]:
            mark = " ✅" if current_grace == d else ""
            kb.button(text=f"{d} روز{mark}", callback_data=f"adm:grace:set:{d}")
    else:
        for d in [0, 1, 2]:
            label = "No grace (0)" if d == 0 else f"{d}d"
            mark = " ✅" if current_grace == d else ""
            kb.button(text=f"{label}{mark}", callback_data=f"adm:grace:set:{d}")
        for d in [3, 5, 7]:
            mark = " ✅" if current_grace == d else ""
            kb.button(text=f"{d}d{mark}", callback_data=f"adm:grace:set:{d}")
        for d in [10, 14, 30]:
            mark = " ✅" if current_grace == d else ""
            kb.button(text=f"{d}d{mark}", callback_data=f"adm:grace:set:{d}")

    kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    kb.adjust(3, 3, 3, 1)

    grace_display = "بدون مهلت (سرویس بلافاصله مسدود می‌شود)" if current_grace == 0 else f"{current_grace} روز"
    if lang == "fa":
        text = (
            f"⏳ <b>تنظیم مهلت پس از انقضا (Grace Period)</b>\n{SEPARATOR}\n"
            f"مهلت فعلی: <b>{grace_display}</b>\n\n"
            f"💡 تعداد روزهایی که سرویس کاربر پس از انقضا فعال می‌ماند (مهلت تمدید/پرداخت قبل از قطع شدن) را انتخاب کنید:"
        )
    else:
        text = (
            f"⏳ <b>Expiry Grace Period</b>\n{SEPARATOR}\n"
            f"Current grace period: <b>{current_grace}d</b>\n\n"
            f"💡 Select how many days after expiry the service remains active before being suspended:"
        )

    await render_menu_fn(bot, user, user_repo, text, kb.as_markup())


@router.callback_query(F.data == "adm:grace:picker")
async def grace_days_picker_entry(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    render_grace_fn = resolve_op("_render_grace_days_picker", _render_grace_days_picker)
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_grace_fn(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data.startswith("adm:grace:set:"))
async def grace_days_set(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    app_setting_repo_cls = resolve_op("AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = resolve_op("AdminLogRepository", AdminLogRepository)
    render_grace_fn = resolve_op("_render_grace_days_picker", _render_grace_days_picker)

    action = call.data.rsplit(":", 1)[1]
    try:
        days_num = int(action)
    except ValueError:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if days_num not in GRACE_DAYS_CHOICES and not (0 <= days_num <= 365):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await app_setting_repo_cls(session).set("expiry_grace_days", str(days_num))
    await admin_log_repo_cls(session).log(
        call.from_user.id, "setting", detail=f"expiry_grace_days={days_num}"
    )
    await render_grace_fn(bot, user, user_repo, session)
    ans_msg = f"✅ مهلت پس از انقضا: {days_num} روز" if user.language == "fa" else f"Grace period set to {days_num}d"
    await call.answer(ans_msg)


@router.callback_query(F.data.startswith("adm:set:"))
async def settings_edit_start(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    field = call.data.rsplit(":", 1)[1]
    if field not in SETTING_FIELDS:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    store_fn = resolve_op("get_store_settings", get_store_settings)
    render_menu_fn = resolve_op("render_menu", render_menu)
    render_remind_fn = resolve_op("_render_remind_days_picker", _render_remind_days_picker)
    render_grace_fn = resolve_op("_render_grace_days_picker", _render_grace_days_picker)

    # Special handling for expiry remind days: show multi-select picker!
    if field == "expiry_remind_days":
        await state.clear()
        await render_remind_fn(bot, user, user_repo, session)
        await call.answer()
        return

    # Special handling for expiry grace days: show single-select picker!
    if field == "expiry_grace_days":
        await state.clear()
        await render_grace_fn(bot, user, user_repo, session)
        await call.answer()
        return

    # Special handling for default squad: show squad list buttons!
    if field == "default_squad_uuid":
        await state.clear()
        store = await store_fn(session)
        squads = await remnawave.get_internal_squads()
        lines = [
            "🧩 <b>انتخاب اسکواد پیش‌فرض فروشگاه</b>" if lang == "fa" else "🧩 <b>Select Default Store Squad</b>",
            SEPARATOR,
            "اسکوادی که اکانت‌های جدید پس از خرید خودکار به آن متصل می‌شوند را انتخاب کنید:" if lang == "fa" else "Select default squad for new accounts created via shop:",
        ]
        kb = InlineKeyboardBuilder()
        for sq in squads:
            sq_name = sq.get("name") or "Squad"
            sq_uuid = sq.get("uuid")
            is_active = (store.default_squad_uuid == sq_uuid)
            icon = "✅" if is_active else "🧩"
            kb.button(text=f"{icon} {sq_name}", callback_data=f"adm:setsquad:{sq_uuid}")
        kb.button(
            text="❌ بدون اسکواد پیش‌فرض (غیرفعال)" if lang == "fa" else "❌ No Default Squad (None)",
            callback_data="adm:setsquad:none",
        )
        kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
        sq_count = len(squads)
        sizes = [2] * (sq_count // 2)
        if sq_count % 2:
            sizes.append(1)
        sizes += [1, 1]
        kb.adjust(*sizes)
        await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())
        await call.answer()
        return

    await state.set_state(SettingsStates.waiting_value)
    await state.update_data(settings_field=field)

    cancel_target = (
        "adm:settings:crypto" if ("ton_" in field or field in ("crypto_enabled", "usdt_rate_toman"))
        else ("adm:settings:topics" if field.startswith("topic_")
        else ("adm:settings:trial" if "trial" in field else ("adm:settings:referral" if "referral" in field else "adm:settings")))
    )
    kb = InlineKeyboardBuilder()
    if field == "card_number":
        store = await store_fn(session)
        c_badge = "✅" if store.card_enabled else "❌"
        card_toggle_txt = f"💳 وضعیت درگاه کارت {c_badge}" if lang == "fa" else f"💳 Card Gateway {c_badge}"
        kb.button(text=card_toggle_txt, callback_data="adm:settings:toggle:card_enabled")
    kb.button(text=t(lang, "btn_cancel"), callback_data=cancel_target)
    kb.adjust(1)

    prompt_key = SETTING_FIELDS[field][0]
    extra = t(lang, "skip_for_none") if SETTING_FIELDS[field][1] is False else ""
    desc = SETTING_DESCRIPTIONS.get(lang, SETTING_DESCRIPTIONS["fa"]).get(field, "")

    parts = [f"⚙️ <b>{t(lang, prompt_key)}</b>", SEPARATOR]
    if desc:
        parts.append(f"💡 {desc}\n")
    parts.append(t(lang, "settings_value_prompt"))
    if extra:
        parts.append(f"\n{extra}")

    await render_menu_fn(bot, user, user_repo, "\n".join(parts), kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("adm:setsquad:"))
async def settings_set_squad(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession,
):
    if not is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    app_setting_repo_cls = resolve_op("AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = resolve_op("AdminLogRepository", AdminLogRepository)
    render_settings_fn = resolve_op("_render_settings", _render_settings)

    choice = call.data.rsplit(":", 1)[1]
    val = "" if choice == "none" else choice
    await app_setting_repo_cls(session).set("default_squad_uuid", val)
    await admin_log_repo_cls(session).log(
        call.from_user.id, "setting", detail=f"default_squad_uuid={val[:40]}"
    )
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_settings_fn(bot, user, user_repo, session)
    await call.answer(t(user.language or "fa", "toast_squads_updated"))


@router.message(SettingsStates.waiting_value, F.text)
async def settings_value_save(
    message: Message, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext,
):
    del_msg_fn = resolve_op("delete_message_silently", delete_message_silently)
    render_menu_fn = resolve_op("render_menu", render_menu)
    render_settings_fn = resolve_op("_render_settings", _render_settings)
    render_topics_fn = resolve_op("_render_topics_settings", _render_topics_settings)
    render_crypto_fn = resolve_op("_render_crypto_settings", _render_crypto_settings)
    render_trial_fn = resolve_op("_render_trial_settings", _render_trial_settings)
    render_ref_fn = resolve_op("_render_referral_settings", _render_referral_settings)
    app_setting_repo_cls = resolve_op("AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = resolve_op("AdminLogRepository", AdminLogRepository)

    user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
    lang = user.language
    await del_msg_fn(bot, message.chat.id, message.message_id)

    data = await state.get_data()
    field = data.get("settings_field", "card_number")
    is_numeric = SETTING_FIELDS.get(field, ("", False))[1]

    raw = message.text.strip()
    value = raw
    SKIP_WORDS = ("/skip", "-", "—")
    cancel_target = (
        "adm:settings:crypto" if ("ton_" in field or field in ("crypto_enabled", "usdt_rate_toman"))
        else ("adm:settings:topics" if field.startswith("topic_")
        else ("adm:settings:trial" if "trial" in field else ("adm:settings:referral" if "referral" in field else "adm:settings")))
    )

    if field.startswith("topic_") or field == "expiry_grace_days":
        if raw in SKIP_WORDS or raw == "0":
            value = ""
        else:
            parsed = _parse_int(raw)
            if parsed is None or parsed < 0:
                kb = InlineKeyboardBuilder()
                kb.button(text=t(lang, "btn_cancel"), callback_data=cancel_target)
                kb.adjust(1)
                await render_menu_fn(bot, user, user_repo, t(lang, "settings_invalid_number"), kb.as_markup())
                return
            value = str(parsed)
    elif field in ("trial_enabled", "referral_enabled"):
        parsed = _parse_int(raw)
        if parsed not in (0, 1):
            kb = InlineKeyboardBuilder()
            kb.button(text=t(lang, "btn_cancel"), callback_data=cancel_target)
            kb.adjust(1)
            await render_menu_fn(bot, user, user_repo, "❌ لطفاً فقط عدد 1 (فعال) یا 0 (غیرفعال) را وارد کنید:", kb.as_markup())
            return
        value = str(parsed)
    elif is_numeric:
        parsed = _parse_int(raw)
        if parsed is None or parsed < 0:
            kb = InlineKeyboardBuilder()
            kb.button(text=t(lang, "btn_cancel"), callback_data=cancel_target)
            kb.adjust(1)
            await render_menu_fn(bot, user, user_repo, t(lang, "settings_invalid_number"), kb.as_markup())
            return
        value = str(parsed)
    elif field == "support_contact":
        if raw in SKIP_WORDS or raw == "0":
            value = ""
            await app_setting_repo_cls(session).set("support_direct_enabled", "0")
        else:
            clean_contact = raw.strip()
            t_me_match = re.match(
                r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]{3,32})/?$",
                clean_contact,
                re.IGNORECASE,
            )
            user_match = re.match(r"^@?([A-Za-z0-9_]{3,32})$", clean_contact)
            url_match = re.match(r"^https?://[^\s]+$", clean_contact)

            if t_me_match:
                uname = t_me_match.group(1)
                value = f"https://t.me/{uname}"
            elif user_match:
                uname = user_match.group(1)
                value = f"@{uname}"
            elif url_match:
                value = clean_contact
            else:
                kb = InlineKeyboardBuilder()
                kb.button(text=t(lang, "btn_cancel"), callback_data="adm:settings")
                kb.adjust(1)
                err_msg = (
                    "❌ فرمت نامعتبر است.\n\n"
                    "لطفاً آیدی پشتیبانی را با <b>@</b> (مانند <code>@SupportUsername</code>) "
                    "یا لینک تلگرام (مانند <code>t.me/SupportUsername</code>) ارسال کنید:\n\n"
                    "<i>(برای حذف مقدار می‌توانید /skip یا 0 بفرستید)</i>"
                ) if lang == "fa" else (
                    "❌ Invalid format.\n\n"
                    "Please provide a Telegram username with <b>@</b> (e.g. <code>@SupportUsername</code>) "
                    "or link (e.g. <code>t.me/SupportUsername</code>):\n\n"
                    "<i>(Send /skip or 0 to clear)</i>"
                )
                await render_menu_fn(bot, user, user_repo, err_msg, kb.as_markup())
                return
    elif raw in SKIP_WORDS:
        value = ""

    await app_setting_repo_cls(session).set(field, value)
    await admin_log_repo_cls(session).log(
        message.from_user.id, "setting", detail=f"{field}={value[:40]}"
    )
    await state.clear()
    if field.startswith("topic_"):
        await render_topics_fn(bot, user, user_repo, session)
    elif "ton_" in field or field in ("crypto_enabled", "usdt_rate_toman"):
        await render_crypto_fn(bot, user, user_repo, session)
    elif "trial" in field:
        await render_trial_fn(bot, user, user_repo, session)
    elif "referral" in field:
        await render_ref_fn(bot, user, user_repo, session)
    else:
        await render_settings_fn(bot, user, user_repo, session)
