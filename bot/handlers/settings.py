"""Settings section: per-user alert thresholds.

The user picks at which usage percentage and how many days before
expiry the background alert job (services/alerts.py) should warn them.
A value of 0 turns that alert off.
"""
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.repositories.alert_repo import AlertRepository
from bot.db.repositories.report_repo import ReportRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.menu import render_menu

logger = logging.getLogger(__name__)
router = Router(name="settings")

SEPARATOR = "─" * 18

TRAFFIC_CHOICES = [70, 75, 80, 85, 90, 95]
EXPIRE_CHOICES = [1, 2, 3, 5, 7]


def _fmt_traffic(percent: int, lang: str) -> str:
    if percent <= 0:
        return t(lang, "alerts_off")
    return t(lang, "settings_percent_value", percent=percent)


def _fmt_days(days: int, lang: str) -> str:
    if days <= 0:
        return t(lang, "alerts_off")
    return t(lang, "settings_days_value", days=days)


def _fmt_toggle(value: bool, lang: str = "fa") -> str:
    return "🟢" if value else "🔴"


async def _render_settings(
    bot: Bot,
    user,
    user_repo: UserRepository,
    alert_repo: AlertRepository,
    report_repo: ReportRepository,
    lang: str,
) -> None:
    prefs = await alert_repo.get_settings(user.telegram_id)
    reports = await report_repo.get_settings(user.telegram_id)

    text = "\n".join(
        [
            t(lang, "settings_title"),
            SEPARATOR,
            f"{t(lang, 'settings_traffic_label')} : "
            f"<b>{_fmt_traffic(prefs.traffic_percent, lang)}</b>",
            f"▫️ {t(lang, 'settings_traffic_hint')}",
            "",
            f"{t(lang, 'settings_expire_label')} : "
            f"<b>{_fmt_days(prefs.expire_days, lang)}</b>",
            f"▫️ {t(lang, 'settings_expire_hint')}",
            "",
            f"{t(lang, 'settings_nightly_label')} : "
            f"<b>{_fmt_toggle(reports.nightly, lang)}</b>",
            f"▫️ {t(lang, 'settings_nightly_hint')}",
            "",
            f"{t(lang, 'settings_weekly_label')} : "
            f"<b>{_fmt_toggle(reports.weekly, lang)}</b>",
            f"▫️ {t(lang, 'settings_weekly_hint')}",
            "",
            f"{t(lang, 'settings_monthly_label')} : "
            f"<b>{_fmt_toggle(reports.monthly, lang)}</b>",
            f"▫️ {t(lang, 'settings_monthly_hint')}",
        ]
    )

    kb = InlineKeyboardBuilder()
    # ردیف ۱: تنظیم هشدارهای حجم و انقضا
    kb.button(text=t(lang, "btn_set_traffic"), callback_data="set:traffic")
    kb.button(text=t(lang, "btn_set_expire"), callback_data="set:expire")

    # ردیف ۲: گزارش‌های هفتگی و شبانه (جابجا شده)
    kb.button(
        text=t(lang, "btn_toggle_weekly", state=_fmt_toggle(reports.weekly, lang)),
        callback_data="set:wr",
    )
    kb.button(
        text=t(lang, "btn_toggle_nightly", state=_fmt_toggle(reports.nightly, lang)),
        callback_data="set:nr",
    )

    # ردیف ۳: تغییر زبان و گزارش ماهانه (جابجا شده)
    kb.button(text=t(lang, "btn_language"), callback_data="set:lang")
    kb.button(
        text=t(lang, "btn_toggle_monthly", state=_fmt_toggle(reports.monthly, lang)),
        callback_data="set:mr",
    )

    # ردیف ۴: منوی اصلی
    menu_label = "🏠 منوی اصلی" if lang == "fa" else "🏠 Main Menu"
    kb.button(text=menu_label, callback_data="nav:main_menu")

    kb.adjust(2, 2, 2, 1)

    await render_menu(bot, user, user_repo, text, kb.as_markup())


@router.callback_query(F.data == "set:lang")
async def pick_language(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository,
):
    from bot.keyboards.inline import language_keyboard

    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await render_menu(
        bot, user, user_repo,
        "🌐 <b>Language / زبان</b>",
        language_keyboard(),
    )
    await call.answer()


@router.callback_query(F.data == "menu:settings")
async def settings_entry(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_settings(
        bot, user, user_repo,
        AlertRepository(session), ReportRepository(session), user.language,
    )
    await call.answer()


@router.callback_query(F.data == "set:nr")
async def toggle_nightly(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    report_repo = ReportRepository(session)
    await report_repo.toggle_nightly(user.telegram_id)
    await _render_settings(
        bot, user, user_repo, AlertRepository(session), report_repo, user.language
    )
    await call.answer(t(user.language, "settings_saved"))


@router.callback_query(F.data == "set:wr")
async def toggle_weekly(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    report_repo = ReportRepository(session)
    await report_repo.toggle_weekly(user.telegram_id)
    await _render_settings(
        bot, user, user_repo, AlertRepository(session), report_repo, user.language
    )
    await call.answer(t(user.language, "settings_saved"))


@router.callback_query(F.data == "set:mr")
async def toggle_monthly(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    report_repo = ReportRepository(session)
    await report_repo.toggle_monthly(user.telegram_id)
    await _render_settings(
        bot, user, user_repo, AlertRepository(session), report_repo, user.language
    )
    await call.answer(t(user.language, "settings_saved"))


@router.callback_query(F.data == "set:traffic")
async def pick_traffic(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language
    prefs = await AlertRepository(session).get_settings(user.telegram_id)

    kb = InlineKeyboardBuilder()
    for percent in TRAFFIC_CHOICES:
        mark = " ✅" if prefs.traffic_percent == percent else ""
        kb.button(text=f"{percent}%{mark}", callback_data=f"set:tp:{percent}")
    mark = " ✅" if prefs.traffic_percent <= 0 else ""
    kb.button(text=f"{t(lang, 'alerts_off')}{mark}", callback_data="set:tp:0")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:settings")
    kb.adjust(3, 3, 1, 1)

    text = f"{t(lang, 'settings_title')}\n{SEPARATOR}\n{t(lang, 'settings_pick_traffic')}"
    await render_menu(bot, user, user_repo, text, kb.as_markup())
    await call.answer()


@router.callback_query(F.data == "set:expire")
async def pick_expire(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    lang = user.language
    prefs = await AlertRepository(session).get_settings(user.telegram_id)

    kb = InlineKeyboardBuilder()
    for days in EXPIRE_CHOICES:
        mark = " ✅" if prefs.expire_days == days else ""
        kb.button(
            text=f"{_fmt_days(days, lang)}{mark}", callback_data=f"set:ed:{days}"
        )
    mark = " ✅" if prefs.expire_days <= 0 else ""
    kb.button(text=f"{t(lang, 'alerts_off')}{mark}", callback_data="set:ed:0")
    kb.button(text=t(lang, "btn_back"), callback_data="menu:settings")
    kb.adjust(3, 3, 1, 1)

    text = f"{t(lang, 'settings_title')}\n{SEPARATOR}\n{t(lang, 'settings_pick_expire')}"
    await render_menu(bot, user, user_repo, text, kb.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith("set:tp:"))
async def set_traffic(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession
):
    try:
        percent = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if percent not in (0, *TRAFFIC_CHOICES) or not 0 <= percent <= 100:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    alert_repo = AlertRepository(session)
    await alert_repo.set_traffic_percent(user.telegram_id, percent)
    await _render_settings(
        bot, user, user_repo, alert_repo, ReportRepository(session), user.language
    )
    await call.answer(t(user.language, "settings_saved"))


@router.callback_query(F.data.startswith("set:ed:"))
async def set_expire(
    call: CallbackQuery, bot: Bot, user_repo: UserRepository, session: AsyncSession
):
    try:
        days = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    if days not in (0, *EXPIRE_CHOICES) or not 0 <= days <= 30:
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    alert_repo = AlertRepository(session)
    await alert_repo.set_expire_days(user.telegram_id, days)
    await _render_settings(
        bot, user, user_repo, alert_repo, ReportRepository(session), user.language
    )
    await call.answer(t(user.language, "settings_saved"))
