"""Admin Store Settings, Topics, Crypto, Trial/Referral, and Maintenance Modes."""
import logging
import re
import time
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import SEPARATOR, fmt, is_admin, parse_int
from bot.config import get_settings
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.user_repo import UserRepository
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
router = Router(name="admin_settings")

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

_cached_admin_group_title: str | None = None
_cached_admin_group_title_time: float = 0


async def _get_admin_group_title(bot: Bot) -> str | None:
    global _cached_admin_group_title, _cached_admin_group_title_time
    now = time.time()
    if _cached_admin_group_title is not None and (now - _cached_admin_group_title_time) < 300:
        return _cached_admin_group_title
    cfg = get_settings()
    chat_id = getattr(cfg, "ADMIN_CHAT_ID", None)
    if not chat_id:
        return None
    try:
        chat = await bot.get_chat(chat_id)
        _cached_admin_group_title = chat.title or None
        _cached_admin_group_title_time = now
        return _cached_admin_group_title
    except Exception:
        return _cached_admin_group_title


async def _render_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    import bot.handlers.admin_ops as _ops
    store_fn = getattr(_ops, "get_store_settings", get_store_settings)
    maint_fn = getattr(_ops, "is_maintenance", is_maintenance)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)
    group_title_fn = getattr(_ops, "_get_admin_group_title", _get_admin_group_title)

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


async def _render_topics_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    import bot.handlers.admin_ops as _ops
    store_fn = getattr(_ops, "get_store_settings", get_store_settings)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)
    group_title_fn = getattr(_ops, "_get_admin_group_title", _get_admin_group_title)

    lang = user.language or "fa"
    store = await store_fn(session)
    kb = InlineKeyboardBuilder()

    t_topups = f"{store.topic_topups} (Topups)" if store.topic_topups is not None else "— (Topups)"
    t_orders = f"{store.topic_orders} (Orders)" if store.topic_orders is not None else "— (Orders)"
    t_support = f"{store.topic_support} (Support)" if store.topic_support is not None else "— (Support)"
    t_alerts = f"{store.topic_alerts} (Alerts)" if store.topic_alerts is not None else "— (Alerts)"
    t_crypto = f"{store.topic_crypto} (Crypto)" if store.topic_crypto is not None else "— (Crypto)"
    t_errors = f"{store.topic_errors} (Errors)" if store.topic_errors is not None else "— (Errors)"

    if lang == "fa":
        # Persian RTL: first added is LEFT, second added is RIGHT
        # Row 1: Right = تاپیک شارژها, Left = تاپیک سفارشات
        kb.button(text="🛒 تاپیک سفارشات", callback_data="adm:set:topic_orders")
        kb.button(text="💳 تاپیک شارژها", callback_data="adm:set:topic_topups")
        # Row 2: Right = تاپیک پشتیبانی, Left = تاپیک هشدار و بکاپ
        kb.button(text="🚨 تاپیک هشدار و بکاپ", callback_data="adm:set:topic_alerts")
        kb.button(text="🎧 تاپیک پشتیبانی", callback_data="adm:set:topic_support")
        # Row 3: Right = تاپیک کریپتو و نرخ, Left = تاپیک لاگ‌های ارور
        kb.button(text="⚠️ تاپیک لاگ‌های ارور", callback_data="adm:set:topic_errors")
        kb.button(text="💎 تاپیک کریپتو و نرخ", callback_data="adm:set:topic_crypto")
    else:
        kb.button(text="💳 Top-ups Topic", callback_data="adm:set:topic_topups")
        kb.button(text="🛒 Orders Topic", callback_data="adm:set:topic_orders")
        kb.button(text="🎧 Support Topic", callback_data="adm:set:topic_support")
        kb.button(text="🚨 Alerts & Backup", callback_data="adm:set:topic_alerts")
        kb.button(text="💎 Crypto & Rates Topic", callback_data="adm:set:topic_crypto")
        kb.button(text="⚠️ Error Logs Topic", callback_data="adm:set:topic_errors")

    kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    kb.adjust(2, 2, 2, 1)

    grp_title = await group_title_fn(bot)
    topics_title = f"{t(lang, 'settings_topics_title')} ({escape(grp_title)})" if grp_title else t(lang, 'settings_topics_title')

    text = (
        f"{topics_title}\n{SEPARATOR}\n"
        f"💳 <b>تاپیک تایید شارژها :</b> {t_topups}\n"
        f"🛒 <b>تاپیک ثبت سفارشات :</b> {t_orders}\n"
        f"🎧 <b>تاپیک پیام‌های پشتیبانی :</b> {t_support}\n"
        f"🚨 <b>تاپیک هشدارهای سیستم و بکاپ :</b> {t_alerts}\n"
        f"💎 <b>تاپیک کریپتو و نرخ ارز :</b> {t_crypto}\n"
        f"⚠️ <b>تاپیک لاگ‌های ارور :</b> {t_errors}\n\n"
        f"💡 جهت اتصال هر بخش به تاپیک، روی دکمه مربوطه کلیک کنید و شناسه عددی (Topic ID) آن را ارسال نمایید.\n"
        f"(برای غیرفعال‌سازی هر تاپیک مقدار 0 یا /skip ارسال کنید)"
    ) if lang == "fa" else (
        f"{topics_title}\n{SEPARATOR}\n"
        f"💳 <b>Top-ups Topic :</b> {t_topups}\n"
        f"🛒 <b>Orders Topic :</b> {t_orders}\n"
        f"🎧 <b>Support Topic :</b> {t_support}\n"
        f"🚨 <b>System Alerts & Backup :</b> {t_alerts}\n"
        f"💎 <b>Crypto & Rates Topic :</b> {t_crypto}\n"
        f"⚠️ <b>Error Logs Topic :</b> {t_errors}\n\n"
        f"<i>(Send 0 or /skip to disable any topic)</i>"
    )
    await render_menu_fn(bot, user, user_repo, text, kb.as_markup())


async def _render_crypto_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    import bot.handlers.admin_ops as _ops
    store_fn = getattr(_ops, "get_store_settings", get_store_settings)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

    lang = user.language or "fa"
    store = await store_fn(session)
    kb = InlineKeyboardBuilder()

    status_badge = "✅" if store.crypto_enabled else "❌"
    rate_str = f"{store.ton_rate_toman:,} تومان" if store.ton_rate_toman > 0 else "— (تنظیم‌نشده)"
    wallet_str = store.ton_wallet_address or "— (تنظیم‌نشده)"

    if lang == "fa":
        # Row 1: Status
        kb.button(
            text=f"⚡️ وضعیت درگاه {status_badge}",
            callback_data="adm:settings:toggle:crypto_enabled",
        )
        # Row 2 (RTL): Right = Wallet Address, Left = Exchange Rate
        kb.button(text="💰 نرخ تبدیل", callback_data="adm:set:ton_rate_toman")
        kb.button(text="📬 آدرس والت", callback_data="adm:set:ton_wallet_address")
        # Row 3 (RTL): Right = USDT Rate, Left = Instant Check
        kb.button(text="📊 استعلام آنی نرخ ارز", callback_data="adm:crypto:nobitex_now")
        kb.button(text="💵 نرخ مبنای تتر", callback_data="adm:set:usdt_rate_toman")
    else:
        kb.button(
            text=f"⚡️ Status {status_badge}",
            callback_data="adm:settings:toggle:crypto_enabled",
        )
        kb.button(text="📬 Wallet Address", callback_data="adm:set:ton_wallet_address")
        kb.button(text="💰 Exchange Rate", callback_data="adm:set:ton_rate_toman")
        kb.button(text="💵 USDT Rate", callback_data="adm:set:usdt_rate_toman")
        kb.button(text="📊 Check Market Price", callback_data="adm:crypto:nobitex_now")

    kb.button(text=t(lang, "btn_back"), callback_data="adm:settings")
    kb.adjust(1, 2, 2, 1)

    lines = [
        "💎 <b>تنظیمات پرداخت کریپتو</b>\n" + SEPARATOR,
        f"⚡️ وضعیت درگاه : <b>{status_badge}</b>",
        f"📬 آدرس والت مقصد : <code>{escape(wallet_str)}</code>",
        f"💰 نرخ تبدیل (۱ تون) : <b>{rate_str}</b>",
        f"💵 نرخ مبنای تتر : <b>{store.usdt_rate_toman:,} تومان</b>\n",
        "💡 ربات روزانه ۴ بار (ساعت‌های ۱۰:۰۰، ۱۴:۰۰، ۱۸:۰۰ و ۲۲:۰۰) قیمت لحظه‌ای را در تاپیک کریپتو ارسال می‌کند تا با یک کلیک بتوانید نرخ فروشگاه را آپدیت فرمایید.",
    ] if lang == "fa" else [
        "💎 <b>Crypto Payment Settings</b>\n" + SEPARATOR,
        f"⚡️ Status : <b>{status_badge}</b>",
        f"📬 Wallet : <code>{escape(wallet_str)}</code>",
        f"💰 Rate : <b>{rate_str}</b>",
        f"💵 USDT Rate : <b>{store.usdt_rate_toman:,} Toman</b>",
    ]

    await render_menu_fn(bot, user, user_repo, "\n".join(lines), kb.as_markup())


@router.callback_query(F.data == "adm:settings:crypto")
async def crypto_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_crypto_settings(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:settings:toggle:crypto_enabled")
async def toggle_crypto_enabled(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    import bot.handlers.admin_ops as _ops
    app_setting_repo_cls = getattr(_ops, "AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = getattr(_ops, "AdminLogRepository", AdminLogRepository)
    store_fn = getattr(_ops, "get_store_settings", get_store_settings)

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    store = await store_fn(session)
    new_val = not store.crypto_enabled
    await app_setting_repo_cls(session).set("crypto_enabled", "1" if new_val else "0")
    await admin_log_repo_cls(session).log(
        call.from_user.id, "setting", detail=f"crypto_enabled={'1' if new_val else '0'}"
    )
    await _render_crypto_settings(bot, user, user_repo, session)
    await call.answer("✅ وضعیت پرداخت کریپتو تغییر یافت.")


@router.callback_query(F.data == "adm:crypto:nobitex_now")
async def crypto_nobitex_now(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    import bot.handlers.admin_ops as _ops
    store_fn = getattr(_ops, "get_store_settings", get_store_settings)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

    from bot.services.crypto.nobitex import fetch_all_exchange_prices, format_multi_rate_alert
    store = await store_fn(session)
    market_data = await fetch_all_exchange_prices(usdt_rate=store.usdt_rate_toman)
    best_ton, _ = market_data.get("best_ton", (None, ""))
    if best_ton is None and not market_data.get("usdt"):
        await call.answer(
            "❌ خطا در استعلام از صرافی‌ها (احتمال مسدود بودن دسترسی از خارج کشور). لطفاً نرخ را به‌صورت دستی تنظیم فرمایید.",
            show_alert=True,
        )
        return

    text, kb = format_multi_rate_alert(
        market_data=market_data,
        current_ton_rate=store.ton_rate_toman,
        current_usdt_rate=store.usdt_rate_toman,
    )
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_menu_fn(bot, user, user_repo, text, kb)
    await call.answer("✅ استعلام قیمت لحظه‌ای انجام شد.")


@router.callback_query(F.data.startswith("adm:rate:apply:"))
async def apply_nobitex_rate(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    import bot.handlers.admin_ops as _ops
    app_setting_repo_cls = getattr(_ops, "AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = getattr(_ops, "AdminLogRepository", AdminLogRepository)

    try:
        parts = call.data.split(":")
        # Format can be adm:rate:apply:ton:<price> or adm:rate:apply:usdt:<price> or legacy adm:rate:apply:<price>
        if len(parts) >= 5 and parts[3] in ("ton", "usdt"):
            kind = parts[3]
            price = int(parts[4])
        else:
            kind = "ton"
            price = int(parts[3])
    except (ValueError, IndexError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    setting_key = "ton_rate_toman" if kind == "ton" else "usdt_rate_toman"
    kind_title = "نرخ تون" if kind == "ton" else "نرخ مبنای تتر"

    await app_setting_repo_cls(session).set(setting_key, str(price))
    await admin_log_repo_cls(session).log(
        call.from_user.id, "setting", detail=f"{setting_key}={price}"
    )
    await session.commit()

    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 بازگشت به تنظیمات کریپتو", callback_data="adm:settings:crypto")
    kb.button(text="⚙️ تنظیمات فروشگاه", callback_data="adm:settings")
    kb.adjust(1)

    await call.answer(f"✅ {kind_title} فروشگاه روی {price:,} تومان تنظیم شد.", show_alert=True)
    try:
        await call.message.edit_text(
            f"{call.message.html_text}\n\n✅ <b>{kind_title} فروشگاه با موفقیت روی {price:,} تومان تنظیم شد.</b>",
            reply_markup=kb.as_markup(),
        )
    except Exception:
        pass


@router.callback_query(F.data == "adm:settings")
async def store_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    import bot.handlers.admin_ops as _ops
    render_settings_fn = getattr(_ops, "_render_settings", _render_settings)

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_settings_fn(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:settings:topics")
async def topics_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    import bot.handlers.admin_ops as _ops
    render_topics_fn = getattr(_ops, "_render_topics_settings", _render_topics_settings)

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_topics_fn(bot, user, user_repo, session)
    await call.answer()


async def _render_trial_settings(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    import bot.handlers.admin_ops as _ops
    store_fn = getattr(_ops, "get_store_settings", get_store_settings)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

    lang = user.language or "fa"
    store = await store_fn(session)
    kb = InlineKeyboardBuilder()

    trial_badge = "✅" if store.trial_enabled else "❌"
    trial_btn_text = f"وضعیت {'✅' if store.trial_enabled else '❌'}"

    if lang == "fa":
        # Row 1 (RTL): Left = Duration, Right = Traffic
        kb.button(text=f"⏳ زمان: {store.trial_duration_days} روز", callback_data="adm:set:trial_duration_days")
        kb.button(text=f"📊 حجم: {store.trial_traffic_gb} GB", callback_data="adm:set:trial_traffic_gb")
        # Row 2 (RTL): Left = Back, Right = Status
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
    import bot.handlers.admin_ops as _ops
    store_fn = getattr(_ops, "get_store_settings", get_store_settings)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

    lang = user.language or "fa"
    store = await store_fn(session)
    kb = InlineKeyboardBuilder()

    ref_badge = "✅" if store.referral_enabled else "❌"
    ref_btn_text = f"وضعیت {'✅' if store.referral_enabled else '❌'}"

    if lang == "fa":
        kb.button(text=f"📊 حجم: {store.referral_reward_gb} GB", callback_data="adm:set:referral_reward_gb")
        # Row 2 (RTL): Left = Back, Right = Status
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
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    import bot.handlers.admin_ops as _ops
    render_trial_fn = getattr(_ops, "_render_trial_settings", _render_trial_settings)

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_trial_fn(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:settings:referral")
async def referral_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    import bot.handlers.admin_ops as _ops
    render_ref_fn = getattr(_ops, "_render_referral_settings", _render_referral_settings)

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_ref_fn(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data == "adm:settings:trial_ref")
async def trial_ref_settings_view(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    import bot.handlers.admin_ops as _ops
    render_trial_fn = getattr(_ops, "_render_trial_settings", _render_trial_settings)

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_trial_fn(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data.startswith("adm:settings:toggle:"))
async def setting_toggle_boolean(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
    state: FSMContext | None = None,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    field = call.data.rsplit(":", 1)[1]
    if field not in ("trial_enabled", "referral_enabled", "support_direct_enabled", "card_enabled"):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return

    if state:
        await state.clear()

    import bot.handlers.admin_ops as _ops
    store_fn = getattr(_ops, "get_store_settings", get_store_settings)
    app_setting_repo_cls = getattr(_ops, "AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = getattr(_ops, "AdminLogRepository", AdminLogRepository)
    render_settings_fn = getattr(_ops, "_render_settings", _render_settings)
    render_trial_fn = getattr(_ops, "_render_trial_settings", _render_trial_settings)
    render_ref_fn = getattr(_ops, "_render_referral_settings", _render_referral_settings)

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
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    import bot.handlers.admin_ops as _ops
    maint_fn = getattr(_ops, "is_maintenance", is_maintenance)
    set_maint_fn = getattr(_ops, "set_maintenance", set_maintenance)
    admin_log_repo_cls = getattr(_ops, "AdminLogRepository", AdminLogRepository)
    render_settings_fn = getattr(_ops, "_render_settings", _render_settings)

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
    import bot.handlers.admin_ops as _ops
    store_fn = getattr(_ops, "get_store_settings", get_store_settings)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

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
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_remind_days_picker(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data.startswith("adm:remind:toggle:"))
async def remind_days_toggle(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    import bot.handlers.admin_ops as _ops
    store_fn = getattr(_ops, "get_store_settings", get_store_settings)
    app_setting_repo_cls = getattr(_ops, "AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = getattr(_ops, "AdminLogRepository", AdminLogRepository)

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
    await _render_remind_days_picker(bot, user, user_repo, session)
    await call.answer(ans_msg)


GRACE_DAYS_CHOICES = [0, 1, 2, 3, 5, 7, 10, 14, 30]


async def _render_grace_days_picker(
    bot: Bot, user, user_repo: UserRepository, session: AsyncSession,
) -> None:
    import bot.handlers.admin_ops as _ops
    store_fn = getattr(_ops, "get_store_settings", get_store_settings)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

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
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_grace_days_picker(bot, user, user_repo, session)
    await call.answer()


@router.callback_query(F.data.startswith("adm:grace:set:"))
async def grace_days_set(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    import bot.handlers.admin_ops as _ops
    app_setting_repo_cls = getattr(_ops, "AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = getattr(_ops, "AdminLogRepository", AdminLogRepository)

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
    await _render_grace_days_picker(bot, user, user_repo, session)
    ans_msg = f"✅ مهلت پس از انقضا: {days_num} روز" if user.language == "fa" else f"Grace period set to {days_num}d"
    await call.answer(ans_msg)


@router.callback_query(F.data.startswith("adm:set:"))
async def settings_edit_start(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession, state: FSMContext, remnawave: RemnawaveClient,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    field = call.data.rsplit(":", 1)[1]
    if field not in SETTING_FIELDS:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language

    import bot.handlers.admin_ops as _ops
    store_fn = getattr(_ops, "get_store_settings", get_store_settings)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)

    # Special handling for expiry remind days: show multi-select picker!
    if field == "expiry_remind_days":
        await state.clear()
        await _render_remind_days_picker(bot, user, user_repo, session)
        await call.answer()
        return

    # Special handling for expiry grace days: show single-select picker!
    if field == "expiry_grace_days":
        await state.clear()
        await _render_grace_days_picker(bot, user, user_repo, session)
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
        # 2 columns for squads, then full width for None and Back
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

    await render_menu_fn(
        bot, user, user_repo,
        "\n".join(parts),
        kb.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:setsquad:"))
async def settings_set_squad(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
    session: AsyncSession,
):
    if not _is_admin(call.from_user.id):
        await call.answer(t("fa", "not_authorized"), show_alert=True)
        return
    import bot.handlers.admin_ops as _ops
    app_setting_repo_cls = getattr(_ops, "AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = getattr(_ops, "AdminLogRepository", AdminLogRepository)
    render_settings_fn = getattr(_ops, "_render_settings", _render_settings)

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
    import bot.handlers.admin_ops as _ops
    del_msg_fn = getattr(_ops, "delete_message_silently", delete_message_silently)
    render_menu_fn = getattr(_ops, "render_menu", render_menu)
    render_settings_fn = getattr(_ops, "_render_settings", _render_settings)
    render_topics_fn = getattr(_ops, "_render_topics_settings", _render_topics_settings)
    render_crypto_fn = getattr(_ops, "_render_crypto_settings", _render_crypto_settings)
    render_trial_fn = getattr(_ops, "_render_trial_settings", _render_trial_settings)
    render_ref_fn = getattr(_ops, "_render_referral_settings", _render_referral_settings)
    app_setting_repo_cls = getattr(_ops, "AppSettingRepository", AppSettingRepository)
    admin_log_repo_cls = getattr(_ops, "AdminLogRepository", AdminLogRepository)

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
