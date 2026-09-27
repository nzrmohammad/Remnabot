"""Store settings: runtime DB overrides with .env as the fallback."""
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.db.repositories.app_setting_repo import AppSettingRepository


@dataclass
class StoreSettings:
    card_number: str
    card_holder: str
    topup_min_amount: int
    default_squad_uuid: str
    expiry_grace_days: int
    expiry_remind_days: str
    topic_topups: int | None
    topic_orders: int | None
    topic_support: int | None
    topic_alerts: int | None
    support_contact: str
    trial_enabled: bool = True
    trial_traffic_gb: int = 1
    trial_duration_days: int = 1
    referral_enabled: bool = True
    referral_reward_gb: int = 5
    support_direct_enabled: bool = True
    topic_crypto: int | None = None
    ton_wallet_address: str = ""
    ton_rate_toman: int = 0
    crypto_enabled: bool = False


async def get_store_settings(session: AsyncSession) -> StoreSettings:
    repo = AppSettingRepository(session)
    values = await repo.all()
    env = get_settings()

    def _int(val: Any, default: int) -> int:
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def _opt_int(val: Any, default: int | None) -> int | None:
        if val is None or str(val).strip() == "":
            return default
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def _bool(val: Any, default: bool) -> bool:
        if val is None or str(val).strip() == "":
            return default
        return str(val).strip().lower() in ("1", "true", "yes", "on")

    return StoreSettings(
        card_number=values.get("card_number", env.CARD_NUMBER),
        card_holder=values.get("card_holder", env.CARD_HOLDER),
        topup_min_amount=_int(values.get("topup_min_amount"), env.TOPUP_MIN_AMOUNT),
        default_squad_uuid=values.get("default_squad_uuid", ""),
        expiry_grace_days=_int(values.get("expiry_grace_days"), env.EXPIRY_GRACE_DAYS),
        expiry_remind_days=values.get("expiry_remind_days", env.EXPIRY_REMIND_DAYS),
        topic_topups=_opt_int(values.get("topic_topups"), env.ADMIN_TOPIC_TOPUPS),
        topic_orders=_opt_int(values.get("topic_orders"), env.ADMIN_TOPIC_ORDERS),
        topic_support=_opt_int(values.get("topic_support"), env.ADMIN_TOPIC_SUPPORT),
        topic_alerts=_opt_int(values.get("topic_alerts"), env.ADMIN_TOPIC_ALERTS),
        support_contact=values.get("support_contact", ""),
        trial_enabled=_bool(values.get("trial_enabled"), True),
        trial_traffic_gb=_int(values.get("trial_traffic_gb"), 1),
        trial_duration_days=_int(values.get("trial_duration_days"), 1),
        referral_enabled=_bool(values.get("referral_enabled"), True),
        referral_reward_gb=_int(values.get("referral_reward_gb"), 5),
        support_direct_enabled=_bool(values.get("support_direct_enabled"), True),
        topic_crypto=_opt_int(values.get("topic_crypto"), env.ADMIN_TOPIC_CRYPTO),
        ton_wallet_address=values.get("ton_wallet_address", env.TON_WALLET_ADDRESS),
        ton_rate_toman=_int(values.get("ton_rate_toman"), env.TON_RATE_TOMAN),
        crypto_enabled=_bool(values.get("crypto_enabled"), env.CRYPTO_ENABLED),
    )


async def is_maintenance(session: AsyncSession) -> bool:
    """True when the admin turned on maintenance mode from the panel."""
    value = await AppSettingRepository(session).get("maintenance")
    return value == "1"


async def set_maintenance(session: AsyncSession, enabled: bool) -> None:
    await AppSettingRepository(session).set("maintenance", "1" if enabled else "0")
