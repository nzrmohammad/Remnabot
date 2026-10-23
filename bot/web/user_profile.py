"""User dashboard and profile endpoint for Telegram Mini App.

Decomposed into focused calculation layers:
- `_calc_bandwidth_stats`: Network usage series, today/yesterday/week bandwidth breakdowns
- `_calc_usage_curves`: Traffic split (up/down), device platforms, hourly curves, donut shares
- `_build_active_subscription`: Remnawave account stats, devices, expiration, sub link
- `_fetch_transaction_history`: Orders, topups, and admin wallet adjustment timelines
- `_fetch_user_perks_and_settings`: Wheel status, won coupons, reports & alert preferences
- `get_user_me`: Lightweight async controller orchestrating user dashboard data
"""
import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import jdatetime
from aiohttp import web
from sqlalchemy import func, or_, select

from bot.common.links import ref_link as build_ref_link
from bot.db.models import AdminLog, Coupon, CouponUsage, Order, Service, Topup, User, Wallet
from bot.db.repositories.alert_repo import AlertRepository
from bot.db.repositories.report_repo import ReportRepository
from bot.db.repositories.user_repo import UserRepository
from bot.services.app_settings import get_store_settings, is_maintenance
from bot.services.formatting import now_tz
from bot.web.cache import FastCache
from bot.web.user_common import db_session, require_user

logger = logging.getLogger(__name__)


from bot.web.user_subscription_detail import (
    build_active_subscription as _build_active_subscription,
)


async def _fetch_transaction_history(session: Any, telegram_id: int, tz_name: str) -> list[dict[str, Any]]:
    """Fetch orders, topups, and admin adjustments sorted by timestamp."""
    history_items: list[dict[str, Any]] = []
    try:
        orders_res = await session.execute(
            select(Order).where(Order.telegram_id == telegram_id).order_by(Order.id.desc()).limit(50)
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
                "service_name": o.service_name,
                "amount": o.amount,
                "amount_formatted": f"{o.amount:,} تومان",
                "is_positive": False,
                "status": "موفق",
                "status_color": "emerald",
                "date_jalali": o_j_str,
                "timestamp": o_dt.timestamp() if o_dt else 0,
            })

        topups_res = await session.execute(
            select(Topup).where(Topup.telegram_id == telegram_id).order_by(Topup.id.desc()).limit(50)
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
            history_items.append({
                "id": t.id,
                "type": "topup",
                "title": "افزایش موجودی (کارت به کارت)",
                "amount": t.amount,
                "amount_formatted": f"{t.amount:,} تومان",
                "is_positive": st == "approved",
                "status": "تایید شده" if st == "approved" else ("رد شده" if st == "rejected" else "در انتظار بررسی"),
                "status_color": "emerald" if st == "approved" else ("rose" if st == "rejected" else "amber"),
                "date_jalali": t_j_str,
                "timestamp": t_dt.timestamp() if t_dt else 0,
            })

        admin_logs_res = await session.execute(
            select(AdminLog).where(
                AdminLog.action.in_(["wallet_charge", "wallet_deduct", "balance_add", "balance_sub"]),
                or_(
                    AdminLog.target_user_id == telegram_id,
                    AdminLog.detail.like(f"%{telegram_id}%"),
                ),
            ).order_by(AdminLog.id.desc()).limit(15)
        )
        for al in admin_logs_res.scalars().all():
            al_dt = al.created_at
            al_j_str = ""
            if al_dt:
                al_j = jdatetime.datetime.fromgregorian(
                    datetime=al_dt.astimezone(ZoneInfo(tz_name)) if al_dt.tzinfo else al_dt
                )
                al_j_str = f"{al_j.year}/{al_j.month:02d}/{al_j.day:02d} - {al_j.hour:02d}:{al_j.minute:02d}"

            is_pos = al.action in ("wallet_charge", "balance_add")
            parsed_amt = 0
            m = re.search(r"amount=(\d+)", al.detail or "") or re.search(r"([\d,]+)\s*تومان", al.detail or "")
            if m:
                try:
                    parsed_amt = int(m.group(1).replace(",", ""))
                except Exception:
                    parsed_amt = 0

            history_items.append({
                "id": al.id,
                "type": "admin_adjust",
                "title": "شارژ دستی مدیریت" if is_pos else "کسر دستی مدیریت",
                "amount": parsed_amt,
                "amount_formatted": f"{parsed_amt:,} تومان" if parsed_amt else "--",
                "is_positive": is_pos,
                "status": "ثبت شد",
                "status_color": "emerald" if is_pos else "rose",
                "date_jalali": al_j_str,
                "timestamp": al_dt.timestamp() if al_dt else 0,
            })

        history_items.sort(key=lambda x: x["timestamp"], reverse=True)
    except Exception as exc:
        logger.warning("Failed to fetch transaction history for %s: %s", telegram_id, exc)

    return history_items


async def _fetch_user_perks_and_settings(
    session: Any, cache: FastCache, telegram_id: int, has_active_sub: bool, db_user: Any = None
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Fetch user alert/report preferences, active won coupons, and lucky wheel status."""
    last_spin_dt = getattr(db_user, "wheel_last_spin_at", None) if db_user else None
    cooldown_left = 0
    if isinstance(last_spin_dt, datetime):
        if last_spin_dt.tzinfo is None:
            last_spin_dt = last_spin_dt.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_spin_dt).total_seconds()
        if elapsed < 86400:
            cooldown_left = max(1, int(86400 - elapsed))
    else:
        last_spin = await cache.get(f"tma:user:{telegram_id}:wheel_last_spin")
        if last_spin is not None:
            try:
                elapsed = time.time() - float(last_spin)
                if elapsed < 86400:
                    cooldown_left = max(1, int(86400 - elapsed))
            except (ValueError, TypeError):
                pass

    wheel_streak = int(getattr(db_user, "wheel_streak", 0) or 0) if db_user else 0
    spin_tickets = int(getattr(db_user, "spin_tickets", 0) or 0) if db_user else 0
    streak_multiplier = 1.5 if wheel_streak >= 3 else (1.2 if wheel_streak == 2 else 1.0)

    wheel_status = {
        "can_spin": bool(has_active_sub and (cooldown_left <= 0 or spin_tickets > 0)),
        "has_active_sub": has_active_sub,
        "next_spin_seconds": cooldown_left,
        "streak": wheel_streak,
        "streak_multiplier": streak_multiplier,
        "spin_tickets": spin_tickets,
    }

    rep_settings_data = {"nightly": True, "weekly": True, "monthly": True, "clean_reports": True, "wheel_notify": True}
    try:
        rep_settings = await ReportRepository(session).get_settings(telegram_id)
        rep_settings_data = {
            "nightly": bool(rep_settings.nightly),
            "weekly": bool(rep_settings.weekly),
            "monthly": bool(rep_settings.monthly),
            "clean_reports": bool(rep_settings.clean_reports),
            "wheel_notify": bool(rep_settings.wheel_notify),
        }
    except Exception as exc:
        logger.warning("Failed to fetch report settings for %s: %s", telegram_id, exc)

    alert_settings_data = {"low_traffic": True, "expire_warning": True, "traffic_percent": 80, "expire_days": 3}
    try:
        alert_settings = await AlertRepository(session).get_settings(telegram_id)
        alert_settings_data = {
            "low_traffic": bool(alert_settings.traffic_percent > 0),
            "expire_warning": bool(alert_settings.expire_days > 0),
            "traffic_percent": alert_settings.traffic_percent if alert_settings.traffic_percent > 0 else 80,
            "expire_days": alert_settings.expire_days if alert_settings.expire_days > 0 else 3,
        }
    except Exception as exc:
        logger.warning("Failed to fetch alert settings for %s: %s", telegram_id, exc)

    won_coupons_raw = await cache.get(f"wheel:user_coupons:{telegram_id}") or []
    now_dt_utc = datetime.now(timezone.utc)
    # Strictly filter only coupons with a valid future expiration date
    active_won_coupons = [
        c for c in won_coupons_raw
        if c.get("expires_at") and c.get("expires_at", "") > now_dt_utc.isoformat()
    ]

    try:
        if active_won_coupons:
            used_ids_res = await session.execute(select(CouponUsage.coupon_id).where(CouponUsage.telegram_id == telegram_id))
            used_ids = set(used_ids_res.scalars().all())
            active_codes = [c.get("code") for c in active_won_coupons if c.get("code")]
            if active_codes:
                valid_db_res = await session.execute(
                    select(Coupon).where(
                        Coupon.code.in_(active_codes),
                        Coupon.is_active.is_(True),
                        Coupon.used_count < Coupon.max_uses,
                        or_(Coupon.expires_at.is_(None), Coupon.expires_at > now_dt_utc),
                    )
                )
                valid_map = {dbc.code: dbc for dbc in valid_db_res.scalars().all()}
                # Keep only coupons that exist, are active, not expired, and not yet used by user
                active_won_coupons = [
                    c for c in active_won_coupons
                    if c.get("code") in valid_map and valid_map[c.get("code")].id not in used_ids
                ]
    except Exception as exc:
        logger.debug("Failed to verify user coupons in DB for %s: %s", telegram_id, exc)

    settings_combined = {**rep_settings_data, **alert_settings_data}
    return settings_combined, active_won_coupons, wheel_status


async def get_user_me(request: web.Request) -> web.Response:
    """Return dashboard data for the authenticated user (Cached for 30 seconds)."""
    user_auth, err = require_user(request)
    if err:
        return err

    telegram_id = int(user_auth["id"])
    req_account_id = request.query.get("account_id")
    cache: FastCache = request.app["cache"]
    cache_key = f"tma:user:{telegram_id}:dashboard:{req_account_id or 'default'}"

    cached_data = await cache.get(cache_key)
    if cached_data:
        return web.json_response({"ok": True, "data": cached_data, "cached": True})

    remnawave = request.app["remnawave"]
    settings = request.app["settings"]
    panel_users_task = asyncio.create_task(remnawave.get_users_by_telegram_id(telegram_id))

    async with db_session(request) as session:
        import bot.web.routes_user as _user_routes
        user_repo_cls = getattr(_user_routes, "UserRepository", UserRepository)
        user_repo = user_repo_cls(session)
        first_name = user_auth.get("first_name", "")
        last_name = user_auth.get("last_name", "")
        auth_full_name = f"{first_name} {last_name}".strip() or None
        db_user = await user_repo.get_or_create(telegram_id, user_auth.get("username"))
        if auth_full_name and hasattr(db_user, "full_name"):
            db_user.full_name = auth_full_name

        wallet_res = await session.execute(select(Wallet).where(Wallet.telegram_id == telegram_id))
        wallet = wallet_res.scalar_one_or_none()
        wallet_balance = wallet.balance if wallet else 0

        store_settings = await get_store_settings(session)
        maint_on = await is_maintenance(session)
        ref_count_res = await session.execute(select(func.count(User.id)).where(User.referred_by_id == telegram_id))
        referrals_count = int(ref_count_res.scalar_one() or 0)
        referral_reward_gb = store_settings.referral_reward_gb if store_settings.referral_enabled else 5

        services_res = await session.execute(
            select(Service).where(Service.is_active.is_(True)).order_by(Service.price.asc())
        )
        plans_data = [
            {
                "id": s.id,
                "name": s.name,
                "price": s.price,
                "duration_days": s.duration_days,
                "traffic_gb": s.traffic_gb,
                "description": s.description,
                "hwid_limit": s.hwid_limit,
                "badge": s.badge or "",
            }
            for s in services_res.scalars().all()
        ]

        tz_name = getattr(settings, "TIMEZONE", "Asia/Tehran")
        now_dt = now_tz(tz_name)
        now_j = jdatetime.datetime.fromgregorian(datetime=now_dt)
        today_jalali_str = f"{now_j.year}/{now_j.month:02d}/{now_j.day:02d}"
        yesterday_dt = now_dt - timedelta(days=1)
        yesterday_j = jdatetime.datetime.fromgregorian(datetime=yesterday_dt)
        yesterday_jalali_str = f"{yesterday_j.year}/{yesterday_j.month:02d}/{yesterday_j.day:02d}"

        panel_users = []
        is_partial = False
        panel_error = None
        try:
            panel_users = (await asyncio.wait_for(panel_users_task, timeout=8.0)) or []
        except TimeoutError as exc:
            logger.error("Remnawave panel timeout (8.0s) for telegram_id=%s", telegram_id)
            panel_users = []
            is_partial = True
            panel_error = "panel_timeout"
            try:
                from bot.services.error_reporter import report_error
                bot = request.app.get("bot")
                session_factory = request.app.get("session_factory")
                if bot:
                    await report_error(
                        bot,
                        session_factory=session_factory,
                        session=session,
                        exc=exc,
                        context="Panel timeout /me",
                        user_id=telegram_id,
                    )
            except Exception as rep_err:
                logger.debug("Failed reporting panel timeout: %s", rep_err)
        except Exception as exc:
            logger.error("Failed to get panel users for telegram_id=%s: %s", telegram_id, exc)
            panel_users = []
            is_partial = True
            panel_error = "panel_error"
            try:
                from bot.services.error_reporter import report_error
                bot = request.app.get("bot")
                session_factory = request.app.get("session_factory")
                if bot:
                    await report_error(
                        bot,
                        session_factory=session_factory,
                        session=session,
                        exc=exc,
                        context="Failed to get panel users in /api/user/me",
                        user_id=telegram_id,
                    )
            except Exception as rep_err:
                logger.debug("Failed reporting panel error: %s", rep_err)
        finally:
            if not panel_users_task.done():
                panel_users_task.cancel()
            else:
                _ = panel_users_task.exception() if not panel_users_task.cancelled() else None

        active_sub, has_active_sub, accounts_list = await _build_active_subscription(
            remnawave, panel_users, req_account_id, telegram_id, user_auth, session, tz_name, now_dt
        )
        is_invite_only = False
        is_adm = bool(user_auth.get("is_admin", False))
        if not is_adm:
            try:
                store_sett = await get_store_settings(session)
                if getattr(store_sett, "access_mode", "open") == "invite_only":
                    is_invited = bool(getattr(db_user, "referred_by_id", None) or has_active_sub)
                    if not is_invited:
                        is_invite_only = True
            except Exception as e:
                logger.debug("Failed checking invite-only status: %s", e)
        transactions = await _fetch_transaction_history(session, telegram_id, tz_name)
        user_settings, active_won_coupons, wheel_status = await _fetch_user_perks_and_settings(
            session, cache, telegram_id, has_active_sub, db_user
        )

        user_reg_jalali = ""
        if db_user.created_at:
            try:
                u_j = jdatetime.datetime.fromgregorian(
                    datetime=db_user.created_at.astimezone(ZoneInfo(tz_name)) if db_user.created_at.tzinfo else db_user.created_at
                )
                user_reg_jalali = f"{u_j.year}/{u_j.month:02d}/{u_j.day:02d}"
            except Exception:
                pass

        days_until_birthday = None
        is_birthday_today = False
        birth_date_val = getattr(db_user, "birth_date", None)
        if isinstance(birth_date_val, str) and birth_date_val.strip():
            try:
                clean_bdate = birth_date_val.strip().replace("-", "/")
                b_parts = [int(p) for p in clean_bdate.split("/") if p.isdigit()]
                if len(b_parts) == 3:
                    _by, b_month, b_day = b_parts
                    today_j = jdatetime.date.today()
                    def _safe_jdate(y, m, d):
                        try:
                            return jdatetime.date(y, m, d)
                        except ValueError:
                            if m == 12 and d > 29:
                                return jdatetime.date(y, m, 29)
                            raise

                    this_year_bday = _safe_jdate(today_j.year, b_month, b_day)
                    if this_year_bday == today_j:
                        days_until_birthday = 0
                        is_birthday_today = True
                    elif this_year_bday > today_j:
                        days_until_birthday = (this_year_bday - today_j).days
                    else:
                        next_year_bday = _safe_jdate(today_j.year + 1, b_month, b_day)
                        days_until_birthday = (next_year_bday - today_j).days
            except Exception as bday_err:
                logger.debug("Failed to calculate days_until_birthday: %s", bday_err)

        bot = request.app.get("bot")
        bot_username = getattr(getattr(bot, "_me", None), "username", "") if bot else ""
        ref_link = build_ref_link(bot_username, telegram_id)

        data = {
            "partial": is_partial,
            "panel_error": panel_error,
            "bot_username": bot_username,
            "referral_reward_gb": referral_reward_gb,
            "referral_enabled": store_settings.referral_enabled,
            "referral_link": ref_link,
            "tutorial_channel_url": store_settings.tutorial_channel_url,
            "routing_tutorial_url": store_settings.routing_tutorial_url,
            "client_apps_override": store_settings.client_apps_json,
            "user": {
                "id": telegram_id,
                "first_name": user_auth.get("first_name", "کاربر"),
                "username": user_auth.get("username"),
                "wallet_balance": wallet_balance,
                "referrals_count": referrals_count,
                "phone_number": db_user.phone_number if isinstance(getattr(db_user, "phone_number", None), str) else "",
                "is_phone_verified": bool(db_user.phone_number and db_user.phone_number.strip()),
                "birth_date": db_user.birth_date if isinstance(getattr(db_user, "birth_date", None), str) else "",
                "days_until_birthday": days_until_birthday,
                "is_birthday_today": is_birthday_today,
                "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
                "created_at_jalali": user_reg_jalali,
                "language": db_user.language if isinstance(getattr(db_user, "language", None), str) else "fa",
                "photo_url": user_auth.get("photo_url", ""),
                "is_admin": user_auth.get("is_admin", False),
                "auto_renew": bool(getattr(db_user, "auto_renew", False)),
            },
            "settings": user_settings,
            "accounts": accounts_list,
            "is_maintenance": maint_on,
            "is_invite_only": is_invite_only,
            "active_sub": active_sub,
            "has_active_sub": has_active_sub,
            "today_jalali": today_jalali_str,
            "yesterday_jalali": yesterday_jalali_str,
            "plans": plans_data,
            "transactions": transactions[:50],
            "won_coupons": active_won_coupons,
            "wheel_status": wheel_status,
        }

        if not is_partial:
            await cache.set(cache_key, data, ttl_seconds=30)
        else:
            await cache.set(cache_key, data, ttl_seconds=5)
        return web.json_response({"ok": True, "data": data, "cached": False})


async def post_user_set_birthday(request: web.Request) -> web.Response:
    """Set or update user's Jalali birth date (format: YYYY/MM/DD)."""
    user_auth, err = require_user(request)
    if err:
        return err

    try:
        body = await request.json()
    except Exception:
        body = {}

    birth_date = str(body.get("birth_date") or "").strip()
    clean_bdate = birth_date.replace("-", "/")
    parts = clean_bdate.split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return web.json_response({"ok": False, "error": "فرمت تاریخ نامعتبر است (مثال: ۱۳۷۵/۰۷/۲۲)."}, status=400)

    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    if year < 1300 or year > 1410 or month < 1 or month > 12 or day < 1 or day > 31:
        return web.json_response({"ok": False, "error": "تاریخ وارد شده خارج از بازه مجاز است."}, status=400)

    formatted_date = f"{year:04d}/{month:02d}/{day:02d}"
    telegram_id = int(user_auth["id"])

    async with db_session(request) as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            return web.json_response({"ok": False, "error": "کاربر یافت نشد."}, status=404)

        user.birth_date = formatted_date
        await session.commit()

        cache: FastCache = request.app.get("cache")
        if cache:
            await cache.delete(f"tma:user:{telegram_id}")
            await cache.delete(f"tma:user:{telegram_id}:dashboard:default")
            await cache.delete(f"tma:user:{telegram_id}:dashboard")

        return web.json_response({"ok": True, "birth_date": formatted_date})
