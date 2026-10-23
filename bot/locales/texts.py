"""All bot texts. Add a new language by adding a new key to TEXTS."""
from bot.locales.en import EN_TEXTS
from bot.locales.fa import FA_TEXTS

# Shown before the user has picked a language → must be bilingual.
CHOOSE_LANGUAGE = (
    "🌐 <b>Please choose your language</b>\n"
    "🌐 <b>لطفاً زبان خود را انتخاب کنید</b>"
)

# Shown to brand-new users while maintenance mode is on → must be bilingual.
MAINTENANCE_NOTICE = (
    "🛠 <b>The bot is under maintenance. Please try again later.</b>\n"
    "🛠 <b>ربات در حال بروزرسانی است. لطفاً کمی بعد دوباره تلاش کنید.</b>"
)

# Shown to brand-new users when invite-only mode is active and they lack an invite code.
INVITE_ONLY_NOTICE = (
    "🔒 <b>سامانه خصوصی — عضویت فقط با دعوت‌نامه</b>\n"
    "──────────────────\n"
    "کاربر گرامی، در حال حاضر ثبت‌نام و عضویت در این سامانه <b>تنها از طریق لینک اختصاصی دعوت اعضا</b> امکان‌پذیر است.\n\n"
    "🔹 چنانچه لینک دعوت دارید، لطفاً مجدداً با لمس همان لینک وارد ربات شوید.\n"
    "🔹 در غیر این صورت، جهت کسب اطلاعات بیشتر و دریافت دسترسی می‌توانید با پشتیبانی در ارتباط باشید."
)

TEXTS: dict[str, dict[str, str]] = {
    "en": EN_TEXTS,
    "fa": FA_TEXTS,
}

DEFAULT_LANG = "fa"


def t(lang: str | None, key: str, **kwargs) -> str:
    """Translate a key for the given language with optional formatting."""
    lang = lang if lang in TEXTS else DEFAULT_LANG
    text = TEXTS[lang].get(key, key)
    return text.format(**kwargs) if kwargs else text
