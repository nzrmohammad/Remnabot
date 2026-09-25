"""Repository for completed (auto-activated) purchases / orders."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Order


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        telegram_id: int,
        service_id: int,
        service_name: str,
        amount: int,
        duration_days: int,
        traffic_gb: int,
        panel_user_id: int | None,
        panel_username: str | None,
        subscription_url: str | None,
        status: str = "paid",
    ) -> Order:
        order = Order(
            telegram_id=telegram_id,
            service_id=service_id,
            service_name=service_name,
            amount=amount,
            duration_days=duration_days,
            traffic_gb=traffic_gb,
            panel_user_id=panel_user_id,
            panel_username=panel_username,
            subscription_url=subscription_url,
            status=status,
        )
        self.session.add(order)
        await self.session.flush()
        return order

    async def mark_paid(
        self,
        order: Order,
        panel_user_id: int | None,
        panel_username: str | None,
        subscription_url: str | None,
    ) -> None:
        """Finalize a pending order after panel success + wallet deduction."""
        order.status = "paid"
        order.panel_user_id = panel_user_id
        order.panel_username = panel_username
        order.subscription_url = subscription_url

    async def mark_failed(self, order: Order) -> None:
        """Panel error / balance race — never charged, safe to retry."""
        order.status = "failed"

    async def list_pending(self, older_than_minutes: int = 15) -> list[Order]:
        """Pending orders stuck past the crash window (for the reconcile job)."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        result = await self.session.execute(
            select(Order)
            .where(Order.status == "pending", Order.created_at < cutoff)
            .order_by(Order.id)
        )
        return list(result.scalars().all())

    async def get(self, order_id: int) -> Order | None:
        result = await self.session.execute(
            select(Order).where(Order.id == order_id)
        )
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 10) -> list[Order]:
        result = await self.session.execute(
            select(Order).order_by(Order.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def list_for_user(self, telegram_id: int, limit: int = 10) -> list[Order]:
        result = await self.session.execute(
            select(Order)
            .where(Order.telegram_id == telegram_id)
            .order_by(Order.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count(self, since: datetime | None = None) -> int:
        stmt = select(func.count(Order.id))
        if since is not None:
            stmt = stmt.where(Order.created_at >= since)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def total_revenue(self, since: datetime | None = None) -> int:
        """Sum of PAID orders (refunds are excluded)."""
        stmt = select(func.coalesce(func.sum(Order.amount), 0)).where(
            Order.status == "paid"
        )
        if since is not None:
            stmt = stmt.where(Order.created_at >= since)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def mark_refunded(self, order: Order) -> None:
        order.status = "refunded"
        order.refunded_at = datetime.now(timezone.utc)

    async def claim_refund(self, order_id: int) -> Order | None:
        """Atomically move an order from paid -> refunded.

        Returns the Order on success, None if already refunded
        (prevents double-refund on concurrent admin clicks).
        """
        now = datetime.now(timezone.utc)
        row = await self.session.execute(
            text(
                "UPDATE orders SET status = 'refunded', refunded_at = :now "
                "WHERE id = :i AND status = 'paid' RETURNING id"
            ),
            {"now": now, "i": order_id},
        )
        claimed = row.scalar_one_or_none()
        await self.session.flush()
        if claimed is None:
            return None
        return await self.get(order_id)

    async def list_filtered(
        self,
        status: str = "all",
        query: str | None = None,
        offset: int = 0,
        limit: int = 8,
    ) -> list[Order]:
        """List orders matching status filter and optional search query with pagination."""
        stmt = select(Order)
        if status and status != "all":
            stmt = stmt.where(Order.status == status)
        if query:
            q = query.strip()
            if q.isdigit():
                stmt = stmt.where(
                    or_(
                        Order.id == int(q),
                        Order.telegram_id == int(q),
                        Order.panel_user_id == int(q),
                    )
                )
            else:
                stmt = stmt.where(
                    or_(
                        Order.panel_username.ilike(f"%{q}%"),
                        Order.service_name.ilike(f"%{q}%"),
                    )
                )
        stmt = stmt.order_by(Order.id.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        status: str = "all",
        query: str | None = None,
    ) -> int:
        """Count orders matching status filter and optional search query."""
        stmt = select(func.count(Order.id))
        if status and status != "all":
            stmt = stmt.where(Order.status == status)
        if query:
            q = query.strip()
            if q.isdigit():
                stmt = stmt.where(
                    or_(
                        Order.id == int(q),
                        Order.telegram_id == int(q),
                        Order.panel_user_id == int(q),
                    )
                )
            else:
                stmt = stmt.where(
                    or_(
                        Order.panel_username.ilike(f"%{q}%"),
                        Order.service_name.ilike(f"%{q}%"),
                    )
                )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def status_counts(self, query: str | None = None) -> dict[str, int]:
        """Return counts by status ('paid', 'pending', 'failed', 'refunded') and 'all'."""
        stmt = select(Order.status, func.count(Order.id))
        if query:
            q = query.strip()
            if q.isdigit():
                stmt = stmt.where(
                    or_(
                        Order.id == int(q),
                        Order.telegram_id == int(q),
                        Order.panel_user_id == int(q),
                    )
                )
            else:
                stmt = stmt.where(
                    or_(
                        Order.panel_username.ilike(f"%{q}%"),
                        Order.service_name.ilike(f"%{q}%"),
                    )
                )
        stmt = stmt.group_by(Order.status)
        result = await self.session.execute(stmt)
        counts = {str(row[0]): int(row[1]) for row in result.all()}
        counts["all"] = sum(counts.values())
        return counts

