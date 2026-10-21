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
from typing import Any

from sqlalchemy import select, text

from bot.db.models import Wallet
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
    bot: Any = None,
    session_factory: Any = None,
) -> PurchaseResult:
    """Buy a service. `chosen_account` = panel account to renew, if pre-picked.
    If `create_new` is True, a new panel account is always created regardless of existing accounts.
    """
    from bot.services.app_settings import is_maintenance

    if await is_maintenance(session):
        return PurchaseResult(ok=False, kind="maintenance")

    discount_amount = max(0, min(int(discount_amount or 0), int(service.price)))
    effective_price = max(0, service.price - discount_amount)

    async def _report_purchase_err(reason: str, detail: str = "") -> None:
        logger.error("Purchase error for user %s, service %s (%s): %s", telegram_id, service.id, reason, detail)
        if bot:
            try:
                from bot.services.error_reporter import report_error
                ctx = f"Purchase u={telegram_id} svc={service.id} price={effective_price}"
                if detail:
                    ctx += f" [{detail}]"
                await report_error(
                    bot,
                    session_factory=session_factory,
                    session=session,
                    exc=f"purchase_failed:{reason}",
                    context=ctx,
                    user_id=telegram_id,
                )
            except Exception as rep_exc:
                logger.warning("Failed to report purchase error to topic: %s", rep_exc)

    # Atomic guard: lock wallet row with FOR UPDATE so concurrent requests
    # for the same user cannot race to purchase simultaneously with stale balance.
    wallet_res = await session.execute(
        select(Wallet.balance).where(Wallet.telegram_id == telegram_id).with_for_update()
    )
    val = wallet_res.scalar_one_or_none()
    current_balance = int(getattr(val, "balance", val) or 0)
    if current_balance < effective_price:
        return PurchaseResult(ok=False, kind="insufficient", new_balance=current_balance)

    # Resolve which panel account to use.
    account: dict | None = chosen_account
    if not create_new and account is None:
        accounts = await remnawave.get_users_by_telegram_id(telegram_id)
        if accounts is None:
            await _report_purchase_err("panel_unreachable", "get_users_by_telegram_id returned None")
            return PurchaseResult(ok=False, kind="failed")
        if len(accounts) == 1:
            account = accounts[0]
        elif len(accounts) > 1:
            return PurchaseResult(
                ok=False, kind="needs_account", accounts=accounts
            )
        # len == 0 -> create a new account

    is_extra_traffic = (service.duration_days == 0 and service.traffic_gb > 0) or (getattr(service, "badge", None) == "traffic")
    is_extra_time = (service.traffic_gb == 0 and service.duration_days > 0) or (getattr(service, "badge", None) == "time")

    if account is None and (is_extra_traffic or is_extra_time):
        return PurchaseResult(ok=False, kind="needs_active_sub")

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
            await _report_purchase_err("create_user_failed_4x", "Panel create_user failed 4 times")
            return PurchaseResult(ok=False, kind="failed")
        panel_user_id = user.get("id")
        panel_username = user.get("username")
        subscription_url = user.get("subscriptionUrl")
    else:
        # Renew the existing account (+ reactivate if expiry job disabled it).
        current_expire_str = account.get("expireAt")
        current_expire = _parse_expire(current_expire_str)

        if is_extra_traffic and current_expire is not None and current_expire > now:
            # Extra Traffic Package (+GB): preserve expiration date, stack traffic limit
            expire_iso = current_expire_str
            traffic = _traffic_bytes(
                service.traffic_gb, int(account.get("trafficLimitBytes") or 0), "NO_RESET"
            )
        elif is_extra_time:
            # Extra Time Package (+Days): preserve existing traffic limit, extend expiration
            base = current_expire if (current_expire is not None and current_expire > now) else now
            expire_iso = _iso(_expire_from(service.duration_days, base))
            traffic = int(account.get("trafficLimitBytes") or 0)
        elif strategy == "NO_RESET":
            base = now
            if current_expire is not None and current_expire > now:
                # Still active -> extend from existing expiration date, stack traffic
                base = current_expire
                expire_iso = _iso(_expire_from(service.duration_days, base))
                traffic = _traffic_bytes(
                    service.traffic_gb, int(account.get("trafficLimitBytes") or 0), strategy
                )
            else:
                # Already expired -> start fresh from today, reset used traffic
                expire_iso = _iso(_expire_from(service.duration_days, base))
                traffic = _traffic_bytes(service.traffic_gb, 0, strategy)
                try:
                    await remnawave.reset_user_traffic(int(account["id"]))
                except Exception as exc:
                    logger.exception("Failed to reset traffic on renewal for expired user %s: %s", account["id"], exc)
        else:
            # Periodic strategies (DAY, WEEK, MONTH): reset days from today & reset traffic to 0
            base = now
            expire_iso = _iso(_expire_from(service.duration_days, base))
            traffic = _traffic_bytes(service.traffic_gb, 0, strategy)
            try:
                await remnawave.reset_user_traffic(int(account["id"]))
            except Exception as exc:
                logger.exception("Failed to reset traffic on renewal for panel user %s: %s", account["id"], exc)

        user = await remnawave.update_user_subscription(
            int(account["id"]),
            expire_iso,
            traffic,
            traffic_limit_strategy=service.traffic_strategy or None,
            status="ACTIVE",
        )
        if user is None:
            await order_repo.mark_failed(pending)
            await _report_purchase_err("renew_failed", f"Panel update_user_subscription failed for acc={account.get('id')}")
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
        await order_repo.mark_failed(pending)
        await _report_purchase_err("balance_race", "race: balance went below price during purchase")
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


def calc_price(price: int, discount_amount: int = 0) -> tuple[int, int]:
    """Return (effective_price, sanitized_discount) ensuring non-negative values."""
    discount = max(0, int(discount_amount or 0))
    effective = max(0, int(price or 0) - discount)
    return effective, discount


def receipt_price_lines(
    lang: str,
    original_price: int,
    effective_price: int,
    discount_amount: int = 0,
    coupon_code: str | None = None,
    currency_label: str = "تومان",
    is_confirm_card: bool = False,
) -> list[str]:
    """Generate standardized, RTL-safe price, discount, and total receipt lines."""
    from html import escape

    from bot.common import fmt
    from bot.locales.texts import t

    lines: list[str] = []
    if coupon_code and discount_amount > 0:
        if is_confirm_card:
            lines.append(f"💰 {t(lang, 'svc_field_price')} : <b>{fmt(original_price)}</b> {currency_label}")
            lines.append(f"🏷 {t(lang, 'retention_code_label')} (<code>{escape(coupon_code)}</code>) : <b>\u200e-{fmt(discount_amount)}</b> {currency_label}")
            lines.append(f"💵 {t(lang, 'receipt_amount')} : <b>{fmt(effective_price)}</b> {currency_label}")
        else:
            lines.append(f"💰 {t(lang, 'svc_field_price')} : <b>{fmt(original_price)} {currency_label}</b>")
            lines.append(f"🏷 {t(lang, 'retention_code_label')} (<code>{escape(coupon_code)}</code>) : <b>\u200e-{fmt(discount_amount)} {currency_label}</b>")
            lines.append(f"💵 {t(lang, 'receipt_amount')} : <b>{fmt(effective_price)} {currency_label}</b>")
    else:
        label = t(lang, "svc_field_price" if is_confirm_card else "receipt_amount")
        if is_confirm_card:
            lines.append(f"💰 {label} : <b>{fmt(original_price)}</b> {currency_label}")
        else:
            lines.append(f"💰 {label} : <b>{fmt(original_price)} {currency_label}</b>")
    return lines


async def record_coupon_usage_if_any(
    session,
    coupon_code: str | None,
    telegram_id: int,
    order_id: int | None,
    discount_amount: int = 0,
) -> None:
    """Record coupon usage in database if a valid coupon and order exist."""
    if coupon_code and order_id:
        from bot.db.repositories.coupon_repo import CouponRepository
        c_repo = CouponRepository(session)
        cpn = await c_repo.get_by_code(coupon_code)
        if cpn:
            await c_repo.record_usage(cpn.id, telegram_id, order_id, discount_amount)


async def maybe_reward_referrer(
    bot: Any, session: Any, remnawave: RemnawaveClient, user: Any,
) -> None:
    """Reward user's inviter with extra traffic and spin tickets upon first purchase/trial."""
    if not getattr(user, "referred_by_id", None):
        return
    store = await get_store_settings(session)
    if not store.referral_enabled or store.referral_reward_gb <= 0:
        return
    from bot.db.repositories.referral_repo import ReferralRepository
    referral_repo = ReferralRepository(session)
    if await referral_repo.has_rewarded(user.telegram_id):
        return

    reward_gb = store.referral_reward_gb
    reward = await referral_repo.record_reward(user.referred_by_id, user.telegram_id, reward_gb)

    inviter_accs = await remnawave.get_users_by_telegram_id(user.referred_by_id)
    if inviter_accs:
        inv_acc = inviter_accs[0]
        cur_limit = int(inv_acc.get("trafficLimitBytes") or 0)
        if cur_limit > 0:
            new_limit = cur_limit + reward_gb * (1024 ** 3)
            try:
                await remnawave.update_user_subscription(
                    int(inv_acc["id"]), inv_acc.get("expireAt"), new_limit
                )
            except Exception:
                logger.exception("Failed to add referral traffic to panel user %s", inv_acc.get("id"))
                reward.applied = False

    from bot.db.repositories.user_repo import UserRepository
    inviter_user = await UserRepository(session).get_by_telegram_id(user.referred_by_id)
    if inviter_user:
        inviter_user.spin_tickets = (getattr(inviter_user, "spin_tickets", 0) or 0) + 1
    inv_lang = (inviter_user.language if inviter_user else None) or "fa"
    try:
        from bot.locales.texts import t
        ticket_note = (
            "\n\n🎫 <b>+۱ شانس چرخش گردونه (تیکت اسپین)</b> نیز به حساب شما اضافه شد!"
            if inv_lang == "fa"
            else "\n\n🎫 <b>+1 Lucky Wheel spin ticket</b> has also been credited to your account!"
        )
        await bot.send_message(
            user.referred_by_id,
            t(inv_lang, "referral_reward_notify", reward_gb=reward_gb) + ticket_note,
        )
    except Exception:
        logger.exception("Failed to notify inviter %s of referral reward", user.referred_by_id)


async def notify_admin(
    bot: Any,
    user: Any,
    service: Any,
    result: Any,
    session: Any = None,
    coupon_code: str | None = None,
    discount_amount: int = 0,
    full_name: str | None = None,
) -> None:
    """Notify admin chat/topic about a successful service purchase or renewal."""
    from html import escape

    from bot.common import admin_thread_kwargs, fmt
    from bot.config import get_settings
    from bot.locales.texts import t

    tg_username = f"\u200e@{escape(user.username)}\u200e" if getattr(user, "username", None) else "—"
    effective_price, discount_amount = calc_price(service.price, discount_amount)
    display_name = escape(full_name or getattr(user, "username", None) or str(getattr(user, "telegram_id", "")))

    price_lines = []
    if coupon_code and discount_amount > 0:
        price_lines.append(f"💰 {t('fa', 'svc_field_price')} : <b>{fmt(service.price)}</b> {t('fa', 'svc_currency')}")
        price_lines.append(f"🏷 {t('fa', 'retention_code_label')} (<code>{escape(coupon_code)}</code>) : <b>\u200e-{fmt(discount_amount)}</b> {t('fa', 'svc_currency')}")
        price_lines.append(f"💵 پرداختی از کیف پول : <b>{fmt(effective_price)}</b> {t('fa', 'svc_currency')}")
    else:
        price_lines.append(f"💰 مبلغ کل : <b>{fmt(service.price)}</b> {t('fa', 'svc_currency')}")
        price_lines.append(f"💵 پرداختی از کیف پول : <b>{fmt(service.price)}</b> {t('fa', 'svc_currency')}")

    prices_str = "\n".join(price_lines)

    text = (
        f"🛒 <b>{t('fa', 'buy_admin_log')}</b>\n\n"
        f"📦 <b>\u200e{escape(service.name)}\u200e</b>\n"
        f"{prices_str}\n\n"
        f"👤 {display_name} — <code>{getattr(user, 'telegram_id', '')}</code>\n"
        f"🔗 {t('fa', 'svc_requested_username')} : {tg_username}\n"
        f"🔑 <code>{escape(str(getattr(result, 'panel_username', '') or ''))}</code>\n\n"
        f"{t('fa', 'buy_remaining_balance', balance=fmt(getattr(result, 'new_balance', 0)), currency=t('fa', 'svc_currency'))}"
    )
    settings = get_settings()
    topic_id = settings.ADMIN_TOPIC_ORDERS
    if session is not None:
        store = await get_store_settings(session)
        if getattr(store, "topic_orders", None) is not None:
            topic_id = store.topic_orders
    thread_kwargs = admin_thread_kwargs(topic_id=topic_id)
    try:
        await bot.send_message(settings.ADMIN_CHAT_ID, text, **thread_kwargs)
    except Exception:
        logger.exception("failed to deliver purchase log to admin chat")


_maybe_reward_referrer = maybe_reward_referrer
_notify_admin = notify_admin

