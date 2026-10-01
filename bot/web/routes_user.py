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

        # 3. Active Remnawave account stats
        panel_users = await remnawave.get_users_by_telegram_id(telegram_id)
        active_sub = None
        has_active_sub = False
        panel_user_id = None

        if panel_users:
            # Pick first active or main user
            primary = panel_users[0]
            panel_user_id = primary.get("id")
            has_active_sub = primary.get("status", "").upper() == "ACTIVE"

            bw_stats = await remnawave.get_user_bandwidth_stats(panel_user_id)
            today_stats = await remnawave.get_user_today_usage(
                panel_user_id, timezone=settings.TIMEZONE
            )
            devices = await remnawave.get_user_hwid_devices(panel_user_id)

            # Calculate days left
            expire_at = primary.get("expire")
            days_left = 0
            if expire_at:
                try:
                    exp_dt = datetime.fromtimestamp(expire_at, tz=timezone.utc)
                    days_left = max(0, (exp_dt - datetime.now(timezone.utc)).days)
                except Exception:
                    pass

            active_sub = {
                "account_id": panel_user_id,
                "username": primary.get("username", user_auth.get("username")),
                "status": primary.get("status", "ACTIVE"),
                "traffic_total_gb": round(bw_stats.get("traffic_total_gb", 0), 2) if bw_stats else 0,
                "traffic_used_gb": round(bw_stats.get("traffic_used_gb", 0), 2) if bw_stats else 0,
                "traffic_remaining_gb": round(bw_stats.get("traffic_remaining_gb", 0), 2) if bw_stats else 0,
                "percent_remaining": round(bw_stats.get("percent_remaining", 100), 1) if bw_stats else 100,
                "days_left": days_left,
                "expire_timestamp": expire_at,
                "devices_count": len(devices),
                "devices": devices,
                "subscription_url": primary.get("subscription_url") or "",
                "today_used_gb": round(today_stats.get("used_today_gb", 0), 2) if today_stats else 0,
                "today_breakdown": today_stats.get("breakdown", {}) if today_stats else {},
            }

        # 4. Lucky wheel status
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
            "wheel_status": {
                "has_spun_free": wheel_spun,
                "can_spin": not wheel_spun or has_active_sub,
            },
        }

        # Cache for 12 seconds
        await cache.set(cache_key, data, ttl_seconds=12)
        return web.json_response({"ok": True, "data": data, "cached": False})


async def post_user_spin(request: web.Request) -> web.Response:
    """Handle Lucky Wheel spin with anti-cheat and prize allocation."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

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

    return web.json_response({
        "ok": True,
        "subscription_url": revoked.get("subscription_url"),
    })


async def post_user_kill_device(request: web.Request) -> web.Response:
    """Disconnect a specific HWID session for the user."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

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
