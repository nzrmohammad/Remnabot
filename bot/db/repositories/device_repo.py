"""Repository for known HWID devices."""
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import KnownDevice


class DeviceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_known_hwids(self, account_id: str | int) -> set[str]:
        """Set of known HWIDs for this account_id."""
        result = await self.session.execute(
            select(KnownDevice.hwid).where(KnownDevice.account_id == str(account_id))
        )
        return set(result.scalars().all())

    async def add_device(
        self,
        telegram_id: int,
        account_id: str | int,
        hwid: str,
        platform: str | None = None,
        device_model: str | None = None,
    ) -> KnownDevice:
        dev = KnownDevice(
            telegram_id=telegram_id,
            account_id=str(account_id),
            hwid=hwid,
            platform=platform,
            device_model=device_model,
        )
        self.session.add(dev)
        await self.session.flush()
        return dev

    async def remove_device(self, account_id: str | int, hwid: str) -> None:
        await self.session.execute(
            delete(KnownDevice).where(
                KnownDevice.account_id == str(account_id),
                KnownDevice.hwid == hwid,
            )
        )
