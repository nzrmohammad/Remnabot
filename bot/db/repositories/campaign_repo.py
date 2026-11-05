"""Repository for ad/marketing campaigns."""
import logging

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common.links import ad_link
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
        if not campaigns:
            return []

        campaign_codes = [c.code for c in campaigns if c.code]
        users_by_code: dict[str, int] = {}
        buyers_rev_by_code: dict[str, tuple[int, int]] = {}

        if campaign_codes:
            try:
                u_stmt = (
                    select(User.campaign_code, func.count(User.id))
                    .where(User.campaign_code.in_(campaign_codes))
                    .group_by(User.campaign_code)
                )
                u_res = await self.session.execute(u_stmt)
                users_by_code = {row[0]: int(row[1] or 0) for row in u_res.fetchall()}
            except Exception as e:
                logger.warning("Error batch querying campaign users count: %s", e)

            try:
                b_stmt = (
                    select(
                        User.campaign_code,
                        func.count(distinct(Order.telegram_id)),
                        func.coalesce(func.sum(Order.amount), 0),
                    )
                    .join(User, Order.telegram_id == User.telegram_id)
                    .where(User.campaign_code.in_(campaign_codes), Order.status.in_(["paid", "PAID"]))
                    .group_by(User.campaign_code)
                )
                b_res = await self.session.execute(b_stmt)
                buyers_rev_by_code = {
                    row[0]: (int(row[1] or 0), int(row[2] or 0)) for row in b_res.fetchall()
                }
            except Exception as e:
                logger.warning("Error batch querying campaign buyers/revenue: %s", e)

        stats = []
        for c in campaigns:
            try:
                users_count = users_by_code.get(c.code, 0)
                buyers_count, total_revenue = buyers_rev_by_code.get(c.code, (0, 0))

                profit = total_revenue - c.cost
                roi_pct = round((profit / c.cost) * 100, 1) if c.cost > 0 else 0
                deep_link = ad_link(bot_username, c.code)

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
            except Exception as e:
                logger.warning("Error computing stats for campaign %s: %s", getattr(c, 'code', 'unknown'), e)
                stats.append({
                    "id": c.id,
                    "code": c.code,
                    "name": c.name,
                    "cost": getattr(c, 'cost', 0) or 0,
                    "cost_formatted": f"{getattr(c, 'cost', 0) or 0:,} تومان",
                    "created_at": c.created_at.isoformat() if getattr(c, 'created_at', None) else None,
                    "users_count": 0,
                    "buyers_count": 0,
                    "conversion_rate": 0.0,
                    "total_revenue": 0,
                    "total_revenue_formatted": "0 تومان",
                    "profit": 0,
                    "profit_formatted": "0 تومان",
                    "roi_percent": 0.0,
                    "roi": 0.0,
                    "deep_link": ad_link(bot_username, c.code),
                })
        return stats
