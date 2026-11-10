"""Lucky Wheel Service: Core business logic, anti-cheat, streaks and prize allocation.

Single Source of Truth (SSOT) shared by both Telegram Mini App and Telegram Bot.
"""
from __future__ import annotations

import logging
import random
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repositories.coupon_repo import CouponRepository
from bot.db.repositories.report_repo import ReportRepository
from bot.services.app_settings import get_store_settings
from bot.services.formatting import ltr_frag

logger = logging.getLogger(__name__)

# Configured prizes
WHEEL_PRIZES = [
    {"id": "1gb", "name": f"{ltr_frag('1 GB')} ترافیک هدیه", "icon": "🎁", "type": "traffic", "value": 1},
    {"id": "blank_1", "name": "پوچ (شانس بعدی فردا)", "icon": "❌", "type": "blank", "value": 0},
    {"id": "discount10", "name": f"{ltr_frag('10%')} کد تخفیف ویژه", "icon": "🎟", "type": "coupon", "code": "OFF10"},
    {"id": "500mb", "name": f"{ltr_frag('500 MB')} ترافیک هدیه", "icon": "⚡️", "type": "traffic", "value": 0.5},
    {"id": "2gb", "name": f"{ltr_frag('2 GB')} ترافیک هدیه (سوپر شانس)", "icon": "👑", "type": "traffic", "value": 2},
    {"id": "again", "name": "دوباره (شانس مجدد!)", "icon": "🔄", "type": "again", "value": 0},
]


async def invalidate_user_wheel_caches(cache: Any, telegram_id: int) -> None:
    if not cache or not hasattr(cache, "delete"):
        return
    for k in (
        f"tma:user:{telegram_id}:dashboard",
        f"tma:user:{telegram_id}:dashboard:default",
        f"tma:user:{telegram_id}:profile",
        f"tma:user:{telegram_id}:topup_info",
    ):
        await cache.delete(k)


async def get_wheel_status(
    session: AsyncSession,
    cache: Any,
    telegram_id: int,
    tz_name: str = "Asia/Tehran",
) -> dict[str, Any]:
    """Retrieve user's current lucky wheel status, streak, tickets and cooldown."""
    wheel_ts_key = f"tma:user:{telegram_id}:wheel_last_spin"
    now_ts = time.time()
    now_utc = datetime.now(timezone.utc)

    is_cooldown = False
    rem_secs = 0

    if cache and hasattr(cache, "get"):
        last_spin = await cache.get(wheel_ts_key)
        if last_spin is not None:
            try:
                elapsed = now_ts - float(last_spin)
                if elapsed < 86400:
                    is_cooldown = True
                    rem_secs = max(1, int(86400 - elapsed))
            except (ValueError, TypeError):
                pass

    user_res = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    db_user = user_res.scalar_one_or_none()

    if not is_cooldown and db_user and db_user.wheel_last_spin_at:
        db_last_spin_utc = db_user.wheel_last_spin_at
        if db_last_spin_utc.tzinfo is None:
            db_last_spin_utc = db_last_spin_utc.replace(tzinfo=timezone.utc)
        elapsed_db = (now_utc - db_last_spin_utc).total_seconds()
        if elapsed_db < 86400:
            is_cooldown = True
            rem_secs = max(1, int(86400 - elapsed_db))

    has_free_retry = False
    if cache and hasattr(cache, "get"):
        has_free_retry = bool(await cache.get(f"wheel:has_free_retry:{telegram_id}"))
    if has_free_retry:
        is_cooldown = False
        rem_secs = 0

    streak = int(getattr(db_user, "wheel_streak", 0) or 0) if db_user else 0
    spin_tickets = int(getattr(db_user, "spin_tickets", 0) or 0) if db_user else 0

    won_traffic = 0.0
    user_coupons: list[dict] = []
    if cache and hasattr(cache, "get"):
        try:
            won_traffic = float(await cache.get(f"wheel:total_won_traffic:{telegram_id}") or 0.0)
            user_coupons = (await cache.get(f"wheel:user_coupons:{telegram_id}")) or []
        except Exception:
            pass

    return {
        "can_spin": not is_cooldown or spin_tickets > 0,
        "is_cooldown": is_cooldown,
        "remaining_seconds": rem_secs,
        "hours_left": rem_secs // 3600,
        "mins_left": (rem_secs % 3600) // 60,
        "streak": max(1, streak) if streak > 0 else 0,
        "spin_tickets": spin_tickets,
        "total_won_traffic": won_traffic,
        "user_coupons": user_coupons,
    }


async def execute_lucky_wheel_spin(
    session: AsyncSession,
    remnawave: Any,
    cache: Any,
    bot: Any,
    telegram_id: int,
    use_ticket: bool = False,
    tz_name: str = "Asia/Tehran",
) -> dict[str, Any]:
    """Atomically execute lucky wheel spin, calculate anti-cheat prize, and apply rewards."""
    # 1. Require active panel subscription
    panel_users = await remnawave.get_users_by_telegram_id(telegram_id) or []
    has_active_sub = any(
        (u.get("status") or "").upper() == "ACTIVE" for u in panel_users
    )

    if not has_active_sub:
        return {
            "ok": False,
            "error": "برای استفاده از گردونه شانس، داشتن یک اشتراک فعال در پنل الزامی است.",
            "code": "sub_required",
        }

    # 2. Channel Join Gate check
    if session is not None:
        store = await get_store_settings(session)
        if getattr(store, "join_gate_enabled", False) and getattr(store, "join_gate_channel", ""):
            from bot.common.helpers import check_channel_membership
            is_member = await check_channel_membership(bot, store.join_gate_channel, telegram_id)
            if not is_member:
                channel_str = store.join_gate_channel.strip()
                channel_link = channel_str if channel_str.startswith("http") else f"https://t.me/{channel_str.lstrip('@')}"
                return {
                    "ok": False,
                    "error": "برای چرخاندن گردونه شانس، ابتدا باید در کانال ما عضو شوید.",
                    "code": "channel_required",
                    "channel_url": channel_link,
                }

    wheel_ts_key = f"tma:user:{telegram_id}:wheel_last_spin"
    now_ts = time.time()
    now_utc = datetime.now(timezone.utc)

    # 3. Lock user row
    db_user = None
    if session is not None:
        user_res = await session.execute(
            select(User).where(User.telegram_id == telegram_id).with_for_update()
        )
        db_user = user_res.scalar_one_or_none()

    # 4. Check cooldown & ticket
    last_spin = await cache.get(wheel_ts_key) if cache and hasattr(cache, "get") else None
    is_cooldown = False
    rem_secs = 0
    if last_spin is not None:
        try:
            elapsed = now_ts - float(last_spin)
            if elapsed < 86400:
                is_cooldown = True
                rem_secs = max(1, int(86400 - elapsed))
        except (ValueError, TypeError):
            pass

    if not is_cooldown and db_user and db_user.wheel_last_spin_at:
        db_last_spin_utc = db_user.wheel_last_spin_at
        if db_last_spin_utc.tzinfo is None:
            db_last_spin_utc = db_last_spin_utc.replace(tzinfo=timezone.utc)
        elapsed_db = (now_utc - db_last_spin_utc).total_seconds()
        if elapsed_db < 86400:
            is_cooldown = True
            rem_secs = max(1, int(86400 - elapsed_db))

    has_free_retry = False
    if cache and hasattr(cache, "get"):
        has_free_retry = bool(await cache.get(f"wheel:has_free_retry:{telegram_id}"))
    if has_free_retry:
        is_cooldown = False
        rem_secs = 0

    using_ticket = False
    if use_ticket:
        cur_tickets = int(getattr(db_user, "spin_tickets", 0) or 0) if db_user else 0
        if cur_tickets > 0:
            using_ticket = True
            if db_user:
                db_user.spin_tickets = cur_tickets - 1
        else:
            return {
                "ok": False,
                "error": "شما تیکت شانس کافی ندارید.",
                "code": "no_tickets",
            }
    else:
        if is_cooldown:
            hours = rem_secs // 3600
            mins = (rem_secs % 3600) // 60
            return {
                "ok": False,
                "error": f"گردونه شانس هر ۲۴ ساعت یک‌بار قابل استفاده است. زمان باقیمانده: {hours} ساعت و {mins} دقیقه.",
                "next_spin_seconds": rem_secs,
                "code": "cooldown",
            }

    # 5. Calculate streak
    now_local = now_utc.astimezone(ZoneInfo(tz_name))
    today_date = now_local.date()

    last_spin_at = getattr(db_user, "wheel_last_spin_at", None) if db_user else None
    cur_streak = int(getattr(db_user, "wheel_streak", 0) or 0) if db_user else 0

    if not using_ticket:
        if not last_spin_at:
            new_streak = 1
        else:
            if last_spin_at.tzinfo is None:
                last_spin_at = last_spin_at.replace(tzinfo=timezone.utc)
            last_local = last_spin_at.astimezone(ZoneInfo(tz_name))
            days_diff = (today_date - last_local.date()).days
            if days_diff == 1:
                new_streak = min(cur_streak + 1, 7)
            elif days_diff == 0:
                new_streak = max(1, cur_streak)
            elif days_diff == 2 and (now_local - last_local).total_seconds() <= 36 * 3600:
                new_streak = min(cur_streak + 1, 7)
            else:
                new_streak = 1

        if db_user:
            db_user.wheel_streak = new_streak
    else:
        new_streak = max(1, cur_streak)

    streak_multiplier = 1.5 if new_streak >= 3 else (1.2 if new_streak == 2 else 1.0)

    # 6. Anti-cheat dynamic weighted random prize
    prizes = [
        {"id": "1gb", "name": f"{ltr_frag('1 GB')} ترافیک هدیه", "icon": "🎁", "type": "traffic", "value": 1},
        {"id": "blank_1", "name": "پوچ (شانس بعدی فردا)", "icon": "❌", "type": "blank", "value": 0},
        {"id": "discount10", "name": "۱۰٪ کد تخفیف ویژه (کد: OFF10)", "icon": "🎟", "type": "coupon", "code": "OFF10"},
        {"id": "500mb", "name": f"{ltr_frag('500 MB')} ترافیک هدیه", "icon": "⚡️", "type": "traffic", "value": 0.5},
        {"id": "2gb", "name": f"{ltr_frag('2 GB')} ترافیک هدیه (سوپر شانس)", "icon": "👑", "type": "traffic", "value": 2},
        {"id": "again", "name": "دوباره (شانس مجدد!)", "icon": "🔄", "type": "again", "value": 0},
    ]

    w_1gb = max(8, int(10 * streak_multiplier))
    w_500mb = max(12, int(15 * streak_multiplier))
    w_disc = max(12, int(15 * streak_multiplier))
    w_again = 10
    w_blank1 = max(25, int(45 / streak_multiplier))
    w_2gb = max(1, int(1.2 * streak_multiplier))
    weights = [w_1gb, w_blank1, w_disc, w_500mb, w_2gb, w_again]
    chosen = random.choices(prizes, weights=weights, k=1)[0]

    applied = False
    if panel_users and chosen["type"] in ("traffic", "days"):
        primary = next(
            (u for u in panel_users if (u.get("status") or "").upper() == "ACTIVE"),
            panel_users[0],
        )
        primary_id = int(primary.get("id"))
        current_expire = primary.get("expireAt")
        current_limit = int(primary.get("trafficLimitBytes") or 0)
        try:
            if chosen["type"] == "traffic":
                if current_limit > 0:
                    traffic_bytes = int(chosen["value"] * 1024 * 1024 * 1024)
                    new_limit = current_limit + traffic_bytes
                    up_res = await remnawave.update_user_subscription(
                        primary_id,
                        current_expire,
                        new_limit,
                    )
                    if up_res is not None:
                        applied = True
                        if cache and hasattr(cache, "set"):
                            try:
                                cur_traffic = float(await cache.get(f"wheel:total_won_traffic:{telegram_id}") or 0.0)
                                await cache.set(f"wheel:total_won_traffic:{telegram_id}", cur_traffic + float(chosen["value"]), ttl_seconds=86400 * 365)
                            except Exception:
                                pass
                else:
                    # Unlimited traffic account: convert volume prize into +1 day bonus so the spin isn't wasted
                    from bot.services.formatting import parse_iso
                    cur_dt = parse_iso(current_expire)
                    base = cur_dt if cur_dt and cur_dt > now_utc else now_utc
                    new_expire_dt = base + timedelta(days=1)
                    up_res = await remnawave.update_user_subscription(
                        primary_id,
                        new_expire_dt.isoformat(),
                        current_limit,
                    )
                    if up_res is not None:
                        applied = True
                        chosen["name"] = f"{chosen['name']} ← معادل ۱ روز تمدید (حجم نامحدود)"
            elif chosen["type"] == "days":
                from bot.services.formatting import parse_iso
                cur_dt = parse_iso(current_expire)
                base = cur_dt if cur_dt and cur_dt > now_utc else now_utc
                new_expire_dt = base + timedelta(days=int(chosen["value"]))
                up_res = await remnawave.update_user_subscription(
                    primary_id,
                    new_expire_dt.isoformat(),
                    current_limit,
                )
                if up_res is not None:
                    applied = True
        except Exception as exc:
            logger.warning("Failed to auto-apply wheel prize to panel: %s", exc)

    if chosen["type"] == "coupon":
        if session is not None:
            try:
                coupon_repo = CouponRepository(session)
                unique_code = f"WHEEL10_{secrets.token_hex(4).upper()}"
                expire_time = now_utc + timedelta(days=7)
                await coupon_repo.create(
                    code=unique_code,
                    discount_percent=10,
                    max_uses=1,
                    expires_at=expire_time,
                    kind="discount",
                    bound_telegram_id=telegram_id,
                )
                chosen["code"] = unique_code
                chosen["name"] = f"کد تخفیف 10% (مهلت ۷ روز): {unique_code}"

                if cache and hasattr(cache, "get"):
                    user_coupons = await cache.get(f"wheel:user_coupons:{telegram_id}") or []
                    user_coupons.insert(0, {
                        "code": unique_code,
                        "discount_percent": 10,
                        "expires_at": expire_time.isoformat(),
                    })
                    await cache.set(f"wheel:user_coupons:{telegram_id}", user_coupons[:10], ttl_seconds=86400 * 8)
                applied = True
            except Exception as exc:
                logger.warning("Failed to prepare coupon for wheel prize: %s", exc)

    # Record spin in DB report & update spin cooldown
    if chosen["type"] != "again":
        if cache and hasattr(cache, "delete"):
            await cache.delete(f"wheel:has_free_retry:{telegram_id}")
        if not using_ticket:
            if db_user:
                db_user.wheel_last_spin_at = now_utc
            if cache and hasattr(cache, "set"):
                await cache.set(wheel_ts_key, now_ts, ttl_seconds=86400)
        if session is not None:
            try:
                rep_repo = ReportRepository(session)
                await rep_repo.record_wheel_spin(telegram_id)
            except Exception as exc:
                logger.warning("Failed to record wheel spin in DB for %s: %s", telegram_id, exc)
    else:
        # Free retry prize! Keep cooldown off and restore ticket if used
        if cache and hasattr(cache, "set"):
            await cache.set(f"wheel:has_free_retry:{telegram_id}", 1, ttl_seconds=86400)
        if using_ticket and db_user:
            db_user.spin_tickets = cur_tickets
            using_ticket = False

    if session is not None:
        await session.commit()

    remaining_tickets = int(getattr(db_user, "spin_tickets", 0) or 0) if db_user else 0

    await invalidate_user_wheel_caches(cache, telegram_id)

    return {
        "ok": True,
        "prize": chosen,
        "applied": applied,
        "streak": new_streak,
        "streak_multiplier": streak_multiplier,
        "spin_tickets": remaining_tickets,
        "used_ticket": using_ticket,
    }
