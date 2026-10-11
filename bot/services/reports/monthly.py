"""User monthly reports generation and delivery."""
from datetime import datetime, timedelta
from html import escape
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.common import SEPARATOR
from bot.db.models import ReportSettings, User
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

    account_data = []
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
        account_data.append((account, series, prev_series))

    if not account_data:
        return None

    multi_account = len(account_data) > 1
    blocks = []
    grand_month_total = 0
    grand_prev_total = 0
    all_day_totals: dict[str, int] = {}
    all_node_totals: dict[str, int] = {}

    days_in_month = (month_end.date() - month_start.date()).days

    for account, series, prev_series in account_data:
        u_name = escape(str(account.get("username") or "—"))
        acc_prev_total = _week_total(prev_series)
        grand_prev_total += acc_prev_total

        day_totals: dict[str, int] = {}
        day_rows: dict[str, list[tuple[str, int]]] = {}
        node_totals: dict[str, int] = {}

        for row in series:
            label = _node_label(row)
            node_totals[label] = node_totals.get(label, 0) + int(row.get("total") or 0)
            all_node_totals[label] = all_node_totals.get(label, 0) + int(row.get("total") or 0)
            data = row.get("data") or []
            for offset, value in enumerate(data):
                day = (month_start + timedelta(days=offset)).strftime("%Y-%m-%d")
                value = int(value or 0)
                if value <= 0:
                    continue
                day_totals[day] = day_totals.get(day, 0) + value
                all_day_totals[day] = all_day_totals.get(day, 0) + value
                day_rows.setdefault(day, []).append((label, value))

        acc_month_total = sum(day_totals.values())
        grand_month_total += acc_month_total

        acc_lines = []
        if multi_account:
            acc_lines.append(f"👤 {t(lang, 'stats_account')} : <code>{u_name}</code>")

        for offset in range(days_in_month, -1, -1):
            day_dt = month_start + timedelta(days=offset)
            day = day_dt.strftime("%Y-%m-%d")
            total = day_totals.get(day, 0)
            date_str = format_date(day_dt, lang)
            acc_lines.append("")
            acc_lines.append(t(lang, "monthly_day", date=date_str, total=human_bytes(total)))
            rows = sorted(day_rows.get(day, []), key=lambda x: x[1], reverse=True)
            if len(rows) == 1:
                acc_lines.append(f"({rows[0][0]} {human_bytes(rows[0][1])})")
            elif len(rows) > 1:
                top_label, top_value = rows[0]
                rest = sum(v for _, v in rows[1:])
                acc_lines.append(
                    f"({top_label} {human_bytes(top_value)}، "
                    f"{t(lang, 'monthly_others')} {human_bytes(rest)})"
                )

        acc_lines.append("")
        acc_lines.append(t(lang, "monthly_total", total=human_bytes(acc_month_total)))
        blocks.append("\n".join(acc_lines))

    month = month_name(now, lang)
    lines = [
        f"{t(lang, 'monthly_title', month=month)} - {format_datetime(now, lang)}",
        SEPARATOR,
    ]

    lines.append(f"\n{SEPARATOR}\n".join(blocks))

    if multi_account:
        lines.append("")
        lines.append(SEPARATOR)
        lines.append(f"📊 <b>مجموع کل مصارف ماهانه ({len(account_data)} اکانت) : {human_bytes(grand_month_total)}</b>")

    lines.append(SEPARATOR)

    # personalized summary
    display_name = escape(str(account_data[0][0].get("username") or user.username or "")) or "👤"
    lines.append(t(lang, "monthly_hi", name=display_name))
    summary = [t(lang, "monthly_sum_total", total=human_bytes(grand_month_total), month=month)]

    if grand_prev_total > 0 and grand_month_total > 0:
        change = (grand_month_total - grand_prev_total) / grand_prev_total * 100
        if change >= 5:
            summary.append(t(lang, "monthly_sum_more", percent=f"{change:.0f}"))
        elif change <= -5:
            summary.append(t(lang, "monthly_sum_less", percent=f"{abs(change):.0f}"))
        else:
            summary.append(t(lang, "monthly_sum_same"))

    if all_day_totals and all_node_totals:
        busiest_day = max(all_day_totals, key=all_day_totals.get)
        busiest_dt = datetime.strptime(busiest_day, "%Y-%m-%d")
        top_label = max(all_node_totals, key=all_node_totals.get)
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
    bot: Bot,
    user: User,
    remnawave: RemnawaveClient,
    now: datetime,
    prefs: ReportSettings | None = None,
) -> None:
    text = await _monthly_text_for_user(user, remnawave, now)
    if not text:
        return

    target_msg_id = getattr(prefs, "last_monthly_message_id", None)
    if prefs and prefs.clean_reports and target_msg_id:
        try:
            await bot.delete_message(user.telegram_id, target_msg_id)
        except Exception:
            pass

    try:
        sent_msg = await bot.send_message(user.telegram_id, text)
        if prefs and prefs.clean_reports and sent_msg:
            prefs.last_monthly_message_id = sent_msg.message_id
    except TelegramAPIError as exc:
        logger.warning("monthly report not delivered to %s: %s", user.telegram_id, exc)
