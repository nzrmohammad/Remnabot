"""Engagement Services (SSOT for Renewal Advisor, Loyalty Themes, Weekly Quests, Red Packets, Champion Badge, P2P Wallet Transfers)."""
from __future__ import annotations

import asyncio
import logging
import math
import secrets
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    RedPacket,
    RedPacketClaim,
    User,
    Wallet,
    WalletTransfer,
    WeeklyQuestProgress,
)
from bot.db.repositories.user_repo import UserRepository
from bot.db.repositories.wallet_repo import WalletRepository
from bot.locales.texts import normalize_lang
from bot.services.formatting import ltr_frag
from bot.services.loyalty import LOYALTY_TIERS, get_user_loyalty
from bot.web.cache import FastCache, invalidate_user_cache, user_action_lock

_PACKET_LOCAL_LOCKS: dict[str, asyncio.Lock] = {}


def _get_packet_lock(clean_code: str) -> asyncio.Lock:
    if len(_PACKET_LOCAL_LOCKS) > 1024:
        for k, lk in list(_PACKET_LOCAL_LOCKS.items()):
            if not lk.locked():
                _PACKET_LOCAL_LOCKS.pop(k, None)
    lk = _PACKET_LOCAL_LOCKS.get(clean_code)
    if lk is None:
        lk = asyncio.Lock()
        _PACKET_LOCAL_LOCKS[clean_code] = lk
    return lk

logger = logging.getLogger(__name__)

# Financial & gameplay bounds (Single Source of Truth)
MIN_P2P_AMOUNT = 5_000
MAX_P2P_AMOUNT = 50_000_000

MIN_RED_PACKET_SLOTS = 2
MAX_RED_PACKET_SLOTS = 50
MIN_RED_PACKET_SHARE = 5_000
MAX_RED_PACKET_TOTAL = 50_000_000
RED_PACKET_TTL_HOURS = 48

_TIER_ORDER: tuple[str, ...] = tuple(str(t["id"]) for t in LOYALTY_TIERS)
_TIER_NAMES: dict[str, tuple[str, str]] = {
    "bronze": ("برنزی", "Bronze"),
    "silver": ("نقره‌ای", "Silver"),
    "gold": ("طلایی", "Gold"),
    "platinum": ("پلاتین", "Platinum"),
    "ruby": ("یاقوت", "Ruby"),
    "emerald": ("زمرد", "Emerald"),
    "diamond": ("الماس", "Diamond"),
}

# Loyalty-gated visual card & story themes (Single Source of Truth)
CARD_THEMES: tuple[dict[str, Any], ...] = (
    {
        "id": "ocean",
        "min_tier": "bronze",
        "name_fa": "اقیانوس نئون",
        "name_en": "Neon Ocean",
        "accent": "#38bdf8",
        "secondary": "#6366f1",
        "bg_from": "#0b0f19",
        "bg_mid": "#131b2e",
        "bg_to": "#1e1b4b",
        "border_rgba": "rgba(99, 102, 241, 0.45)",
    },
    {
        "id": "emerald",
        "min_tier": "silver",
        "name_fa": "زمرد سلطنتی",
        "name_en": "Royal Emerald",
        "accent": "#34d399",
        "secondary": "#06b6d4",
        "bg_from": "#041612",
        "bg_mid": "#062c22",
        "bg_to": "#0f3d3e",
        "border_rgba": "rgba(16, 185, 129, 0.55)",
    },
    {
        "id": "amber_vip",
        "min_tier": "gold",
        "name_fa": "طلای امپریال",
        "name_en": "Imperial Gold",
        "accent": "#fbbf24",
        "secondary": "#f97316",
        "bg_from": "#181006",
        "bg_mid": "#2b1906",
        "bg_to": "#3f2208",
        "border_rgba": "rgba(245, 158, 11, 0.55)",
    },
    {
        "id": "crimson_ruby",
        "min_tier": "ruby",
        "name_fa": "یاقوت شب",
        "name_en": "Midnight Ruby",
        "accent": "#f43f5e",
        "secondary": "#a855f7",
        "bg_from": "#190713",
        "bg_mid": "#2e0c24",
        "bg_to": "#3b0764",
        "border_rgba": "rgba(244, 63, 94, 0.55)",
    },
    {
        "id": "obsidian_diamond",
        "min_tier": "diamond",
        "name_fa": "الماس کیهانی",
        "name_en": "Cosmic Diamond",
        "accent": "#67e8f9",
        "secondary": "#facc15",
        "bg_from": "#030712",
        "bg_mid": "#0f172a",
        "bg_to": "#1e293b",
        "border_rgba": "rgba(103, 232, 249, 0.65)",
    },
)
_CARD_THEMES_MAP: dict[str, dict[str, Any]] = {t["id"]: t for t in CARD_THEMES}

# Weekly interactive quests (STRICT POLICY: spin_tickets & badge only, NEVER free GB or balance)
WEEKLY_QUESTS: tuple[dict[str, Any], ...] = (
    {
        "id": "weekly_speedtest",
        "event": "speedtest",
        "target": 1,
        "reward_tickets": 1,
        "icon": "zap",
        "title_fa": "تست سرعت شبکه",
        "title_en": "Network Speed Test",
        "desc_fa": "یک تست سرعت کامل انجام دهید",
        "desc_en": "Run one complete speed test",
    },
    {
        "id": "weekly_wallet_card",
        "event": "wallet_card_check",
        "target": 1,
        "reward_tickets": 1,
        "icon": "credit-card",
        "title_fa": "شخصی‌سازی کارت گرافیکی",
        "title_en": "Graphic Wallet Card",
        "desc_fa": "حالت گرافیکی کارت کیف پول را فعال و رنگ یا پشت کارت را بررسی کنید",
        "desc_en": "Enable the graphic wallet card and inspect its color or back",
    },
    {
        "id": "weekly_wallet_boost",
        "event": "wallet_boost",
        "target": 1,
        "reward_tickets": 1,
        "icon": "coins",
        "title_fa": "انتقال یا شارژ رمزارز",
        "title_en": "Transfer or Crypto Top-Up",
        "desc_fa": "یک انتقال مستقیم پول انجام دهید یا کیف پول را با TON/TRX/POL شارژ کنید",
        "desc_en": "Make a direct transfer or top up with TON/TRX/POL",
    },
    {
        "id": "weekly_spin_3",
        "event": "spin",
        "target": 3,
        "reward_tickets": 1,
        "icon": "wheel",
        "title_fa": "چرخش سه‌گانه هفتگی",
        "title_en": "Weekly Spin Trio",
        "desc_fa": "3 بار در این هفته گردونه شانس را بچرخانید",
        "desc_en": "Spin the Lucky Wheel 3 times this week",
    },
)
_QUESTS_BY_ID: dict[str, dict[str, Any]] = {q["id"]: q for q in WEEKLY_QUESTS}
_QUESTS_BY_EVENT: dict[str, list[dict[str, Any]]] = {}
for _q in WEEKLY_QUESTS:
    _QUESTS_BY_EVENT.setdefault(_q["event"], []).append(_q)

PUBLIC_QUEST_EVENTS: frozenset[str] = frozenset({"speedtest", "wallet_card_check"})


def current_iso_week_key(tz_name: str = "Asia/Tehran", now_utc: datetime | None = None) -> str:
    """Return canonical ISO week identifier (e.g. '2026-W48') in configured timezone."""
    dt = now_utc or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        local_dt = dt.astimezone(ZoneInfo(tz_name))
    except Exception:
        local_dt = dt
    iso_y, iso_w, _ = local_dt.isocalendar()
    return f"{iso_y}-W{iso_w:02d}"


def _tier_rank(tier_id: str | None) -> int:
    key = str(tier_id or "bronze").strip().lower()
    return _TIER_ORDER.index(key) if key in _TIER_ORDER else 0


def _strict_positive_int(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, float):
        return None
    if isinstance(raw, int):
        return raw if raw > 0 else None
    if isinstance(raw, str):
        cleaned = raw.strip().replace(",", "")
        if cleaned.isdigit():
            val = int(cleaned)
            return val if val > 0 else None
    return None


def compute_renewal_advisor(
    burn_rate: dict[str, Any] | None,
    sub: dict[str, Any] | None = None,
    custom_settings: Any | None = None,
    lang: str = "fa",
) -> dict[str, Any]:
    """Compute data-driven Custom Plan sliders recommendation from 3-day burn rate."""
    norm_lang = normalize_lang(lang)
    is_en = norm_lang == "en"
    br = burn_rate if isinstance(burn_rate, dict) else {}

    min_gb = max(1, int(getattr(custom_settings, "min_gb", 5) or 5))
    max_gb = max(min_gb, int(getattr(custom_settings, "max_gb", 300) or 300))
    min_days = max(1, int(getattr(custom_settings, "min_days", 10) or 10))
    max_days = max(min_days, int(getattr(custom_settings, "max_days", 180) or 180))
    custom_enabled = bool(getattr(custom_settings, "enabled", getattr(custom_settings, "custom_plan_enabled", True)))

    avg_daily = float(br.get("avg_daily_gb") or 0.0)
    status = str(br.get("status") or "idle")
    days_left = int(br.get("days_left_plan") or (sub or {}).get("days_left") or 0)
    remaining_gb = float((sub or {}).get("traffic_remaining_gb") or 0.0)

    def _round_slider_gb(raw_gb: float) -> int:
        stepped = int(math.ceil(max(float(min_gb), raw_gb) / 5.0) * 5)
        return max(min_gb, min(max_gb, stepped))

    def _clamp_days(raw_days: int) -> int:
        stepped = int(math.ceil(max(float(min_days), float(raw_days)) / 5.0) * 5)
        return max(min_days, min(max_days, stepped))

    rec_days = _clamp_days(30)
    daily_frag = ltr_frag(f"{avg_daily:.2f} GB")
    if status == "unlimited":
        rec_gb = _round_slider_gb(min_gb)
        title = "Smart Plan Suggestion" if is_en else "پیشنهاد دستیار تمدید"
        summary = (
            "Your quota is unlimited; a 30-day renewal matches your subscription cycle."
            if is_en
            else "حجم شما نامحدود است؛ تمدید 30 روزه برای تداوم سرویس پیشنهاد می‌شود."
        )
    elif status == "exhausted":
        daily_base = avg_daily if avg_daily >= 0.5 else 1.5
        rec_gb = _round_slider_gb(daily_base * 30 * 1.3 + 5)
        title = "Urgent Renewal Match" if is_en else "تمدید فوری پیشنهادی"
        summary = (
            f"Based on your average ({avg_daily:.2f} GB), a {rec_gb} GB and {rec_days}-day custom package keeps you safely covered."
            if is_en
            else f"با توجه به میانگین {daily_frag}، بسته {rec_gb} گیگابایت و {rec_days} روز بهترین انتخاب مطمئن شماست."
        )
    elif status == "fast":
        shortfall = max(min_gb, (avg_daily * max(days_left, 30) * 1.2) - max(0.0, remaining_gb))
        rec_gb = _round_slider_gb(max(avg_daily * 30 * 1.3 + 5, shortfall + 10))
        title = "Prevent Early Depletion" if is_en else "پیشگیری از اتمام زودهنگام"
        summary = (
            f"With {avg_daily:.2f} GB average usage, {rec_gb} GB and {rec_days} days gives extra buffer against early depletion."
            if is_en
            else f"با الگوی مصرف {daily_frag}، بسته {rec_gb} گیگابایت و {rec_days} روز با حاشیه اطمینان بیشتر مانع اتمام زودهنگام ترافیک می‌شود."
        )
    elif avg_daily > 0:
        rec_gb = _round_slider_gb(avg_daily * 30 * 1.28 + 5)
        title = "Balanced Custom Match" if is_en else "پیشنهاد متناسب با مصرف شما"
        summary = (
            f"Based on your {avg_daily:.2f} GB average, {rec_gb} GB and {rec_days} days gives extra headroom without shortage."
            if is_en
            else f"بر اساس میانگین {daily_frag}، بسته {rec_gb} گیگابایت و {rec_days} روز با حجم اطمینان بیشتر برایتان به‌صرفه‌تر است."
        )
    else:
        rec_gb = _round_slider_gb(30)
        title = "Starter Recommendation" if is_en else "بسته پیشنهادی پایه"
        summary = (
            f"Low recent traffic detected; {rec_gb} GB and {rec_days} days is a comfortable baseline."
            if is_en
            else f"مصرف اخیر پایین بوده است؛ بسته اقتصادی {rec_gb} گیگابایت و {rec_days} روز برایتان آماده شد."
        )

    return {
        "status": status,
        "avg_daily_gb": round(avg_daily, 2),
        "recommended_gb": rec_gb,
        "recommended_days": rec_days,
        "custom_plan_enabled": custom_enabled,
        "title": title,
        "summary": summary,
        "cta_label": "Apply in Custom Plan" if is_en else "تنظیم خودکار در بسته دلخواه",
    }


def resolve_card_themes(
    loyalty_tier_id: str | None,
    selected_theme: str | None,
    lang: str = "fa",
) -> dict[str, Any]:
    """Return all themes with tier-unlock state and validated active theme selection."""
    norm_lang = normalize_lang(lang)
    is_en = norm_lang == "en"
    user_rank = _tier_rank(loyalty_tier_id)
    cleaned_selected = str(selected_theme or "ocean").strip().lower()
    if cleaned_selected not in _CARD_THEMES_MAP:
        cleaned_selected = "ocean"

    # Fall back safely if user's tier dropped or theme was manually set below threshold
    sel_def = _CARD_THEMES_MAP[cleaned_selected]
    if user_rank < _tier_rank(sel_def["min_tier"]):
        cleaned_selected = "ocean"

    themes_out: list[dict[str, Any]] = []
    for item in CARD_THEMES:
        min_tier = str(item["min_tier"])
        unlocked = user_rank >= _tier_rank(min_tier)
        tier_lbl = _TIER_NAMES.get(min_tier, ("برنزی", "Bronze"))[1 if is_en else 0]
        themes_out.append({
            "id": item["id"],
            "name": item["name_en"] if is_en else item["name_fa"],
            "min_tier": min_tier,
            "min_tier_label": tier_lbl,
            "unlocked": unlocked,
            "selected": item["id"] == cleaned_selected,
            "accent": item["accent"],
            "secondary": item["secondary"],
            "bg_from": item["bg_from"],
            "bg_mid": item["bg_mid"],
            "bg_to": item["bg_to"],
            "border_rgba": item["border_rgba"],
        })

    return {
        "selected": cleaned_selected,
        "themes": themes_out,
    }


async def set_user_card_theme(
    session: AsyncSession,
    telegram_id: int,
    theme_id: str,
    *,
    cache: FastCache | None = None,
    lang: str = "fa",
) -> dict[str, Any]:
    """Persist user card theme after enforcing loyalty-tier unlock requirements."""
    norm_lang = normalize_lang(lang)
    is_en = norm_lang == "en"
    clean_id = str(theme_id or "").strip().lower()
    theme_def = _CARD_THEMES_MAP.get(clean_id)
    if not theme_def:
        return {
            "ok": False,
            "status_code": 400,
            "message": "Invalid theme selected." if is_en else "تم انتخاب‌شده معتبر نیست.",
        }

    user_repo = UserRepository(session)
    db_user = await user_repo.get_by_telegram_id(telegram_id)
    if not db_user:
        return {
            "ok": False,
            "status_code": 404,
            "message": "User not found." if is_en else "کاربر یافت نشد.",
        }
    if getattr(db_user, "is_banned", False):
        return {
            "ok": False,
            "status_code": 403,
            "message": "Account is banned." if is_en else "حساب کاربری مسدود شده است.",
        }

    loyalty = await get_user_loyalty(session, telegram_id, cache=cache)
    tier_id = str((loyalty or {}).get("tier_id") or (loyalty or {}).get("id") or "bronze").lower()
    if _tier_rank(tier_id) < _tier_rank(theme_def["min_tier"]):
        req_name = _TIER_NAMES.get(theme_def["min_tier"], ("برنزی", "Bronze"))[1 if is_en else 0]
        return {
            "ok": False,
            "status_code": 403,
            "message": (
                f"Requires {req_name} loyalty tier to unlock this theme."
                if is_en
                else f"برای فعال‌سازی این تم، رسیدن به سطح وفاداری «{req_name}» الزامی است."
            ),
        }

    db_user.card_theme = clean_id
    await session.commit()
    await invalidate_user_cache(cache, telegram_id)

    payload = resolve_card_themes(tier_id, clean_id, lang=norm_lang)
    return {
        "ok": True,
        "card_theme": clean_id,
        "card_themes": payload,
        "message": "Card theme updated." if is_en else "تم کارت با موفقیت ذخیره شد.",
    }


def compute_leaderboard_champion_badge(
    leaderboard_data: dict[str, Any] | None,
    lang: str = "fa",
) -> dict[str, Any] | None:
    """Inspect user leaderboard rankings and return Top-3 Champion badge metadata when qualified."""
    if not isinstance(leaderboard_data, dict):
        return None
    norm_lang = normalize_lang(lang)
    is_en = norm_lang == "en"

    best_badge: dict[str, Any] | None = None
    period_names = {
        "weekly": ("مصرف هفتگی", "Weekly"),
        "daily": ("مصرف امروز", "Daily"),
        "monthly_30d": ("30 روزه", "30-Day"),
    }
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for p_key in ("weekly", "daily", "monthly_30d"):
        p_data = leaderboard_data.get(p_key)
        if not isinstance(p_data, dict):
            continue
        rank = p_data.get("my_rank")
        used_gb = float(p_data.get("my_used_gb") or 0.0)
        if isinstance(rank, int) and 1 <= rank <= 3 and used_gb > 0:
            p_fa, p_en = period_names[p_key]
            title = (
                f"{medals[rank]} #{rank} {p_en} Champion"
                if is_en
                else f"{medals[rank]} قهرمان رتبه {rank} {p_fa}"
            )
            candidate = {
                "rank": rank,
                "period": p_key,
                "period_label": p_en if is_en else p_fa,
                "used_gb": round(used_gb, 2),
                "icon": medals[rank],
                "title": title,
            }
            if best_badge is None or rank < best_badge["rank"]:
                best_badge = candidate
    return best_badge


async def get_weekly_quests_state(
    session: AsyncSession,
    telegram_id: int,
    *,
    tz_name: str = "Asia/Tehran",
    lang: str = "fa",
) -> dict[str, Any]:
    """Return user's ISO-week quests with live progress and claim status (spin tickets only)."""
    norm_lang = normalize_lang(lang)
    is_en = norm_lang == "en"
    week_key = current_iso_week_key(tz_name=tz_name)

    res = await session.execute(
        select(WeeklyQuestProgress).where(
            WeeklyQuestProgress.telegram_id == telegram_id,
            WeeklyQuestProgress.week_key == week_key,
        )
    )
    rows_by_id = {r.quest_id: r for r in res.scalars().all()}

    items: list[dict[str, Any]] = []
    claimable_count = 0
    completed_count = 0
    for q in WEEKLY_QUESTS:
        row = rows_by_id.get(q["id"])
        target = int(q["target"])
        prog = min(target, int(row.progress if row else 0))
        claimed = bool(row.is_claimed) if row else False
        can_claim = prog >= target and not claimed
        if can_claim:
            claimable_count += 1
        if claimed:
            completed_count += 1
        items.append({
            "id": q["id"],
            "event": q["event"],
            "icon": q["icon"],
            "title": q["title_en"] if is_en else q["title_fa"],
            "description": q["desc_en"] if is_en else q["desc_fa"],
            "progress": prog,
            "target": target,
            "reward_type": "spin_ticket",
            "reward_tickets": int(q["reward_tickets"]),
            "is_completed": prog >= target,
            "is_claimed": claimed,
            "can_claim": can_claim,
        })

    return {
        "week_key": week_key,
        "reward_policy": "spin_tickets_and_badges_only",
        "claimable_count": claimable_count,
        "completed_count": completed_count,
        "total_count": len(items),
        "quests": items,
    }


async def record_weekly_quest_event(
    session: AsyncSession,
    telegram_id: int,
    event_name: str,
    *,
    tz_name: str = "Asia/Tehran",
    increment: int = 1,
    commit: bool = True,
) -> list[str]:
    """Advance progress for weekly quests matching event_name cleanly and idempotently."""
    quests = _QUESTS_BY_EVENT.get(str(event_name or "").strip().lower(), [])
    if not quests or increment <= 0:
        return []

    await UserRepository(session).ensure_exists(telegram_id)
    week_key = current_iso_week_key(tz_name=tz_name)
    updated_ids: list[str] = []

    for q in quests:
        q_id = str(q["id"])
        target = int(q["target"])
        res = await session.execute(
            select(WeeklyQuestProgress).where(
                WeeklyQuestProgress.telegram_id == telegram_id,
                WeeklyQuestProgress.week_key == week_key,
                WeeklyQuestProgress.quest_id == q_id,
            )
        )
        row = res.scalar_one_or_none()
        if row is None:
            row = WeeklyQuestProgress(
                telegram_id=telegram_id,
                week_key=week_key,
                quest_id=q_id,
                progress=min(target, increment),
                target=target,
                is_claimed=False,
            )
            session.add(row)
            try:
                async with session.begin_nested():
                    await session.flush()
            except IntegrityError:
                res = await session.execute(
                    select(WeeklyQuestProgress).where(
                        WeeklyQuestProgress.telegram_id == telegram_id,
                        WeeklyQuestProgress.week_key == week_key,
                        WeeklyQuestProgress.quest_id == q_id,
                    )
                )
                row = res.scalar_one_or_none()
                if row is not None and not row.is_claimed and row.progress < target:
                    row.progress = min(target, int(row.progress or 0) + increment)
        elif not row.is_claimed and int(row.progress or 0) < target:
            row.progress = min(target, int(row.progress or 0) + increment)
        updated_ids.append(q_id)

    if commit:
        await session.commit()
    else:
        await session.flush()
    return updated_ids


async def safe_record_weekly_quest_event(
    session: AsyncSession,
    telegram_id: int,
    event_name: str,
    *,
    tz_name: str = "Asia/Tehran",
    increment: int = 1,
) -> list[str]:
    """Best-effort weekly quest progress hook safe to invoke inside financial commits."""
    try:
        return await record_weekly_quest_event(
            session,
            telegram_id,
            event_name,
            tz_name=tz_name,
            increment=increment,
            commit=False,
        )
    except Exception:
        return []


async def claim_weekly_quest_reward(
    session: AsyncSession,
    telegram_id: int,
    quest_id: str,
    *,
    tz_name: str = "Asia/Tehran",
    cache: FastCache | None = None,
    lang: str = "fa",
) -> dict[str, Any]:
    """Atomically claim a completed weekly quest rewarding spin_tickets ONLY (no free GB or balance)."""
    norm_lang = normalize_lang(lang)
    is_en = norm_lang == "en"
    q_def = _QUESTS_BY_ID.get(str(quest_id or "").strip())
    if not q_def:
        return {
            "ok": False,
            "status_code": 400,
            "message": "Quest not found." if is_en else "مأموریت مورد نظر یافت نشد.",
        }

    db_user = await UserRepository(session).get_by_telegram_id(telegram_id)
    if not db_user:
        return {
            "ok": False,
            "status_code": 404,
            "message": "User not found." if is_en else "کاربر یافت نشد.",
        }
    if getattr(db_user, "is_banned", False):
        return {
            "ok": False,
            "status_code": 403,
            "message": "Account is banned." if is_en else "حساب کاربری مسدود شده است.",
        }

    week_key = current_iso_week_key(tz_name=tz_name)
    now_utc = datetime.now(timezone.utc)

    # Atomic single-claim lock: only succeeds once when progress >= target and is_claimed is False
    claim_stmt = (
        update(WeeklyQuestProgress)
        .where(
            WeeklyQuestProgress.telegram_id == telegram_id,
            WeeklyQuestProgress.week_key == week_key,
            WeeklyQuestProgress.quest_id == q_def["id"],
            WeeklyQuestProgress.progress >= WeeklyQuestProgress.target,
            WeeklyQuestProgress.is_claimed.is_(False),
        )
        .values(is_claimed=True, claimed_at=now_utc)
        .returning(WeeklyQuestProgress.id)
    )
    claimed_row = (await session.execute(claim_stmt)).scalar_one_or_none()
    if claimed_row is None:
        existing_row = (
            await session.execute(
                select(WeeklyQuestProgress).where(
                    WeeklyQuestProgress.telegram_id == telegram_id,
                    WeeklyQuestProgress.week_key == week_key,
                    WeeklyQuestProgress.quest_id == q_def["id"],
                )
            )
        ).scalar_one_or_none()
        if existing_row and existing_row.is_claimed:
            msg = "Quest reward already claimed this week." if is_en else "پاداش این مأموریت قبلاً در این هفته دریافت شده است."
        else:
            msg = "Complete the quest task first to claim your ticket." if is_en else "ابتدا مأموریت را تکمیل کنید تا بلیت گردونه آزاد شود."
        return {"ok": False, "status_code": 400, "message": msg}

    tickets_reward = int(q_def["reward_tickets"])
    ticket_res = await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(spin_tickets=func.coalesce(User.spin_tickets, 0) + tickets_reward)
        .returning(User.spin_tickets)
    )
    new_tickets = int(ticket_res.scalar_one())
    await session.commit()
    await invalidate_user_cache(cache, telegram_id)

    quests_state = await get_weekly_quests_state(session, telegram_id, tz_name=tz_name, lang=norm_lang)
    return {
        "ok": True,
        "reward_type": "spin_ticket",
        "reward_tickets": tickets_reward,
        "spin_tickets": new_tickets,
        "quests": quests_state,
        "message": (
            f"Claimed +{tickets_reward} Lucky Wheel ticket!"
            if is_en
            else f"+{tickets_reward} تیکت گردونه شانس به اکانت شما اضافه شد!"
        ),
    }


def _compute_red_packet_share(remaining_amount: int, remaining_slots: int, split_mode: str) -> int:
    """Compute a fair Red Packet share preserving >= MIN_RED_PACKET_SHARE for every remaining slot."""
    if remaining_slots <= 1:
        return remaining_amount
    if str(split_mode).upper() == "EQUAL":
        return remaining_amount // remaining_slots

    max_safe = remaining_amount - (remaining_slots - 1) * MIN_RED_PACKET_SHARE
    if max_safe <= MIN_RED_PACKET_SHARE:
        return MIN_RED_PACKET_SHARE

    avg = remaining_amount / remaining_slots
    upper = min(max_safe, max(MIN_RED_PACKET_SHARE, int(avg * 2)))
    if upper <= MIN_RED_PACKET_SHARE:
        return MIN_RED_PACKET_SHARE

    span = upper - MIN_RED_PACKET_SHARE
    step = 500 if span >= 1_000 else 1
    steps_count = span // step
    if steps_count <= 0:
        return MIN_RED_PACKET_SHARE
    share = MIN_RED_PACKET_SHARE + secrets.randbelow(steps_count + 1) * step
    return max(MIN_RED_PACKET_SHARE, min(max_safe, share))


def generate_red_packet_code() -> str:
    """Generate an unambiguous 8-hex group drop voucher code."""
    return f"DROP-{secrets.token_hex(4).upper()}"


async def create_red_packet(
    session: AsyncSession,
    *,
    sender_telegram_id: int,
    sender_name: str | None,
    total_amount: Any,
    max_claims: Any,
    split_mode: str = "RANDOM",
    message: str | None = None,
    bot_username: str = "",
    cache: FastCache | None = None,
    lang: str = "fa",
) -> dict[str, Any]:
    """Create a group Red Packet atomically deducting total_amount from sender's wallet."""
    norm_lang = normalize_lang(lang)
    is_en = norm_lang == "en"

    clean_total = _strict_positive_int(total_amount)
    clean_slots = _strict_positive_int(max_claims)
    clean_mode = str(split_mode or "RANDOM").strip().upper()
    if clean_mode not in ("EQUAL", "RANDOM"):
        clean_mode = "RANDOM"

    if clean_slots is None or clean_slots < MIN_RED_PACKET_SLOTS or clean_slots > MAX_RED_PACKET_SLOTS:
        return {
            "ok": False,
            "status_code": 400,
            "message": (
                f"Participant count must be between {MIN_RED_PACKET_SLOTS} and {MAX_RED_PACKET_SLOTS}."
                if is_en
                else f"تعداد نفرات پاکت باید بین {MIN_RED_PACKET_SLOTS} تا {MAX_RED_PACKET_SLOTS} نفر باشد."
            ),
        }

    min_allowed_total = clean_slots * MIN_RED_PACKET_SHARE
    if clean_total is None or clean_total < min_allowed_total or clean_total > MAX_RED_PACKET_TOTAL:
        return {
            "ok": False,
            "status_code": 400,
            "message": (
                f"Total amount must be between {min_allowed_total:,} and {MAX_RED_PACKET_TOTAL:,} Toman."
                if is_en
                else f"مبلغ کل پاکت باید بین {min_allowed_total:,} تا {MAX_RED_PACKET_TOTAL:,} تومان (حداقل 5,000 به ازای هر نفر) باشد."
            ),
        }

    sender = await UserRepository(session).get_by_telegram_id(sender_telegram_id)
    if not sender or getattr(sender, "is_banned", False):
        return {
            "ok": False,
            "status_code": 403,
            "message": "Sender account unavailable." if is_en else "حساب فرستنده فعال نیست.",
        }

    row = await session.execute(
        text(
            "UPDATE wallets SET balance = balance - :cost "
            "WHERE telegram_id = :tid AND balance >= :cost "
            "RETURNING balance"
        ),
        {"cost": clean_total, "tid": sender_telegram_id},
    )
    new_bal = row.scalar_one_or_none()
    if new_bal is None:
        w = (await session.execute(select(Wallet).where(Wallet.telegram_id == sender_telegram_id))).scalar_one_or_none()
        return {
            "ok": False,
            "status_code": 400,
            "error": "insufficient_balance",
            "needed": clean_total,
            "current": w.balance if w else 0,
            "message": "Insufficient wallet balance." if is_en else "موجودی کیف پول شما برای ایجاد پاکت گروهی کافی نیست.",
        }

    code = generate_red_packet_code()
    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc + timedelta(hours=RED_PACKET_TTL_HOURS)
    packet = RedPacket(
        code=code,
        sender_telegram_id=sender_telegram_id,
        sender_name=(sender_name or getattr(sender, "full_name", None) or "دوست شما")[:128],
        split_mode=clean_mode,
        total_amount=clean_total,
        remaining_amount=clean_total,
        max_claims=clean_slots,
        claimed_count=0,
        message=(message or "").strip()[:250] or None,
        is_refunded=False,
        expires_at=expires_at,
    )
    session.add(packet)
    await session.commit()
    await invalidate_user_cache(cache, sender_telegram_id)

    share_url = f"https://t.me/{bot_username}?start=drop_{code}" if bot_username else code
    return {
        "ok": True,
        "code": code,
        "share_url": share_url,
        "total_amount": clean_total,
        "max_claims": clean_slots,
        "split_mode": clean_mode,
        "expires_at": expires_at.isoformat(),
        "new_balance": int(new_bal),
        "message": (
            "Group Red Packet created!"
            if is_en
            else f"پاکت شانس گروهی با ظرفیت {clean_slots} نفر ایجاد شد!"
        ),
    }


async def claim_red_packet(
    session: AsyncSession,
    *,
    code: str,
    claimer_telegram_id: int,
    claimer_name: str | None = None,
    bot: Any = None,
    cache: FastCache | None = None,
    lang: str = "fa",
) -> dict[str, Any]:
    """Atomically claim one share of an active Red Packet (prevents double-claim, self-claim & race condition)."""
    norm_lang = normalize_lang(lang)
    is_en = norm_lang == "en"
    clean_code = str(code or "").strip().upper()
    if clean_code.startswith("DROP_"):
        clean_code = clean_code.removeprefix("DROP_")
    if not clean_code:
        return {
            "ok": False,
            "status_code": 400,
            "message": "Invalid code." if is_en else "کد پاکت نامعتبر است.",
        }

    async with user_action_lock(cache, claimer_telegram_id, f"rp:{clean_code}", ttl_seconds=10) as locked:
        if not locked:
            return {
                "ok": False,
                "status_code": 429,
                "message": "Please wait a moment and try again." if is_en else "لطفاً یک لحظه صبر کنید و مجدداً تلاش کنید.",
            }

        async with _get_packet_lock(clean_code):
            packet = None
            share = 0
            upd_vals = None
            for _attempt in range(5):
                res = await session.execute(
                    select(RedPacket).where(RedPacket.code == clean_code).with_for_update()
                )
                packet = res.scalar_one_or_none()
                if not packet:
                    return {
                        "ok": False,
                        "status_code": 404,
                        "message": "Red Packet not found." if is_en else "پاکت شانس مورد نظر یافت نشد.",
                    }

                if packet.sender_telegram_id == claimer_telegram_id:
                    return {
                        "ok": False,
                        "status_code": 400,
                        "message": "You cannot claim your own Red Packet." if is_en else "شما سازنده این پاکت هستید و نمی‌توانید از آن برداشت کنید.",
                    }

                if packet.is_refunded:
                    return {
                        "ok": False,
                        "status_code": 400,
                        "message": "This Red Packet has been refunded." if is_en else "این پاکت منقضی شده و مابقی آن به فرستنده بازگشت داده شده است.",
                    }

                now_utc = datetime.now(timezone.utc)
                exp_utc = packet.expires_at if packet.expires_at.tzinfo else packet.expires_at.replace(tzinfo=timezone.utc)
                if exp_utc <= now_utc:
                    return {
                        "ok": False,
                        "status_code": 400,
                        "message": "This Red Packet has expired." if is_en else "مهلت زمانی این پاکت به پایان رسیده است.",
                    }

                exp_claimed = int(packet.claimed_count or 0)
                exp_remaining = int(packet.remaining_amount or 0)
                if exp_claimed >= int(packet.max_claims or 0) or exp_remaining <= 0:
                    return {
                        "ok": False,
                        "status_code": 400,
                        "message": "All shares have already been claimed." if is_en else "تمامی سهم‌های این پاکت شانس قبلاً دریافت شده‌اند!",
                    }

                claimer_user = await UserRepository(session).get_by_telegram_id(claimer_telegram_id)
                if claimer_user and getattr(claimer_user, "is_banned", False):
                    return {
                        "ok": False,
                        "status_code": 403,
                        "message": "Account is banned." if is_en else "حساب کاربری شما مسدود است.",
                    }

                existing_claim = (
                    await session.execute(
                        select(RedPacketClaim.id).where(
                            RedPacketClaim.packet_id == packet.id,
                            RedPacketClaim.telegram_id == claimer_telegram_id,
                        )
                    )
                ).scalar_one_or_none()
                if existing_claim is not None:
                    return {
                        "ok": False,
                        "status_code": 400,
                        "message": "You have already claimed from this Red Packet." if is_en else "شما قبلاً سهم خود را از این پاکت شانس دریافت کرده‌اید.",
                    }

                rem_slots = int(packet.max_claims) - exp_claimed
                share = _compute_red_packet_share(exp_remaining, rem_slots, packet.split_mode)
                if share <= 0 or share > exp_remaining:
                    return {
                        "ok": False,
                        "status_code": 400,
                        "message": "All shares have already been claimed." if is_en else "تمامی سهم‌های این پاکت دریافت شده است.",
                    }

                upd_res = await session.execute(
                    update(RedPacket)
                    .where(
                        RedPacket.id == packet.id,
                        RedPacket.is_refunded.is_(False),
                        RedPacket.claimed_count == exp_claimed,
                        RedPacket.claimed_count < RedPacket.max_claims,
                        RedPacket.remaining_amount == exp_remaining,
                        RedPacket.remaining_amount >= share,
                    )
                    .values(
                        claimed_count=RedPacket.claimed_count + 1,
                        remaining_amount=RedPacket.remaining_amount - share,
                    )
                    .returning(RedPacket.claimed_count, RedPacket.remaining_amount)
                )
                upd_vals = upd_res.first()
                if upd_vals is not None:
                    break
                await session.rollback()
                session.expire_all()
                await asyncio.sleep(0)

            if upd_vals is None or packet is None:
                return {
                    "ok": False,
                    "status_code": 409,
                    "message": "All shares were just claimed." if is_en else "متأسفانه تمامی سهم‌های این پاکت تکمیل شد.",
                }

            await UserRepository(session).ensure_exists(claimer_telegram_id)
            claim_row = RedPacketClaim(
                packet_id=packet.id,
                telegram_id=claimer_telegram_id,
                claimer_name=(claimer_name or "دوست")[:128],
                amount=share,
            )
            session.add(claim_row)
            try:
                async with session.begin_nested():
                    await session.flush()
            except IntegrityError:
                await session.rollback()
                return {
                    "ok": False,
                    "status_code": 400,
                    "message": "You have already claimed from this Red Packet." if is_en else "شما قبلاً سهم خود را از این پاکت دریافت کرده‌اید.",
                }

            new_balance = await WalletRepository(session).add_balance_atomic(claimer_telegram_id, share)
            await session.commit()

        await invalidate_user_cache(cache, claimer_telegram_id)
        await invalidate_user_cache(cache, packet.sender_telegram_id)

        new_claimed_count, _new_rem_amount = int(upd_vals[0]), int(upd_vals[1])
        if bot and new_claimed_count == int(packet.max_claims):
            try:
                await bot.send_message(
                    chat_id=packet.sender_telegram_id,
                    text=(
                        f"🧧 <b>پاکت شانس گروهی شما تکمیل شد!</b>\n\n"
                        f"🔖 کد پاکت: <code>{escape(packet.code)}</code>\n"
                        f"👥 تمام {packet.max_claims} سهم بین دوستان تقسیم شد."
                    ),
                    parse_mode="HTML",
                )
            except Exception as notify_err:
                logger.debug("RedPacket full notification error: %s", notify_err)

        return {
            "ok": True,
            "gift_type": "RED_PACKET",
            "amount": share,
            "new_balance": new_balance,
            "sender_name": packet.sender_name,
            "claimed_count": new_claimed_count,
            "max_claims": int(packet.max_claims),
            "message": (
                f"You claimed {share:,} Toman from {packet.sender_name or 'a friend'}'s Red Packet!"
                if is_en
                else f"تبریک! {share:,} تومان شانس گروهی به کیف پول شما واریز شد!"
            ),
        }


async def refund_red_packet(
    session: AsyncSession,
    *,
    packet_id: int,
    sender_telegram_id: int,
    cache: FastCache | None = None,
    lang: str = "fa",
) -> dict[str, Any]:
    """Refund leftover balance from an expired Red Packet back to sender."""
    norm_lang = normalize_lang(lang)
    is_en = norm_lang == "en"

    packet = (
        await session.execute(
            select(RedPacket)
            .where(RedPacket.id == packet_id, RedPacket.sender_telegram_id == sender_telegram_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not packet:
        return {"ok": False, "status_code": 404, "message": "Packet not found." if is_en else "پاکت یافت نشد."}

    now_utc = datetime.now(timezone.utc)
    exp_utc = packet.expires_at if packet.expires_at.tzinfo else packet.expires_at.replace(tzinfo=timezone.utc)
    if exp_utc > now_utc:
        return {
            "ok": False,
            "status_code": 400,
            "message": "Cannot refund before packet expires." if is_en else "امکان استرداد مابقی پاکت پیش از پایان مهلت 48 ساعته وجود ندارد.",
        }

    refund_amt = int(packet.remaining_amount or 0)
    if packet.is_refunded or refund_amt <= 0:
        return {
            "ok": False,
            "status_code": 400,
            "message": "No remaining balance to refund." if is_en else "مبلغی برای استرداد باقی نمانده است.",
        }

    packet.is_refunded = True
    packet.remaining_amount = 0
    new_bal = await WalletRepository(session).add_balance_atomic(sender_telegram_id, refund_amt)
    await session.commit()
    await invalidate_user_cache(cache, sender_telegram_id)
    return {
        "ok": True,
        "refunded_amount": refund_amt,
        "new_balance": new_bal,
        "message": (
            f"Refunded {refund_amt:,} Toman to your wallet."
            if is_en
            else f"مبلغ {refund_amt:,} تومان باقی‌مانده به کیف پول شما بازگشت داده شد."
        ),
    }


async def get_user_red_packets(
    session: AsyncSession,
    telegram_id: int,
    *,
    bot_username: str = "",
) -> dict[str, list[dict[str, Any]]]:
    """Return created and claimed Red Packets for user history."""
    now_utc = datetime.now(timezone.utc)
    sent_rows = (
        await session.execute(
            select(RedPacket)
            .where(RedPacket.sender_telegram_id == telegram_id)
            .order_by(RedPacket.id.desc())
            .limit(20)
        )
    ).scalars().all()

    sent_out: list[dict[str, Any]] = []
    for rp in sent_rows:
        exp_utc = rp.expires_at if rp.expires_at.tzinfo else rp.expires_at.replace(tzinfo=timezone.utc)
        is_expired = exp_utc <= now_utc
        sent_out.append({
            "id": rp.id,
            "code": rp.code,
            "split_mode": rp.split_mode,
            "total_amount": int(rp.total_amount),
            "remaining_amount": int(rp.remaining_amount),
            "max_claims": int(rp.max_claims),
            "claimed_count": int(rp.claimed_count),
            "is_refunded": bool(rp.is_refunded),
            "is_expired": is_expired,
            "can_refund": bool(is_expired and not rp.is_refunded and int(rp.remaining_amount or 0) > 0),
            "share_url": f"https://t.me/{bot_username}?start=drop_{rp.code}" if bot_username else rp.code,
            "created_at": rp.created_at.isoformat() if rp.created_at else None,
        })

    claims_rows = (
        await session.execute(
            select(RedPacketClaim, RedPacket)
            .join(RedPacket, RedPacketClaim.packet_id == RedPacket.id)
            .where(RedPacketClaim.telegram_id == telegram_id)
            .order_by(RedPacketClaim.id.desc())
            .limit(20)
        )
    ).all()

    claimed_out: list[dict[str, Any]] = []
    for cl, rp in claims_rows:
        claimed_out.append({
            "code": rp.code,
            "sender_name": rp.sender_name,
            "amount": int(cl.amount),
            "claimed_at": cl.claimed_at.isoformat() if cl.claimed_at else None,
        })

    return {"sent": sent_out, "claimed": claimed_out}


async def transfer_wallet_balance(
    session: AsyncSession,
    *,
    sender_telegram_id: int,
    recipient_target: str,
    amount: Any,
    note: str | None = None,
    bot: Any = None,
    cache: FastCache | None = None,
    lang: str = "fa",
) -> dict[str, Any]:
    """Atomically transfer Toman balance between two registered Telegram users."""
    norm_lang = normalize_lang(lang)
    is_en = norm_lang == "en"

    clean_amt = _strict_positive_int(amount)
    if clean_amt is None or clean_amt < MIN_P2P_AMOUNT or clean_amt > MAX_P2P_AMOUNT:
        return {
            "ok": False,
            "status_code": 400,
            "message": (
                f"Transfer amount must be between {MIN_P2P_AMOUNT:,} and {MAX_P2P_AMOUNT:,} Toman."
                if is_en
                else f"مبلغ انتقال باید بین {MIN_P2P_AMOUNT:,} تا {MAX_P2P_AMOUNT:,} تومان باشد."
            ),
        }

    clean_target = str(recipient_target or "").strip().lstrip("@")
    if not clean_target:
        return {
            "ok": False,
            "status_code": 400,
            "message": "Recipient @username or Telegram ID is required." if is_en else "آیدی یا شناسه عددی گیرنده الزامی است.",
        }

    user_repo = UserRepository(session)
    sender = await user_repo.get_by_telegram_id(sender_telegram_id)
    if not sender or getattr(sender, "is_banned", False):
        return {
            "ok": False,
            "status_code": 403,
            "message": "Sender account unavailable." if is_en else "حساب شما مجاز به انجام انتقال نیست.",
        }

    if clean_target.isdigit():
        receiver = await user_repo.get_by_telegram_id(int(clean_target))
    else:
        receiver = (
            await session.execute(select(User).where(func.lower(User.username) == clean_target.lower()))
        ).scalar_one_or_none()

    if not receiver:
        return {
            "ok": False,
            "status_code": 404,
            "message": "Recipient user is not registered in this bot." if is_en else "کاربر مقصد در ربات عضو نیست یا هنوز استارت نکرده است.",
        }
    if getattr(receiver, "is_banned", False):
        return {
            "ok": False,
            "status_code": 400,
            "message": "Cannot transfer to a suspended account." if is_en else "امکان انتقال به حساب کاربری مسدودشده وجود ندارد.",
        }
    if int(receiver.telegram_id) == int(sender_telegram_id):
        return {
            "ok": False,
            "status_code": 400,
            "message": "Cannot transfer to your own wallet." if is_en else "انتقال موجودی به حساب خودتان مجاز نیست.",
        }

    # Atomic SQL sender deduction preventing double-spend races
    row = await session.execute(
        text(
            "UPDATE wallets SET balance = balance - :amt "
            "WHERE telegram_id = :tid AND balance >= :amt "
            "RETURNING balance"
        ),
        {"amt": clean_amt, "tid": sender_telegram_id},
    )
    sender_new_bal = row.scalar_one_or_none()
    if sender_new_bal is None:
        w = (await session.execute(select(Wallet).where(Wallet.telegram_id == sender_telegram_id))).scalar_one_or_none()
        return {
            "ok": False,
            "status_code": 400,
            "error": "insufficient_balance",
            "needed": clean_amt,
            "current": w.balance if w else 0,
            "message": "Insufficient wallet balance." if is_en else "موجودی کیف پول شما برای این انتقال کافی نیست.",
        }

    receiver_new_bal = await WalletRepository(session).add_balance_atomic(receiver.telegram_id, clean_amt)
    clean_note = (note or "").strip()[:160] or None
    transfer_rec = WalletTransfer(
        sender_telegram_id=sender_telegram_id,
        receiver_telegram_id=receiver.telegram_id,
        amount=clean_amt,
        note=clean_note,
    )
    session.add(transfer_rec)
    await safe_record_weekly_quest_event(session, sender_telegram_id, "wallet_boost")
    await session.commit()

    await invalidate_user_cache(cache, sender_telegram_id)
    await invalidate_user_cache(cache, receiver.telegram_id)

    sender_label = (
        f"@{sender.username}" if getattr(sender, "username", None) else f"ID {sender_telegram_id}"
    )
    receiver_label = (
        f"@{receiver.username}" if getattr(receiver, "username", None) else (receiver.full_name or str(receiver.telegram_id))
    )

    if bot:
        try:
            note_line = f"\n💬 یادداشت: <i>{escape(clean_note)}</i>" if clean_note else ""
            await bot.send_message(
                chat_id=receiver.telegram_id,
                text=(
                    f"💸 <b>انتقال کیف پول دریافت شد!</b>\n\n"
                    f"👤 فرستنده: <b>{escape(sender_label)}</b>\n"
                    f"💰 مبلغ: <b>{clean_amt:,} تومان</b>\n"
                    f"👛 موجودی فعلی: <b>{receiver_new_bal:,} تومان</b>"
                    f"{note_line}"
                ),
                parse_mode="HTML",
            )
        except Exception as notify_err:
            logger.debug("P2P receiver notify error: %s", notify_err)

    return {
        "ok": True,
        "transfer_id": transfer_rec.id,
        "amount": clean_amt,
        "new_balance": int(sender_new_bal),
        "receiver_telegram_id": int(receiver.telegram_id),
        "receiver_label": receiver_label,
        "message": (
            f"Transferred {clean_amt:,} Toman to {receiver_label}."
            if is_en
            else f"مبلغ {clean_amt:,} تومان با موفقیت به حساب «{receiver_label}» منتقل شد."
        ),
    }
