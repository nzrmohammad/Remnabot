"""Repository for the admin-managed services (plans) shown to users."""
import logging

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Service

logger = logging.getLogger(__name__)

# Single Source of Truth for service/plan ordering across Shop, Admin, and Telegram bot menus.
SERVICE_ORDER_BY = (Service.sort_order.asc(), Service.price.asc(), Service.id.asc())


class ServiceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> list[Service]:
        result = await self.session.execute(
            select(Service).order_by(*SERVICE_ORDER_BY)
        )
        return list(result.scalars().all())

    async def list_active(self) -> list[Service]:
        try:
            result = await self.session.execute(
                select(Service).where(
                    Service.is_active.is_(True),
                    or_(
                        Service.max_purchases.is_(None),
                        Service.purchases_count < Service.max_purchases,
                    ),
                ).order_by(*SERVICE_ORDER_BY)
            )
            return list(result.scalars().all())
        except Exception as exc:
            logger.warning("Failed to query active services with purchase limits (%s), falling back to basic query", exc)
            await self.session.rollback()
            try:
                result = await self.session.execute(
                    select(Service).where(Service.is_active.is_(True)).order_by(*SERVICE_ORDER_BY)
                )
                return list(result.scalars().all())
            except Exception as exc2:
                logger.exception("Failed fallback query for active services: %s", exc2)
                await self.session.rollback()
                raise

    async def get(self, service_id: int) -> Service | None:
        result = await self.session.execute(
            select(Service).where(Service.id == service_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, service_id: int) -> Service | None:
        """Alias for get(), used by gift handlers."""
        return await self.get(service_id)

    async def create(
        self,
        name: str,
        price: int,
        duration_days: int,
        traffic_gb: int,
        description: str | None = None,
        traffic_strategy: str = "NO_RESET",
        hwid_limit: int | None = None,
        squad_uuid: str | None = None,
        sort_order: int | None = None,
    ) -> Service:
        resolved_order = sort_order
        if resolved_order is None:
            max_sort = await self.session.scalar(select(func.coalesce(func.max(Service.sort_order), 0)))
            resolved_order = (int(max_sort) + 1) if max_sort and int(max_sort) > 0 else 0
        service = Service(
            name=name,
            price=price,
            duration_days=duration_days,
            traffic_gb=traffic_gb,
            description=description or None,
            traffic_strategy=traffic_strategy,
            hwid_limit=hwid_limit,
            squad_uuid=squad_uuid,
            sort_order=resolved_order,
        )
        self.session.add(service)
        await self.session.flush()  # populates service.id
        return service

    async def update(self, service_id: int, **fields) -> Service | None:
        service = await self.get(service_id)
        if service is None:
            return None
        for key, value in fields.items():
            setattr(service, key, value)
        return service

    async def set_active(self, service_id: int, is_active: bool) -> bool:
        service = await self.get(service_id)
        if service is None:
            return False
        service.is_active = is_active
        return True

    async def delete(self, service_id: int) -> bool:
        service = await self.get(service_id)
        if service is None:
            return False
        await self.session.delete(service)
        return True
