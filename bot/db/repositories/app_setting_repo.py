"""Repository for runtime-editable store settings (key/value)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AppSetting


class AppSettingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> str | None:
        result = await self.session.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        return setting.value if setting else None

    async def set(self, key: str, value: str) -> None:
        result = await self.session.execute(
            select(AppSetting).where(AppSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        if setting is None:
            self.session.add(AppSetting(key=key, value=value))
        else:
            setting.value = value
        await self.session.flush()

    async def all(self) -> dict[str, str]:
        result = await self.session.execute(select(AppSetting))
        return {s.key: s.value for s in result.scalars().all()}
