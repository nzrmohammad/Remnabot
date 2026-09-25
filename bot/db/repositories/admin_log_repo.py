"""Repository for the admin action audit log."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminLog


class AdminLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(self, admin_id: int, action: str, detail: str | None = None) -> None:
        self.session.add(AdminLog(admin_id=admin_id, action=action, detail=detail))
        await self.session.flush()

    async def recent(self, limit: int = 15) -> list[AdminLog]:
        result = await self.session.execute(
            select(AdminLog).order_by(AdminLog.id.desc()).limit(limit)
        )
        return list(result.scalars().all())
