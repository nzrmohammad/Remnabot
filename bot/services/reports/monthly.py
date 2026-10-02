"""User monthly reports generation and delivery."""
from datetime import datetime, timedelta
from html import escape
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.common import SEPARATOR
from bot.db.models import User
from bot.locales.texts import t
from bot.services.formatting import format_date, format_datetime, human_bytes
from bot.services.remnawave import RemnawaveClient
from bot.services.reports.common import (
    _node_label,
    _weekday_name,
)
from bot.services.reports.jalali import (
    jalali_month_range,
    month_name,
    prev_jalali_month_range,
)
from bot.services.reports.weekly import _week_total

logger = logging.getLogger(__name__)


async def _monthly_text_for_user(
    user: User, remnawave: RemnawaveClient, now: datetime
) -> str | None:
    accounts = await remnawave.get_users_by_telegram_id(user.telegram_id)
    if not accounts:
        return None
    lang = user.language or "fa"

    month_start, month_end = jalali_month_range(now)
    prev_start, prev_end = prev_jalali_month_range(now)

    # merge all accounts into one report (usually there is exactly one)
    day_totals: dict[str, int] = {}
    day_rows: dict[str, list[tuple[str, int]]] = {}
    node_totals: dict[str, int] = {}
    prev_total = 0

    for account in accounts:
        account_id = account.get("id")
        if account_id is None:
            continue
        series = (
            await remnawave.get_user_bandwidth_stats(
                int(account_id),
                month_start.strftime("%Y-%m-%d"),
                month_end.strftime("%Y-%m-%d"),
            )
            or []
        )
        prev_series = (
            await remnawave.get_user_bandwidth_stats(
                int(account_id),
                prev_start.strftime("%Y-%m-%d"),
                prev_end.strftime("%Y-%m-%d"),
            )
            or []
        )
        prev_total += _week_total(prev_series)

        for row in series:
            label = _node_label(row)
            node_totals[label] = node_totals.get(label, 0) + int(row.get("total") or 0)
            data = row.get("data") or []
            for offset, value in enumerate(data):
                day = (month_start + timedelta(days=offset)).strftime("%Y-%m-%d")
                value = int(value or 0)
                if value <= 0:
                    continue
                day_totals[day] = day_totals.get(day, 0) + value
                day_rows.setdefault(day, []).append((label, value))

    month_total = sum(day_totals.values())
    month = month_name(now, lang)

    lines = [
        f"{t(lang, 'monthly_title', month=month)} - {format_datetime(now, lang)}",
        SEPARATOR,
    ]

    # newest day first, like the weekly layout
    days_in_month = (month_end.date() - month_start.date()).days
    for offset in range(days_in_month, -1, -1):
        day_dt = month_start + timedelta(days=offset)
        day = day_dt.strftime("%Y-%m-%d")
        total = day_totals.get(day, 0)
        date_str = format_date(day_dt, lang)
        lines.append("")
        lines.append(t(lang, "monthly_day", date=date_str, total=human_bytes(total)))
        rows = sorted(day_rows.get(day, []), key=lambda x: x[1], reverse=True)
        if len(rows) == 1:
            lines.append(f"      ({rows[0][0]} {human_bytes(rows[0][1])})")
        elif len(rows) > 1:
            top_label, top_value = rows[0]
            rest = sum(v for _, v in rows[1:])
            lines.append(
                f"      ({top_label} {human_bytes(top_value)}، "
                f"{t(lang, 'monthly_others')} {human_bytes(rest)})"
            )

    lines += [
        "",
        t(lang, "monthly_total", total=human_bytes(month_total)),
        SEPARATOR,
    ]

    # personalized summary
    name = escape(
        str(accounts[0].get("username") or user.username or "")
    ) or "👤"
    lines.append(t(lang, "monthly_hi", name=name))
    summary = [t(lang, "monthly_sum_total", total=human_bytes(month_total), month=month)]

    if prev_total > 0 and month_total > 0:
        change = (month_total - prev_total) / prev_total * 100
        if change >= 5:
            summary.append(t(lang, "monthly_sum_more", percent=f"{change:.0f}"))
        elif change <= -5:
            summary.append(t(lang, "monthly_sum_less", percent=f"{abs(change):.0f}"))
        else:
            summary.append(t(lang, "monthly_sum_same"))

    if day_totals and node_totals:
        busiest_day = max(day_totals, key=day_totals.get)
        busiest_dt = datetime.strptime(busiest_day, "%Y-%m-%d")
        top_label = max(node_totals, key=node_totals.get)
        flag, _, node_name = top_label.partition(" ")
        summary.append(
            t(
                lang, "monthly_sum_top",
                day=_weekday_name(busiest_dt, lang),
                flag=flag,
                node=node_name,
            )
        )

    lines.append(" ".join(summary))
    return "\n".join(lines)


async def _send_monthly_for_user(
    bot: Bot, user: User, remnawave: RemnawaveClient, now: datetime
) -> None:
    text = await _monthly_text_for_user(user, remnawave, now)
    if not text:
        return
    try:
        await bot.send_message(user.telegram_id, text)
    except TelegramAPIError as exc:
        logger.warning("monthly report not delivered to %s: %s", user.telegram_id, exc)
