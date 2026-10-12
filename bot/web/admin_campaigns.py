"""Admin Broadcasts, Marketing Campaigns, and Announcements API endpoints."""
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
from sqlalchemy import desc, func, select

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
from bot.web.admin_common import _check_admin, format_service_name_icon_first
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)

_BROADCAST_STATUSES: dict[str, dict[str, Any]] = {}


async def post_admin_broadcast(request: web.Request) -> web.Response:
    """Queue a broadcast message to bot users with audience filtering and live progress tracking."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    text = body.get("message")
    if not text:
        return web.json_response({"ok": False, "error": "متن پیام خالی است."}, status=400)

    target = str(body.get("target") or "all").strip().lower()
    bot = request.app["bot"]
    session_factory = request.app["session_factory"]
    remnawave = request.app["remnawave"]

    target_labels = {
        "all": "همه کاربران",
        "active": "کاربران با سرویس فعال",
        "expired": "کاربران منقضی شده",
        "buyers": "خریداران قبلی",
        "balance": "کاربران دارای موجودی",
    }
    label = target_labels.get(target, "کاربران انتخاب شده")

    async with session_factory() as session:
        recipients = await _resolve_broadcast_recipients(session, remnawave, target)

    broadcast_id = f"bcast_{int(datetime.now(timezone.utc).timestamp())}_{len(recipients)}"
    _BROADCAST_STATUSES[broadcast_id] = {
        "id": broadcast_id,
        "target": target,
        "target_label": label,
        "total": len(recipients),
        "sent": 0,
        "failed": 0,
        "is_completed": False,
        "start_time": datetime.now(timezone.utc).isoformat(),
    }

    async def _broadcast_worker():
        st = _BROADCAST_STATUSES[broadcast_id]
        for tid in recipients:
            try:
                await bot.send_message(chat_id=tid, text=text, parse_mode="HTML")
                st["sent"] += 1
                await asyncio.sleep(0.04)  # ~25 messages/sec rate limit
            except Exception:
                st["failed"] += 1
        st["is_completed"] = True
        logger.info(
            "Admin broadcast completed: id=%s target=%s sent=%d failed=%d",
            broadcast_id, target, st["sent"], st["failed"]
        )

    asyncio.create_task(_broadcast_worker())
    return web.json_response({
        "ok": True,
        "broadcast_id": broadcast_id,
        "message": f"ارسال پیام همگانی به {label} در حال انجام است.",
        "stats": _BROADCAST_STATUSES[broadcast_id],
    })


async def get_admin_broadcast_status(request: web.Request) -> web.Response:
    """Return status and report of an ongoing or completed broadcast."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    b_id = request.query.get("id")
    if not b_id or b_id not in _BROADCAST_STATUSES:
        return web.json_response({"ok": False, "error": "عملیات یافت نشد"}, status=404)

    return web.json_response({"ok": True, "stats": _BROADCAST_STATUSES[b_id]})


async def get_admin_campaigns(request: web.Request) -> web.Response:
    """Return list of ad/marketing campaigns with aggregated stats."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    session_factory = request.app["session_factory"]
    from bot.db.repositories.campaign_repo import CampaignRepository
    settings = request.app["settings"]
    bot = request.app.get("bot")
    bot_username = getattr(settings, "BOT_USERNAME", "") or ""
    if not bot_username and bot:
        me_obj = getattr(bot, "_me", None)
        if me_obj and getattr(me_obj, "username", None):
            bot_username = me_obj.username
        elif hasattr(bot, "get_me"):
            try:
                bot_info = await bot.get_me()
                bot_username = bot_info.username or ""
            except Exception:
                pass

    async with session_factory() as session:
        repo = CampaignRepository(session)
        stats = await repo.get_campaigns_with_stats(bot_username)
        return web.json_response({"ok": True, "bot_username": bot_username, "campaigns": stats})


async def post_admin_campaign_create(request: web.Request) -> web.Response:
    """Create a new ad/marketing campaign."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    name = str(body.get("name") or "").strip()
    code = str(body.get("code") or "").strip().lower()
    cost = int(body.get("cost") or 0)

    if not name or not code:
        return web.json_response({"ok": False, "error": "نام و شناسه کمپین الزامی است."}, status=400)

    import re
    if not re.match(r"^[a-zA-Z0-9_\-]+$", code):
        return web.json_response({"ok": False, "error": "شناسه کمپین فقط می‌تواند شامل حروف، اعداد، خط تیره و زیرخط باشد."}, status=400)

    session_factory = request.app["session_factory"]
    from bot.db.repositories.campaign_repo import CampaignRepository
    settings = request.app["settings"]
    bot = request.app.get("bot")
    bot_username = getattr(settings, "BOT_USERNAME", "") or ""
    if not bot_username and bot:
        me_obj = getattr(bot, "_me", None)
        if me_obj and getattr(me_obj, "username", None):
            bot_username = me_obj.username
        elif hasattr(bot, "get_me"):
            try:
                bot_info = await bot.get_me()
                bot_username = bot_info.username or ""
            except Exception:
                pass

    async with session_factory() as session:
        repo = CampaignRepository(session)
        existing = await repo.get_by_code(code)
        if existing:
            return web.json_response({"ok": False, "error": "این شناسه کمپین قبلاً تعریف شده است."}, status=400)

        created = await repo.create(code=code, name=name, cost=cost)
        deep_link = f"https://t.me/{bot_username}?start=ad_{created.code}" if bot_username else f"t.me/?start=ad_{created.code}"
        return web.json_response({
            "ok": True,
            "bot_username": bot_username,
            "campaign": {
                "id": created.id,
                "code": created.code,
                "name": created.name,
                "cost": created.cost,
                "deep_link": deep_link,
            }
        })


async def post_admin_campaign_delete(request: web.Request) -> web.Response:
    """Delete an ad/marketing campaign."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    cid = body.get("id")
    if not cid:
        return web.json_response({"ok": False, "error": "شناسه کمپین الزامی است."}, status=400)

    session_factory = request.app["session_factory"]
    from bot.db.repositories.campaign_repo import CampaignRepository

    async with session_factory() as session:
        repo = CampaignRepository(session)
        ok = await repo.delete(int(cid))
        return web.json_response({"ok": ok})
