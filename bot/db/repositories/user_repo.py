"""Repository layer: all DB queries for the User model live here."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User

# Users active within this window are considered "online".
ONLINE_WINDOW = timedelta(minutes=30)


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self, telegram_id: int, username: str | None, full_name: str | None = None
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(telegram_id=telegram_id, username=username, full_name=full_name)
            self.session.add(user)
            await self.session.flush()
        else:
            if username and user.username != username:
                user.username = username
            if full_name and user.full_name != full_name:
                user.full_name = full_name
        user.last_active_at = datetime.now(timezone.utc)
        return user

    async def set_language(self, user: User, language: str) -> None:
        user.language = language

    async def set_menu_message_id(self, user: User, message_id: int | None) -> None:
        user.menu_message_id = message_id

    async def set_verified(self, user: User, verified: bool = True) -> None:
        user.is_verified = verified

    async def all_users(self) -> list[User]:
        result = await self.session.execute(select(User))
        return list(result.scalars())

    async def list_paginated(
        self,
        offset: int,
        limit: int,
        condition=None,
    ) -> list[User]:
        stmt = select(User).order_by(User.id)
        if condition is not None:
            stmt = stmt.where(condition)
        result = await self.session.execute(stmt.offset(offset).limit(limit))
        return list(result.scalars().all())

    async def count(self, condition=None) -> int:
        stmt = select(func.count(User.id))
        if condition is not None:
            stmt = stmt.where(condition)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def search(self, query: str, limit: int = 10) -> list[User]:
        """Search by Telegram ID (numeric) or @username (case-insensitive)."""
        q = query.strip().lstrip("@")
        conditions = []
        if q.isdigit():
            conditions.append(User.telegram_id == int(q))
        if q:
            conditions.append(User.username.ilike(f"%{q}%"))
        if not conditions:
            return []
        result = await self.session.execute(
            select(User).where(or_(*conditions)).order_by(User.id).limit(limit)
        )
        return list(result.scalars().all())

    async def balances_for(self, telegram_ids: list[int]) -> dict[int, int]:
        """Balances for exactly the given users (avoids loading all wallets)."""
        if not telegram_ids:
            return {}
        from bot.db.models import Wallet

        result = await self.session.execute(
            select(Wallet).where(Wallet.telegram_id.in_(telegram_ids))
        )
        return {w.telegram_id: w.balance for w in result.scalars().all()}

    @staticmethod
    def online_condition():
        return User.last_active_at >= datetime.now(timezone.utc) - ONLINE_WINDOW

    async def set_referrer(self, user: User | int, referrer_id: int) -> None:
        if isinstance(user, int):
            user = await self.get_by_telegram_id(user)
        if user:
            user.referred_by_id = referrer_id

    async def set_claimed_trial(self, user: User | int, claimed: bool = True) -> None:
        if isinstance(user, int):
            user = await self.get_by_telegram_id(user)
        if user:
            user.has_claimed_trial = claimed

    async def set_banned(self, user: User | int, banned: bool = True) -> None:
        if isinstance(user, int):
            user = await self.get_by_telegram_id(user)
        if user:
            user.is_banned = banned

    async def list_banned(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.is_banned.is_(True)).order_by(User.id.desc())
        )
        return list(result.scalars().all())
