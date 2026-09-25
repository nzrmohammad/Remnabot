"""Repository for the per-user nightly/weekly/monthly report switches."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import ReportSettings


class ReportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_settings(self, telegram_id: int) -> ReportSettings:
        result = await self.session.execute(
            select(ReportSettings).where(ReportSettings.telegram_id == telegram_id)
        )
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = ReportSettings(telegram_id=telegram_id)
            self.session.add(settings)
            await self.session.flush()
        return settings

    async def toggle_nightly(self, telegram_id: int) -> ReportSettings:
        settings = await self.get_settings(telegram_id)
        settings.nightly = not settings.nightly
        return settings

    async def toggle_weekly(self, telegram_id: int) -> ReportSettings:
        settings = await self.get_settings(telegram_id)
        settings.weekly = not settings.weekly
        return settings

    async def toggle_monthly(self, telegram_id: int) -> ReportSettings:
        settings = await self.get_settings(telegram_id)
        settings.monthly = not settings.monthly
        return settings
