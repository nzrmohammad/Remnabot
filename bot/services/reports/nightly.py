"""User nightly reports generation and delivery."""
from datetime import datetime, timedelta
from html import escape
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.common import SEPARATOR
from bot.db.models import User
from bot.locales.texts import t
from bot.services.formatting import format_date, format_datetime, human_bytes, parse_iso
from bot.services.remnawave import RemnawaveClient
from bot.services.reports.common import (
    MAX_BREAKDOWN_DAYS,
    _breakdown_lines,
    _node_label,
    _series_rows,
)

logger = logging.getLogger(__name__)


async def _nightly_account_block(
    remnawave: RemnawaveClient, account: dict, now: datetime, lang: str
) -> str:
    username = escape(str(account.get("username", "—")))
    limit = int(account.get("trafficLimitBytes") or 0)
    traffic = account.get("userTraffic") or {}
    used = int(traffic.get("usedTrafficBytes") or account.get("usedTrafficBytes") or 0)

    lines = [f"{t(lang, 'stats_account')} : <code>{username}</code>"]

    if limit > 0:
        lines.append(f"{t(lang, 'stats_total')} : <b>{human_bytes(limit)}</b>")
    else:
        lines.append(f"{t(lang, 'stats_total')} : {t(lang, 'stats_unlimited')}")

    # per-node used volume since the last traffic reset (capped window)
    since = parse_iso(account.get("lastTrafficResetAt")) or parse_iso(
        account.get("createdAt")
    )
    start = now - timedelta(days=MAX_BREAKDOWN_DAYS)
    if since is not None and since > start:
        start = since
    today_str = now.strftime("%Y-%m-%d")

    series: list[dict] = []
    account_id = account.get("id")
    if account_id:
        series = (
            await remnawave.get_user_bandwidth_stats(
                int(account_id), start.strftime("%Y-%m-%d"), today_str
            )
            or []
        )
    rows = _series_rows(series)

    lines.append(f"{t(lang, 'stats_used')} : <b>{human_bytes(used)}</b>")
    lines += _breakdown_lines(rows)

    if limit > 0:
        lines.append(
            f"{t(lang, 'stats_remaining')} : <b>{human_bytes(max(0, limit - used))}</b>"
        )

    # today's usage per node: the query range ends today, so today is the
    # LAST element of each node's data array
    today_lines = []
    today_total = 0
    for row in rows:
        data = row.get("data") or []
        value = int(data[-1]) if data else 0
        if value > 0:
            today_lines.append(f"{_node_label(row)} : {human_bytes(value)}")
            today_total += value
    if today_lines:
        lines.append(t(lang, "report_today_breakdown"))
        lines += today_lines

    # expiry
    expire_at = parse_iso(account.get("expireAt"))
    if expire_at is None:
        lines.append(f"{t(lang, 'stats_expire')} : {t(lang, 'stats_no_expire')}")
    else:
        delta_days = (expire_at - now).days
        date_str = format_date(expire_at.astimezone(now.tzinfo), lang)
        if delta_days >= 0:
            when = t(lang, "stats_days_left", days=delta_days)
        else:
            when = t(lang, "stats_expired_ago", days=abs(delta_days))
        lines.append(f"{t(lang, 'stats_expire')} : <b>{when}</b> ({date_str})")

    lines.append(f"{t(lang, 'stats_today')} : <b>{human_bytes(today_total)}</b>")
    return "\n".join(lines)


async def _send_nightly_for_user(
    bot: Bot, user: User, remnawave: RemnawaveClient, now: datetime
) -> None:
    accounts = await remnawave.get_users_by_telegram_id(user.telegram_id)
    if not accounts:
        return
    lang = user.language or "fa"

    blocks = []
    for account in accounts:
        blocks.append(await _nightly_account_block(remnawave, account, now, lang))

    text = (
        f"{t(lang, 'nightly_title')} - {format_datetime(now, lang)}\n"
        f"{SEPARATOR}\n" + f"\n{SEPARATOR}\n".join(blocks)
    )
    try:
        await bot.send_message(user.telegram_id, text)
    except TelegramAPIError as exc:
        logger.warning("nightly report not delivered to %s: %s", user.telegram_id, exc)
