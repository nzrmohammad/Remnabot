"""Admin Services, Plans, and Coupons Management API endpoints."""
import asyncio
import json
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiohttp import web
from sqlalchemy import desc, func, or_, select

from bot.common import admin_thread_kwargs
from bot.common.helpers import get_limit_bytes, get_used_bytes
from bot.db.models import (
    AdminLog,
    AppSetting,
    Coupon,
    CryptoInvoice,
    KnownDevice,
    NodeCost,
    Order,
    Service,
    SupportMessage,
    Topup,
    User,
    Wallet,
)
from bot.db.repositories.admin_log_repo import AdminLogRepository
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.node_cost_repo import NodeCostRepository
from bot.db.repositories.service_repo import ServiceRepository
from bot.db.repositories.support_repo import SupportMessageRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.handlers.admin_broadcast import _resolve_broadcast_recipients
from bot.locales.texts import t
from bot.services.app_settings import get_store_settings
from bot.web.admin_common import _check_admin, db_session, format_service_name_icon_first
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)

try:
    import jdatetime
except ImportError:
    jdatetime = None


async def get_admin_plans(request: web.Request) -> web.Response:
    """List all subscription plans/services."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    async with db_session(request) as session:
        result = await session.execute(select(Service).order_by(Service.price.asc(), Service.id.asc()))
        services = result.scalars().all()
        plans = [
            {
                "id": s.id,
                "name": s.name,
                "price": s.price,
                "duration_days": s.duration_days,
                "traffic_gb": s.traffic_gb,
                "description": s.description or "",
                "is_active": s.is_active,
                "hwid_limit": s.hwid_limit or 0,
            }
            for s in services
        ]
    return web.json_response({"ok": True, "plans": plans})


async def post_admin_plan_save(request: web.Request) -> web.Response:
    """Create or update a subscription plan."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    plan_id = body.get("id")
    name = str(body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "نام پلن الزامی است."}, status=400)

    try:
        price = int(body.get("price", 0))
        traffic_gb = int(body.get("traffic_gb", 0))
        duration_days = int(body.get("duration_days", 0))
        hwid_limit = int(body.get("hwid_limit", 0)) if body.get("hwid_limit") else None
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "مقادیر عددی نامعتبر هستند."}, status=400)

    description = str(body.get("description") or "").strip() or None
    is_active = bool(body.get("is_active", True))

    async with db_session(request) as session:
        if plan_id:
            service = await session.get(Service, int(plan_id))
            if not service:
                return web.json_response({"ok": False, "error": "پلن مورد نظر یافت نشد."}, status=404)
            service.name = name
            service.price = price
            service.traffic_gb = traffic_gb
            service.duration_days = duration_days
            service.description = description
            service.is_active = is_active
            service.hwid_limit = hwid_limit
            msg = "پلن با موفقیت ویرایش شد."
        else:
            service = Service(
                name=name,
                price=price,
                traffic_gb=traffic_gb,
                duration_days=duration_days,
                description=description,
                is_active=is_active,
                hwid_limit=hwid_limit,
            )
            session.add(service)
            msg = "پلن جدید با موفقیت ایجاد شد."

        session.add(AdminLog(admin_id=admin["id"], action="save_plan", detail=f"{name} ({price:,} تومان)"))
        await session.commit()

    return web.json_response({"ok": True, "message": msg})


async def post_admin_plan_toggle(request: web.Request) -> web.Response:
    """Toggle active status of a plan."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    plan_id = body.get("id")
    if not plan_id:
        return web.json_response({"ok": False, "error": "شناسه پلن الزامی است."}, status=400)

    async with db_session(request) as session:
        service = await session.get(Service, int(plan_id))
        if not service:
            return web.json_response({"ok": False, "error": "پلن یافت نشد."}, status=404)

        service.is_active = bool(body.get("is_active", not service.is_active))
        await session.commit()

    return web.json_response({"ok": True, "is_active": service.is_active, "message": "وضعیت پلن تغییر یافت."})


async def post_admin_plan_delete(request: web.Request) -> web.Response:
    """Delete a plan."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    plan_id = body.get("id")
    if not plan_id:
        return web.json_response({"ok": False, "error": "شناسه پلن الزامی است."}, status=400)

    async with db_session(request) as session:
        service = await session.get(Service, int(plan_id))
        if not service:
            return web.json_response({"ok": False, "error": "پلن یافت نشد."}, status=404)

        await session.delete(service)
        session.add(AdminLog(admin_id=admin["id"], action="delete_plan", detail=f"حذف پلن #{plan_id}: {service.name}"))
        await session.commit()

    return web.json_response({"ok": True, "message": "پلن با موفقیت حذف شد."})


async def get_admin_coupons(request: web.Request) -> web.Response:
    """List all discount coupons."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    async with db_session(request) as session:
        now_utc = datetime.now(timezone.utc)
        result = await session.execute(
            select(Coupon)
            .where(or_(Coupon.expires_at.is_(None), Coupon.expires_at > now_utc))
            .order_by(Coupon.id.desc())
        )
        coupons = result.scalars().all()
        data = []
        for c in coupons:
            jalali_exp = None
            if c.expires_at and jdatetime:
                try:
                    pj = jdatetime.datetime.fromgregorian(datetime=c.expires_at)
                    jalali_exp = f"{pj.year}/{pj.month:02d}/{pj.day:02d}"
                except Exception:
                    pass
            data.append({
                "id": c.id,
                "code": c.code,
                "discount_percent": c.discount_percent,
                "discount_amount": c.discount_amount,
                "max_uses": c.max_uses,
                "used_count": c.used_count,
                "expires_at": c.expires_at.strftime("%Y-%m-%d") if c.expires_at else None,
                "expires_at_jalali": jalali_exp,
                "is_active": c.is_active,
            })
    return web.json_response({"ok": True, "coupons": data})


async def post_admin_coupon_save(request: web.Request) -> web.Response:
    """Create a new discount coupon."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    code = str(body.get("code") or "").strip().upper()
    if not code:
        return web.json_response({"ok": False, "error": "کد تخفیف الزامی است."}, status=400)

    try:
        percent = int(body.get("discount_percent", 0))
        amount = int(body.get("discount_amount", 0))
        max_uses = int(body.get("max_uses", 0))
        expires_days = int(body.get("expires_days", 0))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "مقادیر عددی نامعتبر هستند."}, status=400)

    if percent <= 0 and amount <= 0:
        return web.json_response({"ok": False, "error": "درصد تخفیف یا مبلغ تخفیف باید مشخص باشد."}, status=400)

    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days) if expires_days > 0 else None
    is_active = bool(body.get("is_active", True))

    async with db_session(request) as session:
        existing = await session.execute(select(Coupon).where(Coupon.code == code))
        if existing.scalar_one_or_none():
            return web.json_response({"ok": False, "error": "کد تخفیف با این نام از قبل وجود دارد."}, status=400)

        coupon = Coupon(
            code=code,
            discount_percent=percent,
            discount_amount=amount,
            max_uses=max_uses,
            expires_at=expires_at,
            is_active=is_active,
        )
        session.add(coupon)
        session.add(AdminLog(admin_id=admin["id"], action="create_coupon", detail=f"ساخت کوپن {code} ({percent}%)"))
        await session.commit()

    return web.json_response({"ok": True, "message": f"کد تخفیف {code} با موفقیت ساخته شد."})


async def post_admin_coupon_toggle(request: web.Request) -> web.Response:
    """Toggle active status of a coupon."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    coupon_id = body.get("id")
    if not coupon_id:
        return web.json_response({"ok": False, "error": "شناسه کوپن الزامی است."}, status=400)

    async with db_session(request) as session:
        coupon = await session.get(Coupon, int(coupon_id))
        if not coupon:
            return web.json_response({"ok": False, "error": "کوپن یافت نشد."}, status=404)

        coupon.is_active = bool(body.get("is_active", not coupon.is_active))
        await session.commit()

    return web.json_response({"ok": True, "is_active": coupon.is_active, "message": "وضعیت کوپن تغییر یافت."})


async def post_admin_coupon_delete(request: web.Request) -> web.Response:
    """Delete a coupon."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    coupon_id = body.get("id")
    if not coupon_id:
        return web.json_response({"ok": False, "error": "شناسه کوپن الزامی است."}, status=400)

    async with db_session(request) as session:
        coupon = await session.get(Coupon, int(coupon_id))
        if not coupon:
            return web.json_response({"ok": False, "error": "کوپن یافت نشد."}, status=404)

        await session.delete(coupon)
        session.add(AdminLog(admin_id=admin["id"], action="delete_coupon", detail=f"حذف کوپن {coupon.code}"))
        await session.commit()

    return web.json_response({"ok": True, "message": "کد تخفیف با موفقیت حذف شد."})


async def get_admin_coupon_usages(request: web.Request) -> web.Response:
    """Get list of users who redeemed a specific coupon."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    coupon_id_raw = request.match_info.get("id") or request.query.get("id")
    try:
        coupon_id = int(coupon_id_raw)
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "شناسه کوپن نامعتبر است."}, status=400)

    try:
        async with db_session(request) as session:
            coupon_repo = CouponRepository(session)
            user_repo = UserRepository(session)
            coupon = await coupon_repo.get_by_id(coupon_id)
            if not coupon:
                return web.json_response({"ok": False, "error": "کد تخفیف یافت نشد."}, status=404)

            usages = await coupon_repo.get_usages(coupon_id)
            items = []
            for u in usages:
                user = await user_repo.get_by_telegram_id(u.telegram_id)
                items.append({
                    "id": u.id,
                    "telegram_id": u.telegram_id,
                    "username": user.username if user else None,
                    "full_name": getattr(user, "full_name", None),
                    "order_id": u.order_id,
                    "discount_applied": u.discount_applied or 0,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                })

            return web.json_response({
                "ok": True,
                "coupon": {
                    "id": coupon.id,
                    "code": coupon.code,
                    "discount_percent": coupon.discount_percent,
                    "discount_amount": coupon.discount_amount,
                    "used_count": coupon.used_count,
                    "max_uses": coupon.max_uses,
                },
                "usages": items,
            })
    except Exception as exc:
        logger.exception("Error in get_admin_coupon_usages: %s", exc)
        return web.json_response({"ok": False, "error": "خطا در دریافت لیست استفاده‌کنندگان"}, status=500)
