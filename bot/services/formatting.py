"""Formatting helpers: human-readable bytes, progress bar, localized dates."""
from datetime import datetime
from zoneinfo import ZoneInfo

import jdatetime

GB = 1024 ** 3
MB = 1024 ** 2
TB = 1024 ** 4


def human_bytes(n: int | float | None) -> str:
    if not n or n <= 0:
        return "0 MB"
    if n >= TB:
        return f"{n / TB:.2f} TB"
    if n >= GB:
        return f"{n / GB:.2f} GB"
    return f"{n / MB:.2f} MB"


def country_flag(code: str | None) -> str:
    """ISO country code → flag emoji ('DE' → 🇩🇪). Falls back to 🌐."""
    if not code or len(code) != 2 or not code.isalpha() or code.upper() == "XX":
        return "🌐"
    code = code.upper()
    return chr(0x1F1E6 + ord(code[0]) - 65) + chr(0x1F1E6 + ord(code[1]) - 65)


def progress_bar(percent: float, width: int = 10) -> str:
    percent = max(0.0, min(100.0, percent))
    filled = round(percent / 100 * width)
    return "▓" * filled + "░" * (width - filled)


def now_tz(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def start_of_today(tz_name: str) -> datetime:
    now = now_tz(tz_name)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def format_datetime(dt: datetime, lang: str) -> str:
    """`1404/12/05 - 23:57` for fa, `2026-02-24 - 23:57` for others."""
    if lang == "fa":
        j = jdatetime.datetime.fromgregorian(datetime=dt)
        return j.strftime("%Y/%m/%d - %H:%M")
    return dt.strftime("%Y-%m-%d - %H:%M")


def format_date(dt: datetime, lang: str) -> str:
    if lang == "fa":
        return jdatetime.datetime.fromgregorian(datetime=dt).strftime("%Y/%m/%d")
    return dt.strftime("%Y-%m-%d")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
