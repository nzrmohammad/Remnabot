"""Repository for support reply routing and persistent support chat transcripts."""
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import SupportChatMessage, SupportMessage


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

    async def add_chat_message(
        self,
        telegram_id: int,
        sender: str,
        text: str,
        external_msg_id: str = "",
        created_at: datetime | None = None,
    ) -> SupportChatMessage:
        """Persist a single support chat message row."""
        row = SupportChatMessage(
            telegram_id=int(telegram_id),
            external_msg_id=str(external_msg_id or "")[:64],
            sender=str(sender or "user")[:16],
            text=str(text),
            created_at=created_at or datetime.now(timezone.utc),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_chat_messages(self, telegram_id: int, limit: int = 50) -> list[SupportChatMessage]:
        """Return chronological (oldest -> newest) bounded transcript for one user."""
        stmt = (
            select(SupportChatMessage)
            .where(SupportChatMessage.telegram_id == int(telegram_id))
            .order_by(SupportChatMessage.id.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        rows = list(res.scalars().all())
        rows.reverse()
        return rows

    async def list_active_chat_user_ids(self, limit: int = 100) -> list[int]:
        """Return distinct user telegram_ids ordered by latest message activity."""
        stmt = (
            select(SupportChatMessage.telegram_id)
            .group_by(SupportChatMessage.telegram_id)
            .order_by(func.max(SupportChatMessage.id).desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [int(tid) for tid in res.scalars().all()]
