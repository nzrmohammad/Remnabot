"""Automatic purchase flow: create/renew a panel user from wallet balance.

Decision logic (per the admin's choice):
- If the Telegram ID owns exactly ONE panel account  -> renew that account.
- If it owns MORE than one                          -> ask which one to renew.
- If it owns none (edge case)                       -> create a new account.

Crash safety: a `pending` order row is written BEFORE the panel call.
- Panel error            -> order marked `failed`, nothing charged.
- Panel ok + deduct ok   -> order marked `paid`.
- Crash in between       -> the reconcile job (`services/reconcile.py`)
  marks the stale `pending` order `failed` and notifies the admin, so a
  free service can never go unnoticed. Money is only ever deducted with
  an atomic `UPDATE ... WHERE balance >= price`.
Renewals always send `status="ACTIVE"` so accounts the expiry job
auto-disabled are reactivated on payment.
"""
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from bot.db.repositories.order_repo import OrderRepository
from bot.services.app_settings import get_store_settings
from bot.services.remnawave import RemnawaveClient

logger = logging.getLogger(__name__)

GB = 1024 ** 3

TRAFFIC_STRATEGIES = ("NO_RESET", "DAY", "WEEK", "MONTH", "MONTH_ROLLING")


@dataclass
class PurchaseResult:
    ok: bool
    kind: str  # "success" | "insufficient" | "failed" | "needs_account" | "maintenance"
    subscription_url: str | None = None
    new_balance: int = 0
    panel_user_id: int | None = None
    panel_username: str | None = None
    accounts: list[dict] | None = None  # set when kind == "needs_account"
    order_id: int | None = None


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _expire_from(days: int, base: datetime) -> datetime:
    if days <= 0:
        return datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    # Cap stacking: repeated renewals can't push past 3 years from now.
    computed = base + timedelta(days=days)
    cap = datetime.now(timezone.utc) + timedelta(days=1095)
    return min(computed, cap)


def _traffic_bytes(
    traffic_gb: int, current_limit: int = 0, strategy: str = "NO_RESET"
) -> int:
    """0 in the service means "unlimited" -> 0 bytes (unlimited) in the panel.

    NO_RESET accumulates (adds to the current limit); all periodic
    strategies (DAY/WEEK/MONTH/...) replace the limit with the new plan,
    otherwise the quota grows forever.
    """
    if traffic_gb <= 0:
        return 0
    if strategy == "NO_RESET":
        if current_limit <= 0:
            return traffic_gb * GB
        return current_limit + traffic_gb * GB
    return traffic_gb * GB


def _parse_expire(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _pick_username(remnawave: RemnawaveClient, telegram_id: int) -> str:
    """Generate a unique username for a new panel user (3-36 [a-zA-Z0-9_-])."""
    for _ in range(3):
        suffix = secrets.token_hex(2)  # 4 hex chars
        candidate = f"u{telegram_id}_{suffix}"
        existing = await remnawave.get_users_by_telegram_id(telegram_id) or []
        if not any(
            str(u.get("username", "")).lower() == candidate.lower()
            for u in existing
        ):
            return candidate
    return f"u{telegram_id}_{secrets.token_hex(2)}"


async def execute_purchase(
    remnawave: RemnawaveClient,
    session,
    service,
    telegram_id: int,
    chosen_account: dict | None = None,
    create_new: bool = False,
    discount_amount: int = 0,
) -> PurchaseResult:
    """Buy a service. `chosen_account` = panel account to renew, if pre-picked.
    If `create_new` is True, a new panel account is always created regardless of existing accounts.
    """
    from bot.services.app_settings import is_maintenance

    if await is_maintenance(session):
        return PurchaseResult(ok=False, kind="maintenance")

    effective_price = max(0, service.price - discount_amount)

    # Atomic guard: only pass when the balance covers the price. The actual
    # deduction happens after the panel call succeeds.
    row = await session.execute(
        text("SELECT balance FROM wallets WHERE telegram_id = :t"),
        {"t": telegram_id},
    )
    current_balance = int(row.scalar_one_or_none() or 0)
    if current_balance < effective_price:
        return PurchaseResult(ok=False, kind="insufficient", new_balance=current_balance)

    # Resolve which panel account to use.
    account: dict | None = chosen_account
    if not create_new and account is None:
        accounts = await remnawave.get_users_by_telegram_id(telegram_id)
        if accounts is None:
            return PurchaseResult(ok=False, kind="failed")
        if len(accounts) == 1:
            account = accounts[0]
        elif len(accounts) > 1:
            return PurchaseResult(
                ok=False, kind="needs_account", accounts=accounts
            )
        # len == 0 -> create a new account

    now = datetime.now(timezone.utc)
    strategy = service.traffic_strategy or "NO_RESET"
    order_repo = OrderRepository(session)

    # 1) Reserve a pending order BEFORE touching the panel. If the process
    #    dies mid-purchase, the reconcile job will find this row.
    pending = await order_repo.create(
        telegram_id=telegram_id,
        service_id=service.id,
        service_name=service.name,
        amount=effective_price,
        duration_days=service.duration_days,
        traffic_gb=service.traffic_gb,
        panel_user_id=int(account["id"]) if account is not None else None,
        panel_username=account.get("username") if account else None,
        subscription_url=None,
        status="pending",
    )

    if account is None:
        # Create a brand-new panel user (retry on global username collision).
        store = await get_store_settings(session)
        squad_uuid = service.squad_uuid or store.default_squad_uuid or None
        user = None
        for _ in range(4):
            username = await _pick_username(remnawave, telegram_id)
            user = await remnawave.create_user(
                username=username,
                expire_at_iso=_iso(_expire_from(service.duration_days, now)),
                traffic_limit_bytes=_traffic_bytes(service.traffic_gb, 0, strategy),
                telegram_id=telegram_id,
                traffic_limit_strategy=strategy,
                hwid_device_limit=service.hwid_limit,
                internal_squads=[squad_uuid] if squad_uuid else None,
            )
            if user is not None:
                break
        if user is None:
            await order_repo.mark_failed(pending)
            return PurchaseResult(ok=False, kind="failed")
        panel_user_id = user.get("id")
        panel_username = user.get("username")
        subscription_url = user.get("subscriptionUrl")
    else:
        # Renew the existing account (+ reactivate if expiry job disabled it).
        if strategy == "NO_RESET":
            base = now
            current_expire = _parse_expire(account.get("expireAt"))
            if current_expire is not None and current_expire > now:
                base = current_expire
            expire_iso = _iso(_expire_from(service.duration_days, base))
            traffic = _traffic_bytes(
                service.traffic_gb, int(account.get("trafficLimitBytes") or 0), strategy
            )
        else:
            # Periodic strategies (DAY, WEEK, MONTH): reset days from today & reset traffic to 0
            base = now
            expire_iso = _iso(_expire_from(service.duration_days, base))
            traffic = _traffic_bytes(service.traffic_gb, 0, strategy)
            try:
                await remnawave.reset_user_traffic(int(account["id"]))
            except Exception:
                logger.exception("Failed to reset traffic on renewal for panel user %s", account["id"])

        user = await remnawave.update_user_subscription(
            int(account["id"]),
            expire_iso,
            traffic,
            traffic_limit_strategy=service.traffic_strategy or None,
            status="ACTIVE",
        )
        if user is None:
            await order_repo.mark_failed(pending)
            return PurchaseResult(ok=False, kind="failed")
        panel_user_id = int(account["id"])
        panel_username = user.get("username") or account.get("username")
        subscription_url = user.get("subscriptionUrl") or account.get(
            "subscriptionUrl"
        )

    # 2) Panel succeeded -> deduct atomically.
    result = await session.execute(
        text(
            "UPDATE wallets SET balance = balance - :p "
            "WHERE telegram_id = :t AND balance >= :p "
            "RETURNING balance"
        ),
        {"p": effective_price, "t": telegram_id},
    )
    new_balance = result.scalar_one_or_none()
    if new_balance is None:
        # Balance dropped mid-purchase (double-tap race). The panel was
        # already extended -> keep the order visible for manual review
        # instead of silently giving a free service.
        logger.error(
            "race: balance went below price during purchase (user=%s)", telegram_id
        )
        await order_repo.mark_failed(pending)
        return PurchaseResult(ok=False, kind="failed")
    await session.flush()

    # 3) Finalize the pending order as paid.
    await order_repo.mark_paid(pending, panel_user_id, panel_username, subscription_url)

    return PurchaseResult(
        ok=True,
        kind="success",
        subscription_url=subscription_url,
        new_balance=int(new_balance),
        panel_user_id=panel_user_id,
        panel_username=panel_username,
        order_id=pending.id,
    )
