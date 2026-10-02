"""Expiry lifecycle job: renewal reminders + grace period + auto-disable.

Runs every EXPIRY_CHECK_INTERVAL_MINUTES (default 60):

- days_left in EXPIRY_REMIND_DAYS (e.g. 3,1,0) -> send `expiry_reminder`
  with a Renew button (`svc:renacc:{panelId}`) that jumps straight into
  the purchase flow for that account.
- days_left < 0 and within grace (0 > days_left >= -GRACE) ->
  send `expiry_expired_grace` once per day-left value.
- days_left < -GRACE and account still ACTIVE -> DISABLE it in the panel
  via `set_user_status(DISABLED)` and send `expiry_disabled` once.
- Renewal re-arms everything: if days_left goes back above thresholds,
  `last_days_left` is updated and `disabled_notified` is reset.

State is kept in `expiry_state` (one row per panel account) so each
notice fires exactly once per days-left value, even with hourly sweeps.
Panel-down rounds are skipped silently (no de-verify, no disable).
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import get_settings
from bot.db.models import ExpiryState
from bot.db.repositories.user_repo import UserRepository
from bot.locales.texts import t
from bot.services.formatting import format_date, now_tz, parse_iso
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)


def _parse_remind_days(raw: str) -> set[int]:
    out: set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            try:
                out.add(int(part))
            except ValueError:
                continue
    return out or {3, 1, 0}


def _renew_keyboard(lang: str, account_id: int | str):
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "btn_renew_now"), callback_data=f"svc:renacc:{account_id}")
    kb.button(text=t(lang, "btn_services"), callback_data="alert:goto:services")
    kb.button(text=t(lang, "btn_wallet"), callback_data="alert:goto:wallet")
    kb.adjust(1, 2)
    return kb.as_markup()


async def _get_state(session, account_id: str, telegram_id: int) -> ExpiryState:
    result = await session.execute(
        select(ExpiryState).where(ExpiryState.account_id == account_id)
    )
    state = result.scalar_one_or_none()
    if state is None:
        state = ExpiryState(
            account_id=account_id, telegram_id=telegram_id, last_days_left=None,
            disabled_notified=False,
        )
        session.add(state)
        await session.flush()
    return state


async def run_expiry_check(
    bot: Bot,
    session_factory: async_sessionmaker,
    remnawave: RemnawaveClient,
) -> None:
    settings = get_settings()
    tz = settings.TIMEZONE
    now = now_tz(tz)
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
        from bot.services.app_settings import get_store_settings
        store = await get_store_settings(session)
        grace = max(0, store.expiry_grace_days)
        remind_days = _parse_remind_days(store.expiry_remind_days)

        users = await UserRepository(session).all_users()
        for user in users:
            try:
                accounts = panel_by_tid.get(user.telegram_id) if panel_users is not None else await remnawave.get_users_by_telegram_id(user.telegram_id)
                if accounts is None:
                    continue  # panel down — skip silently
                lang = user.language or "fa"
                for account in accounts:
                    account_id = account.get("id")
                    if account_id is None:
                        continue
                    expire_at = parse_iso(account.get("expireAt"))
                    if expire_at is None:
                        continue  # unlimited — nothing to do
                    days_left = (expire_at - now).days
                    username = str(account.get("username", "—"))
                    date_str = format_date(expire_at.astimezone(now.tzinfo), lang)
                    state = await _get_state(session, str(account_id), user.telegram_id)

                    # Renewed -> re-arm disabled notice.
                    if days_left >= 0:
                        if state.disabled_notified:
                            state.disabled_notified = False

                    # --- auto-disable after grace ---------------------- #
                    if days_left < -grace:
                        status = str(account.get("status", "")).upper()
                        if status not in ("DISABLED", "EXPIRED"):
                            updated = await remnawave.set_user_status(
                                int(account_id), "DISABLED"
                            )
                            if updated is None:
                                continue  # panel error — retry next round
                        if not state.disabled_notified:
                            try:
                                await bot.send_message(
                                    user.telegram_id,
                                    t(lang, "expiry_disabled", username=username),
                                    reply_markup=_renew_keyboard(lang, account_id),
                                )
                                state.disabled_notified = True
                                state.last_days_left = days_left
                            except TelegramAPIError:
                                logger.warning(
                                    "expiry disabled notice failed for %s", user.telegram_id
                                )
                        continue

                    # --- grace period notice --------------------------- #
                    if days_left < 0:
                        if state.last_days_left != days_left:
                            try:
                                await bot.send_message(
                                    user.telegram_id,
                                    t(
                                        lang, "expiry_expired_grace",
                                        username=username, date=date_str,
                                        grace=(days_left + grace + 1),
                                    ),
                                    reply_markup=_renew_keyboard(lang, account_id),
                                )
                                state.last_days_left = days_left
                            except TelegramAPIError:
                                logger.warning(
                                    "expiry grace notice failed for %s", user.telegram_id
                                )
                        continue

                    # --- pre-expiry reminders -------------------------- #
                    if days_left in remind_days and state.last_days_left != days_left:
                        try:
                            await bot.send_message(
                                user.telegram_id,
                                t(
                                    lang, "expiry_reminder",
                                    days=days_left, username=username, date=date_str,
                                ),
                                reply_markup=_renew_keyboard(lang, account_id),
                            )
                            state.last_days_left = days_left
                        except TelegramAPIError:
                            logger.warning(
                                "expiry reminder failed for %s", user.telegram_id
                            )
                    elif days_left not in remind_days and state.last_days_left != days_left:
                        # Keep last_days_left fresh so a later crossing fires.
                        # Only move forward (renewal pushes days_left up).
                        if state.last_days_left is None or days_left > state.last_days_left:
                            state.last_days_left = days_left
            except Exception:  # noqa: BLE001 — one bad user must not stop the sweep
                logger.exception("expiry check failed for user %s", user.telegram_id)
        await session.commit()


async def expiry_loop(
    bot: Bot,
    session_factory: async_sessionmaker,
    remnawave: RemnawaveClient,
) -> None:
    interval = max(5, get_settings().EXPIRY_CHECK_INTERVAL_MINUTES) * 60
    await asyncio.sleep(45)  # let startup finish first
    logger.info("expiry loop started (every %s s)", interval)
    while True:
        try:
            await run_expiry_check(bot, session_factory, remnawave)
        except Exception:  # noqa: BLE001
            logger.exception("expiry sweep failed")
        await asyncio.sleep(interval)
