"""Repository for alert settings (per user) and alert state (per account)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AlertSettings, AlertState


class AlertRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #
    async def get_settings(self, telegram_id: int) -> AlertSettings:
        result = await self.session.execute(
            select(AlertSettings).where(AlertSettings.telegram_id == telegram_id)
        )
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = AlertSettings(telegram_id=telegram_id)
            self.session.add(settings)
            await self.session.flush()
        return settings

    async def set_traffic_percent(self, telegram_id: int, percent: int) -> None:
        settings = await self.get_settings(telegram_id)
        settings.traffic_percent = percent

    async def set_expire_days(self, telegram_id: int, days: int) -> None:
        settings = await self.get_settings(telegram_id)
        settings.expire_days = days

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #
    async def get_state(self, account_id: str, telegram_id: int) -> AlertState:
        result = await self.session.execute(
            select(AlertState).where(AlertState.account_id == account_id)
        )
        state = result.scalar_one_or_none()
        if state is None:
            state = AlertState(account_id=account_id, telegram_id=telegram_id)
            self.session.add(state)
            await self.session.flush()
        return state
