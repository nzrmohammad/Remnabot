"""Repository for the admin-managed services (plans) shown to users."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Service


class ServiceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> list[Service]:
        result = await self.session.execute(
            select(Service).order_by(Service.id)
        )
        return list(result.scalars().all())

    async def list_active(self) -> list[Service]:
        result = await self.session.execute(
            select(Service).where(Service.is_active.is_(True)).order_by(Service.id)
        )
        return list(result.scalars().all())

    async def get(self, service_id: int) -> Service | None:
        result = await self.session.execute(
            select(Service).where(Service.id == service_id)
        )
        return result.scalar_one_or_none()

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
    ) -> Service:
        service = Service(
            name=name,
            price=price,
            duration_days=duration_days,
            traffic_gb=traffic_gb,
            description=description or None,
            traffic_strategy=traffic_strategy,
            hwid_limit=hwid_limit,
            squad_uuid=squad_uuid,
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
