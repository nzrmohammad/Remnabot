"""Tests for hourly traffic snapshot tracking and performance optimizations."""
import datetime
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp.test_utils import make_mocked_request
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.db.models import Base, HourlyTrafficSnapshot
from bot.db.repositories.traffic_snapshot_repo import TrafficSnapshotRepository
from bot.services.traffic_monitor import record_hourly_traffic_snapshot_once
from bot.web.cache import FastCache
from bot.web.routes_admin import get_admin_overview


@pytest.mark.anyio
async def test_traffic_snapshot_repository_lifecycle():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    now = datetime.datetime(2026, 10, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)

    async with session_factory() as session:
        repo = TrafficSnapshotRepository(session)
        # 1. Initially empty
        latest = await repo.get_latest_snapshot()
        assert latest is None

        # 2. Record first snapshot
        s1 = await repo.record_snapshot(
            timestamp=now - datetime.timedelta(hours=2),
            total_bytes=100 * (1024**3),
            delta_bytes=5 * (1024**3),
        )
        assert s1.id is not None
        assert s1.total_bytes == 100 * (1024**3)
        assert s1.delta_bytes == 5 * (1024**3)

        # 3. Record second snapshot
        s2 = await repo.record_snapshot(
            timestamp=now - datetime.timedelta(hours=1),
            total_bytes=110 * (1024**3),
            delta_bytes=10 * (1024**3),
        )

        # 4. Check latest
        latest = await repo.get_latest_snapshot()
        assert latest is not None
        assert latest.id == s2.id
        assert latest.delta_bytes == 10 * (1024**3)

        # 5. List 24h snapshots
        snapshots = await repo.get_last_24_hours(now=now)
        assert len(snapshots) == 2
        assert snapshots[0].id == s1.id
        assert snapshots[1].id == s2.id

    await engine.dispose()


@pytest.mark.anyio
async def test_record_hourly_traffic_snapshot_once():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    mock_remnawave = AsyncMock()
    # Return 2 users with traffic
    mock_remnawave.get_all_panel_users.return_value = [
        {"id": 1, "status": "ACTIVE", "usedTrafficBytes": 20 * (1024**3)},
        {"id": 2, "status": "ACTIVE", "userTraffic": {"usedTrafficBytes": 30 * (1024**3)}},
    ]

    # Run snapshot recorder
    await record_hourly_traffic_snapshot_once(session_factory, mock_remnawave)

    async with session_factory() as session:
        repo = TrafficSnapshotRepository(session)
        latest = await repo.get_latest_snapshot()
        assert latest is not None
        assert latest.total_bytes == 50 * (1024**3)
        assert latest.delta_bytes == 0  # First baseline snapshot has 0 delta

    # Now simulate another hour with increased traffic
    mock_remnawave.get_all_panel_users.return_value = [
        {"id": 1, "status": "ACTIVE", "usedTrafficBytes": 25 * (1024**3)},
        {"id": 2, "status": "ACTIVE", "userTraffic": {"usedTrafficBytes": 35 * (1024**3)}},
    ]

    # Force a new hour by passing future_time
    future_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    await record_hourly_traffic_snapshot_once(session_factory, mock_remnawave, now_utc=future_time)

    async with session_factory() as session:
        repo = TrafficSnapshotRepository(session)
        snapshots = await repo.get_last_24_hours()
        assert len(snapshots) == 2
        latest = await repo.get_latest_snapshot()
        assert latest.total_bytes == 60 * (1024**3)
        assert latest.delta_bytes == 10 * (1024**3)  # 60 - 50 = 10 GB

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_overview_uses_real_hourly_snapshots():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    target_hour = now_utc.hour

    # Insert a real snapshot for target hour
    async with session_factory() as session:
        repo = TrafficSnapshotRepository(session)
        await repo.record_snapshot(
            timestamp=datetime.datetime(
                now_utc.year, now_utc.month, now_utc.day, target_hour, tzinfo=datetime.timezone.utc
            ),
            total_bytes=100 * (1024**3),
            delta_bytes=15 * (1024**3),  # 15 GB delta
        )

    mock_remnawave = AsyncMock()
    mock_remnawave.get_all_panel_users.return_value = []
    mock_remnawave.get_nodes.return_value = []
    mock_remnawave.get_hwid_stats.return_value = {}

    app = {
        "bot_token": "123:abc",
        "admin_ids": [11111],
        "is_dev": True,
        "session_factory": session_factory,
        "cache": FastCache(redis_client=None),
        "remnawave": mock_remnawave,
    }

    req = make_mocked_request("GET", "/api/admin/overview?user_id=11111&refresh=1", app=app)
    resp = await get_admin_overview(req)
    assert resp.status == 200

    import json
    data = json.loads(resp.text)
    hourly = data["data"]["charts"]["hourly_distribution"]
    assert hourly["is_real_telemetry"] is True
    # The target_hour bucket (2-hour interval) must match at least 15.0 GB
    bin_idx = target_hour // 2
    assert hourly["data"][bin_idx] >= 15.0

    await engine.dispose()
