"""Quick Stats section.

Fetches the user's account(s) from the Remnawave panel by Telegram ID and
renders a full usage report: total / used / remaining volume, expiration
(days left), today's consumption, status and a progress bar.

With several panel accounts only ONE is shown per page (Prev/Next buttons),
so the message stays short instead of stacking all accounts at once.

If the Telegram ID exists in the panel the user is auto-verified here, so
panel users are never blocked by a stale `is_verified` flag.
"""
import logging
from datetime import datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import get_settings
from bot.db.repositories.user_repo import UserRepository
from bot.keyboards.inline import welcome_keyboard
from bot.locales.texts import t
from bot.services.formatting import (
    country_flag,
    format_date,
    format_datetime,
    human_bytes,
    now_tz,
    parse_iso,
    progress_bar,
    start_of_today,
)
from bot.services.menu import render_menu
from bot.services.remnawave import RemnawaveClient

from bot.common import SEPARATOR

logger = logging.getLogger(__name__)
router = Router(name="stats")

STATUS_KEYS = {
    "ACTIVE": "status_active",
    "DISABLED": "status_disabled",
    "LIMITED": "status_limited",
    "EXPIRED": "status_expired",
}


def _stats_keyboard(lang: str, sub_url: str | None = None, page: int = 0, total: int = 1):
    kb = InlineKeyboardBuilder()
    sizes: list[int] = []

    # ردیف ۱: باز کردن لینک و به‌روزرسانی در یک ردیف
    row1 = 0
    if sub_url:
        kb.button(text=t(lang, "btn_open_sub"), url=sub_url)
        row1 += 1
    kb.button(text=t(lang, "btn_refresh"), callback_data=f"stats:page:{page}")
    row1 += 1
    sizes.append(row1)

    # ردیف ۲: دکمه‌های بعدی و قبلی در یک ردیف (فقط اگر بیشتر از ۱ اکانت باشد)
    if total > 1:
        row2 = 0
        if page > 0:
            kb.button(text=t(lang, "btn_prev"), callback_data=f"stats:page:{page - 1}")
            row2 += 1
        if page < total - 1:
            kb.button(text=t(lang, "btn_next"), callback_data=f"stats:page:{page + 1}")
            row2 += 1
        if row2 > 0:
            sizes.append(row2)

    # ردیف ۳ (یا ۲): دکمه رنگی منوی اصلی
    menu_label = "🏠 منوی اصلی" if lang == "fa" else "🏠 Main Menu"
    kb.button(text=menu_label, callback_data="nav:main_menu")
    sizes.append(1)

    kb.adjust(*sizes)
    return kb.as_markup()


def _clamp_page(page: int, total: int) -> int:
    """Keep the requested page inside [0, total-1]."""
    if total <= 0:
        return 0
    return max(0, min(page, total - 1))


ONLINE_WINDOW = timedelta(minutes=5)
SPARKLINE_BARS = (" ", "▂", "▃", "▄", "▅", "▆", "▇", "█")


def generate_sparkline(daily_values: list[int]) -> str:
    """Generate a text-based sparkline (e.g.  ▂▃▅▇) for daily usage values."""
    if not daily_values:
        return ""
    max_val = max(daily_values)
    if max_val <= 0:
        return "       "
    bars = []
    for val in daily_values:
        if val <= 0:
            bars.append(" ")
        else:
            idx = min(7, max(1, int((val / max_val) * 7)))
            bars.append(SPARKLINE_BARS[idx])
    return "".join(bars)

def _connection_line(traffic: dict, now: datetime, lang: str) -> str:
    label = t(lang, "stats_online_label")
    online_at = parse_iso(traffic.get("onlineAt"))
    if online_at is None:
        return f"{label} : ⚪️"
    if now - online_at <= ONLINE_WINDOW:
        return f"{label} : 🟢"
    return f"{label} : 🔴 ({format_datetime(online_at.astimezone(now.tzinfo), lang)})"


def _last_connection_line(traffic: dict, now: datetime, lang: str) -> str:
    last_conn_label = "🕒 آخرین اتصال" if lang == "fa" else "🕒 Last connection"
    online_at = parse_iso(traffic.get("onlineAt"))
    if online_at is None:
        time_txt = "ثبت نشده" if lang == "fa" else "None"
    else:
        time_txt = format_datetime(online_at.astimezone(now.tzinfo), lang)
    return f"{last_conn_label} : <b>{time_txt}</b>"


def _account_block(
    account: dict,
    today: tuple[int, list[dict]] | None,
    now: datetime,
    lang: str,
    index: int = 1,
    count: int = 1,
    burn_rate_days: int | None = None,
    sparkline: tuple[str, int] | None = None,
) -> str:
    username = escape(str(account.get("username", "—")))
    status = str(account.get("status", "")).upper()
    status_text = t(lang, STATUS_KEYS.get(status, "status_active"))

    limit = int(account.get("trafficLimitBytes") or 0)
    # Newer Remnawave versions nest usage under `userTraffic`; older ones
    # expose `usedTrafficBytes` at the top level.
    traffic = account.get("userTraffic") or {}
    used = int(traffic.get("usedTrafficBytes") or account.get("usedTrafficBytes") or 0)

    account_label = t(lang, "stats_account")
    if count > 1:
        account_label = f"{account_label} ({index}/{count})"

    lines = [
        f"{account_label} : <code>{username}</code>",
        f"{t(lang, 'stats_status')} : {status_text}",
        _connection_line(traffic, now, lang),
        _last_connection_line(traffic, now, lang),
    ]

    if limit > 0:
        remaining = max(0, limit - used)
        percent = min(100.0, used / limit * 100)
        lines += [
            f"{t(lang, 'stats_total')} : <b>{human_bytes(limit)}</b>",
            f"{t(lang, 'stats_used')} : <b>{human_bytes(used)}</b>",
            f"{t(lang, 'stats_remaining')} : <b>{human_bytes(remaining)}</b>",
            f"{progress_bar(percent)} {percent:.0f}%",
        ]
    else:
        lines += [
            f"{t(lang, 'stats_total')} : {t(lang, 'stats_unlimited')}",
            f"{t(lang, 'stats_used')} : <b>{human_bytes(used)}</b>",
        ]

    # expiration
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

    if today is not None:
        today_bytes, nodes = today
        lines.append(f"{t(lang, 'stats_today')} : <b>{human_bytes(today_bytes)}</b>")
        for node in nodes:
            if int(node.get("total") or 0) <= 0:
                continue
            flag = country_flag(node.get("countryCode"))
            lines.append(f"{flag} : <b>{human_bytes(node['total'])}</b>")

    lifetime = int(traffic.get("lifetimeUsedTrafficBytes") or 0)
    if lifetime > 0:
        lines.append(f"{t(lang, 'stats_lifetime')} : <b>{human_bytes(lifetime)}</b>")

    return "\n".join(lines)


@router.callback_query(F.data == "menu:stats")
async def quick_stats(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    remnawave: RemnawaveClient,
):
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_stats_page(bot, user, user_repo, remnawave, call.from_user.id, 0)
    await call.answer()


@router.callback_query(F.data.startswith("stats:page:"))
async def stats_page(
    call: CallbackQuery,
    bot: Bot,
    user_repo: UserRepository,
    remnawave: RemnawaveClient,
):
    try:
        page = int(call.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await call.answer(t("fa", "acc_error"), show_alert=True)
        return
    user = await user_repo.get_or_create(call.from_user.id, call.from_user.username)
    await _render_stats_page(bot, user, user_repo, remnawave, call.from_user.id, page)
    await call.answer()


async def _render_stats_page(
    bot: Bot,
    user,
    user_repo: UserRepository,
    remnawave: RemnawaveClient,
    telegram_id: int,
    page: int,
) -> None:
    """Render a single account (page) of the quick-stats view."""
    lang = user.language
    tz = get_settings().TIMEZONE

    accounts = await remnawave.get_users_by_telegram_id(telegram_id)

    if accounts is None:
        # Panel down — never de-verify on transient errors.
        await render_menu(
            bot, user, user_repo,
            t(lang, "stats_error"),
            _stats_keyboard(lang),
        )
        return

    if not accounts:
        await user_repo.set_verified(user, False)
        await render_menu(
            bot, user, user_repo,
            t(lang, "not_verified"),
            welcome_keyboard(lang),
        )
        return

    await user_repo.set_verified(user, True)

    if accounts:
        seen = set()
        deduped = []
        for a in accounts:
            aid = str(a.get("id"))
            if aid not in seen:
                seen.add(aid)
                deduped.append(a)
        accounts = deduped

    page = _clamp_page(page, len(accounts))
    account = accounts[page]

    # Today's usage is fetched only for the visible account (faster pages).
    now = now_tz(tz)
    today: tuple[int, list[dict]] | None = None
    burn_rate_days: int | None = None
    sparkline: tuple[str, int] | None = None
    account_id = account.get("id")
    limit = int(account.get("trafficLimitBytes") or 0)
    traffic = account.get("userTraffic") or {}
    used = int(traffic.get("usedTrafficBytes") or account.get("usedTrafficBytes") or 0)
    remaining = max(0, limit - used) if limit > 0 else 0

    if account_id:
        try:
            today = await remnawave.get_user_today_usage(
                int(account_id), start_of_today(tz).isoformat(), now.isoformat()
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("today-usage failed for %s: %s", account_id, exc)

        # 7-day stats for sparkline and burn-rate estimate
        try:
            seven_days_ago = (now - timedelta(days=6)).strftime("%Y-%m-%d")
            today_str = now.strftime("%Y-%m-%d")
            series = await remnawave.get_user_bandwidth_stats(
                int(account_id), seven_days_ago, today_str
            )
            if series:
                daily_totals = [0] * 7
                for r in series:
                    data = r.get("data") or []
                    for i, val in enumerate(data[:7]):
                        daily_totals[i] += int(val or 0)
                total_7d = sum(daily_totals)
                if total_7d > 0:
                    sparkline = (generate_sparkline(daily_totals), total_7d)

                if limit > 0 and remaining > 0:
                    recent_3d = sum(daily_totals[-3:])
                    daily_avg = (
                        recent_3d / 3.0
                        if recent_3d > 0
                        else (total_7d / 7.0 if total_7d > 0 else 0)
                    )
                    if daily_avg > 0:
                        burn_rate_days = max(1, int(remaining / daily_avg))
        except Exception as exc:  # pragma: no cover
            logger.debug("bandwidth stats / burn-rate error: %s", exc)

    block = _account_block(
        account,
        today,
        now,
        lang,
        page + 1,
        len(accounts),
        burn_rate_days=burn_rate_days,
        sparkline=sparkline,
    )

    header = f"{t(lang, 'stats_title')} - {format_datetime(now, lang)}\n"
    text = header + f"{SEPARATOR}\n" + block

    await render_menu(
        bot, user, user_repo, text,
        _stats_keyboard(lang, account.get("subscriptionUrl"), page, len(accounts)),
    )
