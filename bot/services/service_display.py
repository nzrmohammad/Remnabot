"""Shared formatting/rendering for services (user list + admin panel)."""
from html import escape

from bot.locales.texts import t


def fmt_price(value: int) -> str:
    return f"{value:,}"


def fmt_duration(days: int, lang: str) -> str:
    if days <= 0:
        return t(lang, "unlimited")
    return t(lang, "svc_days", days=days)


def fmt_traffic(gb: int, lang: str) -> str:
    if gb <= 0:
        return t(lang, "unlimited")
    return t(lang, "svc_gb", gb=gb)


def fmt_strategy(strategy: str | None, lang: str) -> str:
    key = {
        "NO_RESET": "stgy_no_reset",
        "DAY": "stgy_day",
        "WEEK": "stgy_week",
        "MONTH": "stgy_month",
        "MONTH_ROLLING": "stgy_month",
    }.get((strategy or "NO_RESET").upper(), "stgy_no_reset")
    return t(lang, key)


def fmt_hwid(limit: int | None, lang: str) -> str:
    if limit is None:
        return t(lang, "hwid_default")
    if limit <= 0:
        return t(lang, "hwid_zero")
    return t(lang, "svc_devices", n=limit)


def fmt_state(is_active: bool, lang: str) -> str:
    return t(lang, "svc_state_active") if is_active else t(lang, "svc_state_inactive")


def service_block(service, lang: str, show_state: bool = False) -> str:
    """Multi-line description of one service (escaped, HTML-safe)."""
    title = f"<b>{escape(service.name)}</b>"
    if show_state:
        title += f" — {fmt_state(service.is_active, lang)}"

    lines = [
        title,
        f"   💰 {t(lang, 'svc_field_price')} : "
        f"<b>{fmt_price(service.price)}</b> {t(lang, 'svc_currency')}",
        f"   📅 {t(lang, 'svc_field_duration')} : "
        f"<b>{fmt_duration(service.duration_days, lang)}</b>",
        f"   📊 {t(lang, 'svc_field_traffic')} : "
        f"<b>{fmt_traffic(service.traffic_gb, lang)}</b>",
        f"   🔁 {t(lang, 'svc_field_strategy')} : "
        f"<b>{fmt_strategy(getattr(service, 'traffic_strategy', None), lang)}</b>",
        f"   📱 {t(lang, 'svc_field_hwid')} : "
        f"<b>{fmt_hwid(getattr(service, 'hwid_limit', None), lang)}</b>",
    ]
    squad = getattr(service, "squad_uuid", None)
    if squad:
        lines.append(f"   🧩 <code>{escape(str(squad)[:18])}…</code>")
    if service.description:
        lines.append(f"   📝 {escape(service.description)}")
    return "\n".join(lines)
