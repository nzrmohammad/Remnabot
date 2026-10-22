from bot.web.user_common import db_session, require_user

"""TMA User Shop, Purchase, Subscriptions, Devices, and Lucky Wheel endpoints."""
import logging
import random
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiohttp import web
from sqlalchemy import select

from bot.db.models import Service, User
from bot.db.repositories.coupon_repo import CouponRepository
from bot.services.app_settings import get_store_settings
from bot.services.formatting import ltr_frag
from bot.services.purchases import execute_purchase
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


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

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    use_ticket_req = bool(body.get("use_ticket") or request.query.get("use_ticket") in ("1", "true", "True"))

    wheel_ts_key = f"tma:user:{telegram_id}:wheel_last_spin"
    now_ts = time.time()
    last_spin = await cache.get(wheel_ts_key)
    is_cooldown = False
    rem_secs = 0
    if last_spin is not None:
        try:
            elapsed = now_ts - float(last_spin)
            if elapsed < 86400:
                is_cooldown = True
                rem_secs = max(1, int(86400 - elapsed))
        except (ValueError, TypeError):
            pass

    async with db_session(request) as session:
        # Check mandatory channel join gate if enabled
        if session is not None:
            store = await get_store_settings(session)
            if getattr(store, "join_gate_enabled", False) and getattr(store, "join_gate_channel", ""):
                bot = request.app.get("bot")
                from bot.common.helpers import check_channel_membership
                is_member = await check_channel_membership(bot, store.join_gate_channel, telegram_id)
                if not is_member:
                    channel_str = store.join_gate_channel.strip()
                    channel_link = channel_str if channel_str.startswith("http") else f"https://t.me/{channel_str.lstrip('@')}"
                    return web.json_response(
                        {
                            "ok": False,
                            "error": "برای چرخاندن گردونه شانس، ابتدا باید در کانال ما عضو شوید.",
                            "code": "channel_required",
                            "channel_url": channel_link,
                        },
                        status=403,
                    )

            # Atomic row lock to prevent double-spending tickets or streaks
            user_res = await session.execute(
                select(User).where(User.telegram_id == telegram_id).with_for_update()
            )
            db_user = user_res.scalar_one_or_none()
        else:
            db_user = None

        using_ticket = False
        if use_ticket_req:
            # Check tickets inventory
            cur_tickets = int(getattr(db_user, "spin_tickets", 0) or 0) if db_user else 0
            if cur_tickets > 0:
                using_ticket = True
                if db_user:
                    db_user.spin_tickets = cur_tickets - 1
            else:
                return web.json_response(
                    {
                        "ok": False,
                        "error": "شما تیکت شانس کافی ندارید.",
                        "code": "no_tickets",
                    },
                    status=400,
                )
        elif is_cooldown:
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

        # Calculate daily streak
        settings = request.app.get("settings")
        tz_name = getattr(settings, "TIMEZONE", "Asia/Tehran")
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(ZoneInfo(tz_name))
        today_date = now_local.date()

        last_spin_at = getattr(db_user, "wheel_last_spin_at", None) if db_user else None
        cur_streak = int(getattr(db_user, "wheel_streak", 0) or 0) if db_user else 0

        if not using_ticket:
            if not last_spin_at:
                new_streak = 1
            else:
                last_local = last_spin_at.astimezone(ZoneInfo(tz_name))
                days_diff = (today_date - last_local.date()).days
                if days_diff == 1:
                    new_streak = min(cur_streak + 1, 7)
                elif days_diff == 0:
                    new_streak = max(1, cur_streak)
                elif days_diff == 2 and (now_local - last_local).total_seconds() <= 36 * 3600:
                    # 36-hour grace window
                    new_streak = min(cur_streak + 1, 7)
                else:
                    new_streak = 1

            if db_user:
                db_user.wheel_streak = new_streak
                db_user.wheel_last_spin_at = now_utc
        else:
            # Using a referral ticket preserves existing streak without advancing or breaking it
            new_streak = max(1, cur_streak)

        streak_multiplier = 1.5 if new_streak >= 3 else (1.2 if new_streak == 2 else 1.0)

        # 6 configured prizes (Slice 1 is blank, Slice 4 is 2GB ultra-rare jackpot)
        prizes = [
            {"id": "1gb", "name": f"{ltr_frag('1 GB')} ترافیک هدیه", "icon": "🎁", "type": "traffic", "value": 1},
            {"id": "blank_1", "name": "پوچ (شانس بعدی فردا)", "icon": "❌", "type": "blank", "value": 0},
            {"id": "discount10", "name": "۱۰٪ کد تخفیف ویژه (کد: OFF10)", "icon": "🎟", "type": "coupon", "code": "OFF10"},
            {"id": "500mb", "name": f"{ltr_frag('500 MB')} ترافیک هدیه", "icon": "⚡️", "type": "traffic", "value": 0.5},
            {"id": "2gb", "name": f"{ltr_frag('2 GB')} ترافیک هدیه (سوپر شانس)", "icon": "👑", "type": "traffic", "value": 2},
            {"id": "again", "name": "دوباره (شانس مجدد!)", "icon": "🔄", "type": "again", "value": 0},
        ]

        # Dynamic anti-cheat weight balance (protect admin margins while rewarding streaks)
        w_1gb = max(8, int(10 * streak_multiplier))
        w_500mb = max(12, int(15 * streak_multiplier))
        w_disc = max(12, int(15 * streak_multiplier))
        w_again = 10
        w_blank1 = max(25, int(45 / streak_multiplier))
        w_2gb = max(1, int(1.2 * streak_multiplier))  # Ultra-rare jackpot (~1-1.5% probability)
        weights = [w_1gb, w_blank1, w_disc, w_500mb, w_2gb, w_again]
        chosen = random.choices(prizes, weights=weights, k=1)[0]

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
                    if current_limit > 0:
                        traffic_bytes = int(chosen["value"] * 1024 * 1024 * 1024)
                        new_limit = current_limit + traffic_bytes
                        up_res = await remnawave.update_user_subscription(
                            primary_id,
                            current_expire,
                            new_limit,
                        )
                        if up_res is not None:
                            applied = True
                elif chosen["type"] == "days":
                    from bot.services.formatting import parse_iso
                    cur_dt = parse_iso(current_expire)
                    base = cur_dt if cur_dt and cur_dt > now_utc else now_utc
                    new_expire_dt = base + timedelta(days=int(chosen["value"]))
                    new_expire_iso = new_expire_dt.isoformat()
                    up_res = await remnawave.update_user_subscription(
                        primary_id,
                        new_expire_iso,
                        current_limit,
                    )
                    if up_res is not None:
                        applied = True
            except Exception as exc:
                logger.warning("Failed to auto-apply wheel prize to panel: %s", exc)

        if chosen["type"] == "coupon":
            if session is not None:
                try:
                    coupon_repo = CouponRepository(session)
                    import secrets
                    unique_code = f"WHEEL10_{secrets.token_hex(2).upper()}"
                    expire_time = now_utc + timedelta(days=7)
                    await coupon_repo.create(
                        code=unique_code,
                        discount_percent=10,
                        max_uses=1,
                        expires_at=expire_time,
                    )
                    chosen["code"] = unique_code
                    chosen["name"] = f"کد تخفیف ۱۰٪ (مهلت ۷ روز): {unique_code}"

                    user_coupons = await cache.get(f"wheel:user_coupons:{telegram_id}") or []
                    user_coupons.insert(0, {
                        "code": unique_code,
                        "discount_percent": 10,
                        "expires_at": expire_time.isoformat(),
                    })
                    await cache.set(f"wheel:user_coupons:{telegram_id}", user_coupons[:10], ttl_seconds=86400 * 8)
                    applied = True
                except Exception as exc:
                    logger.warning("Failed to prepare coupon for wheel prize: %s", exc)

        # Record spin in DB report
        if chosen["type"] != "again":
            if not using_ticket:
                await cache.set(wheel_ts_key, now_ts, ttl_seconds=86400)
            if session is not None:
                try:
                    from bot.db.repositories.report_repo import ReportRepository
                    rep_repo = ReportRepository(session)
                    await rep_repo.record_wheel_spin(telegram_id)
                except Exception as exc:
                    logger.warning("Failed to record wheel spin in DB for %s: %s", telegram_id, exc)

        if session is not None:
            await session.commit()

        remaining_tickets = int(getattr(db_user, "spin_tickets", 0) or 0) if db_user else 0

    # Invalidate dashboard caches
    await cache.delete(f"tma:user:{telegram_id}:dashboard")
    await cache.delete(f"tma:user:{telegram_id}:profile")

    # Notify via Telegram bot if winning
    bot = request.app.get("bot")
    if bot and applied and chosen["type"] not in ("blank", "again"):
        try:
            if chosen["type"] == "coupon":
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
        "streak": new_streak,
        "streak_multiplier": streak_multiplier,
        "spin_tickets": remaining_tickets,
        "used_ticket": using_ticket,
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
    await cache.delete(f"tma:user:{telegram_id}:dashboard")

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
        if not service or not service.is_active:
            return web.json_response({"ok": False, "message": "بسته مورد نظر یافت نشد یا غیرفعال است."}, status=404)

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

        result = await execute_purchase(
            remnawave=remnawave,
            session=session,
            service=service,
            telegram_id=telegram_id,
            chosen_account=chosen_acc,
            discount_amount=discount_amount,
            coupon_code=coupon_code,
            bot=bot,
            session_factory=session_factory,
            cache=cache,
        )

        effective_price = max(0, service.price - discount_amount)
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
                        full_name=user_full_name or None,
                    )
            except Exception as exc:
                logger.warning("TMA purchase post-actions failed: %s", exc)

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
