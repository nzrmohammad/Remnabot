"""Common constants, descriptions and helper functions for Admin Settings."""
import logging

from bot.common import is_admin, parse_int
from bot.services import menu

logger = logging.getLogger(__name__)

delete_message_silently = menu.delete_message_silently


async def render_menu(*args, **kwargs):
    return await menu.render_menu(*args, **kwargs)


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
    "topic_reports": ("settings_topic_reports", True),
    "topic_nodes": ("settings_topic_nodes", True),
    "support_contact": ("settings_support_contact", False),
    "trial_enabled": ("settings_trial_enabled", True),
    "trial_traffic_gb": ("settings_trial_traffic", True),
    "trial_duration_days": ("settings_trial_duration", True),
    "referral_enabled": ("settings_referral_enabled", True),
    "referral_reward_gb": ("settings_referral_reward", True),
    "topic_crypto": ("settings_topic_crypto", True),
    "topic_errors": ("settings_topic_errors", True),
    "topic_backups": ("settings_topic_backups", True),
    "ton_wallet_address": ("settings_ton_wallet", False),
    "ton_rate_toman": ("settings_ton_rate", True),
    "usdt_rate_toman": ("settings_usdt_rate", True),
    "stars_rate_toman": ("settings_stars_rate", True),
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
        "topic_reports": "شناسه تاپیک گزارش‌های مدیریتی (روزانه، شبانه، هفتگی و ماهانه) در سوپرگروه مدیریت.",
        "topic_nodes": "شناسه تاپیک هشدار وضعیت و قطعی/وصلی سرورها در سوپرگروه مدیریت تلگرام.",
        "topic_crypto": "شناسه تاپیک کریپتو در سوپرگروه مدیریت جهت ارسال استعلام نرخ نوبیتکس و لاگ پرداخت‌های تون.",
        "topic_errors": "شناسه تاپیک لاگ‌های خطا و ارورهای سیستم در سوپرگروه مدیریت تلگرام.",
        "topic_backups": "شناسه تاپیک اختصاصی ارسال فایل‌های بکاپ دیتابیس در سوپرگروه مدیریت تلگرام.",
        "ton_wallet_address": "آدرس عمومی کیف پول تون (مانند UQ... یا EQ...) جهت دریافت وجه از کاربران.",
        "ton_rate_toman": "نرخ تبدیل هر یک تون به تومان جهت صدور فاکتور شارژ کیف پول.",
        "usdt_rate_toman": "نرخ هر تتر (USDT) به تومان جهت تبدیل قیمت دلاری تون در صرافی‌های جهانی.",
        "stars_rate_toman": "نرخ هر استارز تلگرام به تومان جهت شارژ کیف پول و خرید سرویس‌ها (پیشنهادی بدون ضرر: ۰.۰۱۳ × نرخ دلار).",
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
        "topic_alerts": "Telegram topic ID for system and reconcile alerts in admin supergroup.",
        "topic_reports": "Telegram topic ID for executive daily/nightly/weekly reports.",
        "topic_nodes": "Telegram topic ID for server connect/disconnect and node health alerts.",
        "topic_crypto": "Telegram topic ID for crypto rates and TON payment logs.",
        "topic_errors": "Telegram topic ID for system error logs and exceptions in admin supergroup.",
        "topic_backups": "Telegram topic ID for automated database backup files in admin supergroup.",
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
