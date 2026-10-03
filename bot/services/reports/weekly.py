"""User weekly reports generation and delivery."""
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
    make_node_flag_map,
)

logger = logging.getLogger(__name__)


def _week_total(series: list[dict]) -> int:
    return sum(int(r.get("total") or 0) for r in series)


async def _weekly_text_for_user(
    user: User, remnawave: RemnawaveClient, now: datetime
) -> str | None:
    accounts = await remnawave.get_users_by_telegram_id(user.telegram_id)
    if not accounts:
        return None
    lang = user.language or "fa"

    week_start = now - timedelta(days=6)
    prev_start, prev_end = now - timedelta(days=13), now - timedelta(days=7)

    # Gather series across all accounts to build node flag map and stats
    all_account_series: list[tuple[dict, list[dict], list[dict]]] = []
    all_nodes: list[dict] = []
    for account in accounts:
        account_id = account.get("id")
        if account_id is None:
            continue
        series = (
            await remnawave.get_user_bandwidth_stats(
                int(account_id), week_start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")
            )
            or []
        )
        prev_series = (
            await remnawave.get_user_bandwidth_stats(
                int(account_id), prev_start.strftime("%Y-%m-%d"), prev_end.strftime("%Y-%m-%d")
            )
            or []
        )
        all_account_series.append((account, series, prev_series))
        all_nodes.extend(series)

    flag_map = make_node_flag_map(all_nodes)

    day_totals: dict[str, int] = {}
    day_rows: dict[str, list[tuple[str, int]]] = {}
    node_totals: dict[str, int] = {}
    prev_total = 0

    for account, series, prev_series in all_account_series:
        prev_total += _week_total(prev_series)

        for row in series:
            name = row.get("name") or row.get("nodeName") or "—"
            lbl = flag_map.get(name) or country_flag(row.get("countryCode"))
            node_totals[lbl] = node_totals.get(lbl, 0) + int(row.get("total") or 0)
            data = row.get("data") or []
            last_7 = data[-7:] if len(data) >= 7 else ([0] * (7 - len(data)) + data)
            for offset in range(7):
                day = (week_start + timedelta(days=offset)).strftime("%Y-%m-%d")
                value = int(last_7[offset] or 0)
                if value <= 0:
                    continue
                day_totals[day] = day_totals.get(day, 0) + value
                day_rows.setdefault(day, []).append((lbl, value))

    week_total = sum(day_totals.values())

    lines = [
        f"{t(lang, 'weekly_title')} - {format_datetime(now, lang)}",
        SEPARATOR,
    ]

    # newest day first, like the requested layout
    for offset in range(6, -1, -1):
        day_dt = week_start + timedelta(days=offset)
        day = day_dt.strftime("%Y-%m-%d")
        total = day_totals.get(day, 0)
        d_name = _weekday_name(day_dt, lang)
        date_str = format_date(day_dt, lang)
        lines.append("")
        lines.append(t(lang, "weekly_day", day=d_name, date=date_str, total=human_bytes(total)))
        rows = sorted(day_rows.get(day, []), key=lambda x: x[1], reverse=True)
        if rows:
            parts = [f"{lbl} {human_bytes(val)}" for lbl, val in rows if val > 0]
            if parts:
                lines.append(f"   {' '.join(parts)}")

    lines += [
        "",
        t(lang, "weekly_total", total=human_bytes(week_total)),
        SEPARATOR,
    ]

    # personalized summary
    name = escape(
        str(accounts[0].get("username") or user.username or "")
    ) or "👤"
    lines.append(t(lang, "weekly_hi", name=name))
    summary = [t(lang, "weekly_sum_total", total=human_bytes(week_total))]

    if prev_total > 0 and week_total > 0:
        change = (week_total - prev_total) / prev_total * 100
        if change >= 5:
            summary.append(t(lang, "weekly_sum_more", percent=f"{change:.0f}"))
        elif change <= -5:
            summary.append(t(lang, "weekly_sum_less", percent=f"{abs(change):.0f}"))
        else:
            summary.append(t(lang, "weekly_sum_same"))

    if day_totals and node_totals:
        busiest_day = max(day_totals, key=day_totals.get)
        busiest_dt = datetime.strptime(busiest_day, "%Y-%m-%d")
        top_label = max(node_totals, key=node_totals.get)
        summary.append(
            t(
                lang, "weekly_sum_top",
                day=_weekday_name(busiest_dt, lang),
                flag=top_label,
            )
        )

    lines.append(" ".join(summary))
    return "\n".join(lines)


async def _send_weekly_for_user(
    bot: Bot, user: User, remnawave: RemnawaveClient, now: datetime
) -> None:
    text = await _weekly_text_for_user(user, remnawave, now)
    if not text:
        return
    try:
        await bot.send_message(user.telegram_id, text)
    except TelegramAPIError as exc:
        logger.warning("weekly report not delivered to %s: %s", user.telegram_id, exc)
