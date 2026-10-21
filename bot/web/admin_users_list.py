"""Admin Users List and Bulk Actions API."""
import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Any

from aiohttp import web

from bot.common.helpers import get_limit_bytes, get_used_bytes
from bot.db.models import AdminLog, User
from bot.db.repositories.user_repo import UserRepository
from bot.web.admin_common import _check_admin, db_session

try:
    import jdatetime
except ImportError:
    jdatetime = None

logger = logging.getLogger(__name__)


async def _extract_online_telegram_ids(remnawave: Any) -> set[int]:
    """Collect telegram IDs of active/connected users."""
    online_ids: set[int] = set()
    try:
        sessions = await remnawave.get_active_sessions() or []
        for s in sessions:
            user_obj = s.get("user") if isinstance(s.get("user"), dict) else {}
            tid = (
                s.get("telegramId")
                or s.get("telegram_id")
                or user_obj.get("telegramId")
                or user_obj.get("telegram_id")
            )
            if not tid and user_obj.get("username", "").startswith("tg_"):
                try:
                    tid = int(user_obj["username"].replace("tg_", ""))
                except ValueError:
                    pass
            if tid:
                online_ids.add(int(tid))
        if not online_ids:
            hwid_devs = await remnawave.get_all_hwid_devices(size=300) or []
            active_uids = {d.get("userId") for d in hwid_devs if d.get("userId")}
            if active_uids:
                p_users = await remnawave.get_all_panel_users() or []
                for pu in p_users:
                    if pu.get("id") in active_uids and pu.get("telegramId"):
                        online_ids.add(int(pu["telegramId"]))
    except Exception as exc:
        logger.debug("Failed fetching online sessions for admin: %s", exc)
    return online_ids


def _serialize_user_item(
    u: User,
    panel_users: list[dict[str, Any]],
    balances: dict[int, int],
    online_ids: set[int],
    now_utc: datetime,
    status_filter: str,
) -> dict[str, Any] | None:
    """Format single user record and apply status filtering."""
    p = panel_users[0] if panel_users else {}
    panel_exists = bool(panel_users)

    used_bytes = get_used_bytes(p) if panel_exists else 0
    limit_bytes = get_limit_bytes(p) if panel_exists else 0
    used_gb = round(used_bytes / (1024**3), 2)
    limit_gb = round(limit_bytes / (1024**3), 2)

    if limit_bytes > 0:
        remaining_gb = max(0.0, round((limit_bytes - used_bytes) / (1024**3), 2))
    else:
        remaining_gb = -1.0 if panel_exists else 0.0

    days_left = None
    expire_jalali_str = ""
    expire_at_str = p.get("expireAt")
    if expire_at_str:
        try:
            exp_dt = datetime.fromisoformat(str(expire_at_str).replace("Z", "+00:00"))
            delta = exp_dt - now_utc
            days_left = max(0, int(math.ceil(delta.total_seconds() / 86400.0))) if delta.total_seconds() > 0 else 0
            if jdatetime:
                exp_j = jdatetime.datetime.fromgregorian(datetime=exp_dt)
                expire_jalali_str = f"{exp_j.year}/{exp_j.month:02d}/{exp_j.day:02d}"
        except Exception:
            pass

    is_online = (u.telegram_id in online_ids) if online_ids else False
    is_expiring = False
    is_expired = False
    if panel_exists:
        status_up = str(p.get("status") or "").upper()
        if (days_left is not None and days_left <= 0) or status_up == "EXPIRED" or (remaining_gb == 0.0 and limit_bytes > 0):
            is_expired = True

        if not is_expired:
            if (days_left is not None and 0 < days_left <= 3) or (0 <= remaining_gb <= 2.0 and limit_bytes > 0):
                is_expiring = True

    if status_filter == "expiring" and not is_expiring:
        return None
    if status_filter == "expired" and not is_expired:
        return None

    profile_name = getattr(u, "full_name", None)
    if not profile_name:
        p_desc = p.get("description") if (p and p.get("description") and p.get("description") != u.username and not str(p.get("description")).startswith("@")) else None
        p_name = p.get("name") if (p and p.get("name") and p.get("name") != u.username and not str(p.get("name")).startswith("@")) else None
        profile_name = p_desc or p_name

    user_reg_jalali = ""
    if getattr(u, "created_at", None) and jdatetime:
        try:
            reg_dt = u.created_at
            j_reg = jdatetime.datetime.fromgregorian(
                datetime=reg_dt if reg_dt.tzinfo else reg_dt.replace(tzinfo=timezone.utc)
            )
            user_reg_jalali = f"{j_reg.year}/{j_reg.month:02d}/{j_reg.day:02d}"
        except Exception:
            pass

    return {
        "telegram_id": u.telegram_id,
        "username": u.username,
        "full_name": profile_name or f"کاربر {u.telegram_id}",
        "wallet_balance": balances.get(u.telegram_id, 0),
        "is_banned": u.is_banned,
        "is_online": is_online,
        "is_expiring": is_expiring,
        "is_expired": is_expired,
        "avatar_url": f"/api/user/avatar?user_id={u.telegram_id}",
        "phone_number": u.phone_number if getattr(u, "phone_number", None) else "",
        "birth_date": u.birth_date if getattr(u, "birth_date", None) else "",
        "created_at": u.created_at.isoformat() if getattr(u, "created_at", None) else None,
        "created_at_jalali": user_reg_jalali,
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
    }


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
    remnawave = request.app["remnawave"]

    async with db_session(request) as session:
        user_repo = UserRepository(session)
        online_ids = await _extract_online_telegram_ids(remnawave)

        condition = None
        if status_filter == "banned":
            condition = User.is_banned.is_(True)
        elif status_filter == "online":
            condition = User.telegram_id.in_(list(online_ids)) if online_ids else User.telegram_id.in_([-1])

        if query:
            users = await user_repo.search(query, limit=limit)
            total = len(users)
        else:
            total = await user_repo.count(condition)
            users = await user_repo.list_paginated(offset, limit, condition)

        balances = await user_repo.balances_for([u.telegram_id for u in users])

    async def _fetch_single_panel(uid: int):
        try:
            return await asyncio.wait_for(remnawave.get_users_by_telegram_id(uid), timeout=4.0) or []
        except Exception as exc:
            logger.debug("Failed fetching panel user for %s: %s", uid, exc)
            return []

    panel_fetch_results = await asyncio.gather(*[_fetch_single_panel(u.telegram_id) for u in users])
    now_utc = datetime.now(timezone.utc)
    user_items = []
    for u, p_users in zip(users, panel_fetch_results, strict=True):
        item = _serialize_user_item(u, p_users if isinstance(p_users, list) else [], balances, online_ids, now_utc, status_filter)
        if item is not None:
            user_items.append(item)

    return web.json_response({"ok": True, "users": user_items, "total": total, "page": page, "limit": limit})


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

    remnawave = request.app["remnawave"]
    all_users = await remnawave.get_all_panel_users(size=2000) or []
    if not all_users:
        return web.json_response({"ok": False, "error": "هیچ کاربری در پنل یافت نشد."}, status=404)

    target_users = [u for u in all_users if (u.get("status") or "").upper() == "ACTIVE"] if target == "all_active" else all_users
    if not target_users:
        return web.json_response({"ok": False, "error": "هیچ کاربری با فیلتر مشخص‌شده یافت نشد."}, status=404)

    extra_gb = amount if action_type == "add_traffic" else 0
    extra_days = amount if action_type == "add_days" else 0
    res = await remnawave.bulk_update_users(target_users, extra_gb=extra_gb, extra_days=extra_days)

    action_label = f"افزایش {amount} گیگابایت حجم" if action_type == "add_traffic" else f"تمدید {amount} روزه اعتبار"
    detail_msg = f"{action_label} برای {res['success_count']} کاربر اعمال شد."
    try:
        async with db_session(request) as session:
            session.add(AdminLog(admin_id=admin.get("telegram_id", 0), action="BULK_USERS_UPDATE", detail=detail_msg))
            await session.commit()
    except Exception as e:
        logger.warning("Failed to save AdminLog for bulk action: %s", e)

    return web.json_response({
        "ok": True,
        "message": f"{action_label} به {res['success_count']} کاربر با موفقیت اعمال شد.",
        "details": res,
    })
