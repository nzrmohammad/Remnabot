"""TMA User Shop, Purchase, Subscriptions, Devices, and Lucky Wheel endpoints."""
import logging
import random

from aiohttp import web

from bot.db.models import Service
from bot.services.purchases import execute_purchase
from bot.web.auth import get_authenticated_user
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def post_user_spin(request: web.Request) -> web.Response:
    """Handle Lucky Wheel spin with anti-cheat and prize allocation."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    if user_auth.get("is_preview"):
        return web.json_response(
            {"ok": False, "error": "چرخش گردونه فقط در محیط رسمی تلگرام امکان‌پذیر است."},
            status=400,
        )

    telegram_id = int(user_auth["id"])
    cache: FastCache = request.app["cache"]
    wheel_key = f"tma:user:{telegram_id}:wheel_spins"
    has_spun_free = bool(await cache.get(wheel_key))

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(telegram_id)
    has_active_sub = bool(
        panel_users and panel_users[0].get("status", "").upper() == "ACTIVE"
    )

    if has_spun_free and not has_active_sub:
        return web.json_response(
            {
                "ok": False,
                "error": "شانس رایگان شما مصرف شده است. برای دریافت جوایز روزانه به یک اشتراک فعال نیاز دارید.",
            },
            status=400,
        )

    # 6 configured prizes:
    # 1. 1 GB
    # 2. 1 روز VIP
    # 3. 10% تخفیف
    # 4. 500 MB
    # 5. پوچ
    # 6. دوباره
    prizes = [
        {"id": "1gb", "name": "1 GB ترافیک هدیه", "icon": "🎁", "type": "traffic", "value": 1},
        {"id": "1day", "name": "1 روز اشتراک VIP رایگان", "icon": "💎", "type": "days", "value": 1},
        {"id": "discount10", "name": "۱۰٪ کد تخفیف ویژه (کد: OFF10)", "icon": "🎟", "type": "coupon", "code": "OFF10"},
        {"id": "500mb", "name": "500 MB ترافیک هدیه", "icon": "⚡️", "type": "traffic", "value": 0.5},
        {"id": "blank", "name": "پوچ (شانس بعدی فردا)", "icon": "❌", "type": "blank", "value": 0},
        {"id": "again", "name": "دوباره (شانس مجدد!)", "icon": "🔄", "type": "again", "value": 0},
    ]

    chosen = random.choice(prizes)

    # If prize is traffic or days, apply to active account if available
    applied = False
    if panel_users and chosen["type"] in ("traffic", "days"):
        primary_id = panel_users[0].get("id")
        try:
            if chosen["type"] == "traffic":
                # Add GB
                traffic_bytes = int(chosen["value"] * 1024 * 1024 * 1024)
                await remnawave.update_user_subscription(
                    primary_id,
                    bandwidth_limit_delta=traffic_bytes,
                )
                applied = True
            elif chosen["type"] == "days":
                # Add 1 day
                await remnawave.update_user_subscription(
                    primary_id,
                    expire_delta_seconds=86400,
                )
                applied = True
        except Exception as exc:
            logger.warning("Failed to auto-apply wheel prize to panel: %s", exc)

    # Record spin unless it's "try again"
    if chosen["type"] != "again":
        # Keep until end of day (86400s)
        await cache.set(wheel_key, True, ttl_seconds=86400)

    # Invalidate dashboard cache
    await cache.delete(f"tma:user:{telegram_id}:dashboard")

    return web.json_response({
        "ok": True,
        "prize": chosen,
        "applied": applied,
    })


async def post_user_revoke_sub(request: web.Request) -> web.Response:
    """Revoke and generate a fresh subscription URL for user."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    if user_auth.get("is_preview"):
        return web.json_response(
            {"ok": False, "error": "این عملیات فقط در محیط رسمی تلگرام امکان‌پذیر است."},
            status=400,
        )

    telegram_id = int(user_auth["id"])
    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(telegram_id)
    if not panel_users:
        return web.json_response({"ok": False, "error": "سرویس فعالی یافت نشد."}, status=404)

    primary_id = panel_users[0].get("id")
    revoked = await remnawave.revoke_user_subscription(primary_id)
    if not revoked:
        return web.json_response({"ok": False, "error": "خطا در تغییر لینک اشتراک."}, status=500)

    # Invalidate cache
    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{telegram_id}:dashboard")

    new_sub_url = revoked.get("subscriptionUrl") or revoked.get("subscription_url") or ""
    return web.json_response({
        "ok": True,
        "subscription_url": new_sub_url,
    })


async def post_user_kill_device(request: web.Request) -> web.Response:
    """Disconnect a specific HWID session for the user."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    if user_auth.get("is_preview"):
        return web.json_response(
            {"ok": False, "error": "این عملیات فقط در محیط رسمی تلگرام امکان‌پذیر است."},
            status=400,
        )

    try:
        body = await request.json()
    except Exception:
        body = {}

    hwid = body.get("hwid")
    if not hwid:
        return web.json_response({"ok": False, "error": "شناسه دستگاه (HWID) الزامی است."}, status=400)

    telegram_id = int(user_auth["id"])
    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(telegram_id)
    if not panel_users:
        return web.json_response({"ok": False, "error": "سرویس فعالی یافت نشد."}, status=404)

    primary_id = panel_users[0].get("id")
    success = await remnawave.delete_hwid_device(primary_id, hwid)

    # Invalidate cache
    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{telegram_id}:dashboard")

    return web.json_response({"ok": bool(success)})


async def post_user_validate_coupon(request: web.Request) -> web.Response:
    """Validate a discount coupon code for authenticated user."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    code = (body.get("code") or "").strip()
    if not code:
        return web.json_response({"ok": False, "message": "کد تخفیف الزامی است."}, status=400)

    telegram_id = int(user_auth["id"])
    session_factory = request.app["session_factory"]

    from bot.db.repositories.coupon_repo import CouponRepository

    async with session_factory() as session:
        coupon_repo = CouponRepository(session)
        is_valid, err_key, discount_amount = await coupon_repo.validate_coupon(
            code=code,
            telegram_id=telegram_id,
            price=0,
        )
        if not is_valid:
            err_map = {
                "coupon_not_found": "کد تخفیف وارد شده یافت نشد.",
                "coupon_inactive": "این کد تخفیف در حال حاضر غیرفعال است.",
                "coupon_expired": "مهلت استفاده از این کد تخفیف به پایان رسیده است.",
                "coupon_limit_reached": "ظرفیت استفاده از این کد تخفیف تکمیل شده است.",
                "coupon_already_used": "شما قبلاً از این کد تخفیف استفاده کرده‌اید.",
            }
            msg = err_map.get(err_key, "کد تخفیف نامعتبر است.")
            return web.json_response({"ok": False, "message": msg}, status=400)

        coupon = await coupon_repo.get_by_code(code)
        return web.json_response({
            "ok": True,
            "data": {
                "code": coupon.code,
                "discount_percent": coupon.discount_percent or 0,
                "discount_amount": coupon.discount_amount or 0,
            }
        })


async def post_user_purchase(request: web.Request) -> web.Response:
    """Execute purchase/renewal using user wallet balance directly from TMA."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    service_id = body.get("service_id")
    coupon_code = (body.get("coupon_code") or "").strip().upper() or None
    account_id = body.get("account_id")

    if not service_id:
        return web.json_response({"ok": False, "message": "شناسه بسته الزامی است."}, status=400)

    telegram_id = int(user_auth["id"])
    session_factory = request.app["session_factory"]
    remnawave = request.app["remnawave"]
    cache: FastCache = request.app["cache"]

    async with session_factory() as session:
        service = await session.get(Service, int(service_id))
        if not service or not service.is_active:
            return web.json_response({"ok": False, "message": "بسته مورد نظر یافت نشد یا غیرفعال است."}, status=404)

        coupon_repo = CouponRepository(session)
        discount_amount = 0
        coupon_obj = None
        if coupon_code:
            is_valid, _, disc = await coupon_repo.validate_coupon(coupon_code, telegram_id, price=service.price)
            if is_valid:
                discount_amount = disc
                coupon_obj = await coupon_repo.get_by_code(coupon_code)

        chosen_acc = None
        if account_id:
            panel_users = await remnawave.get_users_by_telegram_id(telegram_id) or []
            chosen_acc = next((u for u in panel_users if str(u.get("id")) == str(account_id)), None)

        result = await execute_purchase(
            remnawave=remnawave,
            session=session,
            service=service,
            telegram_id=telegram_id,
            chosen_account=chosen_acc,
            discount_amount=discount_amount,
        )

        if not result.ok:
            if result.kind == "insufficient":
                effective_price = max(0, service.price - discount_amount)
                return web.json_response({
                    "ok": False,
                    "error": "insufficient_balance",
                    "needed": effective_price,
                    "current": result.new_balance,
                    "message": "موجودی کیف پول شما کافی نیست.",
                }, status=400)
            return web.json_response({"ok": False, "message": "خطا در پردازش خرید سرویس."}, status=500)

        if coupon_obj and result.order_id:
            try:
                await coupon_repo.record_usage(coupon_obj.id, telegram_id, result.order_id, discount_amount)
                await session.commit()
            except Exception as exc:
                logger.warning("Failed to record coupon usage in TMA purchase: %s", exc)

        await cache.delete(f"tma:user:{telegram_id}:dashboard")

        return web.json_response({
            "ok": True,
            "message": "سرویس با موفقیت فعال / تمدید شد!",
            "subscription_url": result.subscription_url,
            "new_balance": result.new_balance,
        })
