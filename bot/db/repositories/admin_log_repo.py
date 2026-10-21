"""Repository for the admin action audit log."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminLog


class AdminLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(self, admin_id: int, action: str, detail: str | None = None, target_user_id: int | None = None) -> None:
        if target_user_id is None and detail:
            import re
            m = re.search(r"(?:target_id=|user_id=|کاربر\s+)(\d+)", detail)
            if m:
                try:
                    target_user_id = int(m.group(1))
                except (ValueError, TypeError):
                    pass
        self.session.add(AdminLog(admin_id=admin_id, action=action, detail=detail, target_user_id=target_user_id))
        await self.session.flush()

    async def recent(self, limit: int = 15) -> list[AdminLog]:
        result = await self.session.execute(
            select(AdminLog).order_by(AdminLog.id.desc()).limit(limit)
        )
        return list(result.scalars().all())
