"""Repository for ad/marketing campaigns."""
import logging
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Campaign, Order, User

logger = logging.getLogger(__name__)


class CampaignRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, code: str, name: str, cost: int = 0) -> Campaign:
        normalized_code = code.strip().lower()
        campaign = Campaign(
            code=normalized_code,
            name=name.strip(),
            cost=int(cost or 0),
        )
        self.session.add(campaign)
        await self.session.commit()
        await self.session.refresh(campaign)
        return campaign

    async def get_by_code(self, code: str) -> Campaign | None:
        normalized = code.strip().lower()
        stmt = select(Campaign).where(Campaign.code == normalized)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_all(self) -> list[Campaign]:
        stmt = select(Campaign).order_by(Campaign.created_at.desc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def delete(self, campaign_id: int) -> bool:
        stmt = select(Campaign).where(Campaign.id == campaign_id)
        res = await self.session.execute(stmt)
        item = res.scalar_one_or_none()
        if not item:
            return False
        await self.session.delete(item)
        await self.session.commit()
        return True

    async def get_campaigns_with_stats(self, bot_username: str = "") -> list[dict]:
        campaigns = await self.list_all()
        stats = []
        for c in campaigns:
            # 1. Total users registered through this campaign
            u_stmt = select(func.count(User.id)).where(User.campaign_code == c.code)
            u_res = await self.session.execute(u_stmt)
            users_count = int(u_res.scalar_one() or 0)

            # 2. Distinct buyers
            b_stmt = (
                select(func.count(distinct(Order.telegram_id)))
                .join(User, Order.telegram_id == User.telegram_id)
                .where(User.campaign_code == c.code, Order.status == "paid")
            )
            b_res = await self.session.execute(b_stmt)
            buyers_count = int(b_res.scalar_one() or 0)

            # 3. Total revenue from this campaign
            r_stmt = (
                select(func.coalesce(func.sum(Order.amount), 0))
                .join(User, Order.telegram_id == User.telegram_id)
                .where(User.campaign_code == c.code, Order.status == "paid")
            )
            r_res = await self.session.execute(r_stmt)
            total_revenue = int(r_res.scalar_one() or 0)

            profit = total_revenue - c.cost
            roi_pct = round((profit / c.cost) * 100, 1) if c.cost > 0 else 0

            clean_username = bot_username.strip().lstrip("@") if bot_username else ""
            deep_link = f"https://t.me/{clean_username}?start=ad_{c.code}" if clean_username else f"https://t.me/?start=ad_{c.code}"

            stats.append({
                "id": c.id,
                "code": c.code,
                "name": c.name,
                "cost": c.cost,
                "cost_formatted": f"{c.cost:,} تومان",
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "users_count": users_count,
                "buyers_count": buyers_count,
                "conversion_rate": round((buyers_count / users_count) * 100, 1) if users_count > 0 else 0.0,
                "total_revenue": total_revenue,
                "total_revenue_formatted": f"{total_revenue:,} تومان",
                "profit": profit,
                "profit_formatted": f"{profit:,} تومان",
                "roi_percent": roi_pct,
                "roi": roi_pct,
                "deep_link": deep_link,
            })
        return stats
