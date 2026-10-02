"""Background job: usage / expiry alerts.

Runs every ALERT_CHECK_INTERVAL_MINUTES. For every known bot user it
fetches the panel accounts and sends a warning when

  * used traffic crossed the user's configured percentage, or
  * the expiry date is closer than the user's configured number of days.

Each alert fires exactly once per crossing: the sent-flag is stored in
`alert_state` and re-armed automatically when the account is renewed
(usage drops below the threshold / expiry moves away again).
"""
import asyncio
from html import escape
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import get_settings
from bot.db.models import User
from bot.db.repositories.alert_repo import AlertRepository
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.formatting import format_date, human_bytes, now_tz, parse_iso
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)


def _alert_keyboard(lang: str, account_id: int | str | None = None):
    """تمدید این اکانت (if known) + سرویس‌ها | کیف پول."""
    kb = InlineKeyboardBuilder()
    if account_id is not None:
        kb.button(
            text=t(lang, "btn_renew_account"),
            callback_data=f"svc:renacc:{account_id}",
        )
        kb.adjust(1)
    kb.button(text=t(lang, "btn_services"), callback_data="alert:goto:services")
    kb.button(text=t(lang, "btn_wallet"), callback_data="alert:goto:wallet")
    kb.adjust(2)
    return kb.as_markup()


async def _send_alert(
    bot: Bot, telegram_id: int, lang: str, text: str,
    account_id: int | str | None = None,
) -> bool:
    try:
        await bot.send_message(
            telegram_id, text, reply_markup=_alert_keyboard(lang, account_id)
        )
        return True
    except TelegramAPIError as exc:
        # user blocked the bot, deleted the chat, ...
        logger.warning("alert not delivered to %s: %s", telegram_id, exc)
        return False


async def _check_user(
    bot: Bot,
    user: User,
    alert_repo: AlertRepository,
    remnawave: RemnawaveClient,
    now: datetime,
    accounts: list[dict] | None = None,
) -> None:
    prefs = await alert_repo.get_settings(user.telegram_id)
    if prefs.traffic_percent <= 0 and prefs.expire_days <= 0:
        return

    if accounts is None:
        accounts = await remnawave.get_users_by_telegram_id(user.telegram_id)
    if accounts is None:
        return  # panel down — skip this round, keep is_verified untouched
    lang = user.language or "fa"

    for account in accounts:
        account_id = account.get("id")
        if account_id is None:
            continue
        state = await alert_repo.get_state(str(account_id), user.telegram_id)
        username = escape(str(account.get("username", "—")))

        # ---- traffic ------------------------------------------------- #
        limit = int(account.get("trafficLimitBytes") or 0)
        traffic = account.get("userTraffic") or {}
        used = int(traffic.get("usedTrafficBytes") or account.get("usedTrafficBytes") or 0)

        if prefs.traffic_percent > 0 and limit > 0:
            percent = used / limit * 100
            if percent >= prefs.traffic_percent:
                if not state.traffic_alerted:
                    text = t(
                        lang, "alert_traffic",
                        username=username,
                        percent=f"{min(100.0, percent):.0f}",
                        remaining=human_bytes(max(0, limit - used)),
                    )
                    if await _send_alert(bot, user.telegram_id, lang, text, account_id=account_id):
                        state.traffic_alerted = True
            else:
                # renewed / traffic reset → re-arm
                state.traffic_alerted = False

        # ---- expiry --------------------------------------------------- #
        expire_at = parse_iso(account.get("expireAt"))
        if prefs.expire_days > 0 and expire_at is not None:
            days_left = (expire_at - now).days
            if days_left <= prefs.expire_days:
                if not state.expire_alerted:
                    date_str = format_date(expire_at.astimezone(now.tzinfo), lang)
                    if days_left >= 1:
                        text = t(
                            lang, "alert_expire",
                            username=username, days=days_left, date=date_str,
                        )
                    else:
                        text = t(
                            lang, "alert_expire_now",
                            username=username, date=date_str,
                        )
                    if await _send_alert(bot, user.telegram_id, lang, text, account_id=account_id):
                        state.expire_alerted = True
            else:
                # renewed → re-arm
                state.expire_alerted = False


async def run_alert_check(
    bot: Bot,
    session_factory: async_sessionmaker,
    remnawave: RemnawaveClient,
) -> None:
    now = now_tz(get_settings().TIMEZONE)
    panel_users = await remnawave.get_all_panel_users()
    panel_by_tid: dict[int, list[dict]] = {}
    if panel_users is not None:
        for acc in panel_users:
            tg_id = acc.get("telegramId") or acc.get("telegram_id")
            if tg_id:
                try:
                    panel_by_tid.setdefault(int(tg_id), []).append(acc)
                except (ValueError, TypeError):
                    pass

    async with session_factory() as session:
        user_repo = UserRepository(session)
        alert_repo = AlertRepository(session)
        users = await user_repo.all_users()
        for user in users:
            try:
                user_accounts = panel_by_tid.get(user.telegram_id) if panel_users is not None else None
                await _check_user(bot, user, alert_repo, remnawave, now, accounts=user_accounts)
            except Exception:  # noqa: BLE001 — one bad user must not stop the sweep
                logger.exception("alert check failed for user %s", user.telegram_id)
        await session.commit()


async def alerts_loop(
    bot: Bot,
    session_factory: async_sessionmaker,
    remnawave: RemnawaveClient,
) -> None:
    interval = max(5, get_settings().ALERT_CHECK_INTERVAL_MINUTES) * 60
    await asyncio.sleep(30)  # let startup finish first
    logger.info("alerts loop started (every %s s)", interval)
    while True:
        try:
            await run_alert_check(bot, session_factory, remnawave)
        except Exception:  # noqa: BLE001
            logger.exception("alert sweep failed")
        await asyncio.sleep(interval)
