"""Repository for referral tracking and rewards."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import ReferralReward, User


class ReferralRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_reward(
        self, inviter_id: int, referee_id: int, reward_gb: int = 5
    ) -> ReferralReward:
        reward = ReferralReward(
            inviter_id=inviter_id,
            referee_id=referee_id,
            reward_gb=reward_gb,
            applied=True,
        )
        self.session.add(reward)
        await self.session.flush()
        return reward

    async def has_rewarded(self, referee_id: int, inviter_id: int | None = None) -> bool:
        stmt = select(func.count(ReferralReward.id)).where(ReferralReward.referee_id == referee_id)
        if inviter_id is not None:
            stmt = stmt.where(ReferralReward.inviter_id == inviter_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one()) > 0

    async def get_invites_count(self, inviter_id: int) -> int:
        result = await self.session.execute(
            select(func.count(User.id)).where(User.referred_by_id == inviter_id)
        )
        return int(result.scalar_one())

    async def get_total_gb_earned(self, inviter_id: int) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(ReferralReward.reward_gb), 0)).where(
                ReferralReward.inviter_id == inviter_id,
                ReferralReward.applied.is_(True),
            )
        )
        return int(result.scalar_one())
