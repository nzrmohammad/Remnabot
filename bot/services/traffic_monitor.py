"""Background worker: Hourly cluster traffic snapshot recorder."""
import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from bot.common.helpers import get_used_bytes
from bot.db.repositories.traffic_snapshot_repo import TrafficSnapshotRepository
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)


async def record_hourly_traffic_snapshot_once(
    session_factory: Any,
    remnawave: RemnawaveClient,
    now_utc: datetime | None = None,
) -> None:
    """Record a single hourly snapshot of cluster-wide traffic consumption."""
    try:
        panel_users = await remnawave.get_all_panel_users(size=1000) or []
    except Exception as exc:
        logger.warning("Failed to fetch panel users for traffic snapshot: %s", exc)
        return

    current_total_bytes = sum(get_used_bytes(u) for u in panel_users)
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    current_hour_dt = datetime(
        now_utc.year, now_utc.month, now_utc.day, now_utc.hour, tzinfo=timezone.utc
    )

    async with session_factory() as session:
        repo = TrafficSnapshotRepository(session)
        latest = await repo.get_latest_snapshot()

        def _to_utc(dt: datetime) -> datetime:
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

        if latest and _to_utc(latest.timestamp) >= current_hour_dt:
            # Current hour already has a snapshot
            return

        if latest and latest.total_bytes > 0:
            delta_bytes = max(0, current_total_bytes - latest.total_bytes)
        else:
            delta_bytes = 0

        await repo.record_snapshot(
            timestamp=current_hour_dt,
            total_bytes=current_total_bytes,
            delta_bytes=delta_bytes,
        )
        logger.info(
            "📊 Recorded hourly traffic snapshot for %s: Total=%d B, Delta=%d B",
            current_hour_dt.strftime("%Y-%m-%d %H:00"),
            current_total_bytes,
            delta_bytes,
        )

        # Periodically cleanup snapshots older than 30 days
        try:
            await repo.cleanup_older_than(days=30)
        except Exception:
            pass


async def traffic_monitor_loop(
    remnawave: RemnawaveClient,
    session_factory: Any,
    interval_seconds: int = 600,
) -> None:
    """Background loop that records hourly traffic snapshots at every hour boundary."""
    logger.info("⏱️ Traffic monitor loop started (check interval: %ds)", interval_seconds)
    # Give the app a few seconds to finish boot
    await asyncio.sleep(10)

    # Initial check on startup
    try:
        await record_hourly_traffic_snapshot_once(session_factory, remnawave)
    except Exception as exc:
        logger.warning("Initial traffic snapshot check failed: %s", exc)

    while True:
        try:
            await record_hourly_traffic_snapshot_once(session_factory, remnawave)
        except asyncio.CancelledError:
            logger.info("Traffic monitor loop canceled.")
            break
        except Exception as exc:
            logger.error("Error in traffic monitor loop: %s", exc)

        await asyncio.sleep(interval_seconds)
