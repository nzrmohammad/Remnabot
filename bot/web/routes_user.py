"""User API endpoints for Telegram Mini App."""
import json
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any

from aiohttp import web
from sqlalchemy import func, select

from bot.db.models import Order, Topup, User, Wallet
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
    req_account_id = request.query.get("account_id")
    cache: FastCache = request.app["cache"]
    cache_key = f"tma:user:{telegram_id}:dashboard:{req_account_id or 'default'}"

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
            if req_account_id:
                primary = next((u for u in panel_users if str(u.get("id")) == str(req_account_id)), panel_users[0])
            else:
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

            # Calculate bandwidth stats and per-node breakdown aligned with bot reports
            from bot.services.formatting import country_flag, human_bytes

            since = parse_iso(primary.get("lastTrafficResetAt")) or parse_iso(primary.get("createdAt"))
            stats_start_dt = now_dt - timedelta(days=90)
            if since is not None and since > stats_start_dt:
                stats_start_dt = since
            week_start_dt = now_dt - timedelta(days=6)
            if stats_start_dt > week_start_dt:
                stats_start_dt = week_start_dt

            today_str = now_dt.strftime("%Y-%m-%d")
            start_str = stats_start_dt.strftime("%Y-%m-%d")

            series = []
            try:
                series = await remnawave.get_user_bandwidth_stats(int(panel_user_id), start_str, today_str) or []
            except Exception as exc:
                logger.warning("Failed to fetch bandwidth stats for %s: %s", panel_user_id, exc)

            today_bytes = 0
            today_breakdown = []
            yesterday_bytes = 0
            yesterday_breakdown = []
            all_nodes_breakdown = []
            week_daily_totals = [0] * 7
            week_nodes_dict = {}
            week_total_bytes = 0

            if series and isinstance(series, list) and isinstance(series[0], dict):
                # 1. Total volume since reset per node (matches 'used_breakdown' in reports)
                for r in series:
                    tot = int(r.get("total") or 0)
                    if tot > 0:
                        c_code = (r.get("countryCode") or "EU").upper()
                        all_nodes_breakdown.append({
                            "name": r.get("name") or r.get("nodeName") or "Server",
                            "country_code": c_code,
                            "flag": country_flag(c_code),
                            "total_formatted": human_bytes(tot),
                            "total_bytes": tot,
                            "total_gb": round(tot / (1024**3), 2),
                        })
                all_nodes_breakdown.sort(key=lambda x: x["total_bytes"], reverse=True)

                # 2. Today's usage (last element in daily data array)
                today_temp = []
                for r in series:
                    data = r.get("data") or []
                    val = int(data[-1]) if data else 0
                    if val > 0:
                        today_bytes += val
                        c_code = (r.get("countryCode") or "EU").upper()
                        today_temp.append({
                            "name": r.get("name") or r.get("nodeName") or "Server",
                            "country_code": c_code,
                            "flag": country_flag(c_code),
                            "total_bytes": val,
                            "total_formatted": human_bytes(val),
                            "total_gb": round(val / (1024**3), 2),
                        })
                today_temp.sort(key=lambda x: x["total_bytes"], reverse=True)
                for item in today_temp:
                    pct = round((item["total_bytes"] / today_bytes) * 100) if today_bytes > 0 else 0
                    item["percent"] = pct
                    today_breakdown.append(item)

                # 3. Yesterday's usage (second to last element in daily data array - strictly single day)
                yesterday_temp = []
                for r in series:
                    data = r.get("data") or []
                    val = int(data[-2]) if len(data) >= 2 else 0
                    if val > 0:
                        yesterday_bytes += val
                        c_code = (r.get("countryCode") or "EU").upper()
                        yesterday_temp.append({
                            "name": r.get("name") or r.get("nodeName") or "Server",
                            "country_code": c_code,
                            "flag": country_flag(c_code),
                            "total_bytes": val,
                            "total_formatted": human_bytes(val),
                            "total_gb": round(val / (1024**3), 2),
                        })
                yesterday_temp.sort(key=lambda x: x["total_bytes"], reverse=True)
                for item in yesterday_temp:
                    pct = round((item["total_bytes"] / yesterday_bytes) * 100) if yesterday_bytes > 0 else 0
                    item["percent"] = pct
                    yesterday_breakdown.append(item)

                # 4. Weekly 7-day stats
                for r in series:
                    data = r.get("data") or []
                    last_7 = data[-7:] if len(data) >= 7 else ([0] * (7 - len(data)) + data)
                    node_week = sum(int(v or 0) for v in last_7)
                    week_total_bytes += node_week
                    n_name = r.get("name") or r.get("nodeName") or "Server"
                    c_code = (r.get("countryCode") or "EU").upper()
                    if node_week > 0:
                        week_nodes_dict[n_name] = {
                            "name": n_name,
                            "flag": country_flag(c_code),
                            "total_formatted": human_bytes(node_week),
                            "total_bytes": node_week,
                        }
                    for i, val in enumerate(last_7):
                        week_daily_totals[i] += int(val or 0)
            else:
                # Graceful fallback for mock tests or panels without series
                try:
                    start_today_dt = start_of_today(tz_name)
                    today_tuple = await remnawave.get_user_today_usage(
                        int(panel_user_id), start_today_dt.isoformat(), now_dt.isoformat()
                    )
                    if today_tuple and isinstance(today_tuple, tuple):
                        today_bytes = today_tuple[0]
                        for n in today_tuple[1]:
                            b_val = int(n.get("total") or 0)
                            if b_val <= 0:
                                continue
                            c_code = (n.get("countryCode") or "EU").upper()
                            pct = round((b_val / today_bytes) * 100) if today_bytes > 0 else 0
                            today_breakdown.append({
                                "name": n.get("name") or "Server",
                                "country_code": c_code,
                                "flag": country_flag(c_code),
                                "total_formatted": human_bytes(b_val),
                                "total_gb": round(b_val / (1024**3), 2),
                                "percent": pct,
                            })
                except Exception as exc:
                    logger.warning("Fallback today usage failed for %s: %s", panel_user_id, exc)

            today_used_gb = round(today_bytes / (1024**3), 2)
            yesterday_used_gb = round(yesterday_bytes / (1024**3), 2)
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
                "all_nodes_breakdown": all_nodes_breakdown,
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

        # 6. Orders and topups history for Wallet & History view
        history_items = []
        try:
            orders_res = await session.execute(
                select(Order).where(Order.telegram_id == telegram_id).order_by(Order.id.desc()).limit(15)
            )
            for o in orders_res.scalars().all():
                o_dt = o.created_at
                o_j_str = ""
                if o_dt:
                    o_j = jdatetime.datetime.fromgregorian(
                        datetime=o_dt.astimezone(ZoneInfo(tz_name)) if o_dt.tzinfo else o_dt
                    )
                    o_j_str = f"{o_j.year}/{o_j.month:02d}/{o_j.day:02d} - {o_j.hour:02d}:{o_j.minute:02d}"
                history_items.append({
                    "id": o.id,
                    "type": "order",
                    "title": f"خرید {o.service_name}",
                    "amount": o.amount,
                    "amount_formatted": f"{o.amount:,} تومان",
                    "is_positive": False,
                    "status": "موفق",
                    "status_color": "emerald",
                    "date_jalali": o_j_str,
                    "timestamp": o_dt.timestamp() if o_dt else 0,
                })

            topups_res = await session.execute(
                select(Topup).where(Topup.telegram_id == telegram_id).order_by(Topup.id.desc()).limit(15)
            )
            for t in topups_res.scalars().all():
                t_dt = t.created_at
                t_j_str = ""
                if t_dt:
                    t_j = jdatetime.datetime.fromgregorian(
                        datetime=t_dt.astimezone(ZoneInfo(tz_name)) if t_dt.tzinfo else t_dt
                    )
                    t_j_str = f"{t_j.year}/{t_j.month:02d}/{t_j.day:02d} - {t_j.hour:02d}:{t_j.minute:02d}"
                st = (t.status or "pending").lower()
                st_text = "تایید شده" if st == "approved" else ("رد شده" if st == "rejected" else "در انتظار بررسی")
                st_color = "emerald" if st == "approved" else ("rose" if st == "rejected" else "amber")
                history_items.append({
                    "id": t.id,
                    "type": "topup",
                    "title": "افزایش موجودی (کارت به کارت)",
                    "amount": t.amount,
                    "amount_formatted": f"{t.amount:,} تومان",
                    "is_positive": True if st == "approved" else False,
                    "status": st_text,
                    "status_color": st_color,
                    "date_jalali": t_j_str,
                    "timestamp": t_dt.timestamp() if t_dt else 0,
                })

            history_items.sort(key=lambda x: x["timestamp"], reverse=True)
        except Exception as exc:
            logger.warning("Failed to fetch transaction history for %s: %s", telegram_id, exc)

        user_reg_jalali = ""
        if db_user.created_at:
            try:
                u_j = jdatetime.datetime.fromgregorian(
                    datetime=db_user.created_at.astimezone(ZoneInfo(tz_name)) if db_user.created_at.tzinfo else db_user.created_at
                )
                user_reg_jalali = f"{u_j.year}/{u_j.month:02d}/{u_j.day:02d}"
            except Exception:
                pass

        # Accounts list for account switcher
        accounts_list = []
        for pu in panel_users:
            pu_traffic = pu.get("userTraffic") or {}
            pu_used = int(pu_traffic.get("usedTrafficBytes") or pu.get("usedTrafficBytes") or 0)
            pu_limit = int(pu.get("trafficLimitBytes") or 0)
            accounts_list.append({
                "id": pu.get("id"),
                "username": pu.get("username") or f"Account #{pu.get('id')}",
                "status": (pu.get("status") or "").upper(),
                "used_gb": round(pu_used / (1024**3), 2),
                "total_gb": round(pu_limit / (1024**3), 2) if pu_limit > 0 else 0,
                "is_active": (pu.get("id") == panel_user_id),
            })

        # 7. Lucky wheel status
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
                "created_at_jalali": user_reg_jalali,
                "language": db_user.language if isinstance(getattr(db_user, "language", None), str) else "fa",
                "is_admin": user_auth.get("is_admin", False),
            },
            "accounts": accounts_list,
            "active_sub": active_sub,
            "has_active_sub": has_active_sub,
            "today_jalali": today_jalali_str,
            "yesterday_jalali": yesterday_jalali_str,
            "plans": plans_data,
            "transactions": history_items[:20],
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

    from bot.db.models import Service
    from bot.db.repositories.coupon_repo import CouponRepository
    from bot.services.purchases import execute_purchase

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


async def get_user_topup_info(request: web.Request) -> web.Response:
    """Return payment methods configuration (card and crypto settings)."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    session_factory = request.app["session_factory"]
    from bot.services.app_settings import get_store_settings

    async with session_factory() as session:
        store = await get_store_settings(session)
        return web.json_response({
            "ok": True,
            "min_amount": store.topup_min_amount,
            "card_enabled": bool(store.card_enabled and store.card_number and store.card_number.strip()),
            "card_number": store.card_number or "",
            "card_holder": store.card_holder or "",
            "crypto_enabled": bool(store.crypto_enabled and store.ton_wallet_address and store.ton_rate_toman > 0),
            "ton_wallet_address": store.ton_wallet_address or "",
            "ton_rate_toman": store.ton_rate_toman or 0,
        })


async def post_user_topup_card(request: web.Request) -> web.Response:
    """Submit card-to-card topup receipt directly from WebApp and alert admins."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    if user_auth.get("is_preview"):
        return web.json_response({"ok": False, "message": "این عملیات در حالت پیش‌نمایش در دسترس نیست."}, status=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    amount = int(body.get("amount") or 0)
    receipt_info = (body.get("receipt_text") or "").strip()

    telegram_id = int(user_auth["id"])
    session_factory = request.app["session_factory"]
    bot = request.app["bot"]
    settings = request.app["settings"]

    from bot.db.repositories.wallet_repo import WalletRepository
    from bot.services.app_settings import get_store_settings
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    async with session_factory() as session:
        store = await get_store_settings(session)
        if amount < store.topup_min_amount:
            return web.json_response(
                {"ok": False, "message": f"حداقل مبلغ شارژ {store.topup_min_amount:,} تومان است."},
                status=400,
            )

        wallet_repo = WalletRepository(session)
        if await wallet_repo.pending_count(telegram_id) >= 3:
            return web.json_response(
                {"ok": False, "message": "شما حداکثر ۳ درخواست در انتظار بررسی دارید. لطفاً تا تعیین تکلیف آن‌ها صبر کنید."},
                status=400,
            )

        import hashlib
        receipt_hash = "tma:" + hashlib.sha256(f"{telegram_id}:{amount}:{receipt_info}:{time.time()}".encode()).hexdigest()[:40]
        topup = await wallet_repo.create_topup(telegram_id, amount, receipt_hash)
        await session.commit()

        # Send alert with inline buttons to admin chat
        admin_chat_id = settings.ADMIN_CHAT_ID
        if admin_chat_id and bot:
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ تایید", callback_data=f"topup:ok:{topup.id}")
            kb.button(text="❌ رد", callback_data=f"topup:no:{topup.id}")
            kb.adjust(2)

            topic_id = store.topic_topups if store.topic_topups is not None else settings.ADMIN_TOPIC_TOPUPS
            thread_kwargs = {"message_thread_id": topic_id} if topic_id else {}

            from html import escape
            tg_username = f"@{user_auth.get('username')}" if user_auth.get("username") else "—"
            user_full_name = user_auth.get("first_name", "کاربر")
            if user_auth.get("last_name"):
                user_full_name += f" {user_auth.get('last_name')}"

            caption = (
                f"💳 <b>درخواست شارژ حساب (از طریق مینی‌اپ)</b>\n"
                f"──────────────────\n"
                f"🆔 شناسه درخواست : <code>#{topup.id}</code>\n"
                f"👤 نام کاربر : <b>{escape(user_full_name)}</b>\n"
                f"🔢 شناسه تلگرام : <code>{telegram_id}</code>\n"
                f"🏷 نام کاربری : {escape(tg_username)}\n"
                f"💰 مبلغ شارژ : <b>{amount:,}</b> تومان\n"
                f"📝 اطلاعات رسید / پیگیری :\n<code>{escape(receipt_info or 'رسید ثبت‌شده در وب‌اپ')}</code>"
            )

            try:
                await bot.send_message(
                    chat_id=admin_chat_id,
                    text=caption,
                    reply_markup=kb.as_markup(),
                    **thread_kwargs,
                )
            except Exception as exc:
                logger.error("Failed to notify admin of TMA topup: %s", exc)

        return web.json_response({
            "ok": True,
            "message": "رسید شما با موفقیت ثبت شد و پس از بررسی ادمین حساب شما شارژ می‌گردد.",
        })


async def post_user_topup_crypto(request: web.Request) -> web.Response:
    """Create a TON crypto invoice for authenticated user."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    amount = int(body.get("amount") or 0)
    telegram_id = int(user_auth["id"])
    session_factory = request.app["session_factory"]

    from bot.db.repositories.crypto_repo import CryptoRepository
    from bot.services.app_settings import get_store_settings

    async with session_factory() as session:
        store = await get_store_settings(session)
        if not (store.crypto_enabled and store.ton_wallet_address and store.ton_rate_toman > 0):
            return web.json_response({"ok": False, "message": "پرداخت ارز دیجیتال در حال حاضر غیرفعال است."}, status=400)

        if amount < store.topup_min_amount:
            return web.json_response(
                {"ok": False, "message": f"حداقل مبلغ شارژ {store.topup_min_amount:,} تومان است."},
                status=400,
            )

        crypto_repo = CryptoRepository(session)
        ton_amount = round(amount / store.ton_rate_toman, 4)
        nanotons = int(round(ton_amount * 1_000_000_000))
        invoice = await crypto_repo.create_invoice(
            telegram_id=telegram_id,
            amount_toman=amount,
            amount_ton=f"{ton_amount:.4f}",
            nanotons=nanotons,
            pay_address=store.ton_wallet_address,
            expires_minutes=30,
        )
        await session.commit()

        deep_link = f"ton://transfer/{invoice.pay_address}?amount={invoice.nanotons}&text={invoice.comment}"

        return web.json_response({
            "ok": True,
            "invoice": {
                "id": invoice.id,
                "amount_toman": invoice.amount_toman,
                "amount_ton": invoice.amount_ton,
                "pay_address": invoice.pay_address,
                "comment": invoice.comment,
                "deep_link": deep_link,
                "expires_minutes": 30,
            }
        })


async def post_user_topup_crypto_check(request: web.Request) -> web.Response:
    """Verify on-chain payment for a TON invoice."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    invoice_id = body.get("invoice_id")
    if not invoice_id:
        return web.json_response({"ok": False, "message": "شناسه فاکتور الزامی است."}, status=400)

    session_factory = request.app["session_factory"]
    cache: FastCache = request.app["cache"]
    telegram_id = int(user_auth["id"])

    from bot.db.repositories.crypto_repo import CryptoRepository
    from bot.db.repositories.wallet_repo import WalletRepository
    from bot.services.app_settings import get_store_settings
    from bot.services.crypto.ton import fetch_ton_transactions

    async with session_factory() as session:
        crypto_repo = CryptoRepository(session)
        inv = await crypto_repo.get_by_id(int(invoice_id))
        if not inv or inv.telegram_id != telegram_id:
            return web.json_response({"ok": False, "message": "فاکتور یافت نشد."}, status=404)

        if inv.status == "paid":
            wallet_repo = WalletRepository(session)
            w = await wallet_repo.get_wallet(telegram_id)
            return web.json_response({"ok": True, "paid": True, "balance": w.balance})

        if inv.status in ("expired", "cancelled"):
            return web.json_response({"ok": False, "message": "فاکتور منقضی یا لغو شده است."}, status=400)

        store = await get_store_settings(session)
        txs = await fetch_ton_transactions(store.ton_wallet_address)
        for tx in txs:
            if tx.get("comment") == inv.comment and tx.get("nanotons", 0) >= inv.nanotons:
                paid_inv = await crypto_repo.mark_paid(inv.id, tx.get("tx_hash", ""))
                if paid_inv:
                    wallet_repo = WalletRepository(session)
                    new_bal = await wallet_repo.add_balance_atomic(telegram_id, inv.amount_toman)
                    await session.commit()
                    await cache.delete(f"tma:user:{telegram_id}:dashboard")
                    return web.json_response({
                        "ok": True,
                        "paid": True,
                        "new_balance": new_bal,
                        "message": "پرداخت با موفقیت تایید شد و کیف پول شارژ گردید!",
                    })

        return web.json_response({
            "ok": True,
            "paid": False,
            "message": "تراکنش هنوز در شبکه تون شناسایی نشده است. لطفاً چند لحظه بعد دوباره بررسی کنید.",
        })


async def post_user_settings(request: web.Request) -> web.Response:
    """Save user settings (language, etc.)."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.json_response({"ok": False, "error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    telegram_id = int(user_auth["id"])
    language = body.get("language")

    session_factory = request.app["session_factory"]
    cache: FastCache = request.app["cache"]

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create(telegram_id, user_auth.get("username"))
        if language in ("fa", "en"):
            user.language = language
            await session.commit()
            await cache.delete(f"tma:user:{telegram_id}:dashboard")

        return web.json_response({"ok": True, "language": user.language})


async def get_user_avatar(request: web.Request) -> web.Response:
    """Fetch user Telegram avatar or redirect to it."""
    user_auth = get_authenticated_user(request)
    if not user_auth:
        return web.Response(status=401)

    telegram_id = int(user_auth["id"])
    bot = request.app.get("bot")
    if not bot:
        return web.Response(status=404)

    try:
        photos = await bot.get_user_profile_photos(telegram_id, limit=1)
        if photos.total_count > 0 and photos.photos:
            file_id = photos.photos[0][0].file_id
            tg_file = await bot.get_file(file_id)
            if tg_file and tg_file.file_path:
                file_url = f"https://api.telegram.org/file/bot{bot.token}/{tg_file.file_path}"
                raise web.HTTPFound(location=file_url)
    except web.HTTPFound:
        raise
    except Exception as exc:
        logger.debug("Failed to fetch avatar for %s: %s", telegram_id, exc)

    return web.Response(status=404)


