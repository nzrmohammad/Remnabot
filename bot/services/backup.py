"""Database backup export service."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminLog, AppSetting, Coupon, Order, Service, User, Wallet

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

    # 7. Admin Logs
    logs_res = await session.execute(select(AdminLog).order_by(AdminLog.id.desc()).limit(500))
    logs = [
        {
            "id": log_item.id,
            "admin_id": log_item.admin_id,
            "action": log_item.action,
            "detail": log_item.detail,
            "created_at": _serialize_val(log_item.created_at),
        }
        for log_item in logs_res.scalars().all()
    ]

    data = {
        "export_date": now.isoformat(),
        "users": users,
        "wallets": wallets,
        "orders": orders,
        "services": services,
        "coupons": coupons,
        "settings": settings,
        "admin_logs": logs,
    }

    target_dir = Path(out_dir) if out_dir else Path.cwd() / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"remnabot_backup_{timestamp}.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Database backup created at %s", file_path)
    return file_path


async def restore_database_backup(session: AsyncSession, file_path: str | Path) -> dict[str, int]:
    """Restore database records from a JSON backup file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Backup file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    stats = {
        "users": 0,
        "wallets": 0,
        "services": 0,
        "orders": 0,
        "coupons": 0,
        "settings": 0,
    }

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


async def auto_backup_loop(bot, session_factory) -> None:
    """Daily automated backup loop sending database export to admin chat/topic at 01:30 AM."""
    import asyncio

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
                    backup_path = await create_database_backup(session)
                    store = await get_store_settings(session)
                    topic_id = store.topic_alerts or settings.ADMIN_TOPIC_ALERTS
                    thread_kwargs = {"message_thread_id": topic_id} if topic_id else {}

                    caption = (
                        "💾 <b>نسخه پشتیبان خودکار دیتابیس (ساعت ۰۱:۳۰ بامداد)</b>\n\n"
                        f"📅 تاریخ: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                        "🔐 فایل شامل رکوردهای کاربران، کیف پول، سفارشات، سرویس‌ها، کدهای تخفیف و تنظیمات می‌باشد."
                    )
                    doc = FSInputFile(backup_path, filename=backup_path.name)
                    await bot.send_document(
                        chat_id=admin_chat_id,
                        document=doc,
                        caption=caption,
                        **thread_kwargs,
                    )
                    logger.info("Auto database backup delivered to %s (topic: %s)", admin_chat_id, topic_id)
        except Exception:
            logger.exception("Failed to execute scheduled database backup")
        # Sleep 120s to ensure we roll past 01:30
        await asyncio.sleep(120)
