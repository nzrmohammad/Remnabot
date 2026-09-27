"""Application configuration loaded from .env via pydantic-settings."""
from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram ---
    BOT_TOKEN: str
    ADMIN_IDS: list[int] = []          # e.g. [111,222] or "111, 222"
    ADMIN_CHAT_ID: int                 # supergroup/channel that receives alerts

    # --- Admin Forum Topics (Optional, for Supergroups with topics enabled) ---
    ADMIN_TOPIC_TOPUPS: int | None = None   # Topic ID for receipts and top-ups
    ADMIN_TOPIC_ORDERS: int | None = None   # Topic ID for purchase logs
    ADMIN_TOPIC_SUPPORT: int | None = None  # Topic ID for support messages
    ADMIN_TOPIC_ALERTS: int | None = None   # Topic ID for system/reconcile alerts
    ADMIN_TOPIC_CRYPTO: int | None = None   # Topic ID for crypto rates and payments

    # --- Crypto (TON on-chain top-up) ---
    TON_WALLET_ADDRESS: str = ""
    TON_RATE_TOMAN: int = 0
    CRYPTO_ENABLED: bool = False
    USDT_RATE_TOMAN: int = 95000
    IRAN_PROXY: str = ""

    # --- Database ---
    DATABASE_URL: str                  # postgresql+asyncpg://user:pass@host:5432/dbname

    # --- Remnawave panel ---
    REMNAWAVE_BASE_URL: str            # e.g. https://panel.example.com
    REMNAWAVE_TOKEN: str               # API token created in the panel

    # --- Misc ---
    TIMEZONE: str = "Asia/Tehran"      # used for "today's usage" and report dates
    ALERT_CHECK_INTERVAL_MINUTES: int = 180   # how often the alert job runs

    # --- Wallet (card-to-card top-up) ---
    CARD_NUMBER: str = ""              # e.g. 6037-9917-1234-5678 (empty → top-up disabled)
    CARD_HOLDER: str = ""              # card owner's name shown to the user
    TOPUP_MIN_AMOUNT: int = 10000      # Toman

    # --- Expiry lifecycle ---
    EXPIRY_GRACE_DAYS: int = 3         # days after expire before auto-disable
    EXPIRY_CHECK_INTERVAL_MINUTES: int = 60
    EXPIRY_REMIND_DAYS: str = "3,1,0"  # comma-separated days-left to remind

    # --- FSM storage (production) ---
    # e.g. REDIS_URL=redis://localhost:6379/0 — empty keeps MemoryStorage.
    REDIS_URL: str = ""

    # --- Observability ---
    SENTRY_DSN: str = ""

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> list[int]:
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return [int(x) for x in json.loads(v)]
                except Exception:
                    v = v[1:-1]
            parts = [p.strip() for p in v.replace(" ", ",").split(",") if p.strip()]
            return [int(p) for p in parts if p.isdigit() or (p.startswith("-") and p[1:].isdigit())]
        return []

    @field_validator(
        "ADMIN_TOPIC_TOPUPS",
        "ADMIN_TOPIC_ORDERS",
        "ADMIN_TOPIC_SUPPORT",
        "ADMIN_TOPIC_ALERTS",
        "ADMIN_TOPIC_CRYPTO",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        return int(v)

    @field_validator("REMNAWAVE_BASE_URL")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("TIMEZONE")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(v)
        except Exception as err:
            raise ValueError(f"Invalid TIMEZONE: {v!r} (e.g. Asia/Tehran)") from err
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
