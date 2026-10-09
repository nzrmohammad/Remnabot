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

    async def toggle_clean_reports(self, telegram_id: int) -> ReportSettings:
        settings = await self.get_settings(telegram_id)
        settings.clean_reports = not settings.clean_reports
        return settings

    async def toggle_wheel_notify(self, telegram_id: int) -> ReportSettings:
        settings = await self.get_settings(telegram_id)
        settings.wheel_notify = not settings.wheel_notify
        return settings

    async def record_wheel_spin(self, telegram_id: int) -> ReportSettings:
        from datetime import datetime, timezone
        settings = await self.get_settings(telegram_id)
        settings.wheel_last_spin_at = datetime.now(timezone.utc)
        settings.wheel_notified = False
        return settings

    async def get_users_due_for_wheel_reminder(self) -> list[ReportSettings]:
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self.session.execute(
            select(ReportSettings).where(
                ReportSettings.wheel_notify.is_(True),
                ReportSettings.wheel_notified.is_(False),
                ReportSettings.wheel_last_spin_at.is_not(None),
                ReportSettings.wheel_last_spin_at <= cutoff,
            )
        )
        return list(result.scalars().all())

