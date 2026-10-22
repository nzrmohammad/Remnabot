"""Unit tests for Jalali calendar and leap year algorithms."""
import jdatetime


def is_jalali_leap_year(jy: int) -> bool:
    """33-year cycle algorithm (matching app.js implementation)."""
    rem = ((jy % 33) + 33) % 33
    return rem in (1, 5, 9, 13, 17, 22, 26, 30)


def get_jalali_month_days(year: int, month: int) -> int:
    """Days count in Jalali month matching app.js getJalaliMonthDays."""
    if 1 <= month <= 6:
        return 31
    if 7 <= month <= 11:
        return 30
    if month == 12:
        return 30 if is_jalali_leap_year(year) else 29
    return 31


def test_jalali_leap_years():
    """Verify leap year results for recent, current, and future years."""
    # 1403 is a leap year; 1404 is not
    assert is_jalali_leap_year(1403) is True
    assert is_jalali_leap_year(1404) is False

    # Historical leap years
    assert is_jalali_leap_year(1399) is True
    assert is_jalali_leap_year(1395) is True
    assert is_jalali_leap_year(1391) is True
    assert is_jalali_leap_year(1387) is True
    assert is_jalali_leap_year(1383) is True
    assert is_jalali_leap_year(1379) is True
    assert is_jalali_leap_year(1375) is True

    # Esfand days count
    assert get_jalali_month_days(1403, 12) == 30
    assert get_jalali_month_days(1404, 12) == 29
    assert get_jalali_month_days(1403, 1) == 31
    assert get_jalali_month_days(1403, 7) == 30


def test_jalali_matches_jdatetime():
    """Verify 100% agreement with jdatetime library for years 1300 to 1450."""
    for y in range(1300, 1450):
        expected = jdatetime.date(y, 1, 1).isleap()
        assert is_jalali_leap_year(y) == expected, f"Mismatch at year {y}"
