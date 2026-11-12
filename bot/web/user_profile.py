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
import inspect
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
from bot.db.models import (
    AdminLog,
    CardAutoInvoice,
    Coupon,
    CouponUsage,
    CryptoInvoice,
    Order,
    Service,
    Topup,
    User,
    Wallet,
)
from bot.db.repositories.alert_repo import AlertRepository
from bot.db.repositories.report_repo import ReportRepository
from bot.db.repositories.service_repo import SERVICE_ORDER_BY
from bot.db.repositories.user_repo import UserRepository
from bot.services.app_settings import get_store_settings, is_maintenance
from bot.services.formatting import COUNTRY_FLAGS_MAP, country_flag, now_tz
from bot.services.loyalty import apply_loyalty_discount, get_user_loyalty

FLAG_EMOJI_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")


def _extract_node_flag(node: dict[str, Any]) -> str | None:
    """Extract a country flag emoji from node metadata, name, or country code."""
    if not isinstance(node, dict):
        return None
    cc = str(node.get("countryCode") or node.get("country_code") or node.get("country") or "").strip().upper()
    if cc and len(cc) == 2 and cc.isalpha() and cc != "XX":
        f = country_flag(cc)
        if f and f != "🌐":
            return f
    name = str(node.get("name") or node.get("nodeName") or "")
    m = FLAG_EMOJI_RE.search(name)
    if m:
        return m.group(0)
    tags_str = " ".join(str(t) for t in (node.get("tags") or []) if t)
    search_text = f"{name} {node.get('country_name') or ''} {node.get('address') or ''} {node.get('hostname') or ''} {node.get('city') or ''} {node.get('remark') or ''} {tags_str}".lower()
    for kw, (f_emoji, _) in sorted(COUNTRY_FLAGS_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if kw in search_text:
            return f_emoji
    if "ایران" in search_text or "تهران" in search_text:
        return "🇮🇷"
    return None


def _collect_token_values(items: Any, keys: tuple[str, ...]) -> set[str]:
    """Extract lowercased string identifiers from a dict list or string list."""
    tokens: set[str] = set()
    if not isinstance(items, list):
        return tokens
    for item in items:
        if isinstance(item, dict):
            for k in keys:
                val = item.get(k)
                if val is not None and str(val).strip():
                    tokens.add(str(val).strip().lower())
        elif item:
            tokens.add(str(item).strip().lower())
    return tokens


def _extract_node_squad_and_inbound_tokens(node: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Collect squad aliases and active inbound UUIDs/tags linked to a panel node."""
    squad_keys = ("uuid", "id", "name")
    inbound_keys = ("uuid", "id", "tag", "inboundTag")
    squad_tokens = _collect_token_values(
        node.get("internalSquads") or node.get("squads") or node.get("activeInternalSquads"),
        squad_keys,
    )
    inbounds = node.get("inbounds") or []
    cfg_profile = node.get("configProfile") if isinstance(node.get("configProfile"), dict) else {}
    active_inbounds = cfg_profile.get("activeInbounds") or node.get("activeInbounds") or []

    inbound_tokens = _collect_token_values(inbounds, inbound_keys) | _collect_token_values(active_inbounds, inbound_keys)
    for ib in inbounds:
        if isinstance(ib, dict):
            squad_tokens |= _collect_token_values(ib.get("internalSquads") or ib.get("squads"), squad_keys)
    return squad_tokens, inbound_tokens
from bot.web.cache import FastCache
from bot.web.user_common import db_session, require_user

logger = logging.getLogger(__name__)


from bot.web.admin_overview_charts import (
    USERS_PERIODIC_BANDWIDTH_CACHE_KEY,
    get_periodic_users_bandwidth,
)
from bot.web.user_subscription_detail import (
    build_active_subscription as _build_active_subscription,
)


def _format_jalali_dt(dt: Any, tz_name: str) -> str:
    """Format a datetime object into YYYY/MM/DD - HH:MM Jalali string in target timezone."""
    if not dt:
        return ""
    j_dt = jdatetime.datetime.fromgregorian(
        datetime=dt.astimezone(ZoneInfo(tz_name)) if dt.tzinfo else dt
    )
    return f"{j_dt.year}/{j_dt.month:02d}/{j_dt.day:02d} - {j_dt.hour:02d}:{j_dt.minute:02d}"


async def _fetch_transaction_history(session: Any, telegram_id: int, tz_name: str) -> list[dict[str, Any]]:
    """Fetch orders, topups, and admin adjustments sorted by timestamp."""
    history_items: list[dict[str, Any]] = []
    try:
        orders_res = await session.execute(
            select(Order).where(Order.telegram_id == telegram_id).order_by(Order.id.desc()).limit(50)
        )
        for o in orders_res.scalars().all():
            o_dt = o.created_at
            o_j_str = _format_jalali_dt(o_dt, tz_name)
            raw_st = (
                o.status.value if hasattr(o.status, "value") else str(o.status or "")
            ).lower()
            if raw_st == "paid":
                st_text = "موفق"
                st_color = "emerald"
                is_pos = False
            elif raw_st == "refunded":
                st_text = "مسترد شده"
                st_color = "purple"
                is_pos = True
            elif raw_st == "pending":
                st_text = "در انتظار پرداخت"
                st_color = "amber"
                is_pos = False
            else:
                st_text = "ناموفق"
                st_color = "rose"
                is_pos = False

            history_items.append({
                "id": o.id,
                "type": "order",
                "title": f"خرید {o.service_name}",
                "service_id": o.service_id,
                "service_name": o.service_name,
                "is_custom": not bool(o.service_id) and "دلخواه" in (o.service_name or ""),
                "traffic_gb": o.traffic_gb or 0,
                "duration_days": o.duration_days or 0,
                "amount": o.amount,
                "amount_formatted": f"{o.amount:,} تومان",
                "is_positive": is_pos,
                "status": st_text,
                "status_color": st_color,
                "date_jalali": o_j_str,
                "timestamp": o_dt.timestamp() if o_dt else 0,
            })

        topups_res = await session.execute(
            select(Topup).where(Topup.telegram_id == telegram_id).order_by(Topup.id.desc()).limit(50)
        )
        for t in topups_res.scalars().all():
            t_dt = t.created_at
            t_j_str = _format_jalali_dt(t_dt, tz_name)
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
                AdminLog.target_user_id == telegram_id,
            ).order_by(AdminLog.id.desc()).limit(15)
        )
        for al in admin_logs_res.scalars().all():
            al_dt = al.created_at
            al_j_str = _format_jalali_dt(al_dt, tz_name)

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

        card_auto_res = await session.execute(
            select(CardAutoInvoice).where(
                CardAutoInvoice.telegram_id == telegram_id,
                CardAutoInvoice.status == "paid",
            ).order_by(CardAutoInvoice.id.desc()).limit(30)
        )
        for ca in card_auto_res.scalars().all():
            ca_dt = ca.paid_at or ca.created_at
            history_items.append({
                "id": f"ca_{ca.id}",
                "type": "card_auto",
                "title": "افزایش موجودی (کارت به کارت خودکار)",
                "amount": ca.exact_amount,
                "amount_formatted": f"{ca.exact_amount:,} تومان",
                "is_positive": True,
                "status": "تایید خودکار",
                "status_color": "emerald",
                "date_jalali": _format_jalali_dt(ca_dt, tz_name),
                "timestamp": ca_dt.timestamp() if ca_dt else 0,
            })

        crypto_res = await session.execute(
            select(CryptoInvoice).where(
                CryptoInvoice.telegram_id == telegram_id,
                CryptoInvoice.status == "paid",
            ).order_by(CryptoInvoice.id.desc()).limit(30)
        )
        for cr in crypto_res.scalars().all():
            cr_dt = cr.paid_at or cr.created_at
            cr_curr = (cr.currency or "TON").upper()
            history_items.append({
                "id": f"cr_{cr.id}",
                "type": "crypto",
                "title": f"شارژ کیف پول (رمزارز {cr_curr})",
                "amount": cr.amount_toman,
                "amount_formatted": f"{cr.amount_toman:,} تومان",
                "is_positive": True,
                "status": "تایید شده",
                "status_color": "emerald",
                "date_jalali": _format_jalali_dt(cr_dt, tz_name),
                "timestamp": cr_dt.timestamp() if cr_dt else 0,
            })

        history_items.sort(key=lambda x: x["timestamp"], reverse=True)
    except Exception as exc:
        logger.warning("Failed to fetch transaction history for %s: %s", telegram_id, exc)

    return history_items


async def _fetch_user_perks_and_settings(
    session: Any, cache: FastCache, telegram_id: int, has_active_sub: bool, db_user: Any = None
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], float, bool]:
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

    total_gift_traffic = 0.0
    try:
        raw_gt = await cache.get(f"wheel:total_won_traffic:{telegram_id}")
        if raw_gt is not None:
            total_gift_traffic = float(raw_gt)
    except Exception:
        pass

    birthday_claimed = False
    try:
        tehran_tz = ZoneInfo("Asia/Tehran")
        now_tehran = datetime.now(tehran_tz)
        today_j = jdatetime.date.fromgregorian(date=now_tehran.date()) if jdatetime else None
        if today_j:
            birthday_claimed = bool(await cache.get(f"birthday_reward:{telegram_id}:{today_j.year}"))
    except Exception:
        pass

    return settings_combined, active_won_coupons, wheel_status, total_gift_traffic, birthday_claimed


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
        from bot.web.user_common import is_user_invited

        user_repo_cls = getattr(_user_routes, "UserRepository", UserRepository)
        user_repo = user_repo_cls(session)
        store_settings = await get_store_settings(session)
        is_adm = bool(user_auth.get("is_admin", False))

        if (
            getattr(store_settings, "access_mode", "open") == "invite_only"
            and not is_adm
            and hasattr(user_repo, "get_by_telegram_id")
        ):
            existing_user = await user_repo.get_by_telegram_id(telegram_id)
            if not is_user_invited(existing_user):
                panel_preview = []
                try:
                    panel_preview = (await asyncio.wait_for(panel_users_task, timeout=8.0)) or []
                except Exception:
                    panel_preview = []
                if not is_user_invited(existing_user, panel_preview):
                    raw_support = (getattr(store_settings, "support_contact", "") or "").strip()
                    support_link = ""
                    if raw_support and raw_support not in ("—", "-"):
                        if raw_support.startswith(("http://", "https://")):
                            support_link = raw_support
                        elif raw_support.startswith("t.me/"):
                            support_link = f"https://{raw_support}"
                        elif raw_support.startswith("@"):
                            support_link = f"https://t.me/{raw_support[1:]}"
                        else:
                            support_link = f"https://t.me/{raw_support}"
                    return web.json_response({
                        "ok": True,
                        "cached": False,
                        "data": {
                            "is_invite_only": True,
                            "is_maintenance": await is_maintenance(session),
                            "support_contact": raw_support,
                            "support_link": support_link,
                            "user": {
                                "id": telegram_id,
                                "first_name": user_auth.get("first_name", "کاربر"),
                                "username": user_auth.get("username"),
                                "is_admin": False,
                            },
                        },
                    })

        first_name = user_auth.get("first_name", "")
        last_name = user_auth.get("last_name", "")
        auth_full_name = f"{first_name} {last_name}".strip() or None
        db_user = await user_repo.get_or_create(telegram_id, user_auth.get("username"))
        if auth_full_name and hasattr(db_user, "full_name"):
            db_user.full_name = auth_full_name
        if hasattr(session, "commit"):
            commit_res = session.commit()
            if inspect.isawaitable(commit_res):
                await commit_res

        wallet_res = await session.execute(select(Wallet).where(Wallet.telegram_id == telegram_id))
        wallet = wallet_res.scalar_one_or_none()
        wallet_balance = wallet.balance if wallet else 0

        maint_on = await is_maintenance(session)
        ref_count_res = await session.execute(select(func.count(User.id)).where(User.referred_by_id == telegram_id))
        referrals_count = int(ref_count_res.scalar_one() or 0)
        referral_reward_gb = store_settings.referral_reward_gb if store_settings.referral_enabled else 5

        try:
            services_res = await session.execute(
                select(Service).where(
                    Service.is_active.is_(True),
                    or_(
                        Service.max_purchases.is_(None),
                        Service.purchases_count < Service.max_purchases,
                    ),
                ).order_by(*SERVICE_ORDER_BY)
            )
            raw_services = list(services_res.scalars().all())
        except Exception as exc:
            await session.rollback()
            logger.warning("Failed to query active services with purchase limits in profile: %s", exc)
            try:
                services_res = await session.execute(
                    select(Service).where(Service.is_active.is_(True)).order_by(*SERVICE_ORDER_BY)
                )
                raw_services = list(services_res.scalars().all())
            except Exception:
                await session.rollback()
                raw_services = []

        plans_data = []

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

        active_primary = None
        if panel_users:
            if req_account_id:
                active_primary = next((u for u in panel_users if str(u.get("id")) == str(req_account_id)), None)
            else:
                active_primary = next((u for u in panel_users if (u.get("status") or "").upper() == "ACTIVE"), None)
            if not active_primary:
                active_primary = panel_users[0]

        active_squad_uuids = set()
        if active_primary and has_active_sub:
            raw_sqs = (
                active_primary.get("activeInternalSquads")
                or active_primary.get("internalSquads")
                or active_primary.get("activeInternalSquadsUuids")
                or active_primary.get("internalSquadsUuids")
                or []
            )
            for sq in raw_sqs:
                if isinstance(sq, dict):
                    u = sq.get("uuid") or sq.get("id")
                    if u:
                        active_squad_uuids.add(str(u).strip().lower())
                elif isinstance(sq, str):
                    active_squad_uuids.add(sq.strip().lower())

        filtered_services = []
        for s in raw_services:
            is_addon = (
                (s.traffic_gb > 0 and s.duration_days == 0)
                or (s.duration_days > 0 and s.traffic_gb == 0)
                or bool(s.badge and s.badge.lower() in ("traffic", "time"))
            )
            if is_addon:
                if not has_active_sub or not s.squad_uuid or str(s.squad_uuid).strip().lower() not in active_squad_uuids:
                    continue
            filtered_services.append(s)

        # Resolve server country flags for shop plans
        cluster_nodes = []
        try:
            cached_cluster_nodes = await cache.get("tma:cluster:nodes_overview")
            if cached_cluster_nodes:
                cluster_nodes = cached_cluster_nodes
            else:
                raw_nodes = await remnawave.get_nodes() or []
                cluster_nodes = raw_nodes
                if raw_nodes:
                    await cache.set("tma:cluster:nodes_overview", raw_nodes, ttl_seconds=60)
        except Exception as node_err:
            logger.debug("Failed fetching nodes for plan flags: %s", node_err)

        # Resolve squad lookup map (aliases + inbound UUIDs/tags from Remnawave v2 internal squads)
        squad_alias_map: dict[str, set[str]] = {}
        squad_inbound_map: dict[str, set[str]] = {}
        squad_name_map: dict[str, str] = {}
        try:
            raw_squads = await remnawave.get_internal_squads() or []
            for sq in raw_squads:
                if isinstance(sq, dict):
                    tokens = _collect_token_values([sq], ("uuid", "id", "name"))
                    ib_tokens = _collect_token_values(sq.get("inbounds") or sq.get("activeInbounds"), ("uuid", "id", "tag", "inboundTag"))
                    sq_name = str(sq.get("name") or "")
                    for t in tokens:
                        squad_alias_map[t] = tokens
                        if ib_tokens:
                            squad_inbound_map[t] = squad_inbound_map.get(t, set()) | ib_tokens
                        if sq_name:
                            squad_name_map[t] = sq_name
        except Exception as sq_err:
            logger.debug("Failed fetching internal squads for plan flags: %s", sq_err)

        default_cluster_flags = []
        node_by_uuid: dict[str, dict[str, Any]] = {}
        node_tokens_cache: list[tuple[dict[str, Any], set[str], set[str]]] = []
        for n in cluster_nodes:
            if isinstance(n, dict):
                f = _extract_node_flag(n)
                if f and f != "🌐" and f not in default_cluster_flags:
                    default_cluster_flags.append(f)
                n_uid = str(n.get("uuid") or n.get("id") or "").strip().lower()
                if n_uid:
                    node_by_uuid[n_uid] = n
                sq_t, ib_t = _extract_node_squad_and_inbound_tokens(n)
                node_tokens_cache.append((n, sq_t, ib_t))

        # Fetch accessible nodes once per unresolved dedicated squad
        unresolved_squads = set()
        for s in filtered_services:
            if s.squad_uuid:
                s_key = str(s.squad_uuid).strip().lower()
                matching_tokens = squad_alias_map.get(s_key, {s_key})
                matching_inbounds = squad_inbound_map.get(s_key, set())
                matched_any = any(
                    (sq_t & matching_tokens) or (ib_t & matching_inbounds)
                    for _, sq_t, ib_t in node_tokens_cache
                )
                if not matched_any:
                    unresolved_squads.add(s_key)

        squad_accessible_flags: dict[str, list[str]] = {}
        if unresolved_squads and hasattr(remnawave, "get_internal_squad_accessible_nodes"):
            async def _fetch_squad_acc_flags(s_key: str) -> tuple[str, list[str]]:
                cache_key = f"tma:squad:{s_key}:accessible_nodes"
                acc_nodes = await cache.get(cache_key)
                if not isinstance(acc_nodes, list):
                    try:
                        raw_acc = await remnawave.get_internal_squad_accessible_nodes(s_key)
                        if isinstance(raw_acc, list):
                            acc_nodes = raw_acc
                            await cache.set(cache_key, acc_nodes, ttl_seconds=60)
                    except Exception as acc_err:
                        logger.debug("Failed fetching accessible nodes for squad %s: %s", s_key, acc_err)
                        acc_nodes = None
                flags_out: list[str] = []
                if isinstance(acc_nodes, list):
                    for an in acc_nodes:
                        if not isinstance(an, dict):
                            continue
                        f = _extract_node_flag(an)
                        if (not f or f == "🌐"):
                            ref_uid = str(an.get("uuid") or an.get("nodeUuid") or an.get("id") or "").strip().lower()
                            if ref_uid and ref_uid in node_by_uuid:
                                f = _extract_node_flag(node_by_uuid[ref_uid])
                        if f and f != "🌐" and f not in flags_out:
                            flags_out.append(f)
                return s_key, flags_out

            acc_results = await asyncio.gather(*(_fetch_squad_acc_flags(sk) for sk in unresolved_squads))
            squad_accessible_flags = dict(acc_results)

        loyalty_data = await get_user_loyalty(session, telegram_id, cache=cache)
        loyalty_pct = loyalty_data.get("discount_percent", 0)

        plans_data = []
        for s in filtered_services:
            plan_flags = []
            if s.squad_uuid:
                s_key = str(s.squad_uuid).strip().lower()
                matching_tokens = squad_alias_map.get(s_key, {s_key})
                matching_inbounds = squad_inbound_map.get(s_key, set())
                for n, node_sq_tokens, node_ib_tokens in node_tokens_cache:
                    if (node_sq_tokens & matching_tokens) or (node_ib_tokens & matching_inbounds):
                        f = _extract_node_flag(n)
                        if f and f != "🌐" and f not in plan_flags:
                            plan_flags.append(f)
                if not plan_flags and squad_accessible_flags.get(s_key):
                    plan_flags = list(squad_accessible_flags[s_key])
                if not plan_flags:
                    sq_hint = f"{squad_name_map.get(s_key, '')} {s.badge or ''}".lower()
                    if "iran" in sq_hint or "ایران" in sq_hint:
                        plan_flags = ["🇮🇷"]
            else:
                plan_flags = list(default_cluster_flags)

            disc_amt, final_price = apply_loyalty_discount(s.price, loyalty_pct)

            plans_data.append({
                "id": s.id,
                "name": s.name,
                "price": final_price,
                "original_price": s.price,
                "final_price": final_price,
                "loyalty_discount_percent": loyalty_pct,
                "loyalty_discount_amount": disc_amt,
                "duration_days": s.duration_days,
                "traffic_gb": s.traffic_gb,
                "description": s.description,
                "hwid_limit": s.hwid_limit,
                "badge": s.badge or "",
                "squad_uuid": s.squad_uuid or "",
                "sort_order": s.sort_order or 0,
                "flags": plan_flags,
                "flags_label": "اسکواد اختصاصی" if s.squad_uuid else "بدون اسکواد",
            })
        is_invite_only = False
        is_adm = bool(user_auth.get("is_admin", False))
        if not is_adm:
            try:
                store_sett = await get_store_settings(session)
                if getattr(store_sett, "access_mode", "open") == "invite_only":
                    is_invited = bool(is_user_invited(db_user, panel_users) or has_active_sub)
                    if not is_invited:
                        is_invite_only = True
            except Exception as e:
                logger.debug("Failed checking invite-only status: %s", e)
        transactions = await _fetch_transaction_history(session, telegram_id, tz_name)
        user_settings, active_won_coupons, wheel_status, total_gift_traffic, birthday_claimed = await _fetch_user_perks_and_settings(
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
                    tehran_tz = ZoneInfo("Asia/Tehran")
                    now_tehran = datetime.now(tehran_tz)
                    today_j = jdatetime.date.fromgregorian(date=now_tehran.date())
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

        raw_support_contact = (store_settings.support_contact or "").strip()
        support_link = ""
        if raw_support_contact and raw_support_contact not in ("—", "-"):
            if raw_support_contact.startswith(("http://", "https://")):
                support_link = raw_support_contact
            elif raw_support_contact.startswith("t.me/"):
                support_link = f"https://{raw_support_contact}"
            elif raw_support_contact.startswith("@"):
                support_link = f"https://t.me/{raw_support_contact[1:]}"
            else:
                support_link = f"https://t.me/{raw_support_contact}"

        achievements_data = {
            "total_gift_traffic_gb": round(total_gift_traffic, 2),
            "active_coupons_count": len(active_won_coupons),
            "wheel_streak": wheel_status.get("streak", 0),
            "spin_tickets": wheel_status.get("spin_tickets", 0),
            "has_birthday_set": bool(birth_date_val and str(birth_date_val).strip()),
            "days_until_birthday": days_until_birthday,
            "is_birthday_today": is_birthday_today,
            "birthday_claimed": birthday_claimed,
        }

        user_leaderboard = {}
        now_utc = datetime.now(timezone.utc)
        try:
            cached_bw = await cache.get(USERS_PERIODIC_BANDWIDTH_CACHE_KEY)
            if cached_bw and isinstance(cached_bw, dict) and "weekly" in cached_bw and "daily" in cached_bw and "nightly" in cached_bw:
                periodic_bw = cached_bw
            else:
                cached_all_panel = await cache.get("tma:all_panel_users")
                if cached_all_panel:
                    all_panel = cached_all_panel
                else:
                    all_panel = await remnawave.get_all_panel_users(size=1000) or []
                    if all_panel:
                        await cache.set("tma:all_panel_users", all_panel, ttl_seconds=60)
                periodic_bw = await get_periodic_users_bandwidth(remnawave, cache, all_panel, now_utc)

            my_user_ids = {str(p["id"]) for p in panel_users if isinstance(p, dict) and p.get("id")}

            def _build_user_lb(lb_item, gb_key_override=None):
                if not lb_item or not isinstance(lb_item, dict):
                    return {
                        "top_20": [],
                        "labels": [],
                        "data": [],
                        "my_rank": None,
                        "my_used_gb": 0.0,
                        "in_top_20": False,
                        "diff_gb": 0.0,
                        "month_name": None,
                        "period_label": "",
                    }
                all_u = lb_item.get("all_users", [])
                gb_key = gb_key_override or lb_item.get("gb_key", "used_gb")
                top_20 = []
                my_rank = None
                my_used_gb = 0.0

                for idx, u in enumerate(all_u):
                    uid_str = str(u.get("id", ""))
                    u_tg_id = str(u.get("telegram_id", ""))
                    is_me = bool(
                        (u_tg_id and u_tg_id == str(telegram_id))
                        or (uid_str and uid_str in my_user_ids)
                        or (req_account_id and uid_str == str(req_account_id))
                        or (active_primary and uid_str == str(active_primary.get("id", "")))
                    )
                    used_val = u.get(gb_key, 0.0)

                    if is_me and my_rank is None:
                        my_used_gb = used_val
                        if used_val > 0:
                            my_rank = idx + 1

                    if idx < 20 and used_val > 0:
                        raw_uname = u.get("username") or f"user_{u.get('id')}"
                        if is_me:
                            display_name = f"{raw_uname} (شما)"
                        else:
                            if len(raw_uname) > 4:
                                display_name = f"{raw_uname[:2]}***{raw_uname[-1]}"
                            else:
                                display_name = f"{raw_uname[:1]}***"

                        top_20.append({
                            "rank": idx + 1,
                            "username": display_name,
                            "used_gb": used_val,
                            "is_me": is_me,
                        })

                cutoff_gb = top_20[-1]["used_gb"] if len(top_20) == 20 else (top_20[-1]["used_gb"] if top_20 else 0.0)
                diff_gb = round(max(0.0, cutoff_gb - my_used_gb), 2) if (my_rank and my_rank > 20 and my_used_gb > 0) else 0.0

                return {
                    "top_20": top_20,
                    "labels": [u["username"] for u in top_20],
                    "data": [u["used_gb"] for u in top_20],
                    "my_rank": my_rank if (my_used_gb > 0) else None,
                    "my_used_gb": my_used_gb,
                    "in_top_20": bool(my_rank and my_rank <= 20 and my_used_gb > 0),
                    "diff_gb": diff_gb,
                    "month_name": lb_item.get("month_name"),
                    "period_label": lb_item.get("label", ""),
                }

            user_leaderboard["daily"] = _build_user_lb(periodic_bw.get("daily", {}), "daily_gb")
            user_leaderboard["nightly"] = _build_user_lb(periodic_bw.get("nightly", {}), "yesterday_gb")
            user_leaderboard["weekly"] = _build_user_lb(periodic_bw.get("weekly", {}), "week_gb")
            user_leaderboard["monthly_30d"] = _build_user_lb(periodic_bw.get("monthly_30d", {}), "month_30d_gb")

            cal_months = periodic_bw.get("calendar_months", {})
            user_leaderboard["calendar_months"] = {}
            for m_name, m_lb in cal_months.items():
                built_m = _build_user_lb(m_lb)
                if isinstance(m_lb, dict) and "weeks" in m_lb:
                    built_m["weeks"] = {
                        w_k: _build_user_lb(w_v) for w_k, w_v in m_lb["weeks"].items()
                    }
                user_leaderboard["calendar_months"][m_name] = built_m

            avail_months = periodic_bw.get("available_months", [])
            user_leaderboard["available_months"] = avail_months
            if avail_months and avail_months[0] in user_leaderboard["calendar_months"]:
                user_leaderboard["monthly"] = user_leaderboard["calendar_months"][avail_months[0]]
            else:
                user_leaderboard["monthly"] = _build_user_lb(periodic_bw.get("monthly", {}))
        except Exception as lb_err:
            logger.debug("Failed calculating user leaderboard: %s", lb_err)

        data = {
            "partial": is_partial,
            "panel_error": panel_error,
            "bot_username": bot_username,
            "referral_reward_gb": referral_reward_gb,
            "referral_enabled": store_settings.referral_enabled,
            "referral_link": ref_link,
            "support_contact": raw_support_contact,
            "support_link": support_link,
            "support_direct_enabled": store_settings.support_direct_enabled,
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
            "cluster_flags": default_cluster_flags,
            "transactions": transactions[:50],
            "won_coupons": active_won_coupons,
            "wheel_status": wheel_status,
            "achievements": achievements_data,
            "leaderboard": user_leaderboard,
            "loyalty": loyalty_data,
            "custom_plan_settings": {
                "enabled": store_settings.custom_plan_enabled,
                "price_per_gb": store_settings.custom_plan_price_per_gb,
                "price_per_day": store_settings.custom_plan_price_per_day,
                "base_price": store_settings.custom_plan_base_price,
                "min_gb": store_settings.custom_plan_min_gb,
                "max_gb": store_settings.custom_plan_max_gb,
                "min_days": store_settings.custom_plan_min_days,
                "max_days": store_settings.custom_plan_max_days,
                "extra_device_percent": store_settings.custom_plan_extra_device_percent,
                "volume_tiers_json": store_settings.custom_plan_volume_tiers_json,
            },
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
        return web.json_response({"ok": False, "error": "فرمت تاریخ نامعتبر است (مثال: 1375/07/22)."}, status=400)

    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    if year < 1300 or year > 1410 or month < 1 or month > 12 or day < 1 or day > 31:
        return web.json_response({"ok": False, "error": "تاریخ وارد شده خارج از بازه مجاز است."}, status=400)

    try:
        if jdatetime:
            jdatetime.date(year, month, day)
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "روز وارد شده برای این ماه در تقویم خورشیدی وجود ندارد."}, status=400)

    formatted_date = f"{year:04d}/{month:02d}/{day:02d}"
    telegram_id = int(user_auth["id"])

    async with db_session(request) as session:
        from bot.web.user_common import enforce_invite_only

        inv_err = await enforce_invite_only(session, telegram_id, user_auth, remnawave=request.app.get("remnawave"))
        if inv_err:
            return inv_err

        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not user:
            return web.json_response({"ok": False, "error": "کاربر یافت نشد."}, status=404)

        if getattr(user, "birth_date", None):
            return web.json_response(
                {"ok": False, "error": "تاریخ تولد شما قبلاً ثبت شده و برای جلوگیری از سوءاستفاده قابل تغییر مجدد نیست."},
                status=400,
            )

        user.birth_date = formatted_date
        if hasattr(session, "commit"):
            commit_res = session.commit()
            if inspect.isawaitable(commit_res):
                await commit_res

        cache: FastCache = request.app.get("cache")
        if cache:
            await cache.delete(f"tma:user:{telegram_id}")
            await cache.delete(f"tma:user:{telegram_id}:dashboard:default")
            await cache.delete(f"tma:user:{telegram_id}:dashboard")

        return web.json_response({"ok": True, "birth_date": formatted_date})
