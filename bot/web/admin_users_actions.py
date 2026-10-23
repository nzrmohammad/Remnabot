"""Admin User Modification, Ban, Wallet, and Subscription Actions."""
import logging
from datetime import datetime, timedelta, timezone

from aiohttp import web

from bot.common.helpers import get_limit_bytes
from bot.services.formatting import ltr_frag
from bot.db.models import AdminLog
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.web.admin_common import _check_admin, db_session
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def post_admin_modify_user(request: web.Request) -> web.Response:
    """Add traffic (GB) and/or extend days for a user in a unified action."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    target_id = body.get("telegram_id")
    action = body.get("action")
    traffic_gb = 0.0
    days = 0

    if "traffic_gb" in body or "days" in body:
        try:
            traffic_gb = max(0.0, float(body.get("traffic_gb") or 0))
        except (ValueError, TypeError):
            traffic_gb = 0.0
        try:
            days = max(0, int(body.get("days") or 0))
        except (ValueError, TypeError):
            days = 0
    elif action == "traffic":
        try:
            traffic_gb = max(0.0, float(body.get("amount") or 0))
        except (ValueError, TypeError):
            traffic_gb = 0.0
    elif action == "days":
        try:
            days = max(0, int(body.get("amount") or 0))
        except (ValueError, TypeError):
            days = 0

    if not target_id or (traffic_gb <= 0 and days <= 0):
        return web.json_response({"ok": False, "error": "حداقل یکی از مقادیر حجم یا روز را وارد کنید."}, status=400)

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": False, "error": "اکانتی در پنل برای این کاربر یافت نشد."}, status=404)

    puser = panel_users[0]
    primary_id = puser.get("id")
    cur_limit = get_limit_bytes(puser)
    cur_exp_str = puser.get("expireAt")
    now = datetime.now(timezone.utc)

    new_limit = cur_limit + int(traffic_gb * 1024 * 1024 * 1024) if traffic_gb > 0 else cur_limit
    new_exp_iso = cur_exp_str
    if days > 0:
        base_dt = now
        if cur_exp_str:
            try:
                dt = datetime.fromisoformat(str(cur_exp_str).replace("Z", "+00:00"))
                if dt > now:
                    base_dt = dt
            except Exception:
                pass
        new_exp_iso = (base_dt + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif not new_exp_iso and traffic_gb > 0:
        new_exp_iso = (now + timedelta(days=36500)).strftime("%Y-%m-%dT%H:%M:%SZ")

    res = await remnawave.update_user_subscription(
        primary_id,
        expire_at_iso=new_exp_iso,
        traffic_limit_bytes=new_limit,
        status="ACTIVE",
    )
    if not res:
        return web.json_response({"ok": False, "error": "خطا در اعمال تغییرات در پنل رمناویو."}, status=502)

    parts = []
    if traffic_gb > 0:
        parts.append(f"افزایش {ltr_frag(f'{traffic_gb:g} GB')} ترافیک")
    if days > 0:
        parts.append(f"تمدید {days} روز اشتراک")
    log_detail = f"{' و '.join(parts)} کاربر {target_id}"

    async with db_session(request) as session:
        session.add(AdminLog(admin_id=admin["id"], action="modify_user_subscription", detail=log_detail))
        await session.commit()

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")
    await cache.delete(f"tma:user:{target_id}:dashboard:default")
    await cache.delete(f"tma:user:{target_id}:profile")
    await cache.delete("tma:admin:overview")

    return web.json_response({"ok": True, "message": log_detail})


async def post_admin_kill_sessions(request: web.Request) -> web.Response:
    """Disconnect all active HWID devices for a user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_id = body.get("telegram_id")
    if not target_id:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": False, "error": "اکانتی در پنل یافت نشد."}, status=404)

    primary_id = panel_users[0].get("id")
    devices = await remnawave.get_user_hwid_devices(primary_id)
    killed = 0
    for dev in devices:
        hwid = dev.get("hwid")
        if hwid and await remnawave.delete_hwid_device(primary_id, hwid):
            killed += 1

    return web.json_response({"ok": True, "killed_devices": killed})


async def post_admin_toggle_ban(request: web.Request) -> web.Response:
    """Ban or unban a user in bot DB and Remnawave panel."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_id = body.get("telegram_id")
    ban_state = bool(body.get("ban", True))
    remnawave = request.app["remnawave"]

    async with db_session(request) as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(int(target_id))
        if user:
            user.is_banned = ban_state
            await session.commit()

    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if panel_users:
        primary_id = panel_users[0].get("id")
        await remnawave.set_user_status(primary_id, "DISABLED" if ban_state else "ACTIVE")

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")
    await cache.delete(f"tma:user:{target_id}:dashboard:default")
    await cache.delete(f"tma:user:{target_id}:profile")

    return web.json_response({"ok": True, "banned": ban_state})


async def post_admin_reset_trial(request: web.Request) -> web.Response:
    """Reset trial status so user can claim a test service again."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_id = body.get("telegram_id")
    if not target_id:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    async with db_session(request) as session:
        user_repo = UserRepository(session)
        await user_repo.set_claimed_trial(int(target_id), claimed=False)
        session.add(AdminLog(admin_id=admin["id"], action="reset_trial", detail=f"فعال‌سازی مجدد تست برای کاربر {target_id}"))
        await session.commit()

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")
    await cache.delete(f"tma:user:{target_id}:dashboard:default")
    await cache.delete(f"tma:user:{target_id}:profile")
    return web.json_response({"ok": True, "message": "قابلیت دریافت اشتراک تست برای این کاربر با موفقیت فعال شد."})


async def post_admin_user_wallet(request: web.Request) -> web.Response:
    """Charge or deduct user wallet balance in Toman."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    target_id = body.get("telegram_id")
    try:
        amount = int(body.get("amount", 0))
    except (ValueError, TypeError):
        amount = 0

    reason = str(body.get("reason") or "شارژ دستی توسط مدیریت").strip()
    if not target_id or amount == 0:
        return web.json_response({"ok": False, "error": "مقدار مبلغ و کاربر نامعتبر است."}, status=400)

    async with db_session(request) as session:
        wallet_repo = WalletRepository(session)
        wallet = await wallet_repo.get_wallet(int(target_id))
        old_balance = int(wallet.balance if wallet else 0)
        new_balance = await wallet_repo.adjust_balance_atomic(int(target_id), amount)

        action_name = "wallet_charge" if amount > 0 else "wallet_deduct"
        detail_msg = f"{'افزایش' if amount > 0 else 'کسر'} {abs(amount):,} تومان موجودی کاربر {target_id} ({reason})"
        session.add(AdminLog(admin_id=admin["id"], action=action_name, detail=detail_msg, target_user_id=int(target_id)))
        await session.commit()

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")
    await cache.delete(f"tma:user:{target_id}:dashboard:default")
    await cache.delete(f"tma:user:{target_id}:profile")
    await cache.delete("tma:admin:overview")

    bot = request.app.get("bot")
    if bot:
        sign = "+" if amount > 0 else "-"
        notif = (
            f"🔔 <b>تغییر موجودی کیف پول</b>\n\n"
            f"مبلغ: <b>{sign}{abs(amount):,} تومان</b>\n"
            f"موجودی جدید: <b>{new_balance:,} تومان</b>\n"
            f"توضیحات: {reason}"
        )
        try:
            await bot.send_message(chat_id=int(target_id), text=notif, parse_mode="HTML")
        except Exception:
            pass

    return web.json_response({
        "ok": True,
        "old_balance": old_balance,
        "new_balance": new_balance,
        "delta": amount,
        "message": f"موجودی کاربر با موفقیت به‌روزرسانی شد: {new_balance:,} تومان",
    })


async def post_admin_user_revoke_sub(request: web.Request) -> web.Response:
    """Revoke existing subscription URL and regenerate a new one via Remnawave."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_id = body.get("telegram_id")
    if not target_id:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": False, "error": "اکانتی در پنل برای این کاربر یافت نشد."}, status=404)

    primary_id = panel_users[0].get("id")
    revoked = await remnawave.revoke_user_subscription(primary_id)
    if not revoked:
        return web.json_response({"ok": False, "error": "خطا در برقراری ارتباط با پنل رمناویو."}, status=502)

    async with db_session(request) as session:
        session.add(AdminLog(admin_id=admin["id"], action="revoke_sub", detail=f"تولید مجدد لینک سابسکریپشن کاربر {target_id}"))
        await session.commit()

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")
    await cache.delete(f"tma:user:{target_id}:dashboard:default")
    await cache.delete(f"tma:user:{target_id}:profile")

    new_sub = revoked.get("subscriptionUrl") or revoked.get("subscription_url") or ""
    return web.json_response({
        "ok": True,
        "subscription_url": new_sub,
        "message": "لینک سابسکریپشن کاربر با موفقیت باطل و مجدداً ایجاد شد.",
    })


async def post_admin_create_user(request: web.Request) -> web.Response:
    """Create a new panel user directly linked to a customer's Telegram ID."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "فرمت داده نامعتبر است."}, status=400)

    telegram_id_raw = body.get("telegram_id")
    if not telegram_id_raw:
        return web.json_response({"ok": False, "error": "شناسه عددی تلگرام (Telegram ID) الزامی است."}, status=400)

    try:
        telegram_id = int(telegram_id_raw)
        if telegram_id <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "شناسه عددی تلگرام نامعتبر است."}, status=400)

    username = (body.get("username") or "").strip()
    if not username:
        username = f"user_{telegram_id}"

    try:
        traffic_gb = max(0, int(float(body.get("traffic_gb") or 0)))
    except (ValueError, TypeError):
        traffic_gb = 0

    try:
        duration_days = max(1, int(body.get("duration_days") or 30))
    except (ValueError, TypeError):
        duration_days = 30

    hwid_limit = None
    if body.get("hwid_limit") is not None and str(body.get("hwid_limit")).strip() != "":
        try:
            hwid_limit = max(1, int(body.get("hwid_limit")))
        except (ValueError, TypeError):
            hwid_limit = None

    remnawave = request.app.get("remnawave")
    if not remnawave:
        return web.json_response({"ok": False, "error": "ارتباط با پنل رمناویو برقرار نشد."}, status=503)

    created_user = await remnawave.create_user(
        username=username,
        expire_days=duration_days,
        traffic_gb=traffic_gb,
        telegram_id=telegram_id,
        hwid_device_limit=hwid_limit,
    )

    if not created_user:
        return web.json_response(
            {"ok": False, "error": "خطا در ایجاد کاربر در پنل رمناویو (احتمالاً نام کاربری تکراری است)."},
            status=500,
        )

    async with db_session(request) as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_or_create(telegram_id, username=username)
        db_user.is_verified = True

        log_detail = f"ایجاد کاربر {username} (شناسه: {telegram_id}) با حجم {traffic_gb} گیگابایت و مدت {duration_days} روز"
        if hwid_limit:
            log_detail += f" (محدودیت دستگاه: {hwid_limit})"
        session.add(AdminLog(admin_id=admin["id"], action="create_user", target_user_id=telegram_id, detail=log_detail))
        await session.commit()

    cache: FastCache | None = request.app.get("cache")
    if cache:
        await cache.delete(f"tma:user:{telegram_id}:dashboard")
        await cache.delete(f"tma:user:{telegram_id}:dashboard:default")
        await cache.delete(f"tma:user:{telegram_id}:profile")
        await cache.delete("tma:admin:users:*")

    return web.json_response({
        "ok": True,
        "message": f"کاربر {username} با موفقیت در پنل رمناویو ایجاد شد.",
        "user": created_user,
    })
