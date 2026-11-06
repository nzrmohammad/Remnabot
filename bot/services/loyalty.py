"""Loyalty Tiers Service: DRY and Single Source of Truth for VIP tiers and discounts."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Order, OrderStatus

logger = logging.getLogger(__name__)

# VIP Loyalty Tiers definition (Single Source of Truth - 7 Tiers)
DEFAULT_LOYALTY_TIERS = [
    {
        "id": "bronze",
        "name": "برنزی",
        "icon": "🥉",
        "min_spent": 0,
        "discount_percent": 0,
        "color": "amber-700",
        "badge_class": "bg-amber-700/15 text-amber-600 dark:text-amber-500 border-amber-700/30",
        "description": "سطح آغازین باشگاه مشتریان (بدون تخفیف)",
    },
    {
        "id": "silver",
        "name": "نقره‌ای",
        "icon": "🥈",
        "min_spent": 1_000_000,
        "discount_percent": 3,
        "color": "slate-300",
        "badge_class": "bg-slate-400/15 text-slate-300 border-slate-400/30",
        "description": "3% تخفیف",
    },
    {
        "id": "gold",
        "name": "طلایی",
        "icon": "🥇",
        "min_spent": 2_500_000,
        "discount_percent": 5,
        "color": "amber-400",
        "badge_class": "bg-amber-500/15 text-amber-500 dark:text-amber-400 border-amber-500/30",
        "description": "5% تخفیف",
    },
    {
        "id": "platinum",
        "name": "پلاتین",
        "icon": "💎",
        "min_spent": 5_000_000,
        "discount_percent": 8,
        "color": "cyan-400",
        "badge_class": "bg-cyan-500/15 text-cyan-500 dark:text-cyan-400 border-cyan-500/30",
        "description": "8% تخفیف",
    },
    {
        "id": "ruby",
        "name": "یاقوت",
        "icon": "🔮",
        "min_spent": 8_000_000,
        "discount_percent": 10,
        "color": "purple-400",
        "badge_class": "bg-purple-500/15 text-purple-400 border-purple-500/30",
        "description": "10% تخفیف",
    },
    {
        "id": "emerald",
        "name": "زمرد",
        "icon": "❇️",
        "min_spent": 12_000_000,
        "discount_percent": 12,
        "color": "emerald-400",
        "badge_class": "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
        "description": "12% تخفیف",
    },
    {
        "id": "diamond",
        "name": "الماس",
        "icon": "👑",
        "min_spent": 20_000_000,
        "discount_percent": 15,
        "color": "amber-300",
        "badge_class": "bg-amber-300/15 text-amber-300 border-amber-300/30",
        "description": "15% تخفیف + پشتیبانی اختصاصی",
    },
]

LOYALTY_TIERS = DEFAULT_LOYALTY_TIERS


async def get_configured_loyalty_tiers(session: AsyncSession | None = None) -> list[dict[str, Any]]:
    """Return active loyalty tiers, merged with admin-configured thresholds & discounts if present."""
    if session is None:
        return DEFAULT_LOYALTY_TIERS

    try:
        import json

        from bot.db.repositories.app_setting_repo import AppSettingRepository
        repo = AppSettingRepository(session)
        raw_json = await repo.get("loyalty_tiers_json")
        if not raw_json:
            return DEFAULT_LOYALTY_TIERS
        custom_cfg = json.loads(raw_json)
        if not isinstance(custom_cfg, dict):
            return DEFAULT_LOYALTY_TIERS
        # Automatically upgrade legacy uncustomized defaults (300k, 700k) to current DEFAULT_LOYALTY_TIERS
        if custom_cfg.get("silver", {}).get("min_spent") == 300_000 and custom_cfg.get("gold", {}).get("min_spent") == 700_000:
            return DEFAULT_LOYALTY_TIERS

        merged_tiers: list[dict[str, Any]] = []
        for default_tier in DEFAULT_LOYALTY_TIERS:
            tid = default_tier["id"]
            tier_copy = dict(default_tier)
            if tid in custom_cfg and isinstance(custom_cfg[tid], dict):
                c = custom_cfg[tid]
                if "min_spent" in c and isinstance(c["min_spent"], (int, float)):
                    tier_copy["min_spent"] = max(0, int(c["min_spent"]))
                if "discount_percent" in c and isinstance(c["discount_percent"], (int, float)):
                    tier_copy["discount_percent"] = max(0, min(100, int(c["discount_percent"])))
                if tier_copy["discount_percent"] > 0:
                    tier_copy["description"] = f"{tier_copy['discount_percent']}% تخفیف"
                else:
                    tier_copy["description"] = "سطح آغازین باشگاه مشتریان (بدون تخفیف)"
            merged_tiers.append(tier_copy)
        # Keep sorted by min_spent
        merged_tiers.sort(key=lambda x: x["min_spent"])
        return merged_tiers
    except Exception as exc:
        logger.debug("Failed parsing custom loyalty tiers, fallback to defaults: %s", exc)
        return DEFAULT_LOYALTY_TIERS


async def get_user_loyalty(
    session: AsyncSession,
    telegram_id: int,
    cache: Any = None,
) -> dict[str, Any]:
    """Calculate and return user loyalty tier, total spending, progress, and perks."""
    from bot.services.app_settings import get_store_settings

    store_settings = await get_store_settings(session)
    if not store_settings.loyalty_enabled:
        return {
            "enabled": False,
            "tier": "NONE",
            "tier_id": "bronze",
            "name": "غیرفعال",
            "icon": "⚪️",
            "discount_percent": 0,
            "color": "#94a3b8",
            "badge_class": "bg-slate-400/15 text-slate-300 border border-slate-400/30",
            "description": "باشگاه مشتریان در حال حاضر غیرفعال است.",
            "total_spent": 0,
            "amount_to_next": 0,
            "progress_percent": 0,
            "next_tier": None,
            "next_tier_name": None,
            "next_tier_icon": None,
            "next_tier_discount": None,
            "next_tier_threshold": None,
            "is_max_tier": True,
            "all_tiers": [],
        }

    cache_key = f"loyalty:user:v2:{telegram_id}"
    if cache and hasattr(cache, "get"):
        try:
            cached = await cache.get(cache_key)
            if cached and isinstance(cached, dict) and "tier_id" in cached:
                return cached
        except Exception as exc:
            logger.debug("Failed reading loyalty cache for %s: %s", telegram_id, exc)

    active_tiers = await get_configured_loyalty_tiers(session)

    # Calculate total spent on successful orders
    spent_query = select(func.coalesce(func.sum(Order.amount), 0)).where(
        Order.telegram_id == telegram_id,
        Order.status == OrderStatus.PAID.value,
    )
    res = await session.execute(spent_query)
    total_spent = int(res.scalar() or 0)

    current_tier = active_tiers[0]
    next_tier = None

    for i, tier in enumerate(active_tiers):
        if total_spent >= tier["min_spent"]:
            current_tier = tier
            next_tier = active_tiers[i + 1] if i + 1 < len(active_tiers) else None
        else:
            break

    amount_to_next = 0
    progress_percent = 100
    if next_tier:
        needed = next_tier["min_spent"] - current_tier["min_spent"]
        current_in_tier = total_spent - current_tier["min_spent"]
        amount_to_next = max(0, next_tier["min_spent"] - total_spent)
        progress_percent = int(min(100, max(0, (current_in_tier / needed) * 100))) if needed > 0 else 100

    next_tier_obj = None
    if next_tier:
        next_tier_obj = {
            "id": next_tier["id"],
            "name": next_tier["name"],
            "icon": next_tier["icon"],
            "discount_percent": next_tier["discount_percent"],
            "min_spent": next_tier["min_spent"],
            "remaining_amount": amount_to_next,
        }

    data = {
        "enabled": True,
        "tier": current_tier["id"].upper(),
        "tier_id": current_tier["id"],
        "name": current_tier["name"],
        "icon": current_tier["icon"],
        "discount_percent": current_tier["discount_percent"],
        "color": current_tier["color"],
        "badge_class": current_tier["badge_class"],
        "description": current_tier["description"],
        "total_spent": total_spent,
        "amount_to_next": amount_to_next,
        "progress_percent": progress_percent,
        "next_tier": next_tier_obj,
        "next_tier_name": next_tier["name"] if next_tier else None,
        "next_tier_icon": next_tier["icon"] if next_tier else None,
        "next_tier_discount": next_tier["discount_percent"] if next_tier else None,
        "next_tier_threshold": next_tier["min_spent"] if next_tier else None,
        "is_max_tier": next_tier is None,
        "all_tiers": [
            {
                "id": t["id"],
                "name": t["name"],
                "icon": t["icon"],
                "min_spent": t["min_spent"],
                "discount_percent": t["discount_percent"],
                "description": t["description"],
            }
            for t in active_tiers
        ],
    }

    if cache and hasattr(cache, "set"):
        try:
            await cache.set(cache_key, data, ttl_seconds=60)
        except Exception as exc:
            logger.debug("Failed setting loyalty cache for %s: %s", telegram_id, exc)

    return data


def apply_loyalty_discount(base_price: int, discount_percent: int) -> tuple[int, int]:
    """Calculate discounted price and discount amount. Returns (discount_amount, final_price)."""
    if discount_percent <= 0 or base_price <= 0:
        return 0, base_price
    pct = max(0, min(100, discount_percent))
    discount_amount = int((base_price * pct) / 100)
    final_price = max(0, base_price - discount_amount)
    return discount_amount, final_price
