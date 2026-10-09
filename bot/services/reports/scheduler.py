"""Report background schedulers and sweep loops."""
import asyncio
from datetime import timedelta
import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import get_settings
from bot.db.repositories.report_repo import ReportRepository
from bot.db.repositories.user_repo import UserRepository
from bot.services.formatting import now_tz
from bot.services.remnawave import RemnawaveClient
from bot.services.reports.admin_summaries import (
    _send_admin_monthly_summary,
    _send_admin_nightly_summary,
    _send_admin_weekly_summary,
)
from bot.services.reports.common import (
    FRIDAY,
    MONTHLY_HOUR,
    MONTHLY_MINUTE,
    NIGHTLY_HOUR,
    NIGHTLY_MINUTE,
    WEEKLY_HOUR,
    WEEKLY_MINUTE,
)
from bot.services.reports.jalali import is_last_jalali_day
from bot.services.reports.monthly import _send_monthly_for_user
from bot.services.reports.nightly import _send_nightly_for_user
from bot.services.reports.weekly import _send_weekly_for_user

logger = logging.getLogger(__name__)


async def _sweep(
    bot: Bot,
    session_factory: async_sessionmaker,
    remnawave: RemnawaveClient,
    kind: str,  # "nightly" | "weekly" | "monthly"
) -> None:
    now = now_tz(get_settings().TIMEZONE)
    async with session_factory() as session:
        users = await UserRepository(session).all_users()
        report_repo = ReportRepository(session)
        for user in users:
            try:
                prefs = await report_repo.get_settings(user.telegram_id)
                if kind == "nightly" and prefs.nightly:
                    await _send_nightly_for_user(bot, user, remnawave, now, prefs)
                elif kind == "weekly" and prefs.weekly:
                    await _send_weekly_for_user(bot, user, remnawave, now, prefs)
                elif kind == "monthly" and prefs.monthly:
                    await _send_monthly_for_user(bot, user, remnawave, now, prefs)
            except Exception:  # noqa: BLE001 — one bad user must not stop the sweep
                logger.exception("%s report failed for %s", kind, user.telegram_id)

        # Deliver dedicated executive report to admin
        if kind == "nightly":
            try:
                await _send_admin_nightly_summary(bot, session, remnawave, now)
            except Exception:
                logger.exception("Admin nightly summary sweep failed")
        elif kind == "weekly":
            try:
                await _send_admin_weekly_summary(bot, session, remnawave, now)
            except Exception:
                logger.exception("Admin weekly summary sweep failed")
        elif kind == "monthly":
            try:
                await _send_admin_monthly_summary(bot, session, remnawave, now)
            except Exception:
                logger.exception("Admin monthly summary sweep failed")

        await session.commit()


def _seconds_until(hour: int, minute: int, weekday: int | None = None) -> float:
    """Seconds until the next occurrence of HH:MM (optionally on a given
    python weekday) in the configured timezone."""
    now = now_tz(get_settings().TIMEZONE)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if weekday is None:
        if target <= now:
            target += timedelta(days=1)
    else:
        target += timedelta(days=(weekday - now.weekday()) % 7)
        if target <= now:
            target += timedelta(days=7)
    return max(1.0, (target - now).total_seconds())


async def nightly_report_loop(
    bot: Bot, session_factory: async_sessionmaker, remnawave: RemnawaveClient
) -> None:
    while True:
        wait = _seconds_until(NIGHTLY_HOUR, NIGHTLY_MINUTE)
        logger.info("nightly report in %.0f s", wait)
        await asyncio.sleep(wait)
        now = now_tz(get_settings().TIMEZONE)
        # Skip on Friday (handled by weekly report) and on the last day of Jalali month (handled by monthly report)
        if now.weekday() == FRIDAY:
            logger.info("Skipping nightly report on Friday (covered by weekly report).")
        elif is_last_jalali_day(now):
            logger.info("Skipping nightly report on last day of Jalali month (covered by monthly report).")
        else:
            try:
                await _sweep(bot, session_factory, remnawave, "nightly")
            except Exception:  # noqa: BLE001
                logger.exception("nightly sweep failed")
        await asyncio.sleep(120)  # make sure we roll past 23:59


async def weekly_report_loop(
    bot: Bot, session_factory: async_sessionmaker, remnawave: RemnawaveClient
) -> None:
    while True:
        wait = _seconds_until(WEEKLY_HOUR, WEEKLY_MINUTE, weekday=FRIDAY)
        logger.info("weekly report in %.0f s", wait)
        await asyncio.sleep(wait)
        now = now_tz(get_settings().TIMEZONE)
        # Skip weekly report if Friday happens to be the last day of the Jalali month
        if is_last_jalali_day(now):
            logger.info("Skipping weekly report on last day of Jalali month (covered by monthly report).")
        else:
            try:
                await _sweep(bot, session_factory, remnawave, "weekly")
            except Exception:  # noqa: BLE001
                logger.exception("weekly sweep failed")
        await asyncio.sleep(120)  # make sure we roll past 23:59


def _seconds_until_month_end() -> float:
    """Seconds until 23:59 on the next LAST day of the Jalali month.

    Scans the coming days and picks the nearest future 23:59 whose date
    is the last day of its Jalali month (Esfand 29/30 handled by jdatetime,
    so leap years just work).
    """
    now = now_tz(get_settings().TIMEZONE)
    for delta in range(0, 32):
        day = (now + timedelta(days=delta)).replace(
            hour=MONTHLY_HOUR, minute=MONTHLY_MINUTE, second=0, microsecond=0
        )
        if day <= now:
            continue
        if is_last_jalali_day(day):
            return max(1.0, (day - now).total_seconds())
    return 24 * 3600.0  # unreachable in practice; retry tomorrow


async def monthly_report_loop(
    bot: Bot, session_factory: async_sessionmaker, remnawave: RemnawaveClient
) -> None:
    while True:
        wait = _seconds_until_month_end()
        logger.info("monthly report in %.0f s", wait)
        await asyncio.sleep(wait)
        try:
            await _sweep(bot, session_factory, remnawave, "monthly")
        except Exception:  # noqa: BLE001
            logger.exception("monthly sweep failed")
        # Roll past 23:59 so the same month-end is not picked twice.
        await asyncio.sleep(120)


async def wheel_reminder_loop(
    bot: Bot, session_factory: async_sessionmaker
) -> None:
    """Check every 60 seconds if any user's 24h wheel cooldown has elapsed,
    and send a Telegram reminder if enabled."""
    from aiogram.types import WebAppInfo
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    from bot.db.repositories.user_repo import UserRepository
    from bot.locales.texts import t

    while True:
        try:
            await asyncio.sleep(60)
            async with session_factory() as session:
                rep_repo = ReportRepository(session)
                user_repo = UserRepository(session)
                due_prefs = await rep_repo.get_users_due_for_wheel_reminder()
                if due_prefs:
                    settings = get_settings()
                    web_app_url = (settings.WEB_APP_URL or "").strip()
                    if web_app_url and not web_app_url.startswith(("http://", "https://")):
                        web_app_url = f"https://{web_app_url}"

                    for prefs in due_prefs:
                        try:
                            user = await user_repo.get_by_telegram_id(prefs.telegram_id)
                            lang = (user.language if user else None) or "fa"
                            text = t(lang, "wheel_ready_notify")

                            kb = InlineKeyboardBuilder()
                            if web_app_url:
                                kb.button(text="🎡 چرخاندن گردونه شانس", web_app=WebAppInfo(url=web_app_url))
                            else:
                                kb.button(text="🏠 منوی اصلی", callback_data="nav:main_menu")

                            await bot.send_message(
                                prefs.telegram_id,
                                text,
                                reply_markup=kb.as_markup(),
                            )
                            prefs.wheel_notified = True
                        except Exception as exc:
                            logger.warning(
                                "Failed to send wheel reminder to %s: %s",
                                prefs.telegram_id,
                                exc,
                            )
                            prefs.wheel_notified = True  # Prevent endless retry flood
                    await session.commit()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.exception("Error in wheel_reminder_loop: %s", exc)
            await asyncio.sleep(10)

