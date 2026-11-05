"""Tests for Reports and Telemetry SSOT Alignment between Bot and Web Mini App."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock
import pytest

from bot.common.helpers import get_node_daily_bytes
from bot.db.models import Order, Topup
from bot.db.repositories.order_repo import OrderRepository
from bot.services.reports.common import get_financial_metrics_today
from bot.web.admin_overview_charts import _fetch_user_bandwidth_series


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_get_node_daily_bytes_ignores_cumulative_traffic():
    """Verify get_node_daily_bytes extracts today's bytes and ignores lifetime 'traffic'."""
    # 1. Normal node with todayTrafficBytes
    n1 = {"todayTrafficBytes": 1024, "traffic": 999999999}
    assert get_node_daily_bytes(n1) == 1024

    # 2. Node with dailyTrafficBytes
    n2 = {"dailyTrafficBytes": 2048, "traffic": 999999999}
    assert get_node_daily_bytes(n2) == 2048

    # 3. Node with trafficDailyBytes
    n3 = {"trafficDailyBytes": 4096, "traffic": 999999999}
    assert get_node_daily_bytes(n3) == 4096

    # 4. Node with ONLY lifetime cumulative 'traffic' must return 0, NOT the cumulative lifetime value!
    n4 = {"traffic": 500000000000}
    assert get_node_daily_bytes(n4) == 0

    # 5. Non-dict or None
    assert get_node_daily_bytes(None) == 0
    assert get_node_daily_bytes({}) == 0


@pytest.mark.anyio
async def test_order_repo_count_with_status_filter(session_factory):
    """Verify OrderRepository.count supports status filtering."""
    async with session_factory() as session:
        repo = OrderRepository(session)

        # 1 paid, 1 pending, 1 failed
        session.add(Order(telegram_id=1, service_name="P1", amount=10000, status="paid"))
        session.add(Order(telegram_id=2, service_name="P2", amount=20000, status="pending"))
        session.add(Order(telegram_id=3, service_name="P3", amount=30000, status="failed"))
        await session.commit()

        # Count all
        total_orders = await repo.count()
        assert total_orders >= 3

        # Count only paid
        paid_orders = await repo.count(status="paid")
        assert paid_orders == 1


@pytest.mark.anyio
async def test_get_financial_metrics_today_no_double_counting(session_factory):
    """Verify get_financial_metrics_today separates orders revenue and topups cleanly."""
    async with session_factory() as session:
        now = datetime.now(timezone.utc)

        # User tops up 50,000
        t = Topup(telegram_id=10, amount=50000, status="approved", decided_at=now)
        session.add(t)

        # User spends 50,000 on an order
        o = Order(telegram_id=10, service_name="Plan 1", amount=50000, status="paid", created_at=now)
        session.add(o)

        await session.commit()

        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        fin = await get_financial_metrics_today(session, start_of_day)

        assert fin["orders_count"] == 1
        assert fin["orders_revenue"] == 50000
        assert fin["topups_count"] == 1
        assert fin["topups_amount"] == 50000


@pytest.mark.anyio
async def test_user_bandwidth_series_aligns_short_data():
    """Verify _fetch_user_bandwidth_series keeps users with less than 7 days of history."""
    mock_remnawave = AsyncMock()
    # User with only 3 days of stats
    mock_remnawave.get_user_bandwidth_stats.return_value = [
        {"countryCode": "DE", "data": [100, 200, 300]}
    ]

    panel_users = [{"id": 1, "username": "new_user", "usedTrafficBytes": 10000}]
    daily_bytes_sum, has_real, c_bytes, total_bytes = await _fetch_user_bandwidth_series(
        mock_remnawave, panel_users, "2026-11-01", "2026-11-07"
    )

    assert has_real is True
    # 300 should be aligned to index 6 (today)
    assert daily_bytes_sum[6] == 300
    # 200 to index 5 (yesterday)
    assert daily_bytes_sum[5] == 200
    # 100 to index 4 (2 days ago)
    assert daily_bytes_sum[4] == 100
    assert total_bytes == 300


def test_format_financial_summary_ssot():
    """Verify format_financial_summary formats sales and topups cleanly."""
    from bot.services.reports.common import format_financial_summary

    # Both
    fin1 = {"orders_count": 2, "orders_revenue": 100000, "topups_count": 3, "topups_amount": 150000}
    res1 = format_financial_summary(fin1)
    assert "2 خرید (100,000 ت)" in res1
    assert "3 واریز (150,000 ت)" in res1

    # Purchases only
    fin2 = {"orders_count": 1, "orders_revenue": 50000, "topups_count": 0, "topups_amount": 0}
    res2 = format_financial_summary(fin2)
    assert res2 == "1 خرید (50,000 تومان)"

    # Topups only
    fin3 = {"orders_count": 0, "orders_revenue": 0, "topups_count": 4, "topups_amount": 200000}
    res3 = format_financial_summary(fin3)
    assert res3 == "4 واریز نقدی (200,000 تومان)"

    # Empty
    fin4 = {"orders_count": 0, "orders_revenue": 0, "topups_count": 0, "topups_amount": 0}
    res4 = format_financial_summary(fin4)
    assert res4 == "۰"


def test_get_used_bytes_resilience():
    """Verify get_used_bytes safely handles all panel payload formats."""
    from bot.common.helpers import get_used_bytes

    # 1. Nested format
    u1 = {"userTraffic": {"usedTrafficBytes": 1048576}}
    assert get_used_bytes(u1) == 1048576

    # 2. Flat format
    u2 = {"usedTrafficBytes": 2097152}
    assert get_used_bytes(u2) == 2097152

    # 3. Nested is 0 but flat has value
    u3 = {"userTraffic": {"usedTrafficBytes": 0}, "usedTrafficBytes": 3145728}
    assert get_used_bytes(u3) == 3145728

    # 4. String values
    u4 = {"usedTrafficBytes": "4194304"}
    assert get_used_bytes(u4) == 4194304

    # 5. Invalid / None
    assert get_used_bytes(None) == 0
    assert get_used_bytes({}) == 0
    assert get_used_bytes({"usedTrafficBytes": "invalid"}) == 0


def test_periodic_bandwidth_cache_key_ssot():
    """Verify admin charts and user profile use identical periodic bandwidth cache key."""
    from bot.web.admin_overview_charts import USERS_PERIODIC_BANDWIDTH_CACHE_KEY
    from bot.web.user_profile import USERS_PERIODIC_BANDWIDTH_CACHE_KEY as USER_KEY

    assert USERS_PERIODIC_BANDWIDTH_CACHE_KEY == "analytics:users_periodic_bandwidth_v6"
    assert USERS_PERIODIC_BANDWIDTH_CACHE_KEY == USER_KEY
