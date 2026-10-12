"""Admin Support Tickets & Live Chat API endpoints."""
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
from bot.web.admin_common import _check_admin, db_session, format_service_name_icon_first
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


async def get_admin_ticket_threads(request: web.Request) -> web.Response:
    """Return active user conversation threads (pending receipts + recent support messages)."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    cache: FastCache = request.app["cache"]

    threads: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    async with db_session(request) as session:
        # 1. Prioritize users with pending topups
        pending_res = await session.execute(
            select(Topup)
            .where(Topup.status == "pending")
            .order_by(Topup.created_at.desc())
        )
        pending_topups = pending_res.scalars().all()
        user_repo = UserRepository(session)

        for t in pending_topups:
            if t.telegram_id in seen_ids:
                continue
            seen_ids.add(t.telegram_id)
            user = await user_repo.get_by_telegram_id(t.telegram_id)
            u_name = (getattr(user, "full_name", None) or (f"@{user.username}" if user and user.username else f"کاربر {t.telegram_id}")).strip()

            chat_msgs = await cache.get(f"support:chat:{t.telegram_id}") or []
            last_msg = chat_msgs[-1]["text"] if chat_msgs else f"فیش واریزی {t.id} ({t.amount:,} تومان)"
            last_time = chat_msgs[-1].get("created_at") if chat_msgs else (t.created_at.strftime("%H:%M") if t.created_at else "—")

            threads.append({
                "telegram_id": t.telegram_id,
                "full_name": u_name,
                "username": user.username if user else None,
                "has_pending_topup": True,
                "topup_id": t.id,
                "topup_amount": t.amount,
                "last_message": last_msg,
                "last_time": last_time,
                "timestamp": int(t.created_at.timestamp()) if t.created_at else 0,
            })

        # 2. Add other active threads from cache
        active_ids = await cache.get("support:active_thread_ids") or []
        for tid in active_ids:
            try:
                tid_int = int(tid)
            except (ValueError, TypeError):
                continue
            if tid_int in seen_ids:
                continue
            seen_ids.add(tid_int)
            user = await user_repo.get_by_telegram_id(tid_int)
            u_name = (getattr(user, "full_name", None) or (f"@{user.username}" if user and user.username else f"کاربر {tid_int}")).strip()
            chat_msgs = await cache.get(f"support:chat:{tid_int}") or []
            if not chat_msgs:
                continue
            last_msg = chat_msgs[-1]["text"]
            last_time = chat_msgs[-1].get("created_at", "—")
            threads.append({
                "telegram_id": tid_int,
                "full_name": u_name,
                "username": user.username if user else None,
                "has_pending_topup": False,
                "topup_id": None,
                "topup_amount": 0,
                "last_message": last_msg,
                "last_time": last_time,
                "timestamp": chat_msgs[-1].get("timestamp", 0),
            })

    threads.sort(key=lambda x: (x["has_pending_topup"], x.get("timestamp", 0)), reverse=True)
    return web.json_response({"ok": True, "threads": threads})


async def get_admin_ticket_messages(request: web.Request) -> web.Response:
    """Return chat conversation history for a specific user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    target_id_raw = request.query.get("telegram_id")
    if not target_id_raw:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    try:
        target_id = int(target_id_raw)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "شناسه کاربر نامعتبر است."}, status=400)

    cache: FastCache = request.app["cache"]

    try:
        async with db_session(request) as session:
            user_repo = UserRepository(session)
            wallet_repo = WalletRepository(session)
            user = await user_repo.get_by_telegram_id(target_id)
            u_name = (getattr(user, "full_name", None) or (f"@{user.username}" if user and user.username else f"کاربر {target_id}")).strip()
            wallet = await wallet_repo.get_wallet(target_id)
            balance = wallet.balance if wallet else 0

            topup_res = await session.execute(
                select(Topup)
                .where(Topup.telegram_id == target_id, Topup.status == "pending")
                .order_by(Topup.created_at.desc())
                .limit(1)
            )
            pending_topup = topup_res.scalar_one_or_none()

        chat_msgs = await cache.get(f"support:chat:{target_id}") or []
    except Exception as exc:
        logger.error("Error in get_admin_ticket_messages for user %s: %s", target_id, exc, exc_info=True)
        return web.json_response({
            "ok": True,
            "user": {
                "telegram_id": target_id,
                "full_name": f"کاربر {target_id}",
                "username": None,
                "wallet_balance": 0,
                "pending_topup_id": None,
                "pending_amount": None,
            },
            "messages": [],
        })

    if not chat_msgs and pending_topup:
        time_str = pending_topup.created_at.strftime("%H:%M") if pending_topup.created_at else "—"
        receipt_text = f"فیش واریزی {pending_topup.id} به مبلغ {pending_topup.amount:,} تومان ثبت شد."
        if pending_topup.receipt_hash:
            receipt_text += f"\nکد پیگیری: {pending_topup.receipt_hash}"
        chat_msgs = [{
            "id": f"topup_{pending_topup.id}",
            "sender": "system",
            "text": receipt_text,
            "created_at": time_str,
            "timestamp": int(pending_topup.created_at.timestamp()) if pending_topup.created_at else 0,
        }]

    return web.json_response({
        "ok": True,
        "user": {
            "telegram_id": target_id,
            "full_name": u_name,
            "username": user.username if user else None,
            "wallet_balance": balance,
            "pending_topup_id": pending_topup.id if pending_topup else None,
            "pending_amount": pending_topup.amount if pending_topup else None,
        },
        "messages": chat_msgs,
    })


async def post_admin_reply_ticket(request: web.Request) -> web.Response:
    """Send an instant reply message from admin to user via Telegram Bot and record into thread history."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    target_id_raw = body.get("telegram_id")
    reply_text = str(body.get("reply_text") or "").strip()

    if not target_id_raw or not reply_text:
        return web.json_response({"ok": False, "error": "شناسه کاربر و متن پاسخ الزامی است."}, status=400)

    try:
        target_id = int(target_id_raw)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "شناسه کاربر نامعتبر است."}, status=400)

    bot = request.app["bot"]
    msg_formatted = f"💬 <b>پاسخ پشتیبانی به پیام شما:</b>\n\n{reply_text}"
    try:
        await bot.send_message(chat_id=target_id, text=msg_formatted, parse_mode="HTML")
    except Exception as exc:
        logger.warning("Failed to send reply to user %s: %s", target_id, exc)
        return web.json_response({"ok": False, "error": f"خطا در ارسال به تلگرام: {exc}"}, status=500)

    cache: FastCache = request.app["cache"]
    now_ts = int(time.time())
    now_dt = datetime.fromtimestamp(now_ts)
    chat_key = f"support:chat:{target_id}"
    chat_msgs = await cache.get(chat_key) or []
    new_msg = {
        "id": f"admin_{int(now_ts * 1000)}",
        "sender": "admin",
        "text": reply_text,
        "created_at": now_dt.strftime("%H:%M"),
        "timestamp": now_ts,
    }
    chat_msgs.append(new_msg)
    if len(chat_msgs) > 50:
        chat_msgs = chat_msgs[-50:]
    await cache.set(chat_key, chat_msgs, ttl_seconds=86400 * 30)

    active_ids = await cache.get("support:active_thread_ids") or []
    if target_id not in active_ids:
        active_ids.insert(0, target_id)
        if len(active_ids) > 100:
            active_ids = active_ids[:100]
        await cache.set("support:active_thread_ids", active_ids, ttl_seconds=86400 * 30)

    return web.json_response({
        "ok": True,
        "message": "پاسخ با موفقیت ارسال شد.",
        "chat_message": new_msg,
    })
