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
    "🔒 <b>Private System — Invite Only</b>\n"
    "Registration is currently available only via a member's invite link. "
    "If you have one, tap it again to enter, or contact support.\n\n"
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

SUPPORTED_LANGS: tuple[str, ...] = tuple(TEXTS.keys())
DEFAULT_LANG = "fa"


def normalize_lang(lang: str | None) -> str:
    """Normalize BCP-47 / Telegram language codes (e.g. 'en-US' → 'en', 'fa-IR' → 'fa')."""
    if not isinstance(lang, str):
        return DEFAULT_LANG
    base = lang.strip().lower().replace("_", "-").split("-", 1)[0]
    return base if base in TEXTS else DEFAULT_LANG


def t(lang: str | None, key: str, **kwargs) -> str:
    """Translate a key for the normalized language with safe formatting fallback."""
    norm = normalize_lang(lang)
    text = TEXTS[norm].get(key) or TEXTS[DEFAULT_LANG].get(key, key)
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, ValueError, IndexError):
        return text
