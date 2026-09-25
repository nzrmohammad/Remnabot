"""Repository for routing support replies (admin chat → user chat)."""
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import SupportMessage


class SupportMessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def map_message(self, admin_message_id: int, telegram_id: int) -> None:
        self.session.add(
            SupportMessage(admin_message_id=admin_message_id, telegram_id=telegram_id)
        )
        await self.session.flush()

    async def get_user(self, admin_message_id: int) -> int | None:
        result = await self.session.execute(
            select(SupportMessage).where(
                SupportMessage.admin_message_id == admin_message_id
            )
        )
        row = result.scalar_one_or_none()
        return row.telegram_id if row else None

    async def prune_old(self, limit: int = 5000) -> None:
        """Keep only the newest `limit` rows to bound table growth."""
        count = await self.session.execute(select(func.count(SupportMessage.admin_message_id)))
        total = int(count.scalar_one())
        if total <= limit:
            return
        cutoff = await self.session.execute(
            select(SupportMessage.admin_message_id)
            .order_by(SupportMessage.admin_message_id.desc())
            .offset(limit)
            .limit(1)
        )
        cutoff_id = cutoff.scalar_one_or_none()
        if cutoff_id is not None:
            await self.session.execute(
                delete(SupportMessage).where(SupportMessage.admin_message_id <= cutoff_id)
            )
            await self.session.flush()
