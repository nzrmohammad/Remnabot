"""User API endpoints for Telegram Mini App."""
import json
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any

from aiohttp import web
from sqlalchemy import func, select

from bot.db.models import Order, User, Wallet
from bot.db.repositories.user_repo import UserRepository
from bot.web.auth import get_authenticated_user
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def get_user_me(request: web.Request) -> web.Response:
    """Return dashboard data for the authenticated user.

    Cached for 10 seconds for ultra-low latency.
    """
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    telegram_id = int(user_auth["id"])
    cache: FastCache = request.app["cache"]
    cache_key = f"tma:user:{telegram_id}:dashboard"

    cached_data = await cache.get(cache_key)
    if cached_data:
        return web.json_response({"ok": True, "data": cached_data, "cached": True})

    session_factory = request.app["session_factory"]
    remnawave = request.app["remnawave"]
    settings = request.app["settings"]

    async with session_factory() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_or_create(telegram_id, user_auth.get("username"))

        # 1. Wallet balance
        wallet_res = await session.execute(
            select(Wallet).where(Wallet.telegram_id == telegram_id)
        )
        wallet = wallet_res.scalar_one_or_none()
        wallet_balance = wallet.balance if wallet else 0

        # 2. Referrals count
        ref_count_res = await session.execute(
            select(func.count(User.id)).where(User.referred_by_id == telegram_id)
        )
        referrals_count = int(ref_count_res.scalar_one() or 0)

        # 3. Real plans / services defined by admin
        from bot.db.models import Service
        services_res = await session.execute(
            select(Service).where(Service.is_active.is_(True)).order_by(Service.price.asc())
        )
        services = services_res.scalars().all()
        plans_data = [
            {
                "id": s.id,
                "name": s.name,
                "price": s.price,
                "duration_days": s.duration_days,
                "traffic_gb": s.traffic_gb,
                "description": s.description,
            }
            for s in services
        ]

        # 4. Real Jalali dates
        import jdatetime
        from datetime import timedelta
        from zoneinfo import ZoneInfo
        from bot.services.formatting import now_tz, parse_iso, start_of_today

        tz_name = getattr(settings, "TIMEZONE", "Asia/Tehran")
        now_dt = now_tz(tz_name)
        now_j = jdatetime.datetime.fromgregorian(datetime=now_dt)
        today_jalali_str = f"{now_j.year}/{now_j.month:02d}/{now_j.day:02d}"
        yesterday_dt = now_dt - timedelta(days=1)
        yesterday_j = jdatetime.datetime.fromgregorian(datetime=yesterday_dt)
        yesterday_jalali_str = f"{yesterday_j.year}/{yesterday_j.month:02d}/{yesterday_j.day:02d}"

        # 5. Active Remnawave account stats
        panel_users = []
        try:
            panel_users = await remnawave.get_users_by_telegram_id(telegram_id) or []
        except Exception as exc:
            logger.warning("Failed to get panel users for telegram_id=%s: %s", telegram_id, exc)

        active_sub = None
        has_active_sub = False
        panel_user_id = None

        if panel_users:
            primary = panel_users[0]
            panel_user_id = primary.get("id")
            has_active_sub = primary.get("status", "").upper() == "ACTIVE"

            limit_bytes = int(primary.get("trafficLimitBytes") or 0)
            traffic = primary.get("userTraffic") or {}
            used_bytes = int(
                traffic.get("usedTrafficBytes") or primary.get("usedTrafficBytes") or 0
            )

            traffic_total_gb = round(limit_bytes / (1024**3), 2)
            traffic_used_gb = round(used_bytes / (1024**3), 2)
            if limit_bytes > 0:
                traffic_remaining_gb = max(0.0, round(traffic_total_gb - traffic_used_gb, 2))
                percent_remaining = round(
                    max(0.0, min(100.0, (traffic_remaining_gb / traffic_total_gb) * 100)), 1
                )
            else:
                traffic_remaining_gb = 9999.0
                percent_remaining = 100.0

            # Today's usage & country breakdown
            today_bytes = 0
            today_nodes = []
            try:
                start_today_dt = start_of_today(tz_name)
                today_tuple = await remnawave.get_user_today_usage(
                    int(panel_user_id), start_today_dt.isoformat(), now_dt.isoformat()
                )
                if today_tuple and isinstance(today_tuple, tuple):
                    today_bytes = today_tuple[0]
                    today_nodes = today_tuple[1]
            except Exception as exc:
                logger.warning("Failed to fetch today usage for %s: %s", panel_user_id, exc)
            today_used_gb = round(today_bytes / (1024**3), 2)

            from bot.services.formatting import country_flag, human_bytes
            today_breakdown = []
            if today_nodes:
                total_n_bytes = sum(int(n.get("total") or 0) for n in today_nodes)
                for n in today_nodes:
                    b_val = int(n.get("total") or 0)
                    if b_val <= 0:
                        continue
                    c_code = (n.get("countryCode") or "EU").upper()
                    pct = round((b_val / total_n_bytes) * 100) if total_n_bytes > 0 else 0
                    today_breakdown.append({
                        "name": n.get("name") or "Server",
                        "country_code": c_code,
                        "flag": country_flag(c_code),
                        "total_formatted": human_bytes(b_val),
                        "total_gb": round(b_val / (1024**3), 2),
                        "percent": pct,
                    })

            # Yesterday's usage & breakdown
            yesterday_start_dt = start_today_dt - timedelta(days=1)
            yesterday_bytes = 0
            yesterday_nodes = []
            try:
                yesterday_tuple = await remnawave.get_user_today_usage(
                    int(panel_user_id), yesterday_start_dt.isoformat(), start_today_dt.isoformat()
                )
                if yesterday_tuple and isinstance(yesterday_tuple, tuple):
                    yesterday_bytes = yesterday_tuple[0]
                    yesterday_nodes = yesterday_tuple[1]
            except Exception as exc:
                logger.warning("Failed to fetch yesterday usage for %s: %s", panel_user_id, exc)
            yesterday_used_gb = round(yesterday_bytes / (1024**3), 2)

            yesterday_breakdown = []
            if yesterday_nodes:
                for n in yesterday_nodes:
                    b_val = int(n.get("total") or 0)
                    if b_val <= 0:
                        continue
                    c_code = (n.get("countryCode") or "EU").upper()
                    yesterday_breakdown.append({
                        "name": n.get("name") or "Server",
                        "flag": country_flag(c_code),
                        "total_formatted": human_bytes(b_val),
                    })

            # 7-day weekly stats & daily totals
            week_start_dt = now_dt - timedelta(days=6)
            week_daily_totals = [0] * 7
            week_nodes_dict = {}
            week_total_bytes = 0
            try:
                week_series = await remnawave.get_user_bandwidth_stats(
                    int(panel_user_id), week_start_dt.strftime("%Y-%m-%d"), now_dt.strftime("%Y-%m-%d")
                ) or []
                for r in week_series:
                    n_name = r.get("name") or r.get("nodeName") or "Server"
                    c_code = (r.get("countryCode") or "EU").upper()
                    tot = int(r.get("total") or 0)
                    week_total_bytes += tot
                    if tot > 0:
                        week_nodes_dict[n_name] = {
                            "name": n_name,
                            "flag": country_flag(c_code),
                            "total_formatted": human_bytes(tot),
                            "total_bytes": tot,
                        }
                    data = r.get("data") or []
                    for i, val in enumerate(data[:7]):
                        week_daily_totals[i] += int(val or 0)
            except Exception as exc:
                logger.warning("Failed to fetch weekly stats for %s: %s", panel_user_id, exc)

            week_used_gb = round(week_total_bytes / (1024**3), 2)
            week_breakdown = sorted(week_nodes_dict.values(), key=lambda x: x["total_bytes"], reverse=True)

            busiest_day_name = "—"
            busiest_day_amount = "0 GB"
            if any(week_daily_totals):
                max_val = max(week_daily_totals)
                max_idx = week_daily_totals.index(max_val)
                busiest_dt = week_start_dt + timedelta(days=max_idx)
                b_jd = jdatetime.datetime.fromgregorian(datetime=busiest_dt)
                busiest_day_name = jdatetime.date.j_weekdays_fa[b_jd.weekday()]
                busiest_day_amount = human_bytes(max_val)

            # Month name & usage
            month_names = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
            current_month_name = month_names[now_j.month - 1] if 1 <= now_j.month <= 12 else "ماه جاری"
            month_used_gb = traffic_used_gb

            # HWID devices
            devices = []
            try:
                devices = await remnawave.get_user_hwid_devices(int(panel_user_id)) or []
            except Exception as exc:
                logger.warning("Failed to fetch HWID devices for %s: %s", panel_user_id, exc)

            # Calculate days left and Jalali expire date
            days_left = 0
            expire_jalali_str = ""
            expire_at_raw = primary.get("expireAt")
            expire_timestamp = primary.get("expire")
            try:
                expire_dt = parse_iso(expire_at_raw)
                if not expire_dt and expire_timestamp:
                    expire_dt = datetime.fromtimestamp(expire_timestamp, tz=timezone.utc)
                if expire_dt:
                    days_left = max(0, (expire_dt - datetime.now(timezone.utc)).days)
                    exp_j = jdatetime.datetime.fromgregorian(
                        datetime=expire_dt.astimezone(ZoneInfo(tz_name))
                    )
                    expire_jalali_str = f"{exp_j.year}/{exp_j.month:02d}/{exp_j.day:02d}"
            except Exception as exc:
                logger.warning("Failed to calculate expiration for %s: %s", panel_user_id, exc)

            # Resolve real subscription URL from Remnawave (subscriptionUrl or fallback to Order)
            sub_url = primary.get("subscriptionUrl") or primary.get("subscription_url")
            if not sub_url:
                order_res = await session.execute(
                    select(Order.subscription_url).where(
                        Order.telegram_id == telegram_id,
                        Order.subscription_url.isnot(None),
                    ).order_by(Order.id.desc()).limit(1)
                )
                sub_url = order_res.scalar_one_or_none() or ""

            active_sub = {
                "account_id": panel_user_id,
                "username": primary.get("username", user_auth.get("username")),
                "status": primary.get("status", "ACTIVE"),
                "traffic_total_gb": traffic_total_gb,
                "traffic_used_gb": traffic_used_gb,
                "traffic_remaining_gb": traffic_remaining_gb,
                "percent_remaining": percent_remaining,
                "days_left": days_left,
                "expire_timestamp": expire_timestamp,
                "expire_jalali": expire_jalali_str,
                "devices_count": len(devices),
                "devices": devices,
                "subscription_url": sub_url,
                "today_used_gb": today_used_gb,
                "today_breakdown": today_breakdown,
                "yesterday_used_gb": yesterday_used_gb,
                "yesterday_breakdown": yesterday_breakdown,
                "week_used_gb": week_used_gb,
                "week_breakdown": week_breakdown,
                "week_daily_totals_gb": [round(b / (1024**3), 2) for b in week_daily_totals],
                "busiest_day_name": busiest_day_name,
                "busiest_day_amount": busiest_day_amount,
                "current_month_name": current_month_name,
                "month_used_gb": month_used_gb,
            }

        # 6. Lucky wheel status
        wheel_key = f"tma:user:{telegram_id}:wheel_spins"
        wheel_spun = bool(await cache.get(wheel_key))

        data = {
            "user": {
                "id": telegram_id,
                "first_name": user_auth.get("first_name", "کاربر"),
                "username": user_auth.get("username"),
                "wallet_balance": wallet_balance,
                "referrals_count": referrals_count,
                "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
                "is_admin": user_auth.get("is_admin", False),
            },
            "active_sub": active_sub,
            "has_active_sub": has_active_sub,
            "today_jalali": today_jalali_str,
            "yesterday_jalali": yesterday_jalali_str,
            "plans": plans_data,
            "wheel_status": {
                "has_spun_free": wheel_spun,
                "can_spin": not wheel_spun or has_active_sub,
            },
        }

        # Cache for 10 seconds
        await cache.set(cache_key, data, ttl_seconds=10)
        return web.json_response({"ok": True, "data": data, "cached": False})


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


async def get_user_nodes(request: web.Request) -> web.Response:
    """Return active cluster nodes for the network ping/health checker."""
    remnawave = request.app["remnawave"]
    cache: FastCache = request.app["cache"]
    cache_key = "tma:public:nodes"

    cached_nodes = await cache.get(cache_key)
    if cached_nodes:
        return web.json_response({"ok": True, "nodes": cached_nodes})

    nodes = await remnawave.get_nodes() or []
    cleaned_nodes = []
    for node in nodes:
        cleaned_nodes.append({
            "name": node.get("name", "Server"),
            "country_code": node.get("country_code", "EU"),
            "address": node.get("address", ""),
            "status": node.get("status", "ONLINE"),
        })

    await cache.set(cache_key, cleaned_nodes, ttl_seconds=30)
    return web.json_response({"ok": True, "nodes": cleaned_nodes})


async def get_user_ip_info(request: web.Request) -> web.Response:
    """Return the client's public IP detected by Nginx/proxy."""
    client_ip = (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote
        or "127.0.0.1"
    )
    return web.json_response({
        "ok": True,
        "ip": client_ip,
        "is_safe": not client_ip.startswith(("10.", "192.168.", "172.16.")),
    })

