"""Common constants and formatting helpers for reports."""
from datetime import datetime
import logging

from bot.common import SEPARATOR, fmt
from bot.services.formatting import country_flag, human_bytes

logger = logging.getLogger(__name__)

NIGHTLY_HOUR, NIGHTLY_MINUTE = 23, 59
WEEKLY_HOUR, WEEKLY_MINUTE = 23, 59
MONTHLY_HOUR, MONTHLY_MINUTE = 23, 59
FRIDAY = 4  # datetime.weekday(): Monday=0 … Friday=4

# python weekday() → localized day name.
WEEKDAYS = {
    "fa": ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}

MAX_BREAKDOWN_DAYS = 90


def _weekday_name(dt: datetime, lang: str) -> str:
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
    """One line per node. value_key: index into `data` (per-day
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
        lines.append(f"{_node_label(row)} : {human_bytes(value)}")
    return lines
