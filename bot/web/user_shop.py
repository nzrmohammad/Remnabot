"""TMA User Shop, Purchase, Subscriptions, Devices, and Lucky Wheel endpoints."""
import logging
import random

from aiohttp import web

from bot.db.models import Service
from bot.db.repositories.coupon_repo import CouponRepository
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
    wheel_ts_key = f"tma:user:{telegram_id}:wheel_last_spin"

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(telegram_id) or []
    has_active_sub = any(
        (u.get("status") or "").upper() == "ACTIVE" for u in panel_users
    )

    if not has_active_sub:
        return web.json_response(
            {
                "ok": False,
                "error": "برای استفاده از گردونه شانس، داشتن یک اشتراک فعال در پنل الزامی است.",
                "code": "sub_required",
            },
            status=400,
        )

    import time
    last_spin = await cache.get(wheel_ts_key)
    now_ts = time.time()
    if last_spin is not None:
        try:
            elapsed = now_ts - float(last_spin)
            if elapsed < 86400:
                rem_secs = max(1, int(86400 - elapsed))
                hours = rem_secs // 3600
                mins = (rem_secs % 3600) // 60
                return web.json_response(
                    {
                        "ok": False,
                        "error": f"گردونه شانس هر ۲۴ ساعت یک‌بار قابل استفاده است. زمان باقیمانده: {hours} ساعت و {mins} دقیقه.",
                        "next_spin_seconds": rem_secs,
                        "code": "cooldown",
                    },
                    status=400,
                )
        except (ValueError, TypeError):
            pass

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
        primary = next(
            (u for u in panel_users if (u.get("status") or "").upper() == "ACTIVE"),
            panel_users[0],
        )
        primary_id = int(primary.get("id"))
        current_expire = primary.get("expireAt")
        current_limit = int(primary.get("trafficLimitBytes") or 0)
        try:
            if chosen["type"] == "traffic":
                # Add GB
                traffic_bytes = int(chosen["value"] * 1024 * 1024 * 1024)
                new_limit = current_limit + traffic_bytes
                await remnawave.update_user_subscription(
                    primary_id,
                    current_expire,
                    new_limit,
                )
                applied = True
            elif chosen["type"] == "days":
                # Add 1 day
                from datetime import datetime, timezone, timedelta
                from bot.services.formatting import parse_iso
                cur_dt = parse_iso(current_expire)
                now_utc = datetime.now(timezone.utc)
                base = cur_dt if cur_dt and cur_dt > now_utc else now_utc
                new_expire_dt = base + timedelta(days=int(chosen["value"]))
                new_expire_iso = new_expire_dt.isoformat()
                await remnawave.update_user_subscription(
                    primary_id,
                    new_expire_iso,
                    current_limit,
                )
                applied = True
        except Exception as exc:
            logger.warning("Failed to auto-apply wheel prize to panel: %s", exc)

    if chosen["type"] == "coupon":
        try:
            session_factory = request.app.get("session_factory")
            if session_factory:
                async with session_factory() as session:
                    coupon_repo = CouponRepository(session)
                    existing = await coupon_repo.get_by_code(chosen.get("code", "OFF10"))
                    if not existing:
                        await coupon_repo.create(
                            code=chosen.get("code", "OFF10"),
                            discount_percent=10,
                            max_uses=0,
                        )
                    await session.commit()
                applied = True
        except Exception as exc:
            logger.warning("Failed to prepare coupon for wheel prize: %s", exc)

    # Record spin unless it's "try again"
    if chosen["type"] != "again":
        # Keep 24-hour cooldown
        await cache.set(wheel_ts_key, now_ts, ttl_seconds=86400)
        try:
            session_factory = request.app.get("session_factory")
            if session_factory:
                async with session_factory() as session:
                    from bot.db.repositories.report_repo import ReportRepository
                    rep_repo = ReportRepository(session)
                    await rep_repo.record_wheel_spin(telegram_id)
                    await session.commit()
        except Exception as exc:
            logger.warning("Failed to record wheel spin in DB for %s: %s", telegram_id, exc)

    # Invalidate dashboard cache
    await cache.delete(f"tma:user:{telegram_id}:dashboard")
    await cache.delete(f"tma:user:{telegram_id}:profile")

    # If applied, notify user via Telegram bot
    bot = request.app.get("bot")
    if bot and applied and chosen["type"] not in ("blank", "again"):
        try:
            await bot.send_message(
                telegram_id,
                f"🎉 <b>تبریک! شما در گردونه شانس برنده شدید:</b>\n"
                f"✨ <b>{chosen['name']}</b>\n\n"
                f"این جایزه با موفقیت به حساب شما اعمال گردید.",
            )
        except Exception:
            pass

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
        panel_users = await remnawave.get_users_by_telegram_id(telegram_id) or []
        if account_id:
            chosen_acc = next((u for u in panel_users if str(u.get("id")) == str(account_id)), None)
        if not chosen_acc and panel_users:
            chosen_acc = panel_users[0]

        result = await execute_purchase(
            remnawave=remnawave,
            session=session,
            service=service,
            telegram_id=telegram_id,
            chosen_account=chosen_acc,
            discount_amount=discount_amount,
        )

        effective_price = max(0, service.price - discount_amount)
        if not result.ok:
            if result.kind == "insufficient":
                return web.json_response({
                    "ok": False,
                    "error": "insufficient_balance",
                    "needed": effective_price,
                    "current": result.new_balance,
                    "message": "موجودی کیف پول شما کافی نیست.",
                }, status=400)
            elif result.kind == "maintenance":
                return web.json_response({
                    "ok": False,
                    "message": "فروشگاه در حال حاضر در دست تعمیر و به‌روزرسانی است.",
                }, status=503)
            elif result.kind == "needs_account":
                return web.json_response({
                    "ok": False,
                    "error": "needs_account",
                    "message": "لطفاً حساب کاربری مورد نظر جهت تمدید را انتخاب نمایید.",
                }, status=400)

            logger.error("Purchase failed for user %s, service %s, result_kind: %s", telegram_id, service_id, result.kind)
            return web.json_response({"ok": False, "message": "خطا در ارتباط با سرور پنل جهت فعال‌سازی سرویس."}, status=500)

        if coupon_obj and result.order_id:
            try:
                await coupon_repo.record_usage(coupon_obj.id, telegram_id, result.order_id, discount_amount)
            except Exception as exc:
                logger.warning("Failed to record coupon usage in TMA purchase: %s", exc)

        bot = request.app.get("bot")
        if bot:
            try:
                from bot.handlers.shop_purchase import _maybe_reward_referrer, _notify_admin
                from bot.db.repositories.user_repo import UserRepository
                db_user = await UserRepository(session).get_by_telegram_id(telegram_id)
                if db_user:
                    await _maybe_reward_referrer(bot, session, remnawave, db_user)
                    user_full_name = user_auth.get("first_name", "")
                    if user_auth.get("last_name"):
                        user_full_name += f" {user_auth.get('last_name')}"
                    await _notify_admin(
                        bot, db_user, service, result, session,
                        coupon_code=coupon_code if coupon_obj else None,
                        discount_amount=discount_amount,
                        full_name=user_full_name or None,
                    )
            except Exception as exc:
                logger.warning("TMA purchase post-actions failed: %s", exc)

        await session.commit()
        await cache.delete(f"tma:user:{telegram_id}:dashboard")

        return web.json_response({
            "ok": True,
            "message": "سرویس با موفقیت فعال / تمدید شد!",
            "subscription_url": result.subscription_url,
            "new_balance": result.new_balance,
            "service_name": service.name,
            "traffic_gb": service.traffic_gb,
            "duration_days": service.duration_days,
            "panel_username": result.panel_username,
            "order_id": result.order_id,
            "effective_price": effective_price,
        })
