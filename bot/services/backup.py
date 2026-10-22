"""Database backup export service."""
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.common import admin_thread_kwargs
from bot.services.formatting import now_tz
from bot.db.models import (
    AdminLog,
    AlertSettings,
    AlertState,
    AppSetting,
    Campaign,
    Coupon,
    CouponUsage,
    CryptoInvoice,
    ExpiryState,
    HourlyTrafficSnapshot,
    KnownDevice,
    NodeCost,
    Order,
    ReferralReward,
    ReportSettings,
    RetentionState,
    Service,
    SupportMessage,
    Topup,
    TopupStatus,
    User,
    Wallet,
)

logger = logging.getLogger(__name__)


def _serialize_val(val):
    if isinstance(val, datetime):
        return val.isoformat()
    return val


async def create_database_backup(session: AsyncSession, out_dir: str | Path | None = None) -> Path:
    """Export all primary database tables to a JSON backup file."""
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    # 1. Users
    users_res = await session.execute(select(User))
    users = [
        {
            "id": u.id,
            "telegram_id": u.telegram_id,
            "username": u.username,
            "language": u.language,
            "is_verified": u.is_verified,
            "is_banned": u.is_banned,
            "has_claimed_trial": u.has_claimed_trial,
            "referred_by_id": u.referred_by_id,
            "last_active_at": _serialize_val(u.last_active_at),
            "created_at": _serialize_val(u.created_at),
        }
        for u in users_res.scalars().all()
    ]

    # 2. Wallets
    wallets_res = await session.execute(select(Wallet))
    wallets = [
        {"telegram_id": w.telegram_id, "balance": w.balance}
        for w in wallets_res.scalars().all()
    ]

    # 3. Orders
    orders_res = await session.execute(select(Order))
    orders = [
        {
            "id": o.id,
            "telegram_id": o.telegram_id,
            "service_id": o.service_id,
            "service_name": o.service_name,
            "amount": o.amount,
            "duration_days": o.duration_days,
            "traffic_gb": o.traffic_gb,
            "panel_user_id": o.panel_user_id,
            "panel_username": o.panel_username,
            "subscription_url": o.subscription_url,
            "status": o.status,
            "created_at": _serialize_val(o.created_at),
        }
        for o in orders_res.scalars().all()
    ]

    # 4. Services
    services_res = await session.execute(select(Service))
    services = [
        {
            "id": s.id,
            "name": s.name,
            "price": s.price,
            "duration_days": s.duration_days,
            "traffic_gb": s.traffic_gb,
            "is_active": s.is_active,
            "traffic_strategy": s.traffic_strategy,
            "hwid_limit": s.hwid_limit,
            "squad_uuid": s.squad_uuid,
        }
        for s in services_res.scalars().all()
    ]

    # 5. Coupons
    coupons_res = await session.execute(select(Coupon))
    coupons = [
        {
            "id": c.id,
            "code": c.code,
            "discount_percent": c.discount_percent,
            "discount_amount": c.discount_amount,
            "max_uses": c.max_uses,
            "used_count": c.used_count,
            "expires_at": _serialize_val(c.expires_at),
            "is_active": c.is_active,
        }
        for c in coupons_res.scalars().all()
    ]

    # 6. App Settings
    settings_res = await session.execute(select(AppSetting))
    settings = {s.key: s.value for s in settings_res.scalars().all()}

    # 7. Topups
    topups_res = await session.execute(select(Topup))
    topups = [
        {
            "id": tp.id,
            "telegram_id": tp.telegram_id,
            "amount": tp.amount,
            "status": tp.status.value if hasattr(tp.status, "value") else str(tp.status),
            "receipt_hash": tp.receipt_hash,
            "receipt_photo_id": tp.receipt_photo_id,
            "created_at": _serialize_val(tp.created_at),
            "decided_at": _serialize_val(tp.decided_at),
            "admin_message_id": tp.admin_message_id,
        }
        for tp in topups_res.scalars().all()
    ]

    # 8. Crypto Invoices
    crypto_res = await session.execute(select(CryptoInvoice))
    crypto_invoices = [
        {
            "id": ci.id,
            "telegram_id": ci.telegram_id,
            "amount_toman": ci.amount_toman,
            "amount_ton": ci.amount_ton,
            "nanotons": ci.nanotons,
            "comment": ci.comment,
            "pay_address": ci.pay_address,
            "status": ci.status,
            "tx_hash": ci.tx_hash,
            "expires_at": _serialize_val(ci.expires_at),
            "created_at": _serialize_val(ci.created_at),
            "paid_at": _serialize_val(ci.paid_at),
        }
        for ci in crypto_res.scalars().all()
    ]

    # 9. Coupon Usages
    coupon_usages_res = await session.execute(select(CouponUsage))
    coupon_usages = [
        {
            "id": cu.id,
            "coupon_id": cu.coupon_id,
            "telegram_id": cu.telegram_id,
            "order_id": cu.order_id,
            "discount_applied": cu.discount_applied,
            "created_at": _serialize_val(cu.created_at),
        }
        for cu in coupon_usages_res.scalars().all()
    ]

    # 10. Referral Rewards
    referral_res = await session.execute(select(ReferralReward))
    referral_rewards = [
        {
            "id": rr.id,
            "inviter_id": rr.inviter_id,
            "referee_id": rr.referee_id,
            "reward_gb": rr.reward_gb,
            "applied": rr.applied,
            "created_at": _serialize_val(rr.created_at),
        }
        for rr in referral_res.scalars().all()
    ]

    # 11. Support Messages
    support_res = await session.execute(select(SupportMessage))
    support_messages = [
        {
            "admin_message_id": sm.admin_message_id,
            "telegram_id": sm.telegram_id,
            "created_at": _serialize_val(sm.created_at),
        }
        for sm in support_res.scalars().all()
    ]

    # 12. AlertSettings
    alert_settings_res = await session.execute(select(AlertSettings))
    alert_settings = [
        {
            "telegram_id": a.telegram_id,
            "traffic_percent": a.traffic_percent,
            "expire_days": a.expire_days,
            "updated_at": _serialize_val(a.updated_at),
        }
        for a in alert_settings_res.scalars().all()
    ]

    # 13. ReportSettings
    report_settings_res = await session.execute(select(ReportSettings))
    report_settings = [
        {
            "telegram_id": r.telegram_id,
            "nightly": r.nightly,
            "weekly": r.weekly,
            "monthly": r.monthly,
            "clean_reports": r.clean_reports,
            "last_report_message_id": r.last_report_message_id,
            "last_nightly_message_id": r.last_nightly_message_id,
            "last_weekly_message_id": r.last_weekly_message_id,
            "last_monthly_message_id": r.last_monthly_message_id,
            "wheel_notify": r.wheel_notify,
            "wheel_notified": r.wheel_notified,
            "wheel_last_spin_at": _serialize_val(r.wheel_last_spin_at),
            "last_wheel_message_id": r.last_wheel_message_id,
            "updated_at": _serialize_val(r.updated_at),
        }
        for r in report_settings_res.scalars().all()
    ]

    # 14. AdminLog
    admin_logs_res = await session.execute(select(AdminLog))
    admin_logs = [
        {
            "id": al.id,
            "admin_id": al.admin_id,
            "action": al.action,
            "detail": al.detail,
            "target_user_id": al.target_user_id,
            "created_at": _serialize_val(al.created_at),
        }
        for al in admin_logs_res.scalars().all()
    ]

    # 15. AlertState
    alert_state_res = await session.execute(select(AlertState))
    alert_states = [
        {
            "account_id": ast.account_id,
            "telegram_id": ast.telegram_id,
            "traffic_alerted": ast.traffic_alerted,
            "expire_alerted": ast.expire_alerted,
            "updated_at": _serialize_val(ast.updated_at),
        }
        for ast in alert_state_res.scalars().all()
    ]

    # 16. ExpiryState
    expiry_state_res = await session.execute(select(ExpiryState))
    expiry_states = [
        {
            "account_id": es.account_id,
            "telegram_id": es.telegram_id,
            "last_days_left": es.last_days_left,
            "disabled_notified": es.disabled_notified,
            "updated_at": _serialize_val(es.updated_at),
        }
        for es in expiry_state_res.scalars().all()
    ]

    # 17. KnownDevice
    known_devices_res = await session.execute(select(KnownDevice))
    known_devices = [
        {
            "id": kd.id,
            "telegram_id": kd.telegram_id,
            "account_id": kd.account_id,
            "hwid": kd.hwid,
            "platform": kd.platform,
            "device_model": kd.device_model,
            "created_at": _serialize_val(kd.created_at),
        }
        for kd in known_devices_res.scalars().all()
    ]

    # 18. RetentionState
    retention_res = await session.execute(select(RetentionState))
    retention_states = [
        {
            "telegram_id": ret.telegram_id,
            "notified_at": _serialize_val(ret.notified_at),
        }
        for ret in retention_res.scalars().all()
    ]

    # 19. NodeCost
    node_costs_res = await session.execute(select(NodeCost))
    node_costs = [
        {
            "id": nc.id,
            "node_uuid": nc.node_uuid,
            "node_id": nc.node_id,
            "node_name": nc.node_name,
            "provider": nc.provider,
            "monthly_cost_toman": nc.monthly_cost_toman,
            "monthly_cost_eur": nc.monthly_cost_eur,
            "currency": nc.currency,
            "due_date": nc.due_date,
            "notes": nc.notes,
            "alert_notified": nc.alert_notified,
            "created_at": _serialize_val(nc.created_at),
            "updated_at": _serialize_val(nc.updated_at),
        }
        for nc in node_costs_res.scalars().all()
    ]

    # 20. HourlyTrafficSnapshot
    traffic_snapshots_res = await session.execute(select(HourlyTrafficSnapshot))
    traffic_snapshots = [
        {
            "id": hts.id,
            "timestamp": _serialize_val(hts.timestamp),
            "total_bytes": hts.total_bytes,
            "delta_bytes": hts.delta_bytes,
            "created_at": _serialize_val(hts.created_at),
        }
        for hts in traffic_snapshots_res.scalars().all()
    ]

    # 21. Campaign
    campaigns_res = await session.execute(select(Campaign))
    campaigns = [
        {
            "id": cmp.id,
            "code": cmp.code,
            "name": cmp.name,
            "cost": cmp.cost,
            "created_at": _serialize_val(cmp.created_at),
        }
        for cmp in campaigns_res.scalars().all()
    ]

    data = {
        "export_date": now.isoformat(),
        "users": users,
        "wallets": wallets,
        "orders": orders,
        "services": services,
        "coupons": coupons,
        "settings": settings,
        "topups": topups,
        "crypto_invoices": crypto_invoices,
        "coupon_usages": coupon_usages,
        "referral_rewards": referral_rewards,
        "support_messages": support_messages,
        "alert_settings": alert_settings,
        "report_settings": report_settings,
        "admin_logs": admin_logs,
        "alert_states": alert_states,
        "expiry_states": expiry_states,
        "known_devices": known_devices,
        "retention_states": retention_states,
        "node_costs": node_costs,
        "traffic_snapshots": traffic_snapshots,
        "campaigns": campaigns,
    }

    target_dir = Path(out_dir) if out_dir else Path.cwd() / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"remnabot_backup_{timestamp}.json"

    def _write_file():
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    await asyncio.to_thread(_write_file)

    logger.info("Database backup created at %s", file_path)
    return file_path


async def restore_database_backup(session: AsyncSession, file_path: str | Path) -> dict[str, int]:
    """Restore database records from a JSON backup file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Backup file not found: {path}")

    def _read_file():
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    data = await asyncio.to_thread(_read_file)

    stats = {
        "users": 0,
        "wallets": 0,
        "services": 0,
        "orders": 0,
        "coupons": 0,
        "settings": 0,
        "topups": 0,
        "crypto_invoices": 0,
        "coupon_usages": 0,
        "referral_rewards": 0,
        "support_messages": 0,
        "alert_settings": 0,
        "report_settings": 0,
        "admin_logs": 0,
        "alert_states": 0,
        "expiry_states": 0,
        "known_devices": 0,
        "retention_states": 0,
        "node_costs": 0,
        "traffic_snapshots": 0,
        "campaigns": 0,
    }

    def _parse_dt(val):
        if not val or not isinstance(val, str):
            return None
        try:
            return datetime.fromisoformat(val)
        except Exception:
            return None

    # 1. Users
    for u_data in data.get("users", []):
        tid = u_data.get("telegram_id")
        if not tid:
            continue
        res = await session.execute(select(User).where(User.telegram_id == tid))
        existing_u = res.scalar_one_or_none()
        if existing_u:
            existing_u.username = u_data.get("username", existing_u.username)
            existing_u.language = u_data.get("language", existing_u.language)
            existing_u.is_verified = u_data.get("is_verified", existing_u.is_verified)
            existing_u.is_banned = u_data.get("is_banned", existing_u.is_banned)
            existing_u.has_claimed_trial = u_data.get("has_claimed_trial", existing_u.has_claimed_trial)
        else:
            session.add(
                User(
                    telegram_id=tid,
                    username=u_data.get("username"),
                    language=u_data.get("language") or "fa",
                    is_verified=u_data.get("is_verified", False),
                    is_banned=u_data.get("is_banned", False),
                    has_claimed_trial=u_data.get("has_claimed_trial", False),
                    referred_by_id=u_data.get("referred_by_id"),
                )
            )
        stats["users"] += 1

    await session.flush()

    # 2. Wallets
    for w_data in data.get("wallets", []):
        tid = w_data.get("telegram_id")
        if not tid:
            continue
        existing_w = await session.get(Wallet, tid)
        if existing_w:
            existing_w.balance = w_data.get("balance", existing_w.balance)
        else:
            session.add(Wallet(telegram_id=tid, balance=w_data.get("balance", 0)))
        stats["wallets"] += 1

    # 3. Services
    for s_data in data.get("services", []):
        s_id = s_data.get("id")
        existing_s = await session.get(Service, s_id) if s_id else None
        if existing_s:
            existing_s.name = s_data.get("name", existing_s.name)
            existing_s.price = s_data.get("price", existing_s.price)
            existing_s.duration_days = s_data.get("duration_days", existing_s.duration_days)
            existing_s.traffic_gb = s_data.get("traffic_gb", existing_s.traffic_gb)
            existing_s.is_active = s_data.get("is_active", existing_s.is_active)
            existing_s.traffic_strategy = s_data.get("traffic_strategy", existing_s.traffic_strategy)
            existing_s.hwid_limit = s_data.get("hwid_limit", existing_s.hwid_limit)
            existing_s.squad_uuid = s_data.get("squad_uuid", existing_s.squad_uuid)
        else:
            session.add(
                Service(
                    id=s_id,
                    name=s_data.get("name", ""),
                    price=s_data.get("price", 0),
                    duration_days=s_data.get("duration_days", 30),
                    traffic_gb=s_data.get("traffic_gb", 0),
                    is_active=s_data.get("is_active", True),
                    traffic_strategy=s_data.get("traffic_strategy", "NO_RESET"),
                    hwid_limit=s_data.get("hwid_limit"),
                    squad_uuid=s_data.get("squad_uuid"),
                )
            )
        stats["services"] += 1

    # 4. Orders
    for o_data in data.get("orders", []):
        o_id = o_data.get("id")
        existing_o = await session.get(Order, o_id) if o_id else None
        if not existing_o:
            session.add(
                Order(
                    id=o_id,
                    telegram_id=o_data.get("telegram_id"),
                    service_id=o_data.get("service_id"),
                    service_name=o_data.get("service_name"),
                    amount=o_data.get("amount", 0),
                    duration_days=o_data.get("duration_days", 30),
                    traffic_gb=o_data.get("traffic_gb", 0),
                    panel_user_id=o_data.get("panel_user_id"),
                    panel_username=o_data.get("panel_username"),
                    subscription_url=o_data.get("subscription_url"),
                    status=o_data.get("status", "COMPLETED"),
                )
            )
            stats["orders"] += 1

    # 5. Coupons
    for c_data in data.get("coupons", []):
        code = c_data.get("code")
        if not code:
            continue
        res = await session.execute(select(Coupon).where(Coupon.code == code))
        existing_c = res.scalar_one_or_none()
        if existing_c:
            existing_c.discount_percent = c_data.get("discount_percent", existing_c.discount_percent)
            existing_c.discount_amount = c_data.get("discount_amount", existing_c.discount_amount)
            existing_c.max_uses = c_data.get("max_uses", existing_c.max_uses)
            existing_c.used_count = c_data.get("used_count", existing_c.used_count)
            existing_c.is_active = c_data.get("is_active", existing_c.is_active)
        else:
            session.add(
                Coupon(
                    code=code,
                    discount_percent=c_data.get("discount_percent"),
                    discount_amount=c_data.get("discount_amount"),
                    max_uses=c_data.get("max_uses"),
                    used_count=c_data.get("used_count", 0),
                    is_active=c_data.get("is_active", True),
                )
            )
        stats["coupons"] += 1

    # 6. App Settings
    settings_dict = data.get("settings", {})
    for key, val in settings_dict.items():
        existing_set = await session.get(AppSetting, key)
        if existing_set:
            existing_set.value = str(val)
        else:
            session.add(AppSetting(key=key, value=str(val)))
        stats["settings"] += 1

    # 7. Topups
    for tp_data in data.get("topups", []):
        tp_id = tp_data.get("id")
        existing_tp = await session.get(Topup, tp_id) if tp_id else None
        if not existing_tp:
            status_str = tp_data.get("status", "pending")
            status_val = TopupStatus(status_str) if status_str in TopupStatus._value2member_map_ else TopupStatus.PENDING
            session.add(
                Topup(
                    id=tp_id,
                    telegram_id=tp_data.get("telegram_id"),
                    amount=tp_data.get("amount", 0),
                    status=status_val,
                    receipt_hash=tp_data.get("receipt_hash"),
                    receipt_photo_id=tp_data.get("receipt_photo_id"),
                    created_at=_parse_dt(tp_data.get("created_at")),
                    decided_at=_parse_dt(tp_data.get("decided_at")),
                    admin_message_id=tp_data.get("admin_message_id"),
                )
            )
            stats["topups"] += 1

    # 8. Crypto Invoices
    for ci_data in data.get("crypto_invoices", []):
        ci_id = ci_data.get("id")
        existing_ci = await session.get(CryptoInvoice, ci_id) if ci_id else None
        if not existing_ci:
            session.add(
                CryptoInvoice(
                    id=ci_id,
                    telegram_id=ci_data.get("telegram_id"),
                    amount_toman=ci_data.get("amount_toman", 0),
                    amount_ton=ci_data.get("amount_ton", 0.0),
                    nanotons=ci_data.get("nanotons", 0),
                    comment=ci_data.get("comment", ""),
                    pay_address=ci_data.get("pay_address", ""),
                    status=ci_data.get("status", "pending"),
                    tx_hash=ci_data.get("tx_hash"),
                    expires_at=_parse_dt(ci_data.get("expires_at")),
                    created_at=_parse_dt(ci_data.get("created_at")),
                    paid_at=_parse_dt(ci_data.get("paid_at")),
                )
            )
            stats["crypto_invoices"] += 1

    # 9. Coupon Usages
    for cu_data in data.get("coupon_usages", []):
        cu_id = cu_data.get("id")
        existing_cu = await session.get(CouponUsage, cu_id) if cu_id else None
        if not existing_cu:
            session.add(
                CouponUsage(
                    id=cu_id,
                    coupon_id=cu_data.get("coupon_id"),
                    telegram_id=cu_data.get("telegram_id"),
                    order_id=cu_data.get("order_id"),
                    discount_applied=cu_data.get("discount_applied", 0),
                    created_at=_parse_dt(cu_data.get("created_at")),
                )
            )
            stats["coupon_usages"] += 1

    # 10. Referral Rewards
    for rr_data in data.get("referral_rewards", []):
        rr_id = rr_data.get("id")
        existing_rr = await session.get(ReferralReward, rr_id) if rr_id else None
        if not existing_rr:
            session.add(
                ReferralReward(
                    id=rr_id,
                    inviter_id=rr_data.get("inviter_id"),
                    referee_id=rr_data.get("referee_id"),
                    reward_gb=rr_data.get("reward_gb", 0),
                    applied=rr_data.get("applied", False),
                    created_at=_parse_dt(rr_data.get("created_at")),
                )
            )
            stats["referral_rewards"] += 1

    # 11. Support Messages
    for sm_data in data.get("support_messages", []):
        sm_id = sm_data.get("admin_message_id")
        existing_sm = await session.get(SupportMessage, sm_id) if sm_id else None
        if not existing_sm:
            session.add(
                SupportMessage(
                    admin_message_id=sm_id,
                    telegram_id=sm_data.get("telegram_id"),
                    created_at=_parse_dt(sm_data.get("created_at")),
                )
            )
            stats["support_messages"] += 1

    # 12. AlertSettings
    for a_data in data.get("alert_settings", []):
        tid = a_data.get("telegram_id")
        existing_a = await session.get(AlertSettings, tid) if tid else None
        if existing_a:
            existing_a.traffic_percent = a_data.get("traffic_percent", existing_a.traffic_percent)
            existing_a.expire_days = a_data.get("expire_days", existing_a.expire_days)
        else:
            session.add(
                AlertSettings(
                    telegram_id=tid,
                    traffic_percent=a_data.get("traffic_percent", 80),
                    expire_days=a_data.get("expire_days", 3),
                    updated_at=_parse_dt(a_data.get("updated_at")),
                )
            )
        stats["alert_settings"] += 1

    # 13. ReportSettings
    for r_data in data.get("report_settings", []):
        tid = r_data.get("telegram_id")
        existing_r = await session.get(ReportSettings, tid) if tid else None
        if not existing_r:
            session.add(
                ReportSettings(
                    telegram_id=tid,
                    nightly=r_data.get("nightly", True),
                    weekly=r_data.get("weekly", True),
                    monthly=r_data.get("monthly", True),
                    clean_reports=r_data.get("clean_reports", False),
                    last_report_message_id=r_data.get("last_report_message_id"),
                    last_nightly_message_id=r_data.get("last_nightly_message_id"),
                    last_weekly_message_id=r_data.get("last_weekly_message_id"),
                    last_monthly_message_id=r_data.get("last_monthly_message_id"),
                    wheel_notify=r_data.get("wheel_notify", True),
                    wheel_notified=r_data.get("wheel_notified", False),
                    wheel_last_spin_at=_parse_dt(r_data.get("wheel_last_spin_at")),
                    last_wheel_message_id=r_data.get("last_wheel_message_id"),
                    updated_at=_parse_dt(r_data.get("updated_at")),
                )
            )
            stats["report_settings"] += 1

    # 14. AdminLog
    for al_data in data.get("admin_logs", []):
        al_id = al_data.get("id")
        existing_al = await session.get(AdminLog, al_id) if al_id else None
        if not existing_al:
            session.add(
                AdminLog(
                    id=al_id,
                    admin_id=al_data.get("admin_id"),
                    action=al_data.get("action", ""),
                    detail=al_data.get("detail"),
                    target_user_id=al_data.get("target_user_id"),
                    created_at=_parse_dt(al_data.get("created_at")),
                )
            )
            stats["admin_logs"] += 1

    # 15. AlertState
    for ast_data in data.get("alert_states", []):
        acc_id = ast_data.get("account_id")
        existing_ast = await session.get(AlertState, acc_id) if acc_id else None
        if existing_ast:
            existing_ast.traffic_alerted = ast_data.get("traffic_alerted", existing_ast.traffic_alerted)
            existing_ast.expire_alerted = ast_data.get("expire_alerted", existing_ast.expire_alerted)
        else:
            session.add(
                AlertState(
                    account_id=acc_id,
                    telegram_id=ast_data.get("telegram_id"),
                    traffic_alerted=ast_data.get("traffic_alerted", False),
                    expire_alerted=ast_data.get("expire_alerted", False),
                    updated_at=_parse_dt(ast_data.get("updated_at")),
                )
            )
        stats["alert_states"] += 1

    # 16. ExpiryState
    for es_data in data.get("expiry_states", []):
        acc_id = es_data.get("account_id")
        existing_es = await session.get(ExpiryState, acc_id) if acc_id else None
        if existing_es:
            existing_es.last_days_left = es_data.get("last_days_left", existing_es.last_days_left)
            existing_es.disabled_notified = es_data.get("disabled_notified", existing_es.disabled_notified)
        else:
            session.add(
                ExpiryState(
                    account_id=acc_id,
                    telegram_id=es_data.get("telegram_id"),
                    last_days_left=es_data.get("last_days_left"),
                    disabled_notified=es_data.get("disabled_notified", False),
                    updated_at=_parse_dt(es_data.get("updated_at")),
                )
            )
        stats["expiry_states"] += 1

    # 17. KnownDevice
    for kd_data in data.get("known_devices", []):
        kd_id = kd_data.get("id")
        existing_kd = await session.get(KnownDevice, kd_id) if kd_id else None
        if not existing_kd:
            session.add(
                KnownDevice(
                    id=kd_id,
                    telegram_id=kd_data.get("telegram_id"),
                    account_id=kd_data.get("account_id"),
                    hwid=kd_data.get("hwid", ""),
                    platform=kd_data.get("platform"),
                    device_model=kd_data.get("device_model"),
                    created_at=_parse_dt(kd_data.get("created_at")),
                )
            )
            stats["known_devices"] += 1

    # 18. RetentionState
    for ret_data in data.get("retention_states", []):
        tid = ret_data.get("telegram_id")
        existing_ret = await session.get(RetentionState, tid) if tid else None
        if not existing_ret:
            session.add(
                RetentionState(
                    telegram_id=tid,
                    notified_at=_parse_dt(ret_data.get("notified_at")),
                )
            )
            stats["retention_states"] += 1

    # 19. NodeCost
    for nc_data in data.get("node_costs", []):
        nc_id = nc_data.get("id")
        existing_nc = await session.get(NodeCost, nc_id) if nc_id else None
        if not existing_nc:
            session.add(
                NodeCost(
                    id=nc_id,
                    node_uuid=nc_data.get("node_uuid"),
                    node_id=nc_data.get("node_id"),
                    node_name=nc_data.get("node_name"),
                    provider=nc_data.get("provider"),
                    monthly_cost_toman=nc_data.get("monthly_cost_toman", 0),
                    monthly_cost_eur=nc_data.get("monthly_cost_eur", 0.0),
                    currency=nc_data.get("currency", "EUR"),
                    due_date=nc_data.get("due_date"),
                    notes=nc_data.get("notes"),
                    alert_notified=nc_data.get("alert_notified", False),
                    created_at=_parse_dt(nc_data.get("created_at")),
                    updated_at=_parse_dt(nc_data.get("updated_at")),
                )
            )
            stats["node_costs"] += 1

    # 20. HourlyTrafficSnapshot
    for hts_data in data.get("traffic_snapshots", []):
        hts_id = hts_data.get("id")
        existing_hts = await session.get(HourlyTrafficSnapshot, hts_id) if hts_id else None
        if not existing_hts:
            session.add(
                HourlyTrafficSnapshot(
                    id=hts_id,
                    timestamp=_parse_dt(hts_data.get("timestamp")),
                    total_bytes=hts_data.get("total_bytes", 0),
                    delta_bytes=hts_data.get("delta_bytes", 0),
                    created_at=_parse_dt(hts_data.get("created_at")),
                )
            )
            stats["traffic_snapshots"] += 1

    # 21. Campaign
    for cmp_data in data.get("campaigns", []):
        cmp_id = cmp_data.get("id")
        existing_cmp = await session.get(Campaign, cmp_id) if cmp_id else None
        if not existing_cmp:
            session.add(
                Campaign(
                    id=cmp_id,
                    code=cmp_data.get("code", ""),
                    name=cmp_data.get("name", ""),
                    cost=cmp_data.get("cost", 0),
                    created_at=_parse_dt(cmp_data.get("created_at")),
                )
            )
            stats["campaigns"] += 1

    await session.commit()
    logger.info("Database backup restored from %s: %s", path, stats)
    return stats


BACKUP_HOUR = 1
BACKUP_MINUTE = 30


def _seconds_until_backup(hour: int = BACKUP_HOUR, minute: int = BACKUP_MINUTE) -> float:
    from datetime import timedelta

    from bot.config import get_settings
    from bot.services.formatting import now_tz

    now = now_tz(get_settings().TIMEZONE)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def create_encrypted_backup_archive(json_path: Path, password: str | None = None) -> Path:
    """Compress JSON dump into a password-protected zip file.

    Uses 'zip -P' CLI if available, otherwise pyzipper (AES-256).
    Removes raw unencrypted JSON after compression.
    """
    import shutil
    import subprocess
    import zipfile

    zip_path = json_path.with_suffix(".zip")
    pwd = (password or "").strip()

    if pwd:
        # 1. Try system zip CLI if present (e.g. Linux container)
        if shutil.which("zip"):
            try:
                cmd = ["zip", "-j", "-P", pwd, str(zip_path), str(json_path)]
                subprocess.run(cmd, capture_output=True, text=True, check=True)
                if zip_path.is_file():
                    try:
                        json_path.unlink(missing_ok=True)
                    except Exception as exc:
                        logger.warning("Could not unlink json_path: %s", exc)
                    return zip_path
            except Exception as exc:
                logger.warning("CLI zip command failed, falling back to pyzipper: %s", exc)

        # 2. Use pyzipper (AES-256)
        try:
            import pyzipper
            with pyzipper.AESZipFile(
                zip_path,
                "w",
                compression=pyzipper.ZIP_DEFLATED,
                encryption=pyzipper.WZ_AES,
            ) as zf:
                zf.setpassword(pwd.encode("utf-8"))
                zf.write(json_path, arcname=json_path.name)
            try:
                json_path.unlink(missing_ok=True)
            except Exception as exc:
                logger.warning("Could not unlink json_path: %s", exc)
            return zip_path
        except Exception as exc:
            logger.critical("pyzipper encryption failed: %s. Aborting backup to prevent unencrypted plaintext leak.", exc)
            try:
                json_path.unlink(missing_ok=True)
            except Exception:
                pass
            return None

    # Standard zip archive (only when encryption was not requested)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(json_path, arcname=json_path.name)
    try:
        json_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Could not unlink json_path: %s", exc)
    return zip_path


async def auto_backup_loop(bot, session_factory) -> None:
    """Daily automated backup loop sending database export to admin chat/topic at 01:30 AM."""
    import asyncio
    import os

    from aiogram.types import FSInputFile

    from bot.config import get_settings
    from bot.services.app_settings import get_store_settings

    logger.info("Starting auto database backup loop (target: %02d:%02d)", BACKUP_HOUR, BACKUP_MINUTE)
    while True:
        wait = _seconds_until_backup(BACKUP_HOUR, BACKUP_MINUTE)
        logger.info("Auto database backup scheduled in %.0f s (at %02d:%02d)", wait, BACKUP_HOUR, BACKUP_MINUTE)
        await asyncio.sleep(wait)
        try:
            settings = get_settings()
            admin_chat_id = settings.ADMIN_CHAT_ID
            if admin_chat_id:
                async with session_factory() as session:
                    raw_backup_path = await create_database_backup(session)
                    backup_pwd = getattr(settings, "BACKUP_PASSWORD", "") or os.environ.get("BACKUP_PASSWORD", "")
                    backup_path = await asyncio.to_thread(create_encrypted_backup_archive, raw_backup_path, backup_pwd)

                    store = await get_store_settings(session)
                    thread_kwargs = admin_thread_kwargs(store, settings, kind="backups")
                    if not thread_kwargs:
                        # Fallback to alerts if backups topic not explicitly set
                        thread_kwargs = admin_thread_kwargs(store, settings, kind="alerts")

                    from bot.db.repositories.app_setting_repo import AppSettingRepository
                    app_repo = AppSettingRepository(session)

                    # Delete previous backup message to always keep only the latest backup in chat
                    prev_backup_record = await app_repo.get("last_admin_backup_msg_record")
                    if prev_backup_record:
                        try:
                            prev_data = json.loads(prev_backup_record)
                            prev_cid = prev_data.get("chat_id")
                            prev_mid = prev_data.get("message_id")
                            if prev_cid and prev_mid:
                                await bot.delete_message(chat_id=prev_cid, message_id=prev_mid)
                                logger.info("Deleted previous backup message %s in chat %s", prev_mid, prev_cid)
                        except Exception as del_err:
                            logger.debug("Could not delete previous backup message: %s", del_err)

                    has_pwd = bool(backup_pwd)
                    backup_time_str = now_tz(getattr(settings, "TIMEZONE", "Asia/Tehran")).strftime('%Y-%m-%d %H:%M:%S')
                    caption = (
                        "💾 <b>نسخه پشتیبان خودکار دیتابیس (ساعت ۰۱:۳۰ بامداد)</b>\n\n"
                        f"📅 تاریخ: <code>{backup_time_str}</code>\n"
                        f"🔐 وضعیت رمزگذاری: <b>{'رمزدار (AES-256)' if has_pwd else 'فشرده‌سازی استاندارد'}</b>\n"
                        "📦 فایل شامل نسخه پشتیبان جداول ضروری (کاربران، کیف پول، سفارشات، سرویس‌ها، کدهای تخفیف، تنظیمات) می‌باشد."
                    )
                    doc = FSInputFile(backup_path, filename=backup_path.name)
                    sent_msg = await bot.send_document(
                        chat_id=admin_chat_id,
                        document=doc,
                        caption=caption,
                        **thread_kwargs,
                    )
                    if sent_msg and getattr(sent_msg, "message_id", None):
                        await app_repo.set(
                            "last_admin_backup_msg_record",
                            json.dumps({"chat_id": admin_chat_id, "message_id": sent_msg.message_id}),
                        )
                        await session.commit()

                    topic_id = thread_kwargs.get("message_thread_id")
                    logger.info("Auto database backup delivered to %s (topic: %s)", admin_chat_id, topic_id)

                    # Automated 7-day local backup retention cleanup
                    try:
                        backups_dir = Path("backups")
                        if backups_dir.exists():
                            now_ts = datetime.now(timezone.utc).timestamp()
                            retention_secs = 7 * 86400
                            for old_f in backups_dir.glob("remnabot_backup_*"):
                                if old_f.is_file() and (now_ts - old_f.stat().st_mtime) > retention_secs:
                                    old_f.unlink(missing_ok=True)
                                    logger.info("Purged expired local backup file: %s", old_f.name)
                    except Exception as clean_err:
                        logger.warning("Error cleaning expired backups: %s", clean_err)
        except Exception as exc:
            logger.exception("Failed to execute scheduled database backup: %s", exc)
        # Sleep 120s to ensure we roll past 01:30
        await asyncio.sleep(120)
