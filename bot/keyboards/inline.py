"""Inline keyboards. Telegram renders row items left→right,
so for the requested RTL layout the *right-side* button is the
second item in each row.
"""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.locales.texts import t


def language_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🇮🇷 فارسی", callback_data="lang:fa")
    kb.button(text="🇬🇧 English", callback_data="lang:en")
    kb.adjust(2)
    return kb.as_markup()


def welcome_keyboard(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_login"), callback_data="auth:login")
    kb.button(text=t(lang, "btn_new_service"), callback_data="service:new")
    kb.adjust(1)
    return kb.as_markup()


def back_keyboard(lang: str, target: str = "nav:welcome") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back"), callback_data=target)
    return kb.as_markup()


def main_menu_keyboard(lang: str, is_admin: bool) -> InlineKeyboardMarkup:
    """Requested layout (right | left):
    آمار فوری      | مدیریت اکانت
    کیف پول        | سرویس‌ها
    آموزش          | تنظیمات
    پشتیبانی       | حساب کاربری
    پنل مدیریت (full width, admins only)
    """
    kb = InlineKeyboardBuilder()
    # row 1  (left item first, right item second)
    kb.button(text=t(lang, "btn_account_mgmt"), callback_data="menu:account")
    kb.button(text=t(lang, "btn_quick_stats"), callback_data="menu:stats")
    # row 2
    kb.button(text=t(lang, "btn_services"), callback_data="menu:services")
    kb.button(text=t(lang, "btn_wallet"), callback_data="menu:wallet")
    # row 3
    kb.button(text=t(lang, "btn_settings"), callback_data="menu:settings")
    kb.button(text=t(lang, "btn_connection_guide"), callback_data="menu:guide")
    # row 4
    kb.button(text=t(lang, "btn_profile"), callback_data="menu:profile")
    kb.button(text=t(lang, "btn_support"), callback_data="menu:support")

    sizes = [2, 2, 2, 2]
    if is_admin:
        kb.button(text=t(lang, "btn_admin_panel"), callback_data="menu:admin")
        sizes.append(1)

    kb.adjust(*sizes)
    return kb.as_markup()


def back_to_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_back_to_menu"), callback_data="nav:main_menu")
    return kb.as_markup()
