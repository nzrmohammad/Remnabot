"""Admin API endpoints for Telegram Mini App Management Suite."""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from aiohttp import web
from sqlalchemy import func, select

from bot.db.models import AdminLog, AppSetting, Order, SupportMessage, Topup, User
from bot.db.repositories.app_setting_repo import AppSettingRepository
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.services.app_settings import get_store_settings
from bot.web.auth import get_authenticated_user
from bot.web.cache import FastCache

logger = logging.getLogger(__name__)


def _check_admin(request: web.Request) -> dict[str, Any] | None:
    user = get_authenticated_user(request)
    if not user or not user.get("is_admin"):
        return None
    return user


async def get_admin_overview(request: web.Request) -> web.Response:
    """Return high-level KPIs and cluster status for admin dashboard."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    cache: FastCache = request.app["cache"]
    cache_key = "tma:admin:overview"
    cached_data = await cache.get(cache_key)
    if cached_data:
        return web.json_response({"ok": True, "data": cached_data, "cached": True})

    session_factory = request.app["session_factory"]
    remnawave = request.app["remnawave"]

    async with session_factory() as session:
        # 1. Total users count in bot DB
        user_count_res = await session.execute(select(func.count(User.id)))
        total_bot_users = int(user_count_res.scalar_one() or 0)

        # 2. Today's revenue
        now_utc = datetime.now(timezone.utc)
        start_of_day = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
        rev_res = await session.execute(
            select(func.coalesce(func.sum(Order.amount), 0)).where(
                Order.created_at >= start_of_day,
                Order.status == "paid",
            )
        )
        today_revenue = int(rev_res.scalar_one() or 0)

        # 3. Pending topup receipts
        topup_res = await session.execute(
            select(func.count(Topup.id)).where(Topup.status == "pending")
        )
        pending_topups = int(topup_res.scalar_one() or 0)

        # 4. Open support tickets
        support_res = await session.execute(
            select(func.count(SupportMessage.admin_message_id))
        )
        open_tickets = int(support_res.scalar_one() or 0)

        # 5. Remnawave cluster metrics
        panel_users = await remnawave.get_all_panel_users(size=1000) or []
        active_panel_users = sum(1 for u in panel_users if u.get("status", "").upper() == "ACTIVE")

        # Sum of traffic used across panel
        total_traffic_bytes = sum(u.get("used_traffic", 0) for u in panel_users)
        total_traffic_gb = round(total_traffic_bytes / (1024 ** 3), 2)

        # Node information
        nodes = await remnawave.get_nodes() or []
        nodes_overview = []
        for n in nodes:
            nodes_overview.append({
                "id": n.get("id"),
                "name": n.get("name", "Node"),
                "country_code": n.get("country_code", "NL"),
                "status": n.get("status", "ONLINE"),
                "connected_users": n.get("connected_users", 0),
                "cpu_percent": n.get("cpu", 20),
                "ram_percent": n.get("memory", 45),
            })

        hwid_stats = await remnawave.get_hwid_stats() or {}
        online_devices = hwid_stats.get("online_devices", sum(n.get("connected_users", 0) for n in nodes_overview))

        data = {
            "metrics": {
                "total_users": total_bot_users,
                "active_panel_users": active_panel_users,
                "today_revenue_toman": today_revenue,
                "month_traffic_gb": total_traffic_gb,
                "online_devices": online_devices,
                "pending_topups": pending_topups,
                "open_tickets": open_tickets,
            },
            "nodes": nodes_overview,
        }

        await cache.set(cache_key, data, ttl_seconds=8)
        return web.json_response({"ok": True, "data": data, "cached": False})


async def get_admin_users(request: web.Request) -> web.Response:
    """Search and paginate users for admin management."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    query = request.query.get("q", "").strip()
    status_filter = request.query.get("filter", "all")
    page = max(1, int(request.query.get("page", 1)))
    limit = min(50, max(5, int(request.query.get("limit", 20))))
    offset = (page - 1) * limit

    session_factory = request.app["session_factory"]
    remnawave = request.app["remnawave"]

    async with session_factory() as session:
        user_repo = UserRepository(session)

        condition = None
        if status_filter == "banned":
            condition = User.is_banned.is_(True)

        if query:
            users = await user_repo.search(query, limit=limit)
            total = len(users)
        else:
            total = await user_repo.count(condition)
            users = await user_repo.list_paginated(offset, limit, condition)

        balances = await user_repo.balances_for([u.telegram_id for u in users])

        # Fetch subscriptions in batch or on demand
        user_items = []
        for u in users:
            panel_users = await remnawave.get_users_by_telegram_id(u.telegram_id) or []
            p = panel_users[0] if panel_users else {}

            user_items.append({
                "telegram_id": u.telegram_id,
                "username": u.username,
                "wallet_balance": balances.get(u.telegram_id, 0),
                "is_banned": u.is_banned,
                "panel_account": {
                    "exists": bool(panel_users),
                    "status": p.get("status", "NONE"),
                    "used_traffic_gb": round(p.get("used_traffic", 0) / (1024**3), 2),
                    "limit_traffic_gb": round(p.get("traffic_limit", 0) / (1024**3), 2),
                } if panel_users else None,
            })

        return web.json_response({
            "ok": True,
            "users": user_items,
            "total": total,
            "page": page,
            "limit": limit,
        })


async def post_admin_modify_user(request: web.Request) -> web.Response:
    """Add traffic (GB) or extend days for a user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    target_id = body.get("telegram_id")
    action = body.get("action")  # 'traffic' or 'days'
    amount = body.get("amount", 0)

    if not target_id or amount <= 0:
        return web.json_response({"ok": False, "error": "مقادیر وارد شده نامعتبر است."}, status=400)

    remnawave = request.app["remnawave"]
    session_factory = request.app["session_factory"]

    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": False, "error": "اکانتی در پنل برای این کاربر یافت نشد."}, status=404)

    primary_id = panel_users[0].get("id")

    if action == "traffic":
        bytes_delta = int(amount * 1024 * 1024 * 1024)
        await remnawave.update_user_subscription(primary_id, bandwidth_limit_delta=bytes_delta)
        log_detail = f"افزایش {amount} GB ترافیک به کاربر {target_id}"
    elif action == "days":
        seconds_delta = int(amount * 86400)
        await remnawave.update_user_subscription(primary_id, expire_delta_seconds=seconds_delta)
        log_detail = f"تمدید {amount} روز اشتراک کاربر {target_id}"
    else:
        return web.json_response({"ok": False, "error": "عملیات نامعتبر است."}, status=400)

    # Record in admin log
    async with session_factory() as session:
        session.add(AdminLog(admin_id=admin["id"], action=f"modify_{action}", detail=log_detail))
        await session.commit()

    # Clear caches
    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")
    await cache.delete("tma:admin:overview")

    return web.json_response({"ok": True, "message": log_detail})


async def post_admin_kill_sessions(request: web.Request) -> web.Response:
    """Disconnect all active HWID devices for a user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_id = body.get("telegram_id")
    if not target_id:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": False, "error": "اکانتی در پنل یافت نشد."}, status=404)

    primary_id = panel_users[0].get("id")
    devices = await remnawave.get_user_hwid_devices(primary_id)
    killed = 0
    for dev in devices:
        hwid = dev.get("hwid")
        if hwid:
            if await remnawave.delete_hwid_device(primary_id, hwid):
                killed += 1

    return web.json_response({"ok": True, "killed_devices": killed})


async def post_admin_toggle_ban(request: web.Request) -> web.Response:
    """Ban or unban a user in bot DB and Remnawave panel."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_id = body.get("telegram_id")
    ban_state = bool(body.get("ban", True))

    session_factory = request.app["session_factory"]
    remnawave = request.app["remnawave"]

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(int(target_id))
        if user:
            user.is_banned = ban_state
            await session.commit()

    # Panel status toggle
    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if panel_users:
        primary_id = panel_users[0].get("id")
        new_status = "DISABLED" if ban_state else "ACTIVE"
        await remnawave.set_user_status(primary_id, new_status)

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")

    return web.json_response({"ok": True, "banned": ban_state})


async def post_admin_reply_ticket(request: web.Request) -> web.Response:
    """Send an instant reply message from admin to user via Telegram Bot."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    target_id = body.get("telegram_id")
    reply_text = body.get("reply_text")

    if not target_id or not reply_text:
        return web.json_response({"ok": False, "error": "شناسه کاربر و متن پاسخ الزامی است."}, status=400)

    bot = request.app["bot"]
    msg_formatted = f"💬 <b>پاسخ پشتیبانی به پیام شما:</b>\n\n{reply_text}"
    try:
        await bot.send_message(chat_id=int(target_id), text=msg_formatted, parse_mode="HTML")
        return web.json_response({"ok": True, "message": "پاسخ برای کاربر ارسال شد."})
    except Exception as exc:
        logger.warning("Failed to send reply to user %s: %s", target_id, exc)
        return web.json_response({"ok": False, "error": f"خطا در ارسال به تلگرام: {exc}"}, status=500)


async def post_admin_broadcast(request: web.Request) -> web.Response:
    """Queue a broadcast message to all bot users."""
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

    bot = request.app["bot"]
    session_factory = request.app["session_factory"]

    async def _broadcast_worker():
        async with session_factory() as session:
            user_repo = UserRepository(session)
            users = await user_repo.all_users()

        sent = 0
        for u in users:
            try:
                await bot.send_message(chat_id=u.telegram_id, text=text, parse_mode="HTML")
                sent += 1
                await asyncio.sleep(0.04)  # ~25 messages/sec rate limit
            except Exception:
                pass
        logger.info("Admin broadcast completed: sent to %d users", sent)

    asyncio.create_task(_broadcast_worker())
    return web.json_response({"ok": True, "message": "ارسال پیام همگانی در پس‌زمینه آغاز شد."})


async def get_admin_topups(request: web.Request) -> web.Response:
    """Return list of pending card-to-card topups."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        wallet_repo = WalletRepository(session)
        user_repo = UserRepository(session)
        pending = await wallet_repo.list_pending_topups()

        items = []
        for t in pending:
            u = await user_repo.get_by_telegram_id(t.telegram_id)
            items.append({
                "id": t.id,
                "telegram_id": t.telegram_id,
                "username": u.username if u else None,
                "amount": t.amount,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "receipt_photo_id": t.receipt_photo_id,
            })
        return web.json_response({"ok": True, "topups": items})


async def post_admin_topup_action(request: web.Request) -> web.Response:
    """Approve or reject a pending card-to-card topup."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    topup_id = body.get("topup_id")
    approved = bool(body.get("approved", True))
    if not topup_id:
        return web.json_response({"ok": False, "error": "شناسه فیش الزامی است."}, status=400)

    session_factory = request.app["session_factory"]
    bot = request.app["bot"]

    async with session_factory() as session:
        wallet_repo = WalletRepository(session)
        claimed = await wallet_repo.claim_topup(int(topup_id), approved)
        if not claimed:
            return web.json_response({"ok": False, "error": "این فیش قبلاً تعیین وضعیت شده است."}, status=400)

        if approved:
            await wallet_repo.add_balance(claimed.telegram_id, claimed.amount)
            session.add(
                AdminLog(
                    admin_id=admin["id"],
                    action="topup_approved",
                    detail=f"تایید فیش #{claimed.id} و شارژ {claimed.amount:,} تومان برای {claimed.telegram_id}",
                )
            )
            msg = f"✅ <b>واریز شما تایید شد!</b>\n\nمبلغ {claimed.amount:,} تومان به کیف پول شما اضافه شد."
        else:
            session.add(
                AdminLog(
                    admin_id=admin["id"],
                    action="topup_rejected",
                    detail=f"رد فیش #{claimed.id} برای {claimed.telegram_id}",
                )
            )
            msg = "❌ <b>فیش ارسالی شما رد شد.</b>\n\nدر صورت وجود مغایرت با پشتیبانی در ارتباط باشید."

        await session.commit()

    # Clear cache
    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{claimed.telegram_id}:dashboard")
    await cache.delete("tma:admin:overview")

    # Send telegram notification
    try:
        await bot.send_message(chat_id=claimed.telegram_id, text=msg, parse_mode="HTML")
    except Exception as exc:
        logger.warning("Could not send topup decision notice to %s: %s", claimed.telegram_id, exc)

    return web.json_response({
        "ok": True,
        "message": "فیش با موفقیت تایید شد." if approved else "فیش با موفقیت رد شد.",
    })


async def get_admin_settings(request: web.Request) -> web.Response:
    """Return runtime editable app settings."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        store_settings = await get_store_settings(session)
        app_repo = AppSettingRepository(session)
        maint_val = await app_repo.get("maintenance")
        is_maintenance = maint_val == "1"

        data = {
            "maintenance": is_maintenance,
            "card_enabled": store_settings.card_enabled,
            "crypto_enabled": store_settings.crypto_enabled,
            "card_number": store_settings.card_number,
            "card_holder": store_settings.card_holder,
        }
        return web.json_response({"ok": True, "settings": data})


async def post_admin_settings(request: web.Request) -> web.Response:
    """Update runtime editable app settings."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        app_repo = AppSettingRepository(session)

        if "maintenance" in body:
            await app_repo.set("maintenance", "1" if body["maintenance"] else "0")
        if "card_enabled" in body:
            await app_repo.set("card_enabled", "1" if body["card_enabled"] else "0")
        if "crypto_enabled" in body:
            await app_repo.set("crypto_enabled", "1" if body["crypto_enabled"] else "0")
        if "card_number" in body:
            await app_repo.set("card_number", str(body["card_number"]).strip())
        if "card_holder" in body:
            await app_repo.set("card_holder", str(body["card_holder"]).strip())

        await session.commit()

    return web.json_response({"ok": True, "message": "تنظیمات با موفقیت ذخیره شد."})

