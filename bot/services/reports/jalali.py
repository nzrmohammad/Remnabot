"""Jalali calendar helpers for report scheduling and ranges."""
from datetime import datetime, timedelta


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
