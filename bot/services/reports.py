"""Scheduled usage reports.

* Nightly report — Saturday to Thursday at 23:59 local time (skipped on
  Fridays and on the last day of the Jalali month): account overview with
  per-node used volume, today's per-node usage and expiry.
* Weekly report — Friday 23:59 (skipped if Friday is the last day of the
  Jalali month): day-by-day usage of the last 7 days with per-node breakdown,
  week total, comparison with the previous week, busiest day and top server.
* Monthly report — 23:59 on the LAST day of the Jalali (Shamsi) month:
  day-by-day usage of the current Jalali month with per-node breakdown,
  month total, comparison with the previous Jalali month, busiest day
  and top server.

Each can be switched off per user in the Settings section
(`report_settings` table).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import get_settings
from bot.db.models import AlertState, User
from bot.db.repositories.order_repo import OrderRepository
from bot.db.repositories.report_repo import ReportRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.services.formatting import (
    country_flag,
    format_date,
    format_datetime,
    human_bytes,
    now_tz,
    parse_iso,
)
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)

SEPARATOR = "─" * 18

NIGHTLY_HOUR, NIGHTLY_MINUTE = 23, 59
WEEKLY_HOUR, WEEKLY_MINUTE = 23, 59
MONTHLY_HOUR, MONTHLY_MINUTE = 23, 59
FRIDAY = 4  # datetime.weekday(): Monday=0 … Friday=4

# python weekday() → localized day name.
# NOTE: these map Gregorian weekday() indices (Mon=0..Sun=6) to names,
# so week-start differences (Sat in Jalali) don't shift them.
WEEKDAYS = {
    "fa": ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}

# cap for the "used since last reset" per-node window (API returns per-day
# series, so an unbounded range could get very large)
MAX_BREAKDOWN_DAYS = 90


def _weekday_name(dt: datetime, lang: str) -> str:
    # Prefer the real Jalali weekday name for fa (correct even if the
    # static table ever drifts); fall back to the table on any error.
    if lang == "fa":
        try:
            import jdatetime

            jd = jdatetime.datetime.fromgregorian(datetime=dt)
            return jdatetime.date.j_weekdays_fa[jd.weekday()]
        except Exception:
            pass
    names = WEEKDAYS.get(lang, WEEKDAYS["en"])
    return names[dt.weekday()]


def _node_label(row: dict) -> str:
    return f"{country_flag(row.get('countryCode'))} {row.get('name') or '—'}"


def _series_rows(series: list[dict]) -> list[dict]:
    """Normalize + sort a bandwidth-stats series by total, drop empty nodes."""
    rows = [r for r in series if int(r.get("total") or 0) > 0]
    return sorted(rows, key=lambda r: int(r.get("total") or 0), reverse=True)


def _breakdown_lines(rows: list[dict], value_key: int | None = None) -> list[str]:
    """One indented line per node. value_key: index into `data` (per-day
    value) or None to use the range total."""
    lines = []
    for row in rows:
        if value_key is None:
            value = int(row.get("total") or 0)
        else:
            data = row.get("data") or []
            value = int(data[value_key]) if value_key < len(data) else 0
        if value <= 0:
            continue
        lines.append(f"      {_node_label(row)} : {human_bytes(value)}")
    return lines


# --------------------------------------------------------------------- #
# Nightly report
# --------------------------------------------------------------------- #
async def _nightly_account_block(
    remnawave: RemnawaveClient, account: dict, now: datetime, lang: str
) -> str:
    from html import escape

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
            today_lines.append(f"      {_node_label(row)} : {human_bytes(value)}")
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


# --------------------------------------------------------------------- #
# Weekly report
# --------------------------------------------------------------------- #
def _week_total(series: list[dict]) -> int:
    return sum(int(r.get("total") or 0) for r in series)


async def _weekly_text_for_user(
    user: User, remnawave: RemnawaveClient, now: datetime
) -> str | None:
    from html import escape

    accounts = await remnawave.get_users_by_telegram_id(user.telegram_id)
    if not accounts:
        return None
    lang = user.language or "fa"

    week_start = now - timedelta(days=6)
    prev_start, prev_end = now - timedelta(days=13), now - timedelta(days=7)

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
        prev_total += _week_total(prev_series)

        for row in series:
            label = _node_label(row)
            node_totals[label] = node_totals.get(label, 0) + int(row.get("total") or 0)
            data = row.get("data") or []
            for offset, value in enumerate(data):
                day = (week_start + timedelta(days=offset)).strftime("%Y-%m-%d")
                value = int(value or 0)
                if value <= 0:
                    continue
                day_totals[day] = day_totals.get(day, 0) + value
                day_rows.setdefault(day, []).append((label, value))

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
        date_str = format_date(day_dt, lang)
        lines.append("")
        lines.append(t(lang, "weekly_day", date=date_str, total=human_bytes(total)))
        rows = sorted(day_rows.get(day, []), key=lambda x: x[1], reverse=True)
        if len(rows) == 1:
            lines.append(f"      ({rows[0][0]} {human_bytes(rows[0][1])})")
        elif len(rows) > 1:
            top_label, top_value = rows[0]
            rest = sum(v for _, v in rows[1:])
            lines.append(
                f"      ({top_label} {human_bytes(top_value)}، "
                f"{t(lang, 'weekly_others')} {human_bytes(rest)})"
            )

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
        # top_label is "«flag» «name»"
        flag, _, node_name = top_label.partition(" ")
        summary.append(
            t(
                lang, "weekly_sum_top",
                day=_weekday_name(busiest_dt, lang),
                flag=flag,
                node=node_name,
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


# --------------------------------------------------------------------- #
# Monthly report (Jalali month, sent 23:59 on its last day)
# --------------------------------------------------------------------- #
def is_last_jalali_day(dt: datetime) -> bool:
    """True when `dt` falls on the last day of its Jalali month."""
    try:
        import jdatetime
    except ImportError:
        # Fallback: last Gregorian day (only when jdatetime is missing;
        # in practice jdatetime is a hard dependency).
        nxt = dt + timedelta(days=1)
        return nxt.month != dt.month
    jd = jdatetime.datetime.fromgregorian(datetime=dt)
    nxt = jd + jdatetime.timedelta(days=1)
    return nxt.month != jd.month


def jalali_month_range(now: datetime) -> tuple[datetime, datetime]:
    """(month_start, month_end) as Gregorian datetimes for the Jalali month
    containing `now`. month_end is `now` itself (the report runs at 23:59 on
    the last day, so the range covers the whole month)."""
    try:
        import jdatetime
    except ImportError:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now
    jd_now = jdatetime.datetime.fromgregorian(datetime=now)
    jd_start = jd_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = jd_start.togregorian().replace(tzinfo=now.tzinfo)
    return start, now


def prev_jalali_month_range(now: datetime) -> tuple[datetime, datetime]:
    """Gregorian (start, end) covering the whole PREVIOUS Jalali month."""
    try:
        import jdatetime
    except ImportError:
        first_this = now.replace(day=1)
        end_prev = first_this - timedelta(days=1)
        return end_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0), end_prev
    jd_now = jdatetime.datetime.fromgregorian(datetime=now)
    jd_first = jd_now.replace(day=1)
    jd_end_prev = jd_first - jdatetime.timedelta(days=1)
    jd_start_prev = jd_end_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = jd_start_prev.togregorian().replace(tzinfo=now.tzinfo)
    end = jd_end_prev.replace(hour=23, minute=59, second=59).togregorian().replace(
        tzinfo=now.tzinfo
    )
    return start, end


def month_name(now: datetime, lang: str) -> str:
    """Current month name: Jalali name for fa, Gregorian name for en."""
    if lang == "fa":
        try:
            import jdatetime

            return jdatetime.datetime.fromgregorian(datetime=now).strftime("%B")
        except Exception:
            pass
    return now.strftime("%B")


async def _monthly_text_for_user(
    user: User, remnawave: RemnawaveClient, now: datetime
) -> str | None:
    from html import escape

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
        # top_label is "«flag» «name»"
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


def fmt(amount: int) -> str:
    return f"{amount:,}"


def _chunk_text(text: str, max_chars: int = 3800) -> list[str]:
    """Splits a long report into chunks <= max_chars, breaking on SEPARATOR or newlines."""
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    parts = text.split(f"\n{SEPARATOR}\n")
    for i, part in enumerate(parts):
        part_text = part if i == 0 else f"{SEPARATOR}\n{part}"
        if current_len + len(part_text) + 1 <= max_chars:
            current.append(part_text)
            current_len += len(part_text) + 1
        else:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0

            if len(part_text) > max_chars:
                lines = part_text.split("\n")
                line_chunk: list[str] = []
                line_chunk_len = 0
                for line in lines:
                    if line_chunk_len + len(line) + 1 <= max_chars:
                        line_chunk.append(line)
                        line_chunk_len += len(line) + 1
                    else:
                        if line_chunk:
                            chunks.append("\n".join(line_chunk))
                        line_chunk = [line]
                        line_chunk_len = len(line)
                if line_chunk:
                    chunks.append("\n".join(line_chunk))
            else:
                current.append(part_text)
                current_len = len(part_text)

    if current:
        chunks.append("\n".join(current))
    return chunks


async def _deliver_admin_report(bot: Bot, session: AsyncSession, text: str) -> None:
    settings = get_settings()
    store = await get_store_settings(session)
    topic_id = store.topic_alerts if store.topic_alerts is not None else settings.ADMIN_TOPIC_ALERTS
    thread_kwargs = {"message_thread_id": topic_id} if topic_id else {}

    chunks = _chunk_text(text)
    for chunk in chunks:
        delivered = False
        if settings.ADMIN_CHAT_ID:
            try:
                await bot.send_message(settings.ADMIN_CHAT_ID, chunk, **thread_kwargs)
                delivered = True
            except Exception as exc:
                logger.warning("Admin report delivery to chat %s failed: %s", settings.ADMIN_CHAT_ID, exc)

        if not delivered and settings.ADMIN_IDS:
            for aid in settings.ADMIN_IDS:
                try:
                    await bot.send_message(aid, chunk)
                except Exception as admin_exc:
                    logger.warning("Admin report fallback to admin %s failed: %s", aid, admin_exc)


async def _send_admin_nightly_summary(
    bot: Bot, session: AsyncSession, remnawave: RemnawaveClient, now: datetime
) -> None:
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start.astimezone(timezone.utc)

    # 1. Orders & Revenue today
    order_repo = OrderRepository(session)
    orders_count = await order_repo.count(since=today_start_utc)
    revenue_today = await order_repo.total_revenue(since=today_start_utc)

    # 2. Wallet top-ups today
    wallet_repo = WalletRepository(session)
    topup_count, topup_amount = await wallet_repo.topup_stats(since=today_start_utc)

    total_payments = orders_count + topup_count
    total_amount = revenue_today + topup_amount
    payments_str = f"{total_payments} ({fmt(total_amount)} تومان)" if total_payments > 0 else "0"

    # 3. User growth
    user_repo = UserRepository(session)
    new_users = await user_repo.count(User.created_at >= today_start_utc)

    # 4. Cluster & Panel metrics
    panel_users = await remnawave.get_all_panel_users() or []
    total_panel_users = len(panel_users)
    active_panel_users = sum(
        1 for u in panel_users if str(u.get("status", "")).upper() == "ACTIVE"
    )

    # 5. Nodes telemetry & country totals
    nodes = await remnawave.get_nodes() or []
    country_totals: dict[str, int] = {}
    for n in nodes:
        cc = (n.get("countryCode") or "").upper()
        if cc:
            country_totals.setdefault(cc, 0)
        tb = n.get("todayTrafficBytes") or n.get("traffic") or 0
        try:
            val = int(tb)
            if cc:
                country_totals[cc] += val
        except (ValueError, TypeError):
            pass

    # 6. Active users today and their usage
    today_str = now.strftime("%Y-%m-%d")
    active_traffic_users = [
        u
        for u in panel_users
        if int(
            u.get("usedTrafficBytes")
            or (u.get("userTraffic") or {}).get("usedTrafficBytes")
            or 0
        )
        > 0
    ]

    sem = asyncio.Semaphore(10)

    async def _fetch_user_today(u: dict):
        uid = u.get("id")
        if not uid:
            return u, []
        async with sem:
            try:
                stats = (
                    await remnawave.get_user_bandwidth_stats(
                        int(uid), today_str, today_str
                    )
                    or []
                )
                return u, stats
            except Exception:
                return u, []

    user_stats_results = await asyncio.gather(
        *[_fetch_user_today(u) for u in active_traffic_users]
    )

    active_users_today: list[tuple[str, int, str]] = []
    user_country_totals: dict[str, int] = {}

    for u, stats in user_stats_results:
        username = str(u.get("username", "—"))
        user_node_usage: dict[str, int] = {}
        for row in stats:
            cc = (row.get("countryCode") or "").upper()
            data = row.get("data") or []
            val = int(data[-1]) if data else int(row.get("total") or 0)
            if val > 0:
                user_node_usage[cc] = user_node_usage.get(cc, 0) + val
                user_country_totals[cc] = user_country_totals.get(cc, 0) + val

        user_total = sum(user_node_usage.values())
        if user_total > 0:
            breakdown_parts = [
                f"{country_flag(cc)} {human_bytes(val)}"
                for cc, val in sorted(
                    user_node_usage.items(), key=lambda x: x[1], reverse=True
                )
            ]
            active_users_today.append((username, user_total, " ".join(breakdown_parts)))

    for cc, val in user_country_totals.items():
        if cc:
            country_totals[cc] = max(country_totals.get(cc, 0), val)

    total_bandwidth_today = sum(country_totals.values()) if country_totals else sum(
        u[1] for u in active_users_today
    )
    active_users_today.sort(key=lambda x: x[1], reverse=True)

    # 7. Expiring users in 0..3 days
    expiring_soon_users: list[tuple[int, str]] = []
    for u in panel_users:
        exp_iso = u.get("expireAt")
        if not exp_iso:
            continue
        exp_dt = parse_iso(exp_iso)
        if not exp_dt:
            continue
        days_left = (exp_dt.astimezone(now.tzinfo).date() - now.date()).days
        if 0 <= days_left <= 3:
            expiring_soon_users.append((days_left, str(u.get("username", "—"))))

    expiring_soon_users.sort(key=lambda x: (x[0], x[1].lower()))

    # 8. Expired users in last 24h
    one_day_ago = now - timedelta(days=1)
    expired_24h_users: list[str] = []
    for u in panel_users:
        exp_iso = u.get("expireAt")
        if not exp_iso:
            continue
        exp_dt = parse_iso(exp_iso)
        if not exp_dt:
            continue
        if one_day_ago <= exp_dt < now:
            expired_24h_users.append(str(u.get("username", "—")))

    expired_24h_users.sort(key=str.lower)

    # 9. Alerts sent today
    traffic_alerts_count = (
        await session.scalar(
            select(func.count(AlertState.account_id)).where(
                AlertState.traffic_alerted.is_(True),
                AlertState.updated_at >= today_start_utc,
            )
        )
        or 0
    )
    near_expiry_count = len(expiring_soon_users)
    expired_count = len(expired_24h_users)

    # Build report text
    date_str = format_date(now, "fa")
    lines = [
        f"👑 <b>گزارش جامع - {date_str} - 23:59</b>",
        SEPARATOR,
        "⚙️ <b>خلاصه وضعیت کل پنل</b>",
        f"👤 تعداد کل اکانت‌ها : {total_panel_users}",
        f"✅ اکانت‌های فعال : {active_panel_users}",
        f"➕ کاربران جدید امروز : {new_users}",
        f"💳 پرداخت‌های امروز : {payments_str}",
        f"⚡️ مصرف کل امروز : {human_bytes(total_bandwidth_today)}",
    ]

    if country_totals:
        for cc, val in sorted(country_totals.items(), key=lambda x: x[1], reverse=True):
            lines.append(f" {country_flag(cc)} : {human_bytes(val)}")

    lines.append(SEPARATOR)
    lines.append("✅ <b>کاربران فعال امروز و مصرفشان</b>")
    if active_users_today:
        for uname, _, b_str in active_users_today:
            lines.append(f"👤 {escape(uname)} : {b_str}")
    else:
        lines.append("  (هیچ کاربری امروز مصرف نداشته است)")

    lines.append(SEPARATOR)
    lines.append("⚠️ <b>کاربرانی که تا ۳ روز آینده منقضی می شوند</b>")
    if expiring_soon_users:
        for d_left, uname in expiring_soon_users:
            lines.append(f"👤 {escape(uname)} : {d_left} روز")
    else:
        lines.append("  (هیچ کاربری در ۳ روز آینده منقضی نمی‌شود)")

    lines.append(SEPARATOR)
    lines.append("❌ <b>کاربران منقضی (24 ساعت اخیر)</b>")
    if expired_24h_users:
        for uname in expired_24h_users:
            lines.append(f"👤 {escape(uname)}")
    else:
        lines.append("  (هیچ کاربری در ۲۴ ساعت اخیر منقضی نشده است)")

    lines.append(SEPARATOR)
    lines.append("🔔 <b>هشدارهای ارسال شده امروز</b>")
    lines.append(f"کمبود حجم : {traffic_alerts_count}")
    lines.append(f"در آستانه انقضا : {near_expiry_count}")
    lines.append(f"منقضی شده : {expired_count}")

    text = "\n".join(lines)
    await _deliver_admin_report(bot, session, text)


async def _send_admin_weekly_summary(
    bot: Bot, session: AsyncSession, remnawave: RemnawaveClient, now: datetime
) -> None:
    # Week starts 6 days ago (Saturday) and ends today (Friday)
    week_start = now - timedelta(days=6)
    start_str = week_start.strftime("%Y-%m-%d")
    today_str = now.strftime("%Y-%m-%d")

    panel_users = await remnawave.get_all_panel_users() or []
    active_traffic_users = [
        u
        for u in panel_users
        if int(
            u.get("usedTrafficBytes")
            or (u.get("userTraffic") or {}).get("usedTrafficBytes")
            or 0
        )
        > 0
    ]

    sem = asyncio.Semaphore(10)

    async def _fetch_user_week(u: dict):
        uid = u.get("id")
        if not uid:
            return u, []
        async with sem:
            try:
                stats = (
                    await remnawave.get_user_bandwidth_stats(
                        int(uid), start_str, today_str
                    )
                    or []
                )
                return u, stats
            except Exception:
                return u, []

    results = await asyncio.gather(*[_fetch_user_week(u) for u in active_traffic_users])

    daily_champions: list[tuple[str, int]] = [("", 0) for _ in range(7)]
    user_weekly_totals: list[tuple[str, int]] = []

    for u, stats in results:
        username = str(u.get("username", "—"))
        user_total = 0
        for d_idx in range(7):
            day_bytes = 0
            for row in stats:
                data = row.get("data") or []
                if d_idx < len(data):
                    day_bytes += int(data[d_idx] or 0)
            user_total += day_bytes
            if day_bytes > daily_champions[d_idx][1]:
                daily_champions[d_idx] = (username, day_bytes)
        if user_total > 0:
            user_weekly_totals.append((username, user_total))

    user_weekly_totals.sort(key=lambda x: x[1], reverse=True)
    top_20 = user_weekly_totals[:20]

    lines = [
        "🏆 <b>گزارش هفتگی پرمصرفترین کاربران</b>",
        "🥇 <b>۲۰ کاربر برتر این هفته:</b>",
    ]

    if top_20:
        for rank, (uname, total_bytes) in enumerate(top_20, start=1):
            lines.append(f"{rank}. 👤 {escape(uname)} ({human_bytes(total_bytes)})")
    else:
        lines.append("  (هیچ مصرفی در این هفته ثبت نشده است)")

    lines.append(SEPARATOR)
    lines.append("🔥 <b>قهرمان هر روز هفته:</b>")

    for d_idx in range(7):
        day_dt = week_start + timedelta(days=d_idx)
        day_name = _weekday_name(day_dt, "fa")
        prefix = "🎉" if day_dt.weekday() == 4 else "🗓️"
        champ_uname, champ_bytes = daily_champions[d_idx]
        if champ_bytes > 0:
            lines.append(
                f"{prefix} {day_name}: {escape(champ_uname)} ({human_bytes(champ_bytes)})"
            )
        else:
            lines.append(f"{prefix} {day_name}: —")

    text = "\n".join(lines)
    await _deliver_admin_report(bot, session, text)


# --------------------------------------------------------------------- #
# Sweeps + loops
# --------------------------------------------------------------------- #
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
                    await _send_nightly_for_user(bot, user, remnawave, now)
                elif kind == "weekly" and prefs.weekly:
                    await _send_weekly_for_user(bot, user, remnawave, now)
                elif kind == "monthly" and prefs.monthly:
                    await _send_monthly_for_user(bot, user, remnawave, now)
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
