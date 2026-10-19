"""Formatting helpers: human-readable bytes, progress bar, localized dates."""
from datetime import datetime
from zoneinfo import ZoneInfo

import jdatetime

GB = 1024 ** 3
MB = 1024 ** 2
TB = 1024 ** 4


def human_bytes(n: int | float | None) -> str:
    """Format bytes → '25.50 GB', BiDi-isolated (LRI…PDI) so the Latin unit
    never jumps to the left inside RTL Persian sentences (Telegram & web)."""
    s = _human_bytes_plain(n)
    return f"\u2066{s}\u2069"


def _human_bytes_plain(n: int | float | None) -> str:
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


COUNTRY_NAMES_FA: dict[str, str] = {
    "NL": "هلند",
    "DE": "آلمان",
    "FR": "فرانسه",
    "US": "آمریکا",
    "GB": "انگلیس",
    "TR": "ترکیه",
    "FI": "فنلاند",
    "SE": "سوئد",
    "CA": "کانادا",
    "IR": "ایران",
    "RU": "روسیه",
    "PL": "لهستان",
    "IT": "ایتالیا",
    "ES": "اسپانیا",
    "CH": "سوئیس",
    "AE": "امارات",
    "SG": "سنگاپور",
    "AT": "اتریش",
    "AU": "استرالیا",
    "BR": "برزیل",
    "NO": "نروژ",
    "DK": "دانمارک",
    "BE": "بلژیک",
    "JP": "ژاپن",
    "KR": "کره جنوبی",
    "UA": "اوکراین",
    "RO": "رومانی",
    "BG": "بلغارستان",
    "CZ": "جمهوری چک",
    "HU": "مجارستان",
    "IE": "ایرلند",
    "PT": "پرتغال",
    "GR": "یونان",
    "IN": "هند",
    "HK": "هنگ کنگ",
    "MY": "مالزی",
    "KZ": "قزاقستان",
    "EU": "اروپا",
}


def country_name(code_or_name: str | None, default: str = "") -> str:
    """ISO country code or name → Persian country name ('DE' → 'آلمان')."""
    if not code_or_name:
        return default
    c = str(code_or_name).strip()
    c_up = c.upper()
    if c_up in COUNTRY_NAMES_FA:
        return COUNTRY_NAMES_FA[c_up]
    c_low = c.lower()
    for kw, iso in (
        ("netherland", "NL"), ("holland", "NL"), ("germany", "DE"),
        ("deutschland", "DE"), ("france", "FR"), ("united states", "US"),
        ("usa", "US"), ("united kingdom", "GB"), ("england", "GB"),
        ("britain", "GB"), ("turkey", "TR"), ("turkiye", "TR"),
        ("finland", "FI"), ("sweden", "SE"), ("canada", "CA"),
        ("iran", "IR"), ("russia", "RU"), ("poland", "PL"),
        ("italy", "IT"), ("spain", "ES"), ("switzerland", "CH"),
        ("emirates", "AE"), ("uae", "AE"), ("dubai", "AE"),
        ("singapore", "SG"), ("austria", "AT"), ("australia", "AU"),
        ("brazil", "BR"), ("norway", "NO"), ("denmark", "DK"),
        ("belgium", "BE"), ("japan", "JP"),
    ):
        if kw in c_low:
            return COUNTRY_NAMES_FA.get(iso, default)
    return default


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
