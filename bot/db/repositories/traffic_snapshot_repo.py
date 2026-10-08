"""Repository for hourly cluster traffic snapshots."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import HourlyTrafficSnapshot


class TrafficSnapshotRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_latest_snapshot(self) -> HourlyTrafficSnapshot | None:
        """Return the most recently recorded hourly snapshot."""
        stmt = (
            select(HourlyTrafficSnapshot)
            .order_by(desc(HourlyTrafficSnapshot.timestamp))
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def record_snapshot(
        self,
        timestamp: datetime,
        total_bytes: int,
        delta_bytes: int,
    ) -> HourlyTrafficSnapshot:
        """Create a new snapshot record for the given timestamp."""
        snapshot = HourlyTrafficSnapshot(
            timestamp=timestamp,
            total_bytes=total_bytes,
            delta_bytes=delta_bytes,
        )
        self.session.add(snapshot)
        await self.session.commit()
        await self.session.refresh(snapshot)
        return snapshot

    async def get_last_24_hours(self, now: datetime | None = None) -> list[HourlyTrafficSnapshot]:
        """Fetch all recorded snapshots within the last 24 hours."""
        if now is None:
            now = datetime.now(timezone.utc)
        since = now - timedelta(hours=24)
        stmt = (
            select(HourlyTrafficSnapshot)
            .where(HourlyTrafficSnapshot.timestamp >= since)
            .order_by(HourlyTrafficSnapshot.timestamp.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def cleanup_older_than(self, days: int = 30) -> int:
        """Delete snapshots older than specified days to keep the database lightweight."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = delete(HourlyTrafficSnapshot).where(HourlyTrafficSnapshot.timestamp < cutoff)
        res = await self.session.execute(stmt)
        await self.session.commit()
        return res.rowcount or 0
