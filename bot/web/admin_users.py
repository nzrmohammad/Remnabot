"""Admin Users Management API endpoints."""
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

        # Collect online user Telegram IDs if available
        online_telegram_ids: set[int] = set()
        try:
            sessions = await remnawave.get_active_sessions() or []
            for s in sessions:
                user_obj = s.get("user") if isinstance(s.get("user"), dict) else {}
                tid = s.get("telegramId") or s.get("telegram_id") or user_obj.get("telegramId") or user_obj.get("telegram_id")
                if not tid and user_obj.get("username", "").startswith("tg_"):
                    try:
                        tid = int(user_obj["username"].replace("tg_", ""))
                    except ValueError:
                        pass
                if tid:
                    online_telegram_ids.add(int(tid))
            if not online_telegram_ids:
                hwid_devs = await remnawave.get_all_hwid_devices(size=300) or []
                active_uids = {d.get("userId") for d in hwid_devs if d.get("userId")}
                if active_uids:
                    p_users = await remnawave.get_all_panel_users() or []
                    for pu in p_users:
                        if pu.get("id") in active_uids and pu.get("telegramId"):
                            online_telegram_ids.add(int(pu["telegramId"]))
        except Exception as exc:
            logger.debug("Failed fetching online sessions for admin: %s", exc)

        condition = None
        if status_filter == "banned":
            condition = User.is_banned.is_(True)
        elif status_filter == "online":
            if online_telegram_ids:
                condition = User.telegram_id.in_(list(online_telegram_ids))
            else:
                condition = User.telegram_id.in_([-1])  # Empty match

        if query:
            users = await user_repo.search(query, limit=limit)
            total = len(users)
        else:
            total = await user_repo.count(condition)
            users = await user_repo.list_paginated(offset, limit, condition)

        balances = await user_repo.balances_for([u.telegram_id for u in users])

        # Fetch subscriptions and compute remaining volume and remaining days
        user_items = []
        now_utc = datetime.now(timezone.utc)

        async def _fetch_single_panel(uid: int):
            try:
                return await asyncio.wait_for(remnawave.get_users_by_telegram_id(uid), timeout=4.0) or []
            except Exception as exc:
                logger.debug("Failed fetching panel user for %s: %s", uid, exc)
                return []

        panel_fetch_results = await asyncio.gather(*[_fetch_single_panel(u.telegram_id) for u in users])

        for u, panel_users in zip(users, panel_fetch_results):
            if not isinstance(panel_users, list):
                panel_users = []
            p = panel_users[0] if panel_users else {}
            panel_exists = bool(panel_users)

            used_bytes = get_used_bytes(p) if panel_exists else 0
            limit_bytes = get_limit_bytes(p) if panel_exists else 0
            used_gb = round(used_bytes / (1024**3), 2)
            limit_gb = round(limit_bytes / (1024**3), 2)

            if limit_bytes > 0:
                remaining_gb = max(0.0, round((limit_bytes - used_bytes) / (1024**3), 2))
            else:
                remaining_gb = -1.0 if panel_exists else 0.0  # -1 signifies unlimited

            days_left = None
            expire_jalali_str = ""
            expire_at_str = p.get("expireAt")
            if expire_at_str:
                try:
                    exp_dt = datetime.fromisoformat(str(expire_at_str).replace("Z", "+00:00"))
                    delta = exp_dt - now_utc
                    if delta.total_seconds() > 0:
                        days_left = int(math.ceil(delta.total_seconds() / 86400.0))
                    else:
                        days_left = 0
                    if jdatetime:
                        exp_j = jdatetime.datetime.fromgregorian(datetime=exp_dt)
                        expire_jalali_str = f"{exp_j.year}/{exp_j.month:02d}/{exp_j.day:02d}"
                except Exception:
                    pass

            is_online = (u.telegram_id in online_telegram_ids) if online_telegram_ids else False
            is_expiring = False
            is_expired = False
            if panel_exists:
                status_up = str(p.get("status") or "").upper()
                if days_left is not None and days_left <= 0:
                    is_expired = True
                elif status_up == "EXPIRED":
                    is_expired = True
                elif remaining_gb == 0.0 and limit_bytes > 0:
                    is_expired = True

                if not is_expired:
                    if days_left is not None and 0 < days_left <= 3:
                        is_expiring = True
                    elif 0 <= remaining_gb <= 2.0 and limit_bytes > 0:
                        is_expiring = True

            # If filter is expiring or expired and not matched, skip
            if status_filter == "expiring" and not is_expiring:
                continue
            if status_filter == "expired" and not is_expired:
                continue

            # Determine real Telegram profile name:
            profile_name = getattr(u, "full_name", None)
            if not profile_name:
                p_desc = p.get("description") if (p and p.get("description") and p.get("description") != u.username and not str(p.get("description")).startswith("@")) else None
                p_name = p.get("name") if (p and p.get("name") and p.get("name") != u.username and not str(p.get("name")).startswith("@")) else None
                profile_name = p_desc or p_name

            full_name = profile_name or f"کاربر {u.telegram_id}"

            user_items.append({
                "telegram_id": u.telegram_id,
                "username": u.username,
                "full_name": full_name,
                "wallet_balance": balances.get(u.telegram_id, 0),
                "is_banned": u.is_banned,
                "is_online": is_online,
                "is_expiring": is_expiring,
                "is_expired": is_expired,
                "avatar_url": f"/api/user/avatar?user_id={u.telegram_id}",
                "panel_account": {
                    "exists": panel_exists,
                    "status": p.get("status", "NONE"),
                    "used_traffic_gb": used_gb,
                    "limit_traffic_gb": limit_gb,
                    "remaining_traffic_gb": remaining_gb,
                    "days_left": days_left,
                    "expire_jalali": expire_jalali_str,
                    "expire_at": expire_at_str,
                    "subscription_url": p.get("subscriptionUrl") or p.get("subscription_url") or "",
                } if panel_exists else None,
            })

        return web.json_response({
            "ok": True,
            "users": user_items,
            "total": total,
            "page": page,
            "limit": limit,
        })


async def post_admin_modify_user(request: web.Request) -> web.Response:
    """Add traffic (GB) and/or extend days for a user in a unified action."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    target_id = body.get("telegram_id")
    action = body.get("action")

    # Unified traffic_gb and days, or legacy single action
    traffic_gb = 0.0
    days = 0

    if "traffic_gb" in body or "days" in body:
        try:
            traffic_gb = max(0.0, float(body.get("traffic_gb") or 0))
        except (ValueError, TypeError):
            traffic_gb = 0.0
        try:
            days = max(0, int(body.get("days") or 0))
        except (ValueError, TypeError):
            days = 0
    elif action == "traffic":
        try:
            traffic_gb = max(0.0, float(body.get("amount") or 0))
        except (ValueError, TypeError):
            traffic_gb = 0.0
    elif action == "days":
        try:
            days = max(0, int(body.get("amount") or 0))
        except (ValueError, TypeError):
            days = 0

    if not target_id or (traffic_gb <= 0 and days <= 0):
        return web.json_response({"ok": False, "error": "حداقل یکی از مقادیر حجم یا روز را وارد کنید."}, status=400)

    remnawave = request.app["remnawave"]
    session_factory = request.app["session_factory"]

    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": False, "error": "اکانتی در پنل برای این کاربر یافت نشد."}, status=404)

    puser = panel_users[0]
    primary_id = puser.get("id")

    cur_limit = get_limit_bytes(puser)
    cur_exp_str = puser.get("expireAt")
    now = datetime.now(timezone.utc)

    new_limit = cur_limit
    if traffic_gb > 0:
        new_limit += int(traffic_gb * 1024 * 1024 * 1024)

    new_exp_iso = cur_exp_str
    if days > 0:
        base_dt = now
        if cur_exp_str:
            try:
                dt = datetime.fromisoformat(str(cur_exp_str).replace("Z", "+00:00"))
                if dt > now:
                    base_dt = dt
            except Exception:
                pass
        new_exp_iso = (base_dt + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif not new_exp_iso and traffic_gb > 0:
        new_exp_iso = (now + timedelta(days=36500)).strftime("%Y-%m-%dT%H:%M:%SZ")

    res = await remnawave.update_user_subscription(
        primary_id,
        expire_at_iso=new_exp_iso,
        traffic_limit_bytes=new_limit,
        status="ACTIVE",
    )
    if not res:
        return web.json_response({"ok": False, "error": "خطا در اعمال تغییرات در پنل رمناویو."}, status=502)

    parts = []
    if traffic_gb > 0:
        parts.append(f"افزایش {traffic_gb:g} GB ترافیک")
    if days > 0:
        parts.append(f"تمدید {days} روز اشتراک")
    log_detail = f"{' و '.join(parts)} کاربر {target_id}"

    # Record in admin log
    async with session_factory() as session:
        session.add(AdminLog(admin_id=admin["id"], action="modify_user_subscription", detail=log_detail))
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


async def post_admin_reset_trial(request: web.Request) -> web.Response:
    """Reset trial status so user can claim a test service again."""
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

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        user_repo = UserRepository(session)
        await user_repo.set_claimed_trial(int(target_id), claimed=False)
        session.add(
            AdminLog(
                admin_id=admin["id"],
                action="reset_trial",
                detail=f"فعال‌سازی مجدد تست برای کاربر {target_id}",
            )
        )
        await session.commit()

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")
    return web.json_response({
        "ok": True,
        "message": "قابلیت دریافت اشتراک تست برای این کاربر با موفقیت فعال شد.",
    })


async def post_admin_user_wallet(request: web.Request) -> web.Response:
    """Charge or deduct user wallet balance in Toman."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    target_id = body.get("telegram_id")
    try:
        amount = int(body.get("amount", 0))
    except (ValueError, TypeError):
        amount = 0

    reason = str(body.get("reason") or "شارژ دستی توسط مدیریت").strip()

    if not target_id or amount == 0:
        return web.json_response({"ok": False, "error": "مقدار مبلغ و کاربر نامعتبر است."}, status=400)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        wallet_repo = WalletRepository(session)
        wallet = await wallet_repo.get_wallet(int(target_id))
        old_balance = int(wallet.balance if wallet else 0)
        new_balance = max(0, old_balance + amount)
        wallet.balance = new_balance

        action_name = "wallet_charge" if amount > 0 else "wallet_deduct"
        detail_msg = f"{'افزایش' if amount > 0 else 'کسر'} {abs(amount):,} تومان موجودی کاربر {target_id} ({reason})"
        session.add(AdminLog(admin_id=admin["id"], action=action_name, detail=detail_msg))
        await session.commit()

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")
    await cache.delete("tma:admin:overview")

    bot = request.app.get("bot")
    if bot:
        sign = "+" if amount > 0 else "-"
        notif = (
            f"🔔 <b>تغییر موجودی کیف پول</b>\n\n"
            f"مبلغ: <b>{sign}{abs(amount):,} تومان</b>\n"
            f"موجودی جدید: <b>{new_balance:,} تومان</b>\n"
            f"توضیحات: {reason}"
        )
        try:
            await bot.send_message(chat_id=int(target_id), text=notif, parse_mode="HTML")
        except Exception:
            pass

    return web.json_response({
        "ok": True,
        "old_balance": old_balance,
        "new_balance": new_balance,
        "delta": amount,
        "message": f"موجودی کاربر با موفقیت به‌روزرسانی شد: {new_balance:,} تومان",
    })


async def post_admin_user_revoke_sub(request: web.Request) -> web.Response:
    """Revoke existing subscription URL and regenerate a new one via Remnawave."""
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
        return web.json_response({"ok": False, "error": "اکانتی در پنل برای این کاربر یافت نشد."}, status=404)

    primary_id = panel_users[0].get("id")
    revoked = await remnawave.revoke_user_subscription(primary_id)
    if not revoked:
        return web.json_response({"ok": False, "error": "خطا در برقراری ارتباط با پنل رمناویو."}, status=502)

    session_factory = request.app["session_factory"]
    async with session_factory() as session:
        session.add(
            AdminLog(
                admin_id=admin["id"],
                action="revoke_sub",
                detail=f"تولید مجدد لینک سابسکریپشن کاربر {target_id}",
            )
        )
        await session.commit()

    cache: FastCache = request.app["cache"]
    await cache.delete(f"tma:user:{target_id}:dashboard")

    new_sub = revoked.get("subscriptionUrl") or revoked.get("subscription_url") or ""
    return web.json_response({
        "ok": True,
        "subscription_url": new_sub,
        "message": "لینک سابسکریپشن کاربر با موفقیت باطل و مجدداً ایجاد شد.",
    })


async def get_admin_user_hwid_devices(request: web.Request) -> web.Response:
    """Fetch all active connected HWID devices for a specific user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    target_id = request.query.get("telegram_id")
    if not target_id:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": True, "devices": []})

    primary_id = panel_users[0].get("id")
    primary_uuid = panel_users[0].get("uuid")
    devices = await remnawave.get_user_hwid_devices(primary_id, user_uuid=primary_uuid)
    return web.json_response({"ok": True, "devices": devices or []})


async def get_admin_user_sessions(request: web.Request) -> web.Response:
    """Fetch real-time active connections and sessions for a single user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    target_id = request.query.get("telegram_id")
    if not target_id:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    try:
        panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
        if not panel_users:
            return web.json_response({
                "ok": True,
                "data": {
                    "isOnline": False,
                    "totalConnections": 0,
                    "uniqueIps": [],
                    "nodeConnections": [],
                }
            })

        primary_id = panel_users[0].get("id")
        user_sessions = await remnawave.get_user_live_sessions(primary_id)
        return web.json_response({"ok": True, "data": user_sessions})
    except Exception as exc:
        logger.warning("Error fetching user live sessions: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def get_admin_sessions_explorer(request: web.Request) -> web.Response:
    """Scan and fetch real-time active connections and sessions across all nodes (Sessions Explorer)."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    remnawave = request.app["remnawave"]
    try:
        data = await remnawave.get_live_sessions_explorer()
        # Convert any sets in data to lists for JSON serialization
        if data and isinstance(data, dict):
            for u in data.get("all_online_users", []):
                if "uniqueIps" in u and isinstance(u["uniqueIps"], set):
                    u["uniqueIps"] = sorted(list(u["uniqueIps"]))
            for u in data.get("multi_ip_users", []):
                if "uniqueIps" in u and isinstance(u["uniqueIps"], set):
                    u["uniqueIps"] = sorted(list(u["uniqueIps"]))
        return web.json_response({"ok": True, "data": data})
    except Exception as exc:
        logger.warning("Error fetching sessions explorer data: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def get_admin_user_srh(request: web.Request) -> web.Response:
    """Fetch Subscription Request History (SRH) for a specific user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    target_id = request.query.get("telegram_id")
    panel_user_id = request.query.get("user_id") or request.query.get("panel_user_id")
    panel_user_uuid = request.query.get("uuid")

    remnawave = request.app["remnawave"]

    if target_id:
        try:
            panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
            if panel_users:
                primary = panel_users[0]
                panel_user_id = panel_user_id or primary.get("id")
                panel_user_uuid = panel_user_uuid or primary.get("uuid")
        except Exception:
            pass

    if not panel_user_id and not panel_user_uuid:
        return web.json_response({"ok": False, "error": "شناسه کاربر الزامی است."}, status=400)

    raw_records = await remnawave.get_user_srh(
        panel_user_id or panel_user_uuid,
        user_uuid=panel_user_uuid,
        size=50,
    )

    def _parse_client_app(ua: str) -> dict[str, str]:
        ua_lower = (ua or "").lower()
        if "v2rayn" in ua_lower:
            return {"name": "v2rayN", "icon": "🚀", "tag": "Windows"}
        if "streisand" in ua_lower:
            return {"name": "Streisand", "icon": "🛡️", "tag": "iOS"}
        if "sing-box" in ua_lower or "singbox" in ua_lower:
            return {"name": "Sing-box", "icon": "📦", "tag": "Multi"}
        if "happ" in ua_lower:
            return {"name": "Happ Proxy", "icon": "⚡", "tag": "iOS / Android"}
        if "nekoray" in ua_lower or "nekobox" in ua_lower:
            return {"name": "NekoBox", "icon": "🐱", "tag": "Android / PC"}
        if "clash" in ua_lower or "meta" in ua_lower:
            return {"name": "Clash Meta", "icon": "🐱", "tag": "Multi"}
        if "shadowrocket" in ua_lower:
            return {"name": "Shadowrocket", "icon": "🚀", "tag": "iOS"}
        if "v2box" in ua_lower:
            return {"name": "V2Box", "icon": "📦", "tag": "iOS / Mac"}
        if "foxray" in ua_lower:
            return {"name": "FoXray", "icon": "🦊", "tag": "iOS"}
        if "karing" in ua_lower:
            return {"name": "Karing", "icon": "🚗", "tag": "Multi"}
        if "hiddify" in ua_lower:
            return {"name": "Hiddify", "icon": "✨", "tag": "Multi"}
        if "curl" in ua_lower or "wget" in ua_lower or "python" in ua_lower:
            return {"name": "Script / Bot", "icon": "🤖", "tag": "Bot"}
        short_ua = ua[:25] if ua else "کلاینت ناشناس"
        return {"name": short_ua, "icon": "🌐", "tag": "Client"}

    formatted = []
    now_utc = datetime.now(timezone.utc)
    for r in raw_records:
        ip = r.get("ip") or r.get("clientIp") or r.get("requestIp") or "—"
        ua = r.get("userAgent") or r.get("user_agent") or r.get("clientApp") or ""
        status_code = r.get("responseStatus") or r.get("status") or r.get("statusCode") or 200
        rule_name = r.get("srrRuleName") or r.get("ruleName") or ""
        client_info = _parse_client_app(ua)
        if rule_name and client_info["name"] == "کلاینت ناشناس":
            client_info["name"] = rule_name

        created_at_raw = (
            r.get("requestDate")
            or r.get("requestedAt")
            or r.get("request_date")
            or r.get("requested_at")
            or r.get("createdAt")
            or r.get("created_at")
            or r.get("updatedAt")
            or r.get("updated_at")
            or r.get("dateTime")
            or r.get("date_time")
            or r.get("timestamp")
            or r.get("time")
            or r.get("date")
            or r.get("lastActivity")
            or r.get("last_activity")
            or r.get("lastSeen")
            or r.get("last_seen")
        )
        if not created_at_raw and isinstance(r, dict):
            for k, v in r.items():
                if any(x in k.lower() for x in ("date", "time", "created", "requested")) and v:
                    created_at_raw = v
                    break

        rel_time = "—"
        date_str = "—"
        time_str = "—"
        if created_at_raw:
            try:
                if isinstance(created_at_raw, str) and created_at_raw.strip().isdigit():
                    created_at_raw = int(created_at_raw.strip())

                if isinstance(created_at_raw, (int, float)):
                    if created_at_raw > 1e11:
                        parsed_dt = datetime.fromtimestamp(created_at_raw / 1000, tz=timezone.utc)
                    else:
                        parsed_dt = datetime.fromtimestamp(created_at_raw, tz=timezone.utc)
                else:
                    s = str(created_at_raw).strip()
                    if s.endswith("Z"):
                        s = s[:-1] + "+00:00"
                    if "." in s:
                        parts = s.split(".")
                        tail = parts[1]
                        tz_part = ""
                        if "+" in tail:
                            tail_sub, tz_part = tail.split("+", 1)
                            tz_part = "+" + tz_part
                        elif "-" in tail:
                            tail_sub, tz_part = tail.split("-", 1)
                            tz_part = "-" + tz_part
                        else:
                            tail_sub = tail
                        s = f"{parts[0]}.{tail_sub[:6]}{tz_part}"
                    parsed_dt = datetime.fromisoformat(s)
                    if parsed_dt.tzinfo is None:
                        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)

                # Ensure parsed_dt is timezone-aware in UTC
                parsed_utc = parsed_dt.astimezone(timezone.utc)
                total_sec = (now_utc - parsed_utc).total_seconds()

                # If timestamp was recorded in local Tehran time (+3:30) without timezone, it appears in the future
                if -15000 <= total_sec <= -60:
                    parsed_utc = parsed_utc - timedelta(hours=3, minutes=30)
                    total_sec = (now_utc - parsed_utc).total_seconds()

                diff_sec = max(0, int(total_sec))
                if diff_sec < 60:
                    rel_time = "لحظاتی پیش"
                elif diff_sec < 3600:
                    rel_time = f"{diff_sec // 60} دقیقه پیش"
                elif diff_sec < 86400:
                    rel_time = f"{diff_sec // 3600} ساعت پیش"
                else:
                    rel_time = f"{diff_sec // 86400} روز پیش"

                tehran_tz = ZoneInfo("Asia/Tehran")
                dt_tehran = parsed_utc.astimezone(tehran_tz)
                time_str = dt_tehran.strftime("%H:%M")

                if jdatetime:
                    try:
                        p_j = jdatetime.datetime.fromgregorian(datetime=dt_tehran)
                        date_str = f"{p_j.year}/{p_j.month:02d}/{p_j.day:02d} {p_j.hour:02d}:{p_j.minute:02d}"
                        time_str = f"{p_j.hour:02d}:{p_j.minute:02d}"
                    except Exception:
                        date_str = dt_tehran.strftime("%Y/%m/%d %H:%M")
                else:
                    date_str = dt_tehran.strftime("%Y/%m/%d %H:%M")
            except Exception:
                date_str = str(created_at_raw)[:19]
                rel_time = "ثبت‌شده"

        is_success = str(status_code) in ("200", "201", "304", "OK")

        formatted.append({
            "ip": ip,
            "user_agent": ua,
            "client_name": client_info["name"],
            "client_icon": client_info["icon"],
            "client_tag": client_info["tag"],
            "status_code": status_code,
            "is_success": is_success,
            "relative_time": rel_time,
            "date_str": date_str,
            "time_str": time_str,
        })

    return web.json_response({
        "ok": True,
        "data": formatted,
        "count": len(formatted),
    })


async def post_admin_users_bulk_action(request: web.Request) -> web.Response:
    """Execute bulk traffic or validity days extension across users."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "فرمت داده نامعتبر است."}, status=400)

    action_type = body.get("action_type")
    try:
        amount = int(body.get("amount") or 0)
    except (ValueError, TypeError):
        amount = 0
    target = body.get("target") or "all_active"

    if action_type not in ("add_traffic", "add_days") or amount <= 0:
        return web.json_response({"ok": False, "error": "نوع عملیات یا مقدار عددی معتبر نیست."}, status=400)

    remnawave: RemnawaveClient = request.app["remnawave"]
    session_factory = request.app["session_factory"]

    all_users = await remnawave.get_all_panel_users(size=2000) or []
    if not all_users:
        return web.json_response({"ok": False, "error": "هیچ کاربری در پنل یافت نشد."}, status=404)

    if target == "all_active":
        target_users = [u for u in all_users if (u.get("status") or "").upper() == "ACTIVE"]
    else:
        target_users = all_users

    if not target_users:
        return web.json_response({"ok": False, "error": "هیچ کاربری با فیلتر مشخص‌شده یافت نشد."}, status=404)

    extra_gb = amount if action_type == "add_traffic" else 0
    extra_days = amount if action_type == "add_days" else 0

    res = await remnawave.bulk_update_users(target_users, extra_gb=extra_gb, extra_days=extra_days)

    action_label = f"افزایش {amount} گیگابایت حجم" if action_type == "add_traffic" else f"تمدید {amount} روزه اعتبار"
    detail_msg = f"{action_label} برای {res['success_count']} کاربر اعمال شد."
    try:
        async with session_factory() as session:
            session.add(AdminLog(
                admin_id=admin.get("telegram_id", 0),
                action="BULK_USERS_UPDATE",
                detail=detail_msg
            ))
            await session.commit()
    except Exception as e:
        logger.warning("Failed to save AdminLog for bulk action: %s", e)

    return web.json_response({
        "ok": True,
        "message": f"{action_label} به {res['success_count']} کاربر با موفقیت اعمال شد.",
        "details": res,
    })


async def post_admin_user_delete_hwid(request: web.Request) -> web.Response:
    """Disconnect/delete a single specific HWID device for a user."""
    admin = _check_admin(request)
    if not admin:
        return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_id = body.get("telegram_id")
    hwid = body.get("hwid")
    if not target_id or not hwid:
        return web.json_response({"ok": False, "error": "شناسه کاربر و شناسه دستگاه الزامی است."}, status=400)

    remnawave = request.app["remnawave"]
    panel_users = await remnawave.get_users_by_telegram_id(int(target_id))
    if not panel_users:
        return web.json_response({"ok": False, "error": "اکانتی در پنل یافت نشد."}, status=404)

    primary_id = panel_users[0].get("id")
    success = await remnawave.delete_hwid_device(primary_id, str(hwid))
    if not success:
        return web.json_response({"ok": False, "error": "خطا در قطع اتصال دستگاه."}, status=502)

    return web.json_response({"ok": True, "message": "اتصال دستگاه با موفقیت قطع شد."})
