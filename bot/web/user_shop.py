from bot.web.user_common import db_session, require_user

"""TMA User Shop, Purchase, Subscriptions, Devices, and Lucky Wheel endpoints."""
import json
import logging
import re

from aiogram import Bot
from aiohttp import web

from bot.db.models import Service
from bot.db.repositories.coupon_repo import CouponRepository
from bot.services.app_settings import StoreSettings, get_store_settings
from bot.services.formatting import ltr_frag
from bot.services.gift_service import claim_gift, create_gift, get_user_gifts
from bot.services.invoice_service import get_order_invoice_data, send_invoice_to_telegram
from bot.services.loyalty import apply_loyalty_discount, get_user_loyalty
from bot.services.purchases import execute_purchase
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def _invalidate_user_caches(cache, telegram_id: int) -> None:
    if not cache or not hasattr(cache, "delete"):
        return
    for k in (
        f"tma:user:{telegram_id}:dashboard",
        f"tma:user:{telegram_id}:dashboard:default",
        f"tma:user:{telegram_id}:profile",
        f"tma:user:{telegram_id}:topup_info",
    ):
        await cache.delete(k)


async def post_user_spin(request: web.Request) -> web.Response:
    """Handle Lucky Wheel spin with anti-cheat, streak bonuses, referral tickets and prize allocation."""
    user_auth, err = require_user(request)
    if err:
        return err

    if user_auth.get("is_preview"):
        return web.json_response(
            {"ok": False, "error": "چرخش گردونه فقط در محیط رسمی تلگرام امکان‌پذیر است."},
            status=400,
        )

    telegram_id = int(user_auth["id"])
    cache: FastCache = request.app["cache"]

    # Concurrency / Race-condition guard via distributed lock
    spin_lock_key = f"lock:user:{telegram_id}:spin"
    if hasattr(cache, "set_nx"):
        lock_acquired = await cache.set_nx(spin_lock_key, "1", ttl_seconds=5)
        if not lock_acquired:
            return web.json_response(
                {"ok": False, "error": "درخواست همزمان شناسایی شد. لطفاً چند لحظه بعد تلاش کنید."},
                status=429,
            )

    try:
        return await _do_user_spin(request, telegram_id, cache)
    finally:
        if hasattr(cache, "delete"):
            await cache.delete(spin_lock_key)


async def _do_user_spin(request: web.Request, telegram_id: int, cache: FastCache) -> web.Response:
    from bot.services.wheel_service import execute_lucky_wheel_spin

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    use_ticket_req = bool(body.get("use_ticket") or request.query.get("use_ticket") in ("1", "true", "True"))

    settings = request.app.get("settings")
    tz_name = getattr(settings, "TIMEZONE", "Asia/Tehran")
    remnawave = request.app["remnawave"]
    bot = request.app.get("bot")

    async with db_session(request) as session:
        result = await execute_lucky_wheel_spin(
            session=session,
            remnawave=remnawave,
            cache=cache,
            bot=bot,
            telegram_id=telegram_id,
            use_ticket=use_ticket_req,
            tz_name=tz_name,
        )

    if not result.get("ok"):
        status_code = 403 if result.get("code") == "channel_required" else 400
        return web.json_response(result, status=status_code)

    chosen = result["prize"]
    applied = result["applied"]

    # Notify via Telegram bot if winning
    if bot and applied and chosen.get("type") not in ("blank", "again"):
        try:
            if chosen.get("type") == "coupon":
                msg_text = (
                    f"🎉 <b>تبریک! شما در گردونه شانس برنده شدید:</b>\n\n"
                    f"🎟 <b>کد تخفیف ۱۰٪ اختصاصی شما:</b> <code>{chosen.get('code')}</code>\n\n"
                    f"⏳ <b>مهلت استفاده:</b> ۷ روز\n"
                    f"💡 <i>این کد اختصاصی شماست و برای خرید از فروشگاه قابل استفاده است.</i>"
                )
            else:
                msg_text = (
                    f"🎉 <b>تبریک! شما در گردونه شانس برنده شدید:</b>\n"
                    f"✨ <b>{chosen['name']}</b>\n\n"
                    f"این جایزه با موفقیت به سرویس شما اعمال گردید."
                )
            await bot.send_message(
                telegram_id,
                msg_text,
                parse_mode="HTML",
            )
        except Exception:
            pass

    return web.json_response({
        "ok": True,
        "prize": chosen,
        "applied": applied,
        "streak": result["streak"],
        "streak_multiplier": result["streak_multiplier"],
        "spin_tickets": result["spin_tickets"],
        "used_ticket": result["used_ticket"],
    })


async def post_user_revoke_sub(request: web.Request) -> web.Response:
    """Revoke and generate a fresh subscription URL for user."""
    user_auth, err = require_user(request)
    if err:
        return err

    if user_auth.get("is_preview"):
        return web.json_response(
            {"ok": False, "error": "این عملیات فقط در محیط رسمی تلگرام امکان‌پذیر است."},
            status=400,
        )

    telegram_id = int(user_auth["id"])
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(telegram_id)
    if not panel_users:
        return web.json_response({"ok": False, "error": "سرویس فعالی یافت نشد."}, status=404)

    account_id = data.get("account_id")
    target_user = None
    if account_id:
        for u in panel_users:
            if str(u.get("id")) == str(account_id) or str(u.get("uuid")) == str(account_id):
                target_user = u
                break
    if not target_user:
        target_user = panel_users[0]
    primary_id = target_user.get("id") or target_user.get("uuid")
    user_uuid = target_user.get("uuid")
    if user_uuid:
        revoked = await remnawave.revoke_user_subscription(primary_id, user_uuid=user_uuid)
    else:
        revoked = await remnawave.revoke_user_subscription(primary_id)
    if not revoked:
        return web.json_response({"ok": False, "error": "خطا در تغییر لینک اشتراک."}, status=500)

    # Invalidate cache
    cache: FastCache = request.app["cache"]
    await _invalidate_user_caches(cache, telegram_id)

    new_sub_url = revoked.get("subscriptionUrl") or revoked.get("subscription_url") or ""
    if not new_sub_url:
        fresh_users = await remnawave.get_users_by_telegram_id(telegram_id) or []
        if fresh_users:
            new_sub_url = fresh_users[0].get("subscriptionUrl") or fresh_users[0].get("subscription_url") or ""
    return web.json_response({
        "ok": True,
        "subscription_url": new_sub_url,
    })


async def post_user_kill_device(request: web.Request) -> web.Response:
    """Disconnect a specific HWID session for the user."""
    user_auth, err = require_user(request)
    if err:
        return err

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
    await _invalidate_user_caches(cache, telegram_id)

    return web.json_response({"ok": bool(success)})


async def post_user_validate_coupon(request: web.Request) -> web.Response:
    """Validate a discount coupon code for authenticated user."""
    user_auth, err = require_user(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        body = {}

    code = (body.get("code") or "").strip()
    if not code:
        return web.json_response({"ok": False, "message": "کد تخفیف الزامی است."}, status=400)
    if not re.match(r"^[A-Za-z0-9_-]{3,32}$", code):
        return web.json_response({"ok": False, "message": "فرمت کد تخفیف نامعتبر است."}, status=400)

    telegram_id = int(user_auth["id"])
    from bot.db.repositories.coupon_repo import CouponRepository

    async with db_session(request) as session:
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
    user_auth, err = require_user(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        body = {}

    service_id = body.get("service_id")
    coupon_code = (body.get("coupon_code") or "").strip().upper() or None
    account_id = body.get("account_id")
    if coupon_code and not re.match(r"^[A-Za-z0-9_-]{3,32}$", coupon_code):
        return web.json_response({"ok": False, "message": "فرمت کد تخفیف نامعتبر است."}, status=400)

    if not service_id:
        return web.json_response({"ok": False, "message": "شناسه بسته الزامی است."}, status=400)

    telegram_id = int(user_auth["id"])
    remnawave = request.app["remnawave"]
    cache: FastCache = request.app["cache"]

    async with db_session(request) as session:
        service = await session.get(Service, int(service_id))
        if not service or not service.is_active or (service.max_purchases and (service.purchases_count or 0) >= service.max_purchases):
            return web.json_response({"ok": False, "message": "بسته مورد نظر یافت نشد، منقضی شده یا سقف فروش آن تکمیل شده است."}, status=404)

        coupon_repo = CouponRepository(session)
        discount_amount = 0
        coupon_obj = None
        if coupon_code:
            is_valid, _, disc = await coupon_repo.validate_coupon(coupon_code, telegram_id, price=service.price)
            if not is_valid:
                return web.json_response({
                    "ok": False,
                    "message": "کد تخفیف وارد شده معتبر نیست یا منقضی شده است."
                }, status=400)
            discount_amount = disc
            coupon_obj = await coupon_repo.get_by_code(coupon_code)

        chosen_acc = None
        panel_users = await remnawave.get_users_by_telegram_id(telegram_id) or []
        if account_id:
            chosen_acc = next((u for u in panel_users if str(u.get("id")) == str(account_id)), None)
            if not chosen_acc:
                return web.json_response({
                    "ok": False,
                    "message": "شناسه اکانت انتخاب‌شده نامعتبر است یا متعلق به شما نیست.",
                }, status=400)
        else:
            if len(panel_users) == 1:
                chosen_acc = panel_users[0]
            elif len(panel_users) > 1:
                return web.json_response({
                    "ok": False,
                    "error": "needs_account",
                    "message": "شما چند اکانت فعال دارید. لطفاً ابتدا اکانت مورد نظر خود را جهت خرید یا تمدید انتخاب فرمایید.",
                    "accounts": [
                        {
                            "id": u.get("id"),
                            "username": u.get("username"),
                            "status": u.get("status"),
                            "expireAt": u.get("expireAt"),
                        }
                        for u in panel_users
                    ],
                }, status=400)

        bot = request.app.get("bot")
        session_factory = request.app.get("session_factory")

        loyalty_info = await get_user_loyalty(session, telegram_id, cache=cache)
        loyalty_disc_pct = loyalty_info.get("discount_percent", 0)
        loyalty_disc_amount, _ = apply_loyalty_discount(service.price, loyalty_disc_pct)
        total_discount = min(service.price, discount_amount + loyalty_disc_amount)

        result = await execute_purchase(
            remnawave=remnawave,
            session=session,
            service=service,
            telegram_id=telegram_id,
            chosen_account=chosen_acc,
            discount_amount=total_discount,
            coupon_code=coupon_code,
            bot=bot,
            session_factory=session_factory,
            cache=cache,
        )

        effective_price = max(0, service.price - total_discount)
        if not result.ok:
            await session.rollback()
            if result.kind == "insufficient":
                return web.json_response({
                    "ok": False,
                    "error": "insufficient_balance",
                    "needed": effective_price,
                    "current": result.new_balance,
                    "message": "موجودی کیف پول شما کافی نیست.",
                }, status=400)
            elif result.kind == "coupon_exhausted":
                return web.json_response({
                    "ok": False,
                    "error": "coupon_exhausted",
                    "message": "کد تخفیف به حداکثر سقف مجاز استفاده رسیده است یا قبلاً استفاده شده است.",
                }, status=400)
            elif result.kind == "conflict":
                return web.json_response({
                    "ok": False,
                    "error": "conflict",
                    "message": "یک عملیات خرید برای این حساب در حال انجام است. لطفاً چند لحظه صبر کنید.",
                }, status=409)
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
            elif result.kind == "needs_active_sub":
                return web.json_response({
                    "ok": False,
                    "error": "needs_active_sub",
                    "message": "برای خرید بسته افزایش حجم یا افزایش زمان، داشتن یک اشتراک فعال الزامی است.",
                }, status=400)
            elif result.kind == "squad_mismatch":
                return web.json_response({
                    "ok": False,
                    "error": "squad_mismatch",
                    "message": "این بسته افزایشی با نوع سرویس و سرورهای فعال شما سازگار نیست.",
                }, status=400)

            logger.error("Purchase failed for user %s, service %s, result_kind: %s", telegram_id, service_id, result.kind)
            if bot and session_factory:
                try:
                    from bot.services.error_reporter import report_error
                    await report_error(
                        bot,
                        session_factory,
                        f"purchase_failed:{result.kind}",
                        context=f"Purchase u={telegram_id} svc={service.id} price={effective_price}",
                        user_id=telegram_id,
                    )
                except Exception:
                    pass
            return web.json_response({"ok": False, "message": "خطا در ارتباط با سرور پنل جهت فعال‌سازی سرویس."}, status=500)

        await session.commit()

        bot = request.app.get("bot")
        if bot:
            try:
                from bot.db.repositories.user_repo import UserRepository
                from bot.services.purchases import maybe_reward_referrer as _maybe_reward_referrer
                from bot.services.purchases import notify_admin as _notify_admin
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
                        loyalty_discount_amount=loyalty_disc_amount,
                        full_name=user_full_name or None,
                    )
            except Exception as exc:
                logger.warning("TMA purchase post-actions failed: %s", exc)

        await _invalidate_user_caches(cache, telegram_id)

        return web.json_response({
            "ok": True,
            "message": "سرویس با موفقیت به دسته جدید ارتقا یافت!" if getattr(result, "squad_changed", False) else "سرویس با موفقیت فعال / تمدید شد!",
            "subscription_url": result.subscription_url,
            "new_balance": result.new_balance,
            "service_name": service.name,
            "traffic_gb": service.traffic_gb,
            "duration_days": service.duration_days,
            "panel_username": result.panel_username,
            "order_id": result.order_id,
            "effective_price": effective_price,
            "squad_changed": getattr(result, "squad_changed", False),
        })


async def post_user_create_gift(request: web.Request) -> web.Response:
    """Create a gift card / voucher (Balance or Service) with atomic balance deduction."""
    user_auth, err = require_user(request)
    if err:
        return err

    telegram_id = int(user_auth["id"])
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "message": "فرمت داده نامعتبر است."}, status=400)
    delivery_type = data.get("delivery_type", "LINK")
    gift_type = data.get("gift_type", "BALANCE")
    try:
        amount = int(data.get("amount", 0) or 0)
        service_id = int(data.get("service_id")) if data.get("service_id") else None
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "message": "مقادیر عددی نامعتبر هستند."}, status=400)
    receiver_target = data.get("receiver_target") or data.get("receiver")
    message = data.get("message")
    bot = request.app.get("bot")
    bot_username = getattr(getattr(bot, "_me", None), "username", "") if bot else ""
    cache = request.app.get("cache")

    async with db_session(request) as session:
        sender_full_name = user_auth.get("first_name", "")
        if user_auth.get("last_name"):
            sender_full_name += f" {user_auth.get('last_name')}"
        sender_full_name = sender_full_name.strip() or user_auth.get("username") or "کاربر"

        res = await create_gift(
            session=session,
            sender_telegram_id=telegram_id,
            sender_name=sender_full_name,
            delivery_type=delivery_type,
            gift_type=gift_type,
            amount=amount,
            service_id=service_id,
            receiver_target=receiver_target,
            message=message,
            bot=bot,
            bot_username=bot_username,
            cache=cache,
        )
        if not res.get("ok"):
            return web.json_response(res, status=400)
        if cache:
            await _invalidate_user_caches(cache, telegram_id)
        return web.json_response(res)


async def post_user_claim_gift(request: web.Request) -> web.Response:
    """Claim a gift card by code in TMA."""
    user_auth, err = require_user(request)
    if err:
        return err

    telegram_id = int(user_auth["id"])
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "message": "فرمت داده نامعتبر است."}, status=400)
    code = (data.get("code") or "").strip()
    if not code:
        return web.json_response({"ok": False, "message": "کد هدیه الزامی است."}, status=400)

    bot = request.app.get("bot")
    remnawave = request.app.get("remnawave")
    session_factory = request.app.get("session_factory")
    cache = request.app.get("cache")

    async with db_session(request) as session:
        res = await claim_gift(
            session=session,
            code=code,
            claimer_telegram_id=telegram_id,
            claimer_username=user_auth.get("username"),
            remnawave=remnawave,
            bot=bot,
            session_factory=session_factory,
        )
        if not res.get("ok"):
            return web.json_response(res, status=400)
        if cache:
            await _invalidate_user_caches(cache, telegram_id)
        return web.json_response(res)


async def get_user_gifts_history(request: web.Request) -> web.Response:
    """Return sent and received gift cards history for user."""
    user_auth, err = require_user(request)
    if err:
        return err

    telegram_id = int(user_auth["id"])
    bot = request.app.get("bot")
    bot_username = getattr(getattr(bot, "_me", None), "username", "") if bot else ""
    async with db_session(request) as session:
        gifts = await get_user_gifts(session, telegram_id, bot_username=bot_username)
        return web.json_response({"ok": True, "gifts": gifts})


def compute_custom_plan_price(
    traffic_gb: int,
    duration_days: int,
    store_settings: StoreSettings,
    hwid_limit: int = 1,
) -> tuple[int, int, int]:
    """Calculate (raw_base_price, volume_discount_percent, discounted_base_price).

    Implements tiered volume pricing (مدل پلکانی):
    - Higher traffic = lower rate per GB.
    - Default tiers: 1-50 GB: 0%, 51-100 GB: 10%, 101-200 GB: 20%, >200 GB: 30%.
    - Can be customized via store_settings.custom_plan_volume_tiers_json.
    - Concurrent users (hwid_limit) scales base price dynamically (+15% per extra user beyond 1).
    """
    raw_traffic_price = traffic_gb * store_settings.custom_plan_price_per_gb
    time_price = duration_days * store_settings.custom_plan_price_per_day
    base_fee = store_settings.custom_plan_base_price

    volume_pct = 0
    tiers_json = getattr(store_settings, "custom_plan_volume_tiers_json", "")
    if tiers_json:
        try:
            tiers = json.loads(tiers_json)
            if isinstance(tiers, list):
                for t in tiers:
                    min_g = int(t.get("min_gb", 0))
                    max_g = int(t.get("max_gb", 999999))
                    pct = int(t.get("discount_percent", 0))
                    if min_g <= traffic_gb <= max_g:
                        volume_pct = max(0, min(100, pct))
                        break
        except Exception:
            pass

    # Default slabs if not customized in settings:
    # 1-50 GB: 0%, 51-100 GB: 10%, 101-200 GB: 20%, > 200 GB: 30%
    if volume_pct == 0 and not tiers_json:
        if 51 <= traffic_gb <= 100:
            volume_pct = 10
        elif 101 <= traffic_gb <= 200:
            volume_pct = 20
        elif traffic_gb > 200:
            volume_pct = 30

    discounted_traffic_price = int(raw_traffic_price * (100 - volume_pct) / 100)
    extra_device_rate = getattr(store_settings, "custom_plan_extra_device_percent", 15) or 15
    extra_user_pct = max(0, hwid_limit - 1) * extra_device_rate
    raw_subtotal = raw_traffic_price + time_price + base_fee
    discounted_subtotal = discounted_traffic_price + time_price + base_fee
    hwid_cost = int(discounted_subtotal * extra_user_pct / 100)
    raw_base = raw_subtotal + int(raw_subtotal * extra_user_pct / 100)
    discounted_base = discounted_subtotal + hwid_cost
    return (raw_base, volume_pct, discounted_base)


async def post_user_custom_plan_calculate(request: web.Request) -> web.Response:
    """Calculate price, volume tier discount, and loyalty discount for custom plan on slider change."""
    user_auth, err = require_user(request)
    if err:
        return err

    telegram_id = int(user_auth["id"])
    try:
        data = await request.json()
    except Exception:
        data = {}
    traffic_gb = max(1, int(data.get("traffic_gb", 10) or 10))
    duration_days = max(1, int(data.get("duration_days", 30) or 30))
    hwid_limit = max(1, min(10, int(data.get("hwid_limit", 2) or 2)))
    cache = request.app.get("cache")

    async with db_session(request) as session:
        store_settings = await get_store_settings(session)
        is_configured = not (
            store_settings.custom_plan_price_per_gb <= 0
            and store_settings.custom_plan_price_per_day <= 0
            and store_settings.custom_plan_base_price <= 0
        )
        raw_base, volume_pct, base_price = compute_custom_plan_price(traffic_gb, duration_days, store_settings, hwid_limit=hwid_limit)
        extra_device_rate = getattr(store_settings, "custom_plan_extra_device_percent", 15) or 15
        extra_user_pct = max(0, hwid_limit - 1) * extra_device_rate
        raw_traffic_price = traffic_gb * store_settings.custom_plan_price_per_gb
        time_price = duration_days * store_settings.custom_plan_price_per_day
        base_fee = store_settings.custom_plan_base_price
        discounted_traffic_price = int(raw_traffic_price * (100 - volume_pct) / 100)
        discounted_subtotal = discounted_traffic_price + time_price + base_fee
        hwid_cost = int(discounted_subtotal * extra_user_pct / 100)
        volume_discount_amount = max(0, raw_traffic_price - discounted_traffic_price)

        loyalty = await get_user_loyalty(session, telegram_id, cache=cache)
        loyalty_pct = loyalty.get("discount_percent", 0)
        disc_amt, final_price = apply_loyalty_discount(base_price, loyalty_pct)

        return web.json_response({
            "ok": True,
            "traffic_gb": traffic_gb,
            "duration_days": duration_days,
            "hwid_limit": hwid_limit,
            "extra_device_percent": extra_device_rate,
            "hwid_cost": hwid_cost,
            "raw_base_price": raw_base,
            "base_subtotal": discounted_subtotal,
            "base_price": base_price,
            "volume_discount_percent": volume_pct,
            "volume_discount_amount": volume_discount_amount,
            "loyalty_discount_percent": loyalty_pct,
            "loyalty_discount_amount": disc_amt,
            "final_price": final_price,
            "is_configured": is_configured,
            "enabled": store_settings.custom_plan_enabled,
        })


async def post_user_custom_plan_purchase(request: web.Request) -> web.Response:
    """Purchase and activate a custom built plan with wallet balance."""
    user_auth, err = require_user(request)
    if err:
        return err

    telegram_id = int(user_auth["id"])
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        traffic_gb = int(data.get("traffic_gb", 0) or 0)
        duration_days = int(data.get("duration_days", 0) or 0)
        hwid_limit = max(1, min(10, int(data.get("hwid_limit", 2) or 2)))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "message": "مقادیر حجم و روز نامعتبر است."}, status=400)
    account_id = data.get("account_id")
    remnawave = request.app["remnawave"]
    cache = request.app.get("cache")

    async with db_session(request) as session:
        store_settings = await get_store_settings(session)
        if not store_settings.custom_plan_enabled:
            return web.json_response({"ok": False, "message": "طراحی بسته اختصاصی در حال حاضر غیرفعال است."}, status=400)

        if traffic_gb < store_settings.custom_plan_min_gb or traffic_gb > store_settings.custom_plan_max_gb:
            return web.json_response({
                "ok": False,
                "message": f"حجم انتخابی باید بین {store_settings.custom_plan_min_gb} تا {store_settings.custom_plan_max_gb} گیگابایت باشد."
            }, status=400)

        if duration_days < store_settings.custom_plan_min_days or duration_days > store_settings.custom_plan_max_days:
            return web.json_response({
                "ok": False,
                "message": f"مدت زمان انتخابی باید بین {store_settings.custom_plan_min_days} تا {store_settings.custom_plan_max_days} روز باشد."
            }, status=400)

        if (
            store_settings.custom_plan_price_per_gb <= 0
            and store_settings.custom_plan_price_per_day <= 0
            and store_settings.custom_plan_base_price <= 0
        ):
            return web.json_response({
                "ok": False,
                "message": "تعرفه بسته دلخواه هنوز توسط مدیریت تنظیم نشده است."
            }, status=400)

        raw_base, volume_pct, base_price = compute_custom_plan_price(traffic_gb, duration_days, store_settings, hwid_limit=hwid_limit)
        if base_price <= 0:
            return web.json_response({
                "ok": False,
                "message": "تعرفه محاسبه شده نامعتبر است."
            }, status=400)

        loyalty = await get_user_loyalty(session, telegram_id, cache=cache)
        loyalty_pct = loyalty.get("discount_percent", 0)
        disc_amt, final_price = apply_loyalty_discount(base_price, loyalty_pct)

        chosen_acc = None
        panel_users = await remnawave.get_users_by_telegram_id(telegram_id) or []
        if account_id:
            chosen_acc = next((u for u in panel_users if str(u.get("id")) == str(account_id)), None)
            if not chosen_acc:
                return web.json_response({"ok": False, "message": "اشتراک انتخابی جهت تمدید یافت نشد."}, status=400)
        else:
            if len(panel_users) == 1:
                chosen_acc = panel_users[0]
            elif len(panel_users) > 1:
                return web.json_response({
                    "ok": False,
                    "error": "needs_account",
                    "message": "شما چند اکانت فعال دارید. لطفاً ابتدا اکانت مورد نظر خود را انتخاب فرمایید.",
                    "accounts": [
                        {
                            "id": u.get("id"),
                            "username": u.get("username"),
                            "status": u.get("status"),
                            "expireAt": u.get("expireAt"),
                        }
                        for u in panel_users
                    ],
                }, status=400)

        from types import SimpleNamespace

        # Derive squad from payload if provided, else existing user account or fallback to default squad
        target_squad = data.get("squad_uuid")
        if target_squad:
            # Validate target squad exists in Remnawave squads to prevent arbitrary squad assignment
            try:
                available_squads = await remnawave.get_internal_squads() or []
                squad_uuids = {str(sq.get("uuid") or sq.get("id")) for sq in available_squads if isinstance(sq, dict)}
                if squad_uuids and str(target_squad) not in squad_uuids:
                    target_squad = store_settings.default_squad_uuid or None
            except Exception:
                pass
        elif chosen_acc and isinstance(chosen_acc, dict):
            raw_sqs = (
                chosen_acc.get("activeInternalSquads")
                or chosen_acc.get("internalSquads")
                or chosen_acc.get("squads")
                or []
            )
            for sq in raw_sqs:
                if isinstance(sq, dict):
                    u = sq.get("uuid") or sq.get("id")
                    if u:
                        target_squad = str(u)
                        break
                elif sq:
                    target_squad = str(sq)
                    break
        if not target_squad:
            target_squad = store_settings.default_squad_uuid or None

        custom_svc = SimpleNamespace(
            id=None,
            name="بسته دلخواه",
            price=base_price,
            duration_days=duration_days,
            traffic_gb=traffic_gb,
            hwid_limit=hwid_limit,
            squad_uuid=target_squad,
            badge="custom",
            traffic_strategy="NO_RESET",
            max_purchases=None,
            purchases_count=0,
        )

        bot = request.app.get("bot")
        session_factory = request.app.get("session_factory")

        try:
            result = await execute_purchase(
                remnawave=remnawave,
                session=session,
                service=custom_svc,
                telegram_id=telegram_id,
                chosen_account=chosen_acc,
                discount_amount=disc_amt,
                bot=bot,
                session_factory=session_factory,
                cache=cache,
            )
        except Exception as exc:
            err_str = str(exc)
            if "service_id" in err_str and ("not-null" in err_str.lower() or "not null" in err_str.lower()):
                logger.warning("Detected legacy NOT NULL on orders.service_id, executing inline self-healing migration...")
                try:
                    from sqlalchemy import text
                    await session.rollback()
                    await session.execute(text("ALTER TABLE orders ALTER COLUMN service_id DROP NOT NULL;"))
                    await session.commit()
                    result = await execute_purchase(
                        remnawave=remnawave,
                        session=session,
                        service=custom_svc,
                        telegram_id=telegram_id,
                        chosen_account=chosen_acc,
                        discount_amount=disc_amt,
                        bot=bot,
                        session_factory=session_factory,
                        cache=cache,
                    )
                except Exception as retry_exc:
                    logger.exception("Retry after schema migration failed: %s", retry_exc)
                    raise retry_exc
            else:
                raise exc

        if not result.ok:
            await session.rollback()
            if result.kind == "insufficient":
                return web.json_response({
                    "ok": False,
                    "error": "insufficient_balance",
                    "needed": final_price,
                    "current": result.new_balance,
                    "message": "موجودی کیف پول شما کافی نیست.",
                }, status=400)
            if result.kind == "needs_account":
                return web.json_response({
                    "ok": False,
                    "error": "needs_account",
                    "message": "شما چند اکانت فعال دارید. لطفاً ابتدا اکانت مورد نظر خود را انتخاب فرمایید.",
                    "accounts": [
                        {
                            "id": u.get("id"),
                            "username": u.get("username"),
                            "status": u.get("status"),
                            "expireAt": u.get("expireAt"),
                        }
                        for u in (panel_users or [])
                    ],
                }, status=400)
            if result.kind in ("failed", "error") or not result.message:
                bot = request.app.get("bot")
                if bot:
                    try:
                        from bot.services.error_reporter import report_error
                        await report_error(
                            bot,
                            session_factory=session_factory,
                            session=session,
                            exc=f"custom_plan_purchase_failed: {result.kind or 'unknown'}",
                            context=f"Custom Plan Purchase (u={telegram_id}, gb={traffic_gb}, days={duration_days})",
                            user_id=telegram_id,
                        )
                    except Exception as rep_err:
                        logger.warning("Failed to report custom plan purchase error: %s", rep_err)
            err_msg = result.message or "خطا در خرید بسته اختصاصی."
            return web.json_response({"ok": False, "message": err_msg}, status=400)

        await session.commit()

        bot = request.app.get("bot")
        if bot:
            try:
                from bot.db.repositories.user_repo import UserRepository
                from bot.services.purchases import maybe_reward_referrer as _maybe_reward_referrer
                from bot.services.purchases import notify_admin as _notify_admin
                db_user = await UserRepository(session).get_by_telegram_id(telegram_id)
                if db_user:
                    await _maybe_reward_referrer(bot, session, remnawave, db_user)
                    user_full_name = user_auth.get("first_name", "")
                    if user_auth.get("last_name"):
                        user_full_name += f" {user_auth.get('last_name')}"
                    await _notify_admin(
                        bot, db_user, custom_svc, result, session,
                        discount_amount=disc_amt,
                        loyalty_discount_amount=disc_amt,
                        full_name=user_full_name or None,
                    )
            except Exception as exc:
                logger.warning("TMA custom plan purchase post-actions failed: %s", exc)

        if cache:
            await _invalidate_user_caches(cache, telegram_id)

        return web.json_response({
            "ok": True,
            "message": "بسته دلخواه شما با موفقیت فعال شد!",
            "subscription_url": result.subscription_url,
            "new_balance": result.new_balance,
            "service_name": custom_svc.name,
            "traffic_gb": traffic_gb,
            "duration_days": duration_days,
            "final_price": final_price,
            "effective_price": final_price,
            "panel_username": getattr(result, "panel_username", None),
            "order_id": result.order_id,
            "squad_changed": getattr(result, "squad_changed", False),
        })


async def get_user_invoice(request: web.Request) -> web.Response:
    """Fetch digital invoice for a specific order owned by user."""
    user_auth, err = require_user(request)
    if err:
        return err

    order_id_str = request.match_info.get("order_id", "")
    if not order_id_str.isdigit():
        return web.json_response({"ok": False, "message": "شناسه سفارش نامعتبر است."}, status=400)

    order_id = int(order_id_str)
    telegram_id = int(user_auth["id"])

    cache = request.app.get("cache")
    cache_key = f"inv:ord:{telegram_id}:{order_id}"
    if cache and hasattr(cache, "get"):
        cached_inv = await cache.get(cache_key)
        if cached_inv:
            return web.json_response({"ok": True, "data": cached_inv})

    async with db_session(request) as session:
        store_settings = await get_store_settings(session)
        store_name = getattr(store_settings, "invoice_company_name", "") or getattr(store_settings, "bot_name", "سرویس ابری رمنا") or "سرویس ابری رمنا"
        support_contact = getattr(store_settings, "support_contact", "") or ""
        store_logo_url = getattr(store_settings, "store_logo_url", "") or ""

        inv_data = await get_order_invoice_data(
            session=session,
            order_id=order_id,
            telegram_id=telegram_id,
            store_name=store_name,
            support_contact=support_contact,
            store_logo_url=store_logo_url,
        )
        if not inv_data:
            return web.json_response({"ok": False, "message": "فاکتور مورد نظر یافت نشد."}, status=404)

        if cache and hasattr(cache, "set"):
            await cache.set(cache_key, inv_data, ttl_seconds=600)

        return web.json_response({"ok": True, "data": inv_data})


async def post_user_send_invoice_telegram(request: web.Request) -> web.Response:
    """Send official receipt and digital invoice directly to user's Telegram chat."""
    user_auth, err = require_user(request)
    if err:
        return err

    order_id_str = request.match_info.get("order_id", "")
    if not order_id_str.isdigit():
        return web.json_response({"ok": False, "message": "شناسه سفارش نامعتبر است."}, status=400)

    order_id = int(order_id_str)
    telegram_id = int(user_auth["id"])

    bot: Bot | None = request.app.get("bot")
    if not bot:
        return web.json_response({"ok": False, "message": "ربات در دسترس نیست."}, status=503)

    async with db_session(request) as session:
        store_settings = await get_store_settings(session)
        store_name = getattr(store_settings, "invoice_company_name", "") or getattr(store_settings, "bot_name", "سرویس ابری رمنا") or "سرویس ابری رمنا"
        support_contact = getattr(store_settings, "support_contact", "") or ""
        store_logo_url = getattr(store_settings, "store_logo_url", "") or ""

        inv_data = await get_order_invoice_data(
            session=session,
            order_id=order_id,
            telegram_id=telegram_id,
            store_name=store_name,
            support_contact=support_contact,
            store_logo_url=store_logo_url,
        )
        if not inv_data:
            return web.json_response({"ok": False, "message": "فاکتور یافت نشد."}, status=404)

        sent = await send_invoice_to_telegram(
            bot=bot,
            telegram_id=telegram_id,
            invoice=inv_data,
        )
        if not sent:
            return web.json_response({"ok": False, "message": "خطا در ارسال پیام به تلگرام شما."}, status=500)

        return web.json_response({
            "ok": True,
            "message": "فاکتور رسمی با موفقیت به پیوی تلگرام شما ارسال شد!",
        })


