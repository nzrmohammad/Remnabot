"""Repository for managing server / node infrastructure costs and billing."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import NodeCost


class NodeCostRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_uuid(self, node_uuid: str) -> NodeCost | None:
        result = await self.session.execute(
            select(NodeCost).where(NodeCost.node_uuid == str(node_uuid))
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[NodeCost]:
        result = await self.session.execute(
            select(NodeCost).order_by(NodeCost.id)
        )
        return list(result.scalars().all())

    async def upsert(
        self,
        node_uuid: str,
        node_id: int | None = None,
        node_name: str | None = None,
        provider: str | None = None,
        monthly_cost_toman: int = 0,
        monthly_cost_eur: float = 0.0,
        due_date: datetime | None = None,
        notes: str | None = None,
    ) -> NodeCost:
        item = await self.get_by_uuid(node_uuid)
        if item is None:
            item = NodeCost(
                node_uuid=str(node_uuid),
                node_id=node_id,
                node_name=node_name,
                provider=provider,
                monthly_cost_toman=monthly_cost_toman,
                monthly_cost_eur=monthly_cost_eur,
                due_date=due_date,
                notes=notes,
                alert_notified=False,
            )
            self.session.add(item)
        else:
            if node_id is not None:
                item.node_id = node_id
            if node_name is not None:
                item.node_name = node_name
            if provider is not None:
                item.provider = provider
            item.monthly_cost_toman = monthly_cost_toman
            item.monthly_cost_eur = monthly_cost_eur
            # If due date changed, reset alert_notified
            if item.due_date != due_date:
                item.due_date = due_date
                item.alert_notified = False
            if notes is not None:
                item.notes = notes

        await self.session.flush()
        return item

    async def list_due_soon(self, days_threshold: int = 3) -> list[NodeCost]:
        """Return nodes whose due_date is within the next `days_threshold` days and not yet alerted."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        threshold = now + timedelta(days=days_threshold)
        result = await self.session.execute(
            select(NodeCost).where(
                NodeCost.due_date.is_not(None),
                NodeCost.due_date <= threshold,
                NodeCost.alert_notified.is_(False),
            )
        )
        return list(result.scalars().all())

    async def mark_alert_sent(self, node_uuid: str, sent: bool = True) -> None:
        item = await self.get_by_uuid(node_uuid)
        if item is not None:
            item.alert_notified = sent
            await self.session.flush()
