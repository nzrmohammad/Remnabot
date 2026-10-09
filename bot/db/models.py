"""Database models."""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language: Mapped[str | None] = mapped_column(String(4), nullable=True)

    # The single "menu message" that we always edit (clean-UI pattern).
    menu_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # True once the user's Telegram ID was found in the Remnawave panel.
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Updated on every interaction (used for the "online" admin filter).
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Banned users cannot interact with the bot.
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)

    # Free trial claimed once per Telegram ID.
    has_claimed_trial: Mapped[bool] = mapped_column(Boolean, default=False)

    # The telegram_id of the user who referred this user.
    referred_by_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )

    # Phone number (if verified/entered by user)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Birth date (YYYY/MM/DD or user-specified date string)
    birth_date: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AlertSettings(Base):
    """Per-user thresholds for the automatic usage/expiry alerts.

    A value of 0 disables that alert type.
    """

    __tablename__ = "alert_settings"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    traffic_percent: Mapped[int] = mapped_column(Integer, default=85)
    expire_days: Mapped[int] = mapped_column(Integer, default=3)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Service(Base):
    """A purchasable plan shown in the «Services» section.

    The admin manages these from the admin panel; they are not hardcoded.
    price is in Toman; duration_days and traffic_gb use 0 for "unlimited".
    """

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    price: Mapped[int] = mapped_column(BigInteger, default=0)        # Toman
    duration_days: Mapped[int] = mapped_column(Integer, default=0)   # 0 = unlimited
    traffic_gb: Mapped[int] = mapped_column(Integer, default=0)      # 0 = unlimited
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Traffic reset strategy sent to the panel (NO_RESET/DAY/WEEK/MONTH/...).
    traffic_strategy: Mapped[str] = mapped_column(String(16), default="NO_RESET")
    # Max HWID devices; None -> use the panel default.
    hwid_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Internal squad UUID; None -> use the store-wide default.
    squad_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Wallet(Base):
    """Per-user wallet balance in Toman."""

    __tablename__ = "wallets"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    balance: Mapped[int] = mapped_column(BigInteger, default=0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Topup(Base):
    """Card-to-card top-up request: user sends a receipt, admin approves."""

    __tablename__ = "topups"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    amount: Mapped[int] = mapped_column(BigInteger)          # Toman
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending/approved/rejected
    # Stable receipt fingerprint (photo/document file_unique_id or text hash)
    # used to reject the same receipt submitted twice.
    receipt_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # Telegram photo file_id for direct viewing by admins in TMA
    receipt_photo_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Message ID in admin chat/topic for syncing status updates
    admin_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class Order(Base):
    """A completed auto-activated purchase (service bought with wallet balance)."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    service_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )
    service_name: Mapped[str] = mapped_column(String(128))   # snapshot
    amount: Mapped[int] = mapped_column(BigInteger)          # Toman paid
    duration_days: Mapped[int] = mapped_column(Integer, default=0)
    traffic_gb: Mapped[int] = mapped_column(Integer, default=0)
    panel_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    panel_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subscription_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # paid = done, refunded = money returned, pending = panel call in-flight
    # (crash window), failed = panel error / deducted-race, never charged.
    status: Mapped[str] = mapped_column(String(10), default="paid")
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AdminLog(Base):
    """Audit trail of admin actions (balance changes, refunds, ...)."""

    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SupportMessage(Base):
    """Maps an admin-chat support message back to the user who sent it,
    so an admin reply can be routed to the right chat."""

    __tablename__ = "support_messages"

    admin_message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AppSetting(Base):
    """Runtime-editable store settings (override the .env defaults).

    Managed from the admin panel; the .env value is the fallback.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReportSettings(Base):
    """Per-user on/off switches for nightly/weekly/monthly reports,
    automatic cleanup of old reports, and lucky wheel reminders."""

    __tablename__ = "report_settings"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nightly: Mapped[bool] = mapped_column(Boolean, default=True)
    weekly: Mapped[bool] = mapped_column(Boolean, default=True)
    monthly: Mapped[bool] = mapped_column(Boolean, default=True)
    clean_reports: Mapped[bool] = mapped_column(Boolean, default=True)
    last_report_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    wheel_notify: Mapped[bool] = mapped_column(Boolean, default=True)
    wheel_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    wheel_last_spin_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AlertState(Base):
    """Remembers which alerts were already sent per panel account, so a
    threshold crossing fires exactly once (and re-arms after a renewal)."""

    __tablename__ = "alert_state"

    # The panel account identifier (numeric user id, stored as text).
    account_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    traffic_alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    expire_alerted: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExpiryState(Base):
    """Tracks expiry-lifecycle notices per panel account.

    `last_days_left` avoids re-sending the same reminder every hour;
    `disabled_notified` ensures the disabled notice fires once.
    """

    __tablename__ = "expiry_state"

    account_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    last_days_left: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disabled_notified: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnownDevice(Base):
    """Tracks known HWID devices per panel account to notify user on new device connection."""

    __tablename__ = "known_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    account_id: Mapped[str] = mapped_column(String(40), index=True)
    hwid: Mapped[str] = mapped_column(String(128), index=True)
    platform: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Coupon(Base):
    """Discount / promo code."""

    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    discount_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)  # 0 = unlimited
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CouponUsage(Base):
    """Tracks which user used which coupon to prevent duplicate uses."""

    __tablename__ = "coupon_usages"
    __table_args__ = (
        UniqueConstraint("coupon_id", "telegram_id", name="uq_coupon_usages_coupon_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    coupon_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("coupons.id", ondelete="CASCADE"), index=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_applied: Mapped[int] = mapped_column(BigInteger, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReferralReward(Base):
    """Tracks referral invitations and granted rewards."""

    __tablename__ = "referral_rewards"
    __table_args__ = (
        UniqueConstraint("referee_id", name="uq_referral_rewards_referee"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inviter_id: Mapped[int] = mapped_column(BigInteger, index=True)
    referee_id: Mapped[int] = mapped_column(BigInteger, index=True)
    reward_gb: Mapped[int] = mapped_column(Integer, default=5)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RetentionState(Base):
    """Tracks automated 7-day retention notices sent to users."""

    __tablename__ = "retention_state"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    notified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CryptoInvoice(Base):
    """Invoice for on-chain cryptocurrency (TON) wallet top-up."""

    __tablename__ = "crypto_invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    amount_toman: Mapped[int] = mapped_column(BigInteger)
    amount_ton: Mapped[str] = mapped_column(String(32))
    nanotons: Mapped[int] = mapped_column(BigInteger)
    comment: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    pay_address: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / paid / expired / cancelled
    tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NodeCost(Base):
    """Infrastructure cost and billing details for Remnawave nodes / servers."""

    __tablename__ = "node_costs"

    id: Mapped[int] = mapped_column(primary_key=True)
    node_uuid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    node_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    node_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Hetzner, OVH, etc.
    monthly_cost_toman: Mapped[int] = mapped_column(BigInteger, default=0)
    monthly_cost_eur: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str | None] = mapped_column(String(8), default="EUR", nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_notified: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HourlyTrafficSnapshot(Base):
    """Hourly traffic consumption metrics across the entire Remnawave cluster."""

    __tablename__ = "hourly_traffic_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    delta_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )



